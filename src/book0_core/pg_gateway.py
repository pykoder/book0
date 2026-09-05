"""ReadLibraryGateway contre le schéma PostgreSQL de calibre_pg_sync.

Tout le SQL PG de book0 vit dans ce module. Les tables miroirs sont scopées
par library_uuid ; les ids publics (Book.id, Author.id, ...) sont les
colonnes local_id exposées en str - la même identité stable que les ids
SQLite - tandis que les BIGSERIAL (book_pk, authors.id, ...) restent
internes au module.
"""

import hashlib
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, cast

import psycopg
from epub2md import build_markdown, parse_extract_spec
from psycopg.types.json import Json

from book0_core.errors import (
    AuthorNameMismatchError,
    AuthorNotFoundError,
    BookNotFoundError,
    InvalidAliasError,
    InvalidApplyNameError,
    InvalidExtractError,
    InvalidPatchError,
    LibraryNotFoundError,
    NoEpubError,
)
from book0_core.models import (
    ApplyNameRequest,
    ApplyNameResult,
    Author,
    AuthorAliasGroup,
    Book,
    BookContent,
    BookDetails,
    BookDetailsResult,
    BookPatch,
    BookQuery,
    BookSort,
    EditBooksResult,
    FieldValue,
    Job,
    JobAction,
    JobFailure,
    JobOutcome,
    JobRequest,
    JobStatus,
    NameTargetById,
    NameTargetByName,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedJobsResult,
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

# Échelle Calibre des notes en étoiles (stockée x2 en base : 1..5 -> 2..10).
_RATING_MIN_STARS = 1
_RATING_MAX_STARS = 5

_SESSION_TIMEOUT_SECONDS = 60
_PAGE_COUNT_CAP = 100  # en pages ; le plafond de lignes est _PAGE_COUNT_CAP * page_size

# Niveau de découpage markdown accepté par epub2md (1 = titre seul, 7 = paragraphes).
_LEVEL_MIN = 1
_LEVEL_MAX = 7

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

# Jobs de fond (spec §7.2) : le layout de cette requête est consommé par
# _job_from_row (id, action, status, outcome, created_at, started_at,
# finished_at) ; le WHERE et le ORDER BY sont ajoutés par appelant.
_JOBS_QUERY = (
    "SELECT id, action, status, outcome, created_at, started_at, finished_at FROM jobs"
)


def _iso_utc(value: datetime) -> str:
    """Formate un timestamptz PG en ISO 8601 UTC suffixé 'Z' - le format wire
    des timestamps de jobs dans la spec §7.2 (ex. 2026-08-31T12:00:00Z)."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _job_outcome_from_json(value: object) -> JobOutcome | None:
    """Désérialise l'outcome jsonb d'un job en JobOutcome (None si NULL) ;
    les dicts viennent du décodeur jsonb natif de psycopg."""
    if value is None:
        return None
    data = cast("dict[str, object]", value)
    return JobOutcome(
        succeeded=tuple(
            str(book_id)
            for book_id in cast("list[object]", data.get("succeeded") or ())
        ),
        failed=tuple(
            JobFailure(id=str(item["id"]), reason=str(item["reason"]))
            for item in cast("list[dict[str, object]]", data.get("failed") or ())
        ),
    )


def _job_outcome_to_json(outcome: JobOutcome) -> dict[str, object]:
    """Sérialise un JobOutcome en jsonb (layout miroir de
    _job_outcome_from_json : {'succeeded': [...], 'failed': [{id, reason}]})."""
    return {
        "succeeded": list(outcome.succeeded),
        "failed": [
            {"id": failure.id, "reason": failure.reason} for failure in outcome.failed
        ],
    }


def _extract_syntax_error_type() -> type[Exception]:
    """Capture au chargement du module le type d'exception levé par
    parse_extract_spec sur une erreur de syntaxe d'extract (un
    argparse.ArgumentTypeError côté epub2md), sans que book0_core dépende
    d'argparse - voir CLAUDE.md, dépendances interdites pour book0_core."""
    try:
        parse_extract_spec("not a spec")
    except ValueError:
        return ValueError  # pragma: no cover — "not a spec" est une erreur de syntaxe
    except Exception as e:  # noqa: BLE001 — capture du type seul, pas un silencieux
        return type(e)
    return ValueError  # pragma: no cover


_EXTRACT_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    _extract_syntax_error_type(),
)


class _DryRunRollback(Exception):
    """Sentinelle interne : levée en fin de dry_run pour forcer le ROLLBACK
    de la transaction psycopg ouverte par Connection.transaction(), capturée
    à la frontière de edit_books - jamais exposée aux appelants."""


def _parse_edit_patch(patch: BookPatch) -> tuple[float | None, date | None]:
    """Valide les champs patch à convertir (series_index, rating, pubdate) et
    retourne (series_index en float, pubdate en date). Lève InvalidPatchError
    sur une valeur non analysable ou hors échelle - avant toute écriture."""
    series_index: float | None = None
    if patch.series_index is not None:
        try:
            series_index = float(patch.series_index)
        except ValueError:
            raise InvalidPatchError(
                f"series_index invalide : {patch.series_index!r}"
            ) from None
    if patch.rating is not None and not (
        _RATING_MIN_STARS <= patch.rating <= _RATING_MAX_STARS
    ):
        raise InvalidPatchError(
            f"rating hors échelle {_RATING_MIN_STARS}-{_RATING_MAX_STARS}"
            f" étoiles : {patch.rating}"
        )
    pubdate: date | None = None
    if patch.pubdate is not None:
        try:
            pubdate = date.fromisoformat(patch.pubdate)
        except ValueError:
            raise InvalidPatchError(f"pubdate invalide : {patch.pubdate!r}") from None
    return series_index, pubdate


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

    def __init__(
        self,
        pg_dsn: str,
        tag: str | None = None,
        markdown_cache_dir: Path | None = None,
    ) -> None:
        # Lectures seules : l'autocommit évite de maintenir une transaction
        # (donc des verrous ACCESS SHARE) ouverte entre deux opérations.
        self._connection = psycopg.connect(pg_dsn, autocommit=True)
        self._sessions: dict[str, _PaginationSession] = {}
        self._pg_dsn = pg_dsn
        self._markdown_cache_dir = markdown_cache_dir
        if tag is None:
            # Passer tag=None construit une passerelle non scopée, réservée
            # aux lectures globales de jobs (GET /libraries/jobs sans tag) :
            # les ids de jobs étant des uuid4 uniques, ils n'ont pas besoin de
            # contexte de bibliothèque. Toute autre méthode (books, authors,
            # écritures de jobs...) exige une passerelle scopée par tag.
            self._library_uuid: uuid.UUID | None = None
            self._library_root: Path | None = None
            return
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT library_uuid, base_path FROM libraries WHERE name = %s",
                (tag,),
            )
            row = cursor.fetchone()
        if row is None:
            self._connection.close()
            raise LibraryNotFoundError(f"Library not found for tag: {tag}")
        self._library_uuid = uuid.UUID(str(row[0]))
        self._library_root = Path(str(row[1]))

    def close(self) -> None:
        self._connection.close()

    @property
    def pg_dsn(self) -> str:
        """DSN PG de connexion (exposé à l'exécuteur sync-library pour
        construire son CalibreSyncer)."""
        return self._pg_dsn

    @property
    def base_path(self) -> Path:
        """Racine disque de la bibliothèque (colonne libraries.base_path)."""
        return self._require_library_root()

    def _require_library_uuid(self) -> uuid.UUID:
        """self._library_uuid narrowé non-None : toute méthode hors lectures
        globales de jobs exige une passerelle scopée par tag."""
        if self._library_uuid is None:
            raise RuntimeError(
                "this method requires a tag-scoped gateway (tag=None is"
                " reserved for global job reads)"
            )
        return self._library_uuid

    def _require_library_root(self) -> Path:
        """self._library_root narrowé non-None (même contrat que
        _require_library_uuid)."""
        if self._library_root is None:
            raise RuntimeError(
                "this method requires a tag-scoped gateway (tag=None is"
                " reserved for global job reads)"
            )
        return self._library_root

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
            cover_path = self._compute_cover_path(
                self._require_library_root(), row[10], row[11]
            )
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
        where = _query_books_where(query, params, self._require_library_uuid())
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

    def get_book_content(
        self, book_id: str, level: int, extract: str | None
    ) -> BookContent:
        """Convertis l'EPUB d'un livre en markdown via epub2md, avec cache
        disque clé par (book_id, level, mtime de l'EPUB, hash court de
        l'extract) : le cache est invalidé dès que l'EPUB change sur disque et
        deux extracts distincts ne partagent jamais une entrée.
        markdown_cache_dir=None (constructeur) désactive le cache - conversion
        à chaque appel."""
        if not _LEVEL_MIN <= level <= _LEVEL_MAX:
            raise InvalidExtractError(f"level hors {_LEVEL_MIN}-{_LEVEL_MAX} : {level}")
        if not _VALID_ID_PATTERN.fullmatch(book_id):
            raise BookNotFoundError(f"Book not found: local_id={book_id}")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT book_pk, path FROM books"
                " WHERE library_uuid = %s AND local_id = %s",
                (self._library_uuid, int(book_id)),
            )
            row = cursor.fetchone()
            if row is None:
                raise BookNotFoundError(f"Book not found: local_id={book_id}")
            book_pk, book_path = int(row[0]), str(row[1])
            cursor.execute(
                "SELECT name FROM data WHERE book_pk = %s AND format = 'EPUB'",
                (book_pk,),
            )
            data_row = cursor.fetchone()
        if data_row is None:
            raise NoEpubError(f"No EPUB for book local_id={book_id}")
        epub_path = self._require_library_root() / book_path / f"{data_row[0]}.epub"
        if not epub_path.is_file():
            raise NoEpubError(f"EPUB file missing on disk: {epub_path}")
        extract_spec: tuple[str, str, bool] | None = None
        if extract is not None:
            try:
                extract_spec = parse_extract_spec(extract)
            except _EXTRACT_ERRORS as exc:
                raise InvalidExtractError(
                    f"extract invalide : {extract!r} ({exc})"
                ) from None

        cache_path: Path | None = None
        if self._markdown_cache_dir is not None:
            # La clé intègre un hash court de l'extract demandé : deux extracts
            # distincts au même level/mtime ne doivent pas partager un fichier.
            extract_digest = hashlib.sha256((extract or "").encode()).hexdigest()[:12]
            cache_path = self._markdown_cache_dir / (
                f"{book_id}-{level}-{int(epub_path.stat().st_mtime)}-{extract_digest}.md"
            )
            if cache_path.is_file():
                return BookContent(
                    book_id=book_id,
                    level=level,
                    extract=extract,
                    markdown=cache_path.read_text(encoding="utf-8"),
                )

        try:
            markdown = build_markdown(epub_path, level, extract=extract_spec)
        except ValueError as exc:
            # ValueError sémantique d'epub2md (apply_extract : numéro absent du
            # document, fin avant début) : c'est un extract invalide au sens du
            # contrat, pas une erreur interne à fuir.
            raise InvalidExtractError(
                f"extract invalide : {extract!r} ({exc})"
            ) from None
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(markdown, encoding="utf-8")
        return BookContent(
            book_id=book_id, level=level, extract=extract, markdown=markdown
        )

    def edit_books(
        self, ids: list[str], patch: BookPatch, dry_run: bool = False
    ) -> EditBooksResult:
        """PATCH en masse des champs de métadonnées, en une transaction.

        Les ids de livres inconnus sont signalés dans missing_ids (pas une
        erreur) ; les ids vides ou un patch entièrement None, ainsi qu'un
        publisher_id/series_id inconnu de la bibliothèque, lèvent
        InvalidPatchError. dry_run=True rejoue toute la validation et les
        écritures puis annule la transaction : la réponse est identique à une
        exécution réelle, sans écriture.
        """
        if not ids:
            raise InvalidPatchError("edit_books : liste d'ids de livres vide")
        if (
            patch.publisher_id is None
            and patch.series_id is None
            and patch.series_index is None
            and patch.tags is None
            and patch.rating is None
            and patch.pubdate is None
            and patch.language is None
            and patch.comments is None
        ):
            raise InvalidPatchError("edit_books : patch sans aucun champ à modifier")
        series_index_value, pubdate_value = _parse_edit_patch(patch)

        deduped_ids, valid_ids = self._partition_ids(ids)
        try:
            with self._connection.transaction():
                updated = self._apply_edit_books(
                    deduped_ids, valid_ids, patch, series_index_value, pubdate_value
                )
                if dry_run:
                    raise _DryRunRollback
        except _DryRunRollback:
            pass  # dry_run : la transaction a déjà été annulée par le context manager
        found = set(updated)
        return EditBooksResult(
            updated=tuple(updated),
            missing_ids=tuple(id_ for id_ in deduped_ids if id_ not in found),
        )

    def _apply_edit_books(
        self,
        deduped_ids: list[str],
        valid_ids: list[str],
        patch: BookPatch,
        series_index_value: float | None,
        pubdate_value: date | None,
    ) -> list[str]:
        """Applique le patch à chaque livre existant, dans la transaction
        ouverte par edit_books (verrous FOR UPDATE sur les lignes books).
        Retourne les ids locaux réellement modifiés, dans l'ordre demandé."""
        with self._connection.cursor() as cursor:
            publisher_pk = (
                self._resolve_entity_id(cursor, "publishers", patch.publisher_id)
                if patch.publisher_id is not None
                else None
            )
            series_pk = (
                self._resolve_entity_id(cursor, "series", patch.series_id)
                if patch.series_id is not None
                else None
            )
            # local_id -> (book_pk, series_index courant) ; FOR UPDATE
            # verrouille les lignes pour toute la durée du PATCH en masse.
            book_pks: dict[str, tuple[int, float | None]] = {}
            if valid_ids:
                placeholders = ", ".join("%s" for _ in valid_ids)
                cursor.execute(
                    "SELECT book_pk, local_id, series_index FROM books"
                    f" WHERE library_uuid = %s AND local_id IN ({placeholders})"
                    " ORDER BY local_id FOR UPDATE",
                    (self._library_uuid, *(int(id_) for id_ in valid_ids)),
                )
                book_pks = {
                    str(row[1]): (int(row[0]), cast("float | None", row[2]))
                    for row in cursor.fetchall()
                }
            updated: list[str] = []
            for book_id in deduped_ids:
                if book_id not in book_pks:
                    continue
                book_pk, current_series_index = book_pks[book_id]
                # ord du lien de série : l'index demandé, sinon l'index courant
                # du livre (Calibre garde books.series_index et
                # books_series_link.ord synchronisés).
                series_ord = (
                    series_index_value
                    if patch.series_index is not None
                    else current_series_index
                )
                self._apply_book_patch(
                    cursor,
                    book_pk,
                    patch,
                    publisher_pk,
                    series_pk,
                    series_ord,
                    pubdate_value,
                )
                updated.append(book_id)
            return updated

    def _apply_book_patch(
        self,
        cursor: psycopg.Cursor,
        book_pk: int,
        patch: BookPatch,
        publisher_pk: int | None,
        series_pk: int | None,
        series_ord: float | None,
        pubdate_value: date | None,
    ) -> None:
        """Écrit chaque champ présent dans le patch pour un livre. Chaque lien
        est remplacé (delete + insert) ; tags/ratings/languages en
        get-or-create ; comments en upsert (PK book_pk)."""
        if publisher_pk is not None:
            cursor.execute(
                "DELETE FROM books_publishers_link WHERE book_pk = %s", (book_pk,)
            )
            cursor.execute(
                "INSERT INTO books_publishers_link (book_pk, publisher_id)"
                " VALUES (%s, %s)",
                (book_pk, publisher_pk),
            )
        if series_pk is not None:
            cursor.execute(
                "DELETE FROM books_series_link WHERE book_pk = %s", (book_pk,)
            )
            cursor.execute(
                "INSERT INTO books_series_link (book_pk, series_id, ord)"
                " VALUES (%s, %s, %s)",
                (book_pk, series_pk, series_ord),
            )
        if patch.series_index is not None:
            cursor.execute(
                "UPDATE books SET series_index = %s WHERE book_pk = %s",
                (series_ord, book_pk),
            )
        if patch.tags is not None:
            cursor.execute("DELETE FROM books_tags_link WHERE book_pk = %s", (book_pk,))
            for tag_name in patch.tags:
                tag_id = self._get_or_create_tag(cursor, tag_name)
                cursor.execute(
                    "INSERT INTO books_tags_link (book_pk, tag_id) VALUES (%s, %s)",
                    (book_pk, tag_id),
                )
        if patch.rating is not None:
            rating_id = self._get_or_create_rating(cursor, patch.rating)
            cursor.execute(
                "DELETE FROM books_ratings_link WHERE book_pk = %s", (book_pk,)
            )
            cursor.execute(
                "INSERT INTO books_ratings_link (book_pk, rating_id) VALUES (%s, %s)",
                (book_pk, rating_id),
            )
        if pubdate_value is not None:
            cursor.execute(
                "UPDATE books SET pubdate = %s WHERE book_pk = %s",
                (pubdate_value, book_pk),
            )
        if patch.language is not None:
            language_id = self._get_or_create_language(cursor, patch.language)
            cursor.execute(
                "DELETE FROM books_languages_link WHERE book_pk = %s", (book_pk,)
            )
            cursor.execute(
                "INSERT INTO books_languages_link (book_pk, language_id, item_order)"
                " VALUES (%s, %s, 0)",
                (book_pk, language_id),
            )
        if patch.comments is not None:
            cursor.execute(
                "INSERT INTO comments (book_pk, text) VALUES (%s, %s)"
                " ON CONFLICT (book_pk) DO UPDATE SET text = EXCLUDED.text",
                (book_pk, patch.comments),
            )

    def _resolve_entity_id(
        self, cursor: psycopg.Cursor, table: str, local_id: str
    ) -> int:
        """Résout un id public (local_id) en id interne BIGSERIAL, en levant
        InvalidPatchError si l'entité n'existe pas dans la bibliothèque.
        table vient d'un appel interne à table fixe ('publishers', 'series')."""
        if not _VALID_ID_PATTERN.fullmatch(local_id):
            raise InvalidPatchError(f"{table} : id invalide {local_id!r}")
        cursor.execute(
            f"SELECT id FROM {table} WHERE library_uuid = %s AND local_id = %s",
            (self._library_uuid, int(local_id)),
        )
        row = cursor.fetchone()
        if row is None:
            raise InvalidPatchError(
                f"{table} local_id={local_id} introuvable dans la bibliothèque"
            )
        return int(row[0])

    def _get_or_create_tag(self, cursor: psycopg.Cursor, name: str) -> int:
        cursor.execute(
            "SELECT id FROM tags WHERE library_uuid = %s AND name = %s",
            (self._library_uuid, name),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(row[0])
        return self._insert_dimension_row(cursor, "tags", name, "name")

    def _get_or_create_rating(self, cursor: psycopg.Cursor, stars: int) -> int:
        value = stars * 2  # échelle Calibre 0-10 : 2 points par étoile
        cursor.execute(
            "SELECT id FROM ratings WHERE library_uuid = %s AND rating = %s",
            (self._library_uuid, value),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(row[0])
        return self._insert_dimension_row(cursor, "ratings", value, "rating")

    def _get_or_create_language(self, cursor: psycopg.Cursor, lang_code: str) -> int:
        cursor.execute(
            "SELECT id FROM languages WHERE library_uuid = %s AND lang_code = %s",
            (self._library_uuid, lang_code),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(row[0])
        return self._insert_dimension_row(cursor, "languages", lang_code, "lang_code")

    def _insert_dimension_row(
        self, cursor: psycopg.Cursor, table: str, value: object, column: str
    ) -> int:
        """Insère une ligne de dimension (tags/ratings/languages) avec le
        prochain local_id libre de la bibliothèque et retourne l'id interne."""
        cursor.execute(
            f"SELECT COALESCE(MAX(local_id), 0) + 1 FROM {table}"
            " WHERE library_uuid = %s",
            (self._library_uuid,),
        )
        next_local_id = int(cast("tuple[int, ...]", cursor.fetchone())[0])
        cursor.execute(
            f"INSERT INTO {table} (library_uuid, local_id, {column})"
            " VALUES (%s, %s, %s) RETURNING id",
            (self._library_uuid, next_local_id, value),
        )
        return int(cast("tuple[int, ...]", cursor.fetchone())[0])

    def create_job(self, request: JobRequest) -> Job:
        """Persiste un job en 'pending' et le retourne. params est sérialisé
        en jsonb tel quel ({} quand la requête n'en porte pas)."""
        job_id = uuid.uuid4()
        params = dict(request.params) if request.params else {}
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO jobs (id, library_uuid, action, status, params)"
                " VALUES (%s, %s, %s, 'pending', %s)"
                " RETURNING created_at",
                (job_id, self._library_uuid, request.action.value, Json(params)),
            )
            created_at = _iso_utc(
                cast("datetime", cast("tuple[object, ...]", cursor.fetchone())[0])
            )
        return Job(
            id=str(job_id),
            action=request.action,
            status=JobStatus.PENDING,
            created_at=created_at,
            started_at=None,
            finished_at=None,
            outcome=None,
        )

    def get_job(self, job_id: str) -> Job | None:
        """Retourne le job demandé, None s'il est inconnu (ou si job_id n'est
        pas un UUID - même sémantique « pas trouvé »). Scopé par bibliothèque
        sur une passerelle taguée ; global sinon (l'id uuid4 est unique)."""
        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError:
            return None
        if self._library_uuid is None:
            where = " WHERE id = %s"
            params: tuple[object, ...] = (job_uuid,)
        else:
            where = " WHERE library_uuid = %s AND id = %s"
            params = (self._library_uuid, job_uuid)
        with self._connection.cursor() as cursor:
            cursor.execute(_JOBS_QUERY + where, params)
            row = cursor.fetchone()
        return self._job_from_row(row) if row is not None else None

    def list_jobs_page(
        self,
        status: JobStatus | None,
        action: JobAction | None,
        page: int,
        page_size: int,
    ) -> PagedJobsResult:
        """Liste paginée des jobs, triée created_at DESC (id DESC en
        brise-dégalité), filtres status/action optionnels. Scopée par
        bibliothèque sur une passerelle taguée ; globale sinon (la console de
        jobs du serveur liste toutes les bibliothèques). Pagination offset
        SQL simple : le handle est toujours None."""
        params: list[object] = []
        conditions: list[str] = []
        if self._library_uuid is not None:
            params.append(self._library_uuid)
            conditions.append("library_uuid = %s")
        if status is not None:
            conditions.append("status = %s")
            params.append(status.value)
        if action is not None:
            conditions.append("action = %s")
            params.append(action.value)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self._fetch_all(
            _JOBS_QUERY + where + " ORDER BY created_at DESC, id DESC"
            " LIMIT %s OFFSET %s",
            (*params, page_size, (page - 1) * page_size),
        )
        total_pages, has_more = self._bounded_total_pages(
            "SELECT id FROM jobs" + where, page_size, tuple(params)
        )
        return PagedJobsResult(
            items=tuple(self._job_from_row(row) for row in rows),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=None,
        )

    def mark_interrupted_jobs(self) -> int:
        """Bascule les jobs 'running' en 'interrupted' (un job running sans
        processus vivant l'est forcément après un redémarrage) ; retourne le
        nombre de lignes mises à jour. Scopée par bibliothèque sur une
        passerelle taguée ; globale sinon (au démarrage du serveur, une seule
        passe couvre toutes les bibliothèques PG)."""
        if self._library_uuid is None:
            query = (
                "UPDATE jobs SET status = 'interrupted', finished_at = now()"
                " WHERE status = 'running'"
            )
            params: tuple[object, ...] = ()
        else:
            query = (
                "UPDATE jobs SET status = 'interrupted', finished_at = now()"
                " WHERE status = 'running' AND library_uuid = %s"
            )
            params = (self._library_uuid,)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def update_job_status(
        self, job_id: str, status: JobStatus, outcome: JobOutcome | None = None
    ) -> None:
        """Transition de statut pilotée par l'exécuteur de jobs (book0_api) :
        'running' pose started_at (outcome NULL), 'done'/'failed' posent
        finished_at et l'outcome. Respecte la contrainte CHECK
        (status IN ('done','failed')) = (outcome IS NOT NULL)."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE jobs SET status = %s, outcome = %s,"
                " started_at = CASE WHEN %s = 'running' THEN now()"
                " ELSE started_at END,"
                " finished_at = CASE WHEN %s IN ('done', 'failed') THEN now()"
                " ELSE finished_at END"
                " WHERE id = %s AND library_uuid = %s",
                (
                    status.value,
                    Json(_job_outcome_to_json(outcome)) if outcome else None,
                    status.value,
                    status.value,
                    uuid.UUID(job_id),
                    self._library_uuid,
                ),
            )

    @staticmethod
    def _job_from_row(row: tuple[object, ...]) -> Job:
        """Layout (voir _JOBS_QUERY) : id, action, status, outcome, created_at,
        started_at, finished_at."""
        return Job(
            id=str(row[0]),
            action=JobAction(str(row[1])),
            status=JobStatus(str(row[2])),
            outcome=_job_outcome_from_json(row[3]),
            created_at=_iso_utc(cast("datetime", row[4])),
            started_at=_iso_utc(cast("datetime", row[5]))
            if row[5] is not None
            else None,
            finished_at=(
                _iso_utc(cast("datetime", row[6])) if row[6] is not None else None
            ),
        )

    # --- Groupes d'alias d'auteurs (author_entity / author_entity_member) ---
    # Un auteur ne peut être membre que d'UN groupe (UNIQUE(author_id)) :
    # add_author_alias crée le groupe, y fait entrer l'alias, ou fusionne les
    # deux groupes existants (membres du second migrés vers le premier, second
    # supprimé). display_author_id est posé à la création du groupe sur
    # l'auteur créateur (author_id) ; apply_author_name peut le re-canoniser
    # vers sa cible - c'est l'auteur canonique dont le nom représente le
    # groupe.

    def _resolve_author(
        self, cursor: psycopg.Cursor, author_id: str
    ) -> tuple[int, str, str]:
        """Résout un id public d'auteur en (id interne BIGINT, local_id, nom),
        en levant AuthorNotFoundError si l'auteur n'existe pas dans la
        bibliothèque (un id non numérique ne peut qu'être inconnu)."""
        if not _VALID_ID_PATTERN.fullmatch(author_id):
            raise AuthorNotFoundError(f"Author not found: local_id={author_id}")
        cursor.execute(
            "SELECT id, name FROM authors WHERE library_uuid = %s AND local_id = %s",
            (self._require_library_uuid(), int(author_id)),
        )
        row = cursor.fetchone()
        if row is None:
            raise AuthorNotFoundError(f"Author not found: local_id={author_id}")
        return int(row[0]), str(int(author_id)), str(row[1])

    def _entity_of_author(
        self, cursor: psycopg.Cursor, author_pk: int
    ) -> uuid.UUID | None:
        """Groupe (author_entity.id) auquel appartient l'auteur, None s'il
        n'appartient à aucun."""
        cursor.execute(
            "SELECT ae.id FROM author_entity ae"
            " JOIN author_entity_member m ON m.entity_id = ae.id"
            " WHERE ae.library_uuid = %s AND m.author_id = %s",
            (self._require_library_uuid(), author_pk),
        )
        row = cursor.fetchone()
        return uuid.UUID(str(row[0])) if row is not None else None

    def _members_of_entity(
        self, cursor: psycopg.Cursor, entity_id: uuid.UUID
    ) -> list[tuple[int, str, str]]:
        """Membres d'un groupe, triés par local_id : (id interne, local_id, nom)."""
        cursor.execute(
            "SELECT m.author_id, a.local_id, a.name FROM author_entity_member m"
            " JOIN authors a ON a.id = m.author_id"
            " WHERE m.entity_id = %s ORDER BY a.local_id",
            (entity_id,),
        )
        return [(int(row[0]), str(row[1]), str(row[2])) for row in cursor.fetchall()]

    def _alias_group_for(
        self, cursor: psycopg.Cursor, author_pk: int, author_local_id: str
    ) -> AuthorAliasGroup:
        """AuthorAliasGroup de l'auteur : son groupe réel, ou le singleton
        (lui-même) s'il n'appartient à aucun groupe."""
        entity_id = self._entity_of_author(cursor, author_pk)
        if entity_id is None:
            row = (
                author_pk,
                author_local_id,
                self._author_name(cursor, author_pk),
            )
            members = [row]
        else:
            members = self._members_of_entity(cursor, entity_id)
        return AuthorAliasGroup(
            author_id=author_local_id,
            group=tuple(local_id for _, local_id, _ in members),
            names={local_id: name for _, local_id, name in members},
        )

    def _author_name(self, cursor: psycopg.Cursor, author_pk: int) -> str:
        cursor.execute("SELECT name FROM authors WHERE id = %s", (author_pk,))
        return str(cast("tuple[object, ...]", cursor.fetchone())[0])

    def get_author_aliases(self, author_id: str) -> AuthorAliasGroup:
        """Groupe d'alias de l'auteur : auteur inconnu -> AuthorNotFoundError ;
        sans groupe -> le singleton (author_id,) avec son nom."""
        with self._connection.cursor() as cursor:
            author_pk, author_local_id, _ = self._resolve_author(cursor, author_id)
            return self._alias_group_for(cursor, author_pk, author_local_id)

    def add_author_alias(self, author_id: str, alias_id: str) -> AuthorAliasGroup:
        """Ajoute alias_id au groupe de author_id (créé si besoin) ; si l'alias
        appartient déjà à un AUTRE groupe, les deux groupes fusionnent en une
        transaction (les membres du second migrent vers le premier, le second
        est supprimé). author_id == alias_id -> InvalidAliasError ; auteur
        inconnu -> AuthorNotFoundError. Retourne le groupe résultant."""
        with (
            self._connection.transaction(),
            self._connection.cursor() as cursor,
        ):
            author_pk, author_local_id, _ = self._resolve_author(cursor, author_id)
            alias_pk, _, _ = self._resolve_author(cursor, alias_id)
            if author_pk == alias_pk:
                raise InvalidAliasError(
                    f"un auteur ne peut pas être son propre alias : {author_id}"
                )
            entity_a = self._entity_of_author(cursor, author_pk)
            entity_b = self._entity_of_author(cursor, alias_pk)
            if entity_a is None and entity_b is None:
                # Ni l'auteur ni l'alias n'ont de groupe : création d'un
                # groupe dont display_author_id est l'auteur créateur.
                new_entity_id = uuid.uuid4()
                cursor.execute(
                    "INSERT INTO author_entity (id, library_uuid,"
                    " display_author_id) VALUES (%s, %s, %s)",
                    (new_entity_id, self._require_library_uuid(), author_pk),
                )
                cursor.executemany(
                    "INSERT INTO author_entity_member (entity_id, author_id)"
                    " VALUES (%s, %s)",
                    [(new_entity_id, author_pk), (new_entity_id, alias_pk)],
                )
            elif entity_a is None:
                # L'auteur rejoint le groupe existant de l'alias.
                cursor.execute(
                    "INSERT INTO author_entity_member (entity_id, author_id)"
                    " VALUES (%s, %s)",
                    (entity_b, author_pk),
                )
            elif entity_b is None:
                # L'alias rejoint le groupe existant de l'auteur.
                cursor.execute(
                    "INSERT INTO author_entity_member (entity_id, author_id)"
                    " VALUES (%s, %s)",
                    (entity_a, alias_pk),
                )
            elif entity_a != entity_b:
                # Fusion : les membres du second groupe migrent vers le
                # premier (disjoints par UNIQUE(author_id)), puis le
                # second (vidé) est supprimé - l'ON DELETE CASCADE
                # n'a plus aucune ligne de membre à retirer.
                cursor.execute(
                    "UPDATE author_entity_member SET entity_id = %s"
                    " WHERE entity_id = %s",
                    (entity_a, entity_b),
                )
                cursor.execute("DELETE FROM author_entity WHERE id = %s", (entity_b,))
            return self._alias_group_for(cursor, author_pk, author_local_id)

    def remove_author_alias(self, author_id: str, alias_id: str) -> AuthorAliasGroup:
        """Retire alias_id du groupe de author_id (l'auteur reste en base) ;
        si le groupe devient mono-membre, la ligne author_entity est supprimée.
        alias hors groupe (ou auto-association) -> InvalidAliasError ; auteur
        inconnu -> AuthorNotFoundError. Retourne le groupe résultant."""
        with (
            self._connection.transaction(),
            self._connection.cursor() as cursor,
        ):
            author_pk, author_local_id, _ = self._resolve_author(cursor, author_id)
            alias_pk, _, _ = self._resolve_author(cursor, alias_id)
            if author_pk == alias_pk:
                raise InvalidAliasError(
                    f"un auteur ne peut pas être son propre alias : {author_id}"
                )
            entity_a = self._entity_of_author(cursor, author_pk)
            entity_b = self._entity_of_author(cursor, alias_pk)
            if entity_a is None or entity_a != entity_b:
                raise InvalidAliasError(
                    f"alias {alias_id} hors du groupe de {author_id}"
                )
            cursor.execute(
                "DELETE FROM author_entity_member"
                " WHERE entity_id = %s AND author_id = %s",
                (entity_a, alias_pk),
            )
            if len(self._members_of_entity(cursor, entity_a)) == 1:
                cursor.execute("DELETE FROM author_entity WHERE id = %s", (entity_a,))
            return self._alias_group_for(cursor, author_pk, author_local_id)

    def apply_author_name(
        self, author_id: str, request: ApplyNameRequest
    ) -> ApplyNameResult:
        """Correction en masse des graphies : les livres de author_id liés à
        l'auteur source sont repointés vers l'identité canonique cible, en une
        transaction. Le garde-fou regexp protège d'une re-synchronisation
        intempestive : request.match doit correspondre au nom ACTUEL de
        l'auteur (re.match), une regexp invalide levant InvalidApplyNameError.
        Cible par id : elle doit appartenir au groupe d'alias de l'auteur
        (sinon InvalidAliasError) ; cible par name : la ligne auteur est
        créée si besoin puis ajoutée au groupe (fusion si elle appartient à
        un autre groupe). Quand la cible re-canonise le groupe (display_author
        différent), author_entity.display_author_id est mis à jour vers elle.
        Les ids de livres inconnus sont signalés dans missing_ids (pas une
        erreur), les livres existants non liés à l'auteur dans skipped ; les
        autres auteurs de chaque livre ne sont jamais touchés. dry_run=True
        rejoue toute la validation et les écritures puis annule la
        transaction : la réponse est identique, sans écriture."""
        try:
            compiled = re.compile(request.match)
        except re.error as exc:
            raise InvalidApplyNameError(
                f"regexp invalide : {request.match!r} ({exc})"
            ) from None
        try:
            with (
                self._connection.transaction(),
                self._connection.cursor() as cursor,
            ):
                author_pk, _, author_name = self._resolve_author(cursor, author_id)
                if compiled.match(author_name) is None:
                    raise AuthorNameMismatchError(
                        f"match {request.match!r} ne correspond pas au nom actuel"
                        f" {author_name!r} de l'auteur {author_id}"
                    )
                if isinstance(request.target, NameTargetById):
                    target_pk, _, _ = self._resolve_author(
                        cursor, request.target.author_id
                    )
                elif isinstance(request.target, NameTargetByName):
                    target_pk = self._get_or_create_author_by_name(
                        cursor, request.target.name
                    )
                else:  # pragma: no cover - l'union NameTarget l'exclut
                    raise InvalidApplyNameError(
                        "target : fournir exactement une des formes author_id / name"
                    )
                if target_pk == author_pk:
                    raise InvalidApplyNameError(
                        f"target identique à l'auteur source : {author_id}"
                    )
                self._apply_target_to_group(
                    cursor,
                    author_pk,
                    target_pk,
                    target_must_be_in_group=isinstance(request.target, NameTargetById),
                )
                result = self._move_author_books(
                    cursor, author_pk, target_pk, request.book_ids
                )
                if request.dry_run:
                    raise _DryRunRollback
        except _DryRunRollback:
            pass  # dry_run : la transaction a déjà été annulée par le context manager
        return result

    def _get_or_create_author_by_name(self, cursor: psycopg.Cursor, name: str) -> int:
        """Auteur de la bibliothèque portant exactement ce nom, créé avec le
        prochain local_id libre sinon ; retourne l'id interne."""
        cursor.execute(
            "SELECT id FROM authors WHERE library_uuid = %s AND name = %s",
            (self._require_library_uuid(), name),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(row[0])
        cursor.execute(
            "SELECT COALESCE(MAX(local_id), 0) + 1 FROM authors"
            " WHERE library_uuid = %s",
            (self._require_library_uuid(),),
        )
        next_local_id = int(cast("tuple[int, ...]", cursor.fetchone())[0])
        cursor.execute(
            "INSERT INTO authors (library_uuid, local_id, name)"
            " VALUES (%s, %s, %s) RETURNING id",
            (self._require_library_uuid(), next_local_id, name),
        )
        return int(cast("tuple[int, ...]", cursor.fetchone())[0])

    def _apply_target_to_group(
        self,
        cursor: psycopg.Cursor,
        author_pk: int,
        target_pk: int,
        target_must_be_in_group: bool,
    ) -> None:
        """Fait entrer l'auteur cible dans le groupe de l'auteur source (dans
        la transaction ouverte par apply_author_name) et re-canonise le groupe
        sur elle : display_author_id devient target_pk dès qu'il diffère.

        target_must_be_in_group (cible par id) : la cible doit déjà appartenir
        au groupe de l'auteur, sinon InvalidAliasError ; cible par name : elle
        rejoint le groupe (créé si l'auteur source en est dépourvu), avec
        fusion des deux groupes si elle appartient déjà à un autre - mêmes
        mécaniques que add_author_alias."""
        entity_a = self._entity_of_author(cursor, author_pk)
        if target_must_be_in_group:
            if entity_a is None or target_pk not in {
                member_pk
                for member_pk, _, _ in self._members_of_entity(cursor, entity_a)
            }:
                raise InvalidAliasError(
                    "cible hors du groupe d'alias de l'auteur source"
                )
        else:
            entity_b = self._entity_of_author(cursor, target_pk)
            if entity_a is None and entity_b is None:
                # Ni l'auteur ni la cible n'ont de groupe : création d'un
                # groupe canonisé d'emblée sur la cible.
                entity_a = uuid.uuid4()
                cursor.execute(
                    "INSERT INTO author_entity (id, library_uuid,"
                    " display_author_id) VALUES (%s, %s, %s)",
                    (entity_a, self._require_library_uuid(), target_pk),
                )
                cursor.executemany(
                    "INSERT INTO author_entity_member (entity_id, author_id)"
                    " VALUES (%s, %s)",
                    [(entity_a, author_pk), (entity_a, target_pk)],
                )
            elif entity_a is None:
                # L'auteur source rejoint le groupe existant de la cible.
                cursor.execute(
                    "INSERT INTO author_entity_member (entity_id, author_id)"
                    " VALUES (%s, %s)",
                    (entity_b, author_pk),
                )
                entity_a = entity_b
            elif entity_b is None:
                # La cible rejoint le groupe existant de l'auteur source.
                cursor.execute(
                    "INSERT INTO author_entity_member (entity_id, author_id)"
                    " VALUES (%s, %s)",
                    (entity_a, target_pk),
                )
            elif entity_a != entity_b:
                # Fusion : les membres du groupe de la cible migrent vers
                # celui de l'auteur source, le second (vidé) est supprimé.
                cursor.execute(
                    "UPDATE author_entity_member SET entity_id = %s"
                    " WHERE entity_id = %s",
                    (entity_a, entity_b),
                )
                cursor.execute("DELETE FROM author_entity WHERE id = %s", (entity_b,))
        if entity_a is not None:
            cursor.execute(
                "SELECT display_author_id FROM author_entity WHERE id = %s",
                (entity_a,),
            )
            display = cast("tuple[object, ...]", cursor.fetchone())[0]
            if display is None or int(cast("int", display)) != target_pk:
                cursor.execute(
                    "UPDATE author_entity SET display_author_id = %s WHERE id = %s",
                    (target_pk, entity_a),
                )

    def _move_author_books(
        self,
        cursor: psycopg.Cursor,
        source_pk: int,
        target_pk: int,
        book_ids: tuple[str, ...],
    ) -> ApplyNameResult:
        """Repointe les livres de l'auteur source vers la cible (dans la
        transaction ouverte par apply_author_name) : suppression du lien
        source puis insertion du lien cible (ON CONFLICT DO NOTHING) - les
        autres auteurs de chaque livre ne sont jamais touchés. book_ids vide
        = tous les livres de l'auteur ; ids inconnus -> missing_ids, livres
        non liés à la source -> skipped."""
        if book_ids:
            deduped_ids, valid_ids = self._partition_ids(list(book_ids))
            book_pks: dict[str, int] = {}
            if valid_ids:
                placeholders = ", ".join("%s" for _ in valid_ids)
                cursor.execute(
                    "SELECT book_pk, local_id FROM books"
                    f" WHERE library_uuid = %s AND local_id IN ({placeholders})"
                    " ORDER BY local_id FOR UPDATE",
                    (self._require_library_uuid(), *(int(i) for i in valid_ids)),
                )
                book_pks = {str(row[1]): int(row[0]) for row in cursor.fetchall()}
            linked: list[str] = []
            for book_id in deduped_ids:
                if book_id not in book_pks:
                    continue
                cursor.execute(
                    "SELECT 1 FROM books_authors_link"
                    " WHERE book_pk = %s AND author_id = %s",
                    (book_pks[book_id], source_pk),
                )
                if cursor.fetchone() is not None:
                    linked.append(book_id)
            for book_id in linked:
                self._relink_book(cursor, book_pks[book_id], source_pk, target_pk)
            return ApplyNameResult(
                applied=tuple(linked),
                skipped=tuple(
                    book_id
                    for book_id in deduped_ids
                    if book_id in book_pks and book_id not in linked
                ),
                missing_ids=tuple(
                    book_id for book_id in deduped_ids if book_id not in book_pks
                ),
            )
        cursor.execute(
            "SELECT b.book_pk, b.local_id FROM books b"
            " JOIN books_authors_link l ON l.book_pk = b.book_pk"
            " WHERE b.library_uuid = %s AND l.author_id = %s"
            " ORDER BY b.local_id FOR UPDATE OF b",
            (self._require_library_uuid(), source_pk),
        )
        rows = cursor.fetchall()
        for book_pk, local_id in rows:
            self._relink_book(cursor, int(book_pk), source_pk, target_pk)
        return ApplyNameResult(
            applied=tuple(str(local_id) for _, local_id in rows),
            skipped=(),
            missing_ids=(),
        )

    def _relink_book(
        self,
        cursor: psycopg.Cursor,
        book_pk: int,
        source_pk: int,
        target_pk: int,
    ) -> None:
        cursor.execute(
            "DELETE FROM books_authors_link WHERE book_pk = %s AND author_id = %s",
            (book_pk, source_pk),
        )
        cursor.execute(
            "INSERT INTO books_authors_link (book_pk, author_id)"
            " VALUES (%s, %s) ON CONFLICT (book_pk, author_id) DO NOTHING",
            (book_pk, target_pk),
        )

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
        where = _query_books_where(query, params, self._require_library_uuid())
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
