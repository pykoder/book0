"""ReadLibraryGateway contre le schéma PostgreSQL de calibre_pg_sync.

Tout le SQL PG de book0 vit dans ce module. Les tables miroirs sont scopées
par library_uuid ; les ids publics (Book.id, Author.id, ...) sont les
colonnes local_id exposées en str - la même identité stable que les ids
SQLite - tandis que les BIGSERIAL (book_pk, authors.id, ...) restent
internes au module.
"""

import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import psycopg

from book0_core.errors import LibraryNotFoundError
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    BookQuery,
    BookSort,
    FieldValue,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    PagedSeriesResult,
    Publisher,
    Series,
    SeriesItem,
    SortOrder,
)

# Calibre stocke "pas de date de publication" comme une date sentinelle
# (année 101, calibre.utils.date.UNDEFINED_DATE) plutôt que NULL.
_UNDEFINED_PUBDATE_YEAR = 101

# Réduit la date à 'YYYY-MM-DD' directement en SQL, en neutralisant la
# sentinelle - insensible à la timezone de session du serveur.
_PUBDATE_SQL = (
    "CASE WHEN EXTRACT(YEAR FROM books.pubdate) = "
    f"{_UNDEFINED_PUBDATE_YEAR} THEN NULL"
    " ELSE to_char(books.pubdate, 'YYYY-MM-DD') END"
)

_LIST_BOOKS_QUERY_JOINS = f"""
    SELECT
        books.local_id,
        books.title,
        string_agg(DISTINCT authors.name, ', ' ORDER BY authors.name) AS authors,
        {_PUBDATE_SQL} AS pubdate,
        publishers.local_id AS publisher_id,
        publishers.name AS publisher_name,
        series.local_id AS series_id,
        series.name AS series_name,
        books.series_index,
        ratings.rating AS rating_raw,
        books.has_cover
    FROM books
    LEFT JOIN books_authors_link ON books_authors_link.book_pk = books.book_pk
    LEFT JOIN authors ON authors.id = books_authors_link.author_id
    LEFT JOIN books_publishers_link ON books_publishers_link.book_pk = books.book_pk
    LEFT JOIN publishers ON publishers.id = books_publishers_link.publisher_id
    LEFT JOIN books_series_link ON books_series_link.book_pk = books.book_pk
    LEFT JOIN series ON series.id = books_series_link.series_id
    LEFT JOIN books_ratings_link ON books_ratings_link.book_pk = books.book_pk
    LEFT JOIN ratings ON ratings.id = books_ratings_link.rating_id
"""

_LIST_BOOKS_QUERY_BODY = (
    _LIST_BOOKS_QUERY_JOINS + "\n    WHERE books.library_uuid = %s\n"
)

# PG exige que toute colonne non agrégée soit groupée ou fonctionnellement
# dépendante de la clé groupée : books.* dépend de books.book_pk (PK), mais
# les colonnes des tables jointes (publisher/series/rating, au plus un par
# livre comme côté SQLite) doivent figurer dans le GROUP BY.
_LIST_BOOKS_GROUP_BY = (
    "    GROUP BY books.book_pk, publishers.local_id, publishers.name,"
    " series.local_id, series.name, ratings.rating\n"
)

_LIST_BOOKS_QUERY = (
    _LIST_BOOKS_QUERY_BODY + _LIST_BOOKS_GROUP_BY + "    ORDER BY books.title\n"
)

_LIST_AUTHORS_QUERY = (
    "SELECT local_id, name FROM authors WHERE library_uuid = %s ORDER BY name"
)

_LIST_PUBLISHERS_QUERY = (
    "SELECT local_id, name FROM publishers WHERE library_uuid = %s ORDER BY name"
)

_LIST_SERIES_QUERY = (
    "SELECT local_id, name FROM series WHERE library_uuid = %s ORDER BY name"
)

# Auteurs et tags sont agrégés par sous-requêtes corrélées (même raison que
# côté SQLite : deux tables de lien N-N dans la même requête éventailiseraient
# les lignes). Publisher et series restent des LEFT JOIN simples.
_GET_BOOK_DETAILS_QUERY_TEMPLATE = f"""
    SELECT
        books.local_id,
        books.title,
        {_PUBDATE_SQL} AS pubdate,
        books.series_index,
        (
            SELECT string_agg(authors.name, ', ' ORDER BY authors.name)
            FROM books_authors_link
            JOIN authors ON authors.id = books_authors_link.author_id
            WHERE books_authors_link.book_pk = books.book_pk
        ) AS authors,
        (
            SELECT string_agg(tags.name, ', ' ORDER BY tags.local_id)
            FROM books_tags_link
            JOIN tags ON tags.id = books_tags_link.tag_id
            WHERE books_tags_link.book_pk = books.book_pk
        ) AS tags,
        publishers.local_id,
        publishers.name,
        series.local_id,
        series.name,
        books.path,
        books.has_cover
    FROM books
    LEFT JOIN books_publishers_link ON books_publishers_link.book_pk = books.book_pk
    LEFT JOIN publishers ON publishers.id = books_publishers_link.publisher_id
    LEFT JOIN books_series_link ON books_series_link.book_pk = books.book_pk
    LEFT JOIN series ON series.id = books_series_link.series_id
    WHERE books.library_uuid = %s AND books.local_id IN ({{placeholders}})
"""

_VALID_ID_PATTERN = re.compile(r"^[1-9]\d*$")

_SESSION_TIMEOUT_SECONDS = 60
_PAGE_COUNT_CAP = 100  # en pages ; le plafond de lignes est _PAGE_COUNT_CAP * page_size

# Clés de tri pour query_books_page, exprimées contre les colonnes/alias du
# _LIST_BOOKS_QUERY_BODY. Le schéma PG des books possède author_sort (contrairement
# à la fixture SQLite), la clé AUTHOR est donc réelle ici.
_SORT_EXPRESSIONS = {
    BookSort.TITLE: "books.title",
    BookSort.PUBDATE: "books.pubdate",
    BookSort.PUBLISHER: "publisher_name",
    BookSort.SERIES: "series_name",
    BookSort.SERIES_INDEX: "books.series_index",
    BookSort.RATING: "rating_raw",
    BookSort.AUTHOR: "books.author_sort",
}

# Table books_<entité>_link : table de lien et colonne pointant vers l'id
# interne (BIGSERIAL) de l'entité.
_ENTITY_LINK_TABLES = {
    "authors": ("books_authors_link", "author_id"),
    "publishers": ("books_publishers_link", "publisher_id"),
    "series": ("books_series_link", "series_id"),
}

# Requêtes de facettes pour list_field_values : une par champ autorisé, chacune
# retournant (valeur, count) trié par count DESC puis valeur. Noms de colonnes
# qualifiés - languages joint books_languages_link et ratings joint
# books_ratings_link, des noms non qualifiés seraient ambigus.
_FACET_QUERIES: dict[str, str] = {
    "tags": (
        "SELECT tags.name, count(*) FROM tags"
        " JOIN books_tags_link ON tag_id = tags.id"
        " WHERE tags.library_uuid = %s"
        " GROUP BY tags.name ORDER BY count(*) DESC, tags.name"
    ),
    "languages": (
        "SELECT languages.lang_code, count(*) FROM languages"
        " JOIN books_languages_link ON language_id = languages.id"
        " WHERE languages.library_uuid = %s"
        " GROUP BY languages.lang_code ORDER BY count(*) DESC, languages.lang_code"
    ),
    "formats": (
        "SELECT data.format, count(*) FROM data"
        " JOIN books ON books.book_pk = data.book_pk"
        " WHERE books.library_uuid = %s AND data.format IS NOT NULL"
        " GROUP BY data.format ORDER BY count(*) DESC, data.format"
    ),
    # Étoile = note brute // 2 (échelle 0-10 paire) ; le format ::text est
    # répété dans le GROUP BY pour que PG reconnaisse l'expression groupée.
    "ratings": (
        "SELECT (ratings.rating / 2)::text, count(*) FROM ratings"
        " JOIN books_ratings_link ON rating_id = ratings.id"
        " WHERE ratings.library_uuid = %s AND ratings.rating > 0"
        " GROUP BY (ratings.rating / 2)::text"
        " ORDER BY count(*) DESC, (ratings.rating / 2)::text"
    ),
}


def _query_books_where(
    query: BookQuery, params: list[object], library_uuid: uuid.UUID
) -> str:
    """Construit le WHERE filtrant les books à partir d'une BookQuery.

    Chaque clause est autoportante : elle porte son propre IN (SELECT ...),
    elle s'applique donc à un "FROM books" nu (les filtres d'ids locaux sont
    convertis en ids internes via la sous-requête library_uuid/local_id de la
    table de dimension). Les clés se combinent en AND, les valeurs d'une clé
    en OR. Les notes en étoiles (1-5) sont converties en échelle Calibre 0-10
    dans les placeholders.
    """
    clauses = []
    if query.author_ids:
        placeholders = ",".join(["%s"] * len(query.author_ids))
        clauses.append(
            "books.book_pk IN (SELECT book_pk FROM books_authors_link"
            " WHERE author_id IN (SELECT id FROM authors"
            f" WHERE library_uuid = %s AND local_id IN ({placeholders})))"
        )
        params.append(library_uuid)
        params.extend(int(author_id) for author_id in query.author_ids)
    if query.publisher_ids:
        placeholders = ",".join(["%s"] * len(query.publisher_ids))
        clauses.append(
            "books.book_pk IN (SELECT book_pk FROM books_publishers_link"
            " WHERE publisher_id IN (SELECT id FROM publishers"
            f" WHERE library_uuid = %s AND local_id IN ({placeholders})))"
        )
        params.append(library_uuid)
        params.extend(int(publisher_id) for publisher_id in query.publisher_ids)
    if query.series_ids:
        placeholders = ",".join(["%s"] * len(query.series_ids))
        clauses.append(
            "books.book_pk IN (SELECT book_pk FROM books_series_link"
            " WHERE series_id IN (SELECT id FROM series"
            f" WHERE library_uuid = %s AND local_id IN ({placeholders})))"
        )
        params.append(library_uuid)
        params.extend(int(series_id) for series_id in query.series_ids)
    if query.tags:
        placeholders = ",".join(["%s"] * len(query.tags))
        clauses.append(
            "books.book_pk IN (SELECT book_pk FROM books_tags_link"
            " JOIN tags ON tags.id = tag_id"
            f" WHERE tags.name IN ({placeholders}))"
        )
        params.extend(query.tags)
    if query.languages:
        placeholders = ",".join(["%s"] * len(query.languages))
        clauses.append(
            "books.book_pk IN (SELECT book_pk FROM books_languages_link"
            " JOIN languages ON languages.id = language_id"
            f" WHERE languages.lang_code IN ({placeholders}))"
        )
        params.extend(query.languages)
    if query.formats:
        placeholders = ",".join(["%s"] * len(query.formats))
        clauses.append(
            "books.book_pk IN (SELECT book_pk FROM data"
            f" WHERE format IN ({placeholders}))"
        )
        params.extend(format_.upper() for format_ in query.formats)
    if query.ratings:
        placeholders = ",".join(["%s"] * len(query.ratings))
        clauses.append(
            "books.book_pk IN (SELECT book_pk FROM books_ratings_link"
            " JOIN ratings ON ratings.id = rating_id"
            f" WHERE ratings.rating IN ({placeholders}))"
        )
        params.extend(rating * 2 for rating in query.ratings)  # 1..5 -> 0..10
    if query.pubdate_years:
        placeholders = ",".join(["%s"] * len(query.pubdate_years))
        clauses.append(f"(EXTRACT(YEAR FROM books.pubdate) IN ({placeholders}))")
        params.extend(query.pubdate_years)
    return (" WHERE " + " AND ".join(clauses)) if clauses else ""


@dataclass
class _PaginationSession:
    resource: str
    page_size: int
    next_page: int
    query_sql: str
    query_params: tuple[object, ...]
    last_access: float


class PgLibraryGateway:
    """Réalise ReadLibraryGateway contre le schéma calibre_pg_sync.

    Une connexion psycopg par gateway (fermée par close()), un curseur par
    opération. La pagination rejoue LIMIT/OFFSET : le handle désigne une
    session en mémoire stockant (sql, params, page_size), sans curseur serveur.
    """

    def __init__(self, pg_dsn: str, tag: str) -> None:
        # Lectures seules : l'autocommit évite de maintenir une transaction
        # (donc des verrous ACCESS SHARE) ouverte entre deux opérations.
        self._connection = psycopg.connect(pg_dsn, autocommit=True)
        self._sessions: dict[str, _PaginationSession] = {}
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT library_uuid, base_path FROM libraries WHERE name = %s",
                (tag,),
            )
            row = cursor.fetchone()
        if row is None:
            self._connection.close()
            raise LibraryNotFoundError(f"Library not found for tag: {tag}")
        self._library_uuid: uuid.UUID = row[0]
        self._library_root = Path(row[1])

    def close(self) -> None:
        self._connection.close()

    def list_books(self) -> list[Book]:
        rows = self._fetch_all(_LIST_BOOKS_QUERY, (self._library_uuid,))
        return [self._book_from_row(row) for row in rows]

    @staticmethod
    def _book_from_row(row: tuple[object, ...]) -> Book:
        # Layout (voir _LIST_BOOKS_QUERY_BODY) : id, title, authors, pubdate,
        # publisher_id, publisher_name, series_id, series_name, series_index,
        # rating_raw, has_cover.
        rating_raw = cast("int | None", row[9])
        rating = (int(rating_raw) // 2 or None) if rating_raw is not None else None
        return Book(
            id=str(row[0]),
            title=str(row[1]),
            authors=tuple(str(row[2]).split(", ")) if row[2] else (),
            pubdate=str(row[3]) if row[3] is not None else None,
            publisher=(
                Publisher(id=str(row[4]), name=str(row[5]))
                if row[4] is not None
                else None
            ),
            series=(
                Series(id=str(row[6]), name=str(row[7])) if row[6] is not None else None
            ),
            series_index=str(row[8]) if row[8] is not None else None,
            rating=rating,
            has_cover=bool(row[10]),
        )

    def list_authors(self) -> list[Author]:
        rows = self._fetch_all(_LIST_AUTHORS_QUERY, (self._library_uuid,))
        return [Author(id=str(row[0]), name=str(row[1])) for row in rows]

    def list_publishers(self) -> list[Publisher]:
        rows = self._fetch_all(_LIST_PUBLISHERS_QUERY, (self._library_uuid,))
        return [Publisher(id=str(row[0]), name=str(row[1])) for row in rows]

    def list_series(self) -> list[Series]:
        rows = self._fetch_all(_LIST_SERIES_QUERY, (self._library_uuid,))
        return [Series(id=str(row[0]), name=str(row[1])) for row in rows]

    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        deduped_ids, valid_ids = self._partition_ids(ids)

        placeholders = ", ".join("%s" for _ in valid_ids)
        query = _GET_BOOK_DETAILS_QUERY_TEMPLATE.format(placeholders=placeholders)
        params = (self._library_uuid, *valid_ids)
        rows = self._fetch_all(query, params)

        books = []
        found_ids: set[str] = set()
        for row in rows:
            book_id = str(row[0])
            found_ids.add(book_id)
            cover_path = self._compute_cover_path(self._library_root, row[10], row[11])
            books.append(
                BookDetails(
                    id=book_id,
                    title=str(row[1]),
                    pubdate=str(row[2]) if row[2] is not None else None,
                    authors=tuple(str(row[4]).split(", ")) if row[4] else (),
                    tags=tuple(str(row[5]).split(", ")) if row[5] else (),
                    publisher=(
                        Publisher(id=str(row[6]), name=str(row[7]))
                        if row[6] is not None
                        else None
                    ),
                    series=(
                        SeriesItem(
                            series=Series(id=str(row[8]), name=str(row[9])),
                            index=str(row[3]) if row[3] is not None else None,
                        )
                        if row[8] is not None
                        else None
                    ),
                    cover_path=cover_path,
                )
            )

        missing_ids = tuple(id_ for id_ in deduped_ids if id_ not in found_ids)
        return BookDetailsResult(books=tuple(books), missing_ids=missing_ids)

    def list_books_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult:
        rows, result_handle = self._fetch_page(
            "books", page, page_size, handle, _LIST_BOOKS_QUERY, (self._library_uuid,)
        )
        total_pages, has_more = self._bounded_total_pages(
            "SELECT book_pk FROM books WHERE library_uuid = %s",
            page_size,
            (self._library_uuid,),
        )
        books = tuple(self._book_from_row(row) for row in rows)
        return PagedBooksResult(
            items=books,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )

    def list_authors_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult:
        rows, result_handle = self._fetch_page(
            "authors",
            page,
            page_size,
            handle,
            _LIST_AUTHORS_QUERY,
            (self._library_uuid,),
        )
        total_pages, has_more = self._bounded_total_pages(
            "SELECT id FROM authors WHERE library_uuid = %s",
            page_size,
            (self._library_uuid,),
        )
        authors = tuple(Author(id=str(row[0]), name=str(row[1])) for row in rows)
        return PagedAuthorsResult(
            items=authors,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )

    def list_publishers_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult:
        rows, result_handle = self._fetch_page(
            "publishers",
            page,
            page_size,
            handle,
            _LIST_PUBLISHERS_QUERY,
            (self._library_uuid,),
        )
        total_pages, has_more = self._bounded_total_pages(
            "SELECT id FROM publishers WHERE library_uuid = %s",
            page_size,
            (self._library_uuid,),
        )
        publishers = tuple(Publisher(id=str(row[0]), name=str(row[1])) for row in rows)
        return PagedPublishersResult(
            items=publishers,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )

    def list_series_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedSeriesResult:
        rows, result_handle = self._fetch_page(
            "series",
            page,
            page_size,
            handle,
            _LIST_SERIES_QUERY,
            (self._library_uuid,),
        )
        total_pages, has_more = self._bounded_total_pages(
            "SELECT id FROM series WHERE library_uuid = %s",
            page_size,
            (self._library_uuid,),
        )
        series = tuple(Series(id=str(row[0]), name=str(row[1])) for row in rows)
        return PagedSeriesResult(
            items=series,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )

    def query_books_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult:
        params: list[object] = [self._library_uuid]
        where = _query_books_where(query, params, self._library_uuid)
        # Alignement SQLite : ASC place les NULL en premier (d'où NULLS FIRST
        # explicite, le défaut PG étant NULLS LAST), DESC les garde en dernier.
        direction = (
            " DESC NULLS LAST" if query.order is SortOrder.DESC else " ASC NULLS FIRST"
        )
        order_by = _SORT_EXPRESSIONS[query.sort] + direction
        page_sql = (
            _LIST_BOOKS_QUERY_JOINS
            + "\n    WHERE books.library_uuid = %s"
            + where.replace(" WHERE ", " AND ", 1)
            + "\n"
            + _LIST_BOOKS_GROUP_BY
            + "    ORDER BY "
            + order_by
            + "\n"
        )
        # where commence par " WHERE " : on le convertit en " AND " après la
        # condition de scoping library_uuid déjà posée.
        count_sql = "SELECT book_pk FROM books WHERE library_uuid = %s" + where.replace(
            " WHERE ", " AND ", 1
        )
        rows, result_handle = self._fetch_page(
            "query_books", page, page_size, handle, page_sql, tuple(params)
        )
        total_pages, has_more = self._bounded_total_pages(
            count_sql, page_size, tuple(params)
        )
        books = tuple(self._book_from_row(row) for row in rows)
        return PagedBooksResult(
            items=books,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )

    def query_authors_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult:
        rows, result_handle, total_pages, has_more = self._query_entity_page(
            "authors", "query_authors", query, page, page_size, handle
        )
        authors = tuple(Author(id=str(row[0]), name=str(row[1])) for row in rows)
        return PagedAuthorsResult(
            items=authors,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )

    def query_publishers_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult:
        rows, result_handle, total_pages, has_more = self._query_entity_page(
            "publishers", "query_publishers", query, page, page_size, handle
        )
        publishers = tuple(Publisher(id=str(row[0]), name=str(row[1])) for row in rows)
        return PagedPublishersResult(
            items=publishers,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )

    def query_series_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedSeriesResult:
        rows, result_handle, total_pages, has_more = self._query_entity_page(
            "series", "query_series", query, page, page_size, handle
        )
        series = tuple(Series(id=str(row[0]), name=str(row[1])) for row in rows)
        return PagedSeriesResult(
            items=series,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )

    def list_field_values(
        self, field: Literal["tags", "languages", "formats", "ratings"]
    ) -> list[FieldValue]:
        rows = self._fetch_all(_FACET_QUERIES[field], (self._library_uuid,))
        return [
            FieldValue(value=str(row[0]), count=cast("int", row[1])) for row in rows
        ]

    def _query_entity_page(
        self,
        entity: str,
        resource: str,
        query: BookQuery,
        page: int,
        page_size: int,
        handle: str | None,
    ) -> tuple[list[tuple[object, ...]], str | None, int | None, bool]:
        """Page les entités participant aux books matchés par la requête.

        Chaque clause de _query_books_where est autoportante : elle s'applique
        à un "FROM books" nu à l'intérieur du sous-select d'ids filtrés. La
        table books_<entité>_link relie les book_pk aux ids internes de
        l'entité ; l'id public paginé est local_id.
        """
        params: list[object] = [self._library_uuid]
        where = _query_books_where(query, params, self._library_uuid)
        filtered_books = (
            "SELECT books.book_pk FROM books WHERE books.library_uuid = %s"
            + where.replace(" WHERE ", " AND ", 1)
        )
        link_table, link_column = _ENTITY_LINK_TABLES[entity]
        entity_ids = (
            f"SELECT {link_column} FROM {link_table}"
            f" WHERE book_pk IN ({filtered_books})"
        )
        page_sql = (
            f"SELECT DISTINCT {entity}.local_id, {entity}.name FROM {entity}"
            f" WHERE {entity}.id IN ({entity_ids})"
            f" ORDER BY {entity}.name"
        )
        count_sql = (
            f"SELECT {entity}.id FROM {entity} WHERE {entity}.id IN ({entity_ids})"
        )
        rows, result_handle = self._fetch_page(
            resource, page, page_size, handle, page_sql, tuple(params)
        )
        total_pages, has_more = self._bounded_total_pages(
            count_sql, page_size, tuple(params)
        )
        return rows, result_handle, total_pages, has_more

    def close_pagination(self, handle: str) -> None:
        self._sessions.pop(handle, None)

    def _now(self) -> float:
        return time.monotonic()

    def _prune_expired_sessions(self) -> None:
        now = self._now()
        expired = [
            handle
            for handle, session in self._sessions.items()
            if now - session.last_access > _SESSION_TIMEOUT_SECONDS
        ]
        for handle in expired:
            self._sessions.pop(handle)

    def _fetch_page(
        self,
        resource: str,
        page: int,
        page_size: int,
        handle: str | None,
        query_sql: str,
        query_params: tuple[object, ...],
    ) -> tuple[list[tuple[object, ...]], str | None]:
        """Rejoue LIMIT/OFFSET : le handle désigne une session mémoire.

        La session stocke le SQL et ses paramètres ; chaque page ré-exécute la
        requête avec l'OFFSET (page - 1) * page_size. Quand une page n'est pas
        pleine, la session est supprimée et le handle rendu est None - la
        sémantique de fin de flux est donc identique au curseur côté SQLite.
        """
        self._prune_expired_sessions()

        session = self._sessions.get(handle) if handle is not None else None
        reusable = (
            session is not None
            and session.resource == resource
            and session.page_size == page_size
            and session.next_page == page
        )
        if (
            session is not None
            and not reusable
            and handle is not None
            and session.resource == resource
            and session.page_size == page_size
        ):
            # Un handle connu pour la même ressource/page_size qui n'est pas la
            # page suivante (répétition, saut arrière) est supplanté, pas
            # simplement sans rapport : on le ferme maintenant plutôt que
            # d'attendre l'expiration. Un handle qui ne correspond pas sur la
            # ressource ou le page_size peut encore être une autre session
            # voulue sous son propre handle - on le laisse au timeout.
            self._sessions.pop(handle, None)

        offset = (page - 1) * page_size
        rows = self._fetch_all(
            query_sql + " LIMIT %s OFFSET %s", (*query_params, page_size, offset)
        )

        if reusable and session is not None and handle is not None:
            result_handle: str | None = handle
            session.next_page = page + 1
            session.last_access = self._now()
        else:
            result_handle = str(uuid.uuid4())
            self._sessions[result_handle] = _PaginationSession(
                resource=resource,
                page_size=page_size,
                next_page=page + 1,
                query_sql=query_sql,
                query_params=query_params,
                last_access=self._now(),
            )

        if len(rows) < page_size and result_handle is not None:
            self._sessions.pop(result_handle, None)
            result_handle = None

        return rows, result_handle

    def _bounded_total_pages(
        self,
        count_query: str,
        page_size: int,
        count_params: tuple[object, ...] = (),
    ) -> tuple[int | None, bool]:
        row_cap = _PAGE_COUNT_CAP * page_size + 1
        rows = self._fetch_all(
            f"SELECT COUNT(*) FROM ({count_query} LIMIT %s) AS _count",
            (*count_params, row_cap),
        )
        count = cast("int", rows[0][0])
        if count > _PAGE_COUNT_CAP * page_size:
            return None, True
        total_pages = -(-count // page_size) if count else 0
        return total_pages, False

    def _fetch_all(
        self, query: str, params: tuple[object, ...]
    ) -> list[tuple[object, ...]]:
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    @staticmethod
    def _compute_cover_path(
        library_root: Path, book_path: object, has_cover: object
    ) -> str | None:
        if not has_cover or not book_path:
            return None
        return str(library_root / str(book_path).rstrip("/") / "cover.jpg")

    @staticmethod
    def _partition_ids(raw_ids: list[str]) -> tuple[list[str], list[str]]:
        """Déduplique (ordre de première apparition, segments vides exclus) et
        sépare en (deduped_ids, valid_ids) : deduped_ids contient tous les ids
        distincts demandés dans l'ordre, valid_ids le sous-ensemble sûr à
        placer dans un IN (...) SQL."""
        seen: set[str] = set()
        deduped_ids: list[str] = []
        valid_ids: list[str] = []
        for raw_id in raw_ids:
            if raw_id == "" or raw_id in seen:
                continue
            seen.add(raw_id)
            deduped_ids.append(raw_id)
            if _VALID_ID_PATTERN.fullmatch(raw_id):
                valid_ids.append(raw_id)
        return deduped_ids, valid_ids
