import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
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

_LIST_BOOKS_QUERY_BODY = """
    SELECT
        books.id,
        books.title,
        GROUP_CONCAT(authors.name, ', ') AS authors,
        books.pubdate,
        publishers.id AS publisher_id,
        publishers.name AS publisher_name,
        series.id AS series_id,
        series.name AS series_name,
        books.series_index,
        ratings.rating AS rating_raw,
        books.has_cover
    FROM books
    LEFT JOIN books_authors_link ON books_authors_link.book = books.id
    LEFT JOIN authors ON authors.id = books_authors_link.author
    LEFT JOIN books_publishers_link ON books_publishers_link.book = books.id
    LEFT JOIN publishers ON publishers.id = books_publishers_link.publisher
    LEFT JOIN books_series_link ON books_series_link.book = books.id
    LEFT JOIN series ON series.id = books_series_link.series
    LEFT JOIN books_ratings_link ON books_ratings_link.book = books.id
    LEFT JOIN ratings ON ratings.id = books_ratings_link.rating
"""

_LIST_BOOKS_QUERY = (
    _LIST_BOOKS_QUERY_BODY + "    GROUP BY books.id\n    ORDER BY books.title\n"
)

_LIST_AUTHORS_QUERY = "SELECT id, name FROM authors ORDER BY name"

_LIST_PUBLISHERS_QUERY = "SELECT id, name FROM publishers ORDER BY name"

_LIST_SERIES_QUERY = "SELECT id, name FROM series ORDER BY name"

# Authors and tags are aggregated via correlated subqueries, not a direct LEFT JOIN,
# because joining two many-to-many link tables into the same query would fan out rows
# - a book with 2 authors and 3 tags would produce 6 joined rows before any
# GROUP_CONCAT. A scalar subquery per book avoids that. Publisher and series stay
# plain LEFT JOINs because this project already treats them as at-most-one-per-book,
# same as list_publishers.
_GET_BOOK_DETAILS_QUERY_TEMPLATE = """
    SELECT
        books.id,
        books.title,
        books.pubdate,
        books.series_index,
        (
            SELECT GROUP_CONCAT(authors.name, ', ')
            FROM books_authors_link
            JOIN authors ON authors.id = books_authors_link.author
            WHERE books_authors_link.book = books.id
        ) AS authors,
        (
            SELECT GROUP_CONCAT(tags.name, ', ')
            FROM books_tags_link
            JOIN tags ON tags.id = books_tags_link.tag
            WHERE books_tags_link.book = books.id
        ) AS tags,
        publishers.id,
        publishers.name,
        series.id,
        series.name,
        books.path,
        books.has_cover
    FROM books
    LEFT JOIN books_publishers_link ON books_publishers_link.book = books.id
    LEFT JOIN publishers ON publishers.id = books_publishers_link.publisher
    LEFT JOIN books_series_link ON books_series_link.book = books.id
    LEFT JOIN series ON series.id = books_series_link.series
    WHERE books.id IN ({placeholders})
"""

# Calibre stores "no publication date" as a sentinel timestamp (year 101,
# calibre.utils.date.UNDEFINED_DATE) rather than SQL NULL.
_UNDEFINED_PUBDATE_PREFIX = "0101-01-01"

_VALID_ID_PATTERN = re.compile(r"^[1-9]\d*$")

_SESSION_TIMEOUT_SECONDS = 60
_PAGE_COUNT_CAP = 100  # in pages; the row cap is _PAGE_COUNT_CAP * page_size

_LIST_BOOKS_QUERY_FROM_OFFSET = _LIST_BOOKS_QUERY + "\n    LIMIT -1 OFFSET ?"
_LIST_BOOKS_COUNT_QUERY = "SELECT books.id FROM books"

_LIST_AUTHORS_QUERY_FROM_OFFSET = _LIST_AUTHORS_QUERY + " LIMIT -1 OFFSET ?"
_LIST_AUTHORS_COUNT_QUERY = "SELECT id FROM authors"

_LIST_PUBLISHERS_QUERY_FROM_OFFSET = _LIST_PUBLISHERS_QUERY + " LIMIT -1 OFFSET ?"
_LIST_PUBLISHERS_COUNT_QUERY = "SELECT id FROM publishers"

_LIST_SERIES_QUERY_FROM_OFFSET = _LIST_SERIES_QUERY + " LIMIT -1 OFFSET ?"
_LIST_SERIES_COUNT_QUERY = "SELECT id FROM series"

# Sort keys for query_books_page, expressed against _LIST_BOOKS_QUERY_BODY's
# selected columns/aliases (publisher_name/series_name/rating_raw are aliases,
# which SQLite resolves in ORDER BY).
_SORT_EXPRESSIONS = {
    BookSort.TITLE: "books.title",
    BookSort.PUBDATE: "books.pubdate",
    BookSort.PUBLISHER: "publisher_name",
    BookSort.SERIES: "series_name",
    BookSort.SERIES_INDEX: "books.series_index",
    BookSort.RATING: "rating_raw",
    BookSort.AUTHOR: "books.author_sort",
}

# books_<entity>_link table's column pointing at the entity's id.
_ENTITY_LINK_COLUMNS = {
    "authors": "author",
    "publishers": "publisher",
    "series": "series",
}

# Facet queries for list_field_values: one per whitelisted field, each returning
# (value, count) ordered by count DESC then value. Column names are qualified -
# languages joins books_languages_link (both sides have a lang_code column) and
# ratings joins books_ratings_link, so unqualified names would be ambiguous.
_FACET_QUERIES: dict[str, str] = {
    "tags": (
        "SELECT tags.name, count(*) FROM tags"
        " JOIN books_tags_link ON tag = tags.id"
        " GROUP BY tags.name ORDER BY count(*) DESC, tags.name"
    ),
    "languages": (
        "SELECT languages.lang_code, count(*) FROM languages"
        " JOIN books_languages_link ON books_languages_link.lang_code = languages.id"
        " GROUP BY languages.lang_code ORDER BY count(*) DESC, languages.lang_code"
    ),
    "formats": (
        "SELECT data.format, count(*) FROM data"
        " WHERE data.format IS NOT NULL"
        " GROUP BY data.format ORDER BY count(*) DESC, data.format"
    ),
    # Star rating = raw//2; raw 0 means "no rating" in Calibre, hence the > 0
    # guard. Grouping by the derived star value merges raw 3 and raw 4 (both
    # 1 star) into a single facet entry.
    "ratings": (
        "SELECT ratings.rating / 2, count(*) FROM ratings"
        " JOIN books_ratings_link ON books_ratings_link.rating = ratings.id"
        " WHERE ratings.rating > 0"
        " GROUP BY ratings.rating / 2 ORDER BY count(*) DESC, ratings.rating / 2"
    ),
}


def _query_books_where(query: BookQuery, params: list) -> str:
    """Build the WHERE clause filtering books from a BookQuery.

    Every clause is self-contained: it carries its own IN (SELECT ... FROM
    <link table> ...) with the joins it needs, so the clause can be applied
    to a bare "FROM books" (no display joins required). Keys combine with
    AND, values within a key with OR. Star ratings (1-5) are converted to
    Calibre's 0-10 scale (x2) inside the SQL placeholders.
    """
    clauses = []
    if query.author_ids:
        placeholders = ",".join("?" * len(query.author_ids))
        clauses.append(
            "books.id IN (SELECT book FROM books_authors_link"
            f" WHERE author IN ({placeholders}))"
        )
        params.extend(int(author_id) for author_id in query.author_ids)
    if query.publisher_ids:
        placeholders = ",".join("?" * len(query.publisher_ids))
        clauses.append(
            "books.id IN (SELECT book FROM books_publishers_link"
            f" WHERE publisher IN ({placeholders}))"
        )
        params.extend(int(publisher_id) for publisher_id in query.publisher_ids)
    if query.series_ids:
        placeholders = ",".join("?" * len(query.series_ids))
        clauses.append(
            "books.id IN (SELECT book FROM books_series_link"
            f" WHERE series IN ({placeholders}))"
        )
        params.extend(int(series_id) for series_id in query.series_ids)
    if query.tags:
        placeholders = ",".join("?" * len(query.tags))
        clauses.append(
            "books.id IN (SELECT book FROM books_tags_link"
            " JOIN tags ON tags.id = tag"
            f" WHERE tags.name IN ({placeholders}))"
        )
        params.extend(query.tags)
    if query.languages:
        placeholders = ",".join("?" * len(query.languages))
        clauses.append(
            "books.id IN (SELECT book FROM books_languages_link"
            " JOIN languages ON languages.id = books_languages_link.lang_code"
            f" WHERE languages.lang_code IN ({placeholders}))"
        )
        params.extend(query.languages)
    if query.formats:
        placeholders = ",".join("?" * len(query.formats))
        clauses.append(
            f"books.id IN (SELECT book FROM data WHERE format IN ({placeholders}))"
        )
        params.extend(format_.upper() for format_ in query.formats)
    if query.ratings:
        placeholders = ",".join("?" * len(query.ratings))
        clauses.append(
            "books.id IN (SELECT book FROM books_ratings_link"
            " JOIN ratings ON ratings.id = books_ratings_link.rating"
            f" WHERE ratings.rating IN ({placeholders}))"
        )
        params.extend(rating * 2 for rating in query.ratings)  # 1..5 -> 0..10
    if query.pubdate_years:
        year_clauses = []
        for year in query.pubdate_years:
            year_clauses.append("CAST(substr(books.pubdate, 1, 4) AS INTEGER) = ?")
            params.append(year)
        clauses.append("(" + " OR ".join(year_clauses) + ")")
    return (" WHERE " + " AND ".join(clauses)) if clauses else ""


@dataclass
class _PaginationSession:
    resource: str
    page_size: int
    next_page: int
    cursor: sqlite3.Cursor
    last_access: float
    # The SQL and its parameters behind the cursor, so a query-backed session
    # can be replayed at an OFFSET after expiry instead of being lost.
    query_sql: str | None = None
    query_params: tuple = ()


class SqliteLibraryGateway:
    def __init__(self, library_path: Path) -> None:
        self._db_path = (
            library_path / "metadata.db" if library_path.is_dir() else library_path
        )
        self._connection: sqlite3.Connection | None = None
        self._sessions: dict[str, _PaginationSession] = {}

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            if not self._db_path.exists():
                raise LibraryNotFoundError(
                    f"Calibre library not found: {self._db_path}"
                )
            connection = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            self._check_is_calibre_library(connection)
            self._connection = connection
        return self._connection

    def list_books(self) -> list[Book]:
        connection = self._connect()
        rows = connection.execute(_LIST_BOOKS_QUERY).fetchall()

        return [self._book_from_row(row) for row in rows]

    @staticmethod
    def _book_from_row(row: tuple[object, ...]) -> Book:
        # Row layout (see _LIST_BOOKS_QUERY): id, title, authors, pubdate,
        # publisher_id, publisher_name, series_id, series_name, series_index,
        # rating_raw, has_cover.
        rating_raw = cast("int | None", row[9])
        rating = (rating_raw // 2 or None) if rating_raw is not None else None
        return Book(
            id=str(row[0]),
            title=row[1],  # type: ignore[arg-type]
            authors=tuple(row[2].split(", ")) if row[2] else (),  # type: ignore[attr-defined]
            pubdate=SqliteLibraryGateway._normalize_pubdate(row[3]),  # type: ignore[arg-type]
            publisher=(
                Publisher(id=str(row[4]), name=row[5])  # type: ignore[arg-type]
                if row[4] is not None
                else None
            ),
            series=(
                Series(id=str(row[6]), name=row[7])  # type: ignore[arg-type]
                if row[6] is not None
                else None
            ),
            series_index=str(row[8]) if row[8] is not None else None,
            rating=rating,
            has_cover=bool(row[10]),
        )

    def list_authors(self) -> list[Author]:
        connection = self._connect()
        rows = connection.execute(_LIST_AUTHORS_QUERY).fetchall()

        return [Author(id=str(row[0]), name=row[1]) for row in rows]

    def list_publishers(self) -> list[Publisher]:
        connection = self._connect()
        rows = connection.execute(_LIST_PUBLISHERS_QUERY).fetchall()

        return [Publisher(id=str(row[0]), name=row[1]) for row in rows]

    def list_series(self) -> list[Series]:
        connection = self._connect()
        rows = connection.execute(_LIST_SERIES_QUERY).fetchall()

        return [Series(id=str(row[0]), name=row[1]) for row in rows]

    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        deduped_ids, valid_ids = self._partition_ids(ids)

        connection = self._connect()
        placeholders = ", ".join("?" for _ in valid_ids)
        query = _GET_BOOK_DETAILS_QUERY_TEMPLATE.format(placeholders=placeholders)
        rows = connection.execute(query, valid_ids).fetchall()

        books = []
        found_ids: set[str] = set()
        library_root = self._db_path.parent
        for row in rows:
            book_id = str(row[0])
            found_ids.add(book_id)
            cover_path = self._compute_cover_path(library_root, row[10], row[11])
            books.append(
                BookDetails(
                    id=book_id,
                    title=row[1],
                    pubdate=self._normalize_pubdate(row[2]),
                    authors=tuple(row[4].split(", ")) if row[4] else (),
                    tags=tuple(row[5].split(", ")) if row[5] else (),
                    publisher=(
                        Publisher(id=str(row[6]), name=row[7])
                        if row[6] is not None
                        else None
                    ),
                    series=(
                        SeriesItem(
                            series=Series(id=str(row[8]), name=row[9]),
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
        connection = self._connect()
        rows, result_handle = self._fetch_page(
            connection, "books", page, page_size, handle, _LIST_BOOKS_QUERY_FROM_OFFSET
        )
        total_pages, has_more = self._bounded_total_pages(
            connection, _LIST_BOOKS_COUNT_QUERY, page_size
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
        connection = self._connect()
        rows, result_handle = self._fetch_page(
            connection,
            "authors",
            page,
            page_size,
            handle,
            _LIST_AUTHORS_QUERY_FROM_OFFSET,
        )
        total_pages, has_more = self._bounded_total_pages(
            connection, _LIST_AUTHORS_COUNT_QUERY, page_size
        )
        authors = tuple(
            Author(id=str(row[0]), name=row[1])  # type: ignore[arg-type]
            for row in rows
        )
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
        connection = self._connect()
        rows, result_handle = self._fetch_page(
            connection,
            "publishers",
            page,
            page_size,
            handle,
            _LIST_PUBLISHERS_QUERY_FROM_OFFSET,
        )
        total_pages, has_more = self._bounded_total_pages(
            connection, _LIST_PUBLISHERS_COUNT_QUERY, page_size
        )
        publishers = tuple(
            Publisher(id=str(row[0]), name=row[1])  # type: ignore[arg-type]
            for row in rows
        )
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
        connection = self._connect()
        rows, result_handle = self._fetch_page(
            connection,
            "series",
            page,
            page_size,
            handle,
            _LIST_SERIES_QUERY_FROM_OFFSET,
        )
        total_pages, has_more = self._bounded_total_pages(
            connection, _LIST_SERIES_COUNT_QUERY, page_size
        )
        series = tuple(
            Series(id=str(row[0]), name=row[1])  # type: ignore[arg-type]
            for row in rows
        )
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
        connection = self._connect()
        params: list = []
        where = _query_books_where(query, params)
        direction = " DESC" if query.order is SortOrder.DESC else ""
        order_by = _SORT_EXPRESSIONS[query.sort] + direction
        page_sql = (
            _LIST_BOOKS_QUERY_BODY
            + where
            + "\n    GROUP BY books.id\n    ORDER BY "
            + order_by
            + "\n    LIMIT -1 OFFSET ?"
        )
        count_sql = "SELECT books.id FROM books" + where
        rows, result_handle = self._fetch_page(
            connection, "query_books", page, page_size, handle, page_sql, tuple(params)
        )
        total_pages, has_more = self._bounded_total_pages(
            connection, count_sql, page_size, tuple(params)
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
        authors = tuple(
            Author(id=str(row[0]), name=row[1])  # type: ignore[arg-type]
            for row in rows
        )
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
        publishers = tuple(
            Publisher(id=str(row[0]), name=row[1])  # type: ignore[arg-type]
            for row in rows
        )
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
        series = tuple(
            Series(id=str(row[0]), name=row[1])  # type: ignore[arg-type]
            for row in rows
        )
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
        connection = self._connect()
        rows = connection.execute(_FACET_QUERIES[field]).fetchall()

        return [FieldValue(value=str(row[0]), count=row[1]) for row in rows]

    def _query_entity_page(
        self,
        entity: str,
        resource: str,
        query: BookQuery,
        page: int,
        page_size: int,
        handle: str | None,
    ) -> tuple[list[tuple[object, ...]], str | None, int | None, bool]:
        """Page the entities participating in the books matched by query.

        Each WHERE clause built by _query_books_where is self-contained (its
        own IN-subquery with joins), so it applies to a bare "FROM books"
        inside the entity IN (...) subquery - no display joins needed. The
        entity's link table bridges book ids back to entity ids.
        """
        connection = self._connect()
        params: list = []
        where = _query_books_where(query, params)
        filtered_books = f"SELECT books.id FROM books{where}"
        link_column = _ENTITY_LINK_COLUMNS[entity]
        entity_ids = (
            f"SELECT {link_column} FROM books_{entity}_link"
            f" WHERE book IN ({filtered_books})"
        )
        page_sql = (
            f"SELECT DISTINCT {entity}.id, {entity}.name FROM {entity}"
            f" WHERE {entity}.id IN ({entity_ids})"
            f" ORDER BY {entity}.name LIMIT -1 OFFSET ?"
        )
        count_sql = (
            f"SELECT {entity}.id FROM {entity} WHERE {entity}.id IN ({entity_ids})"
        )
        rows, result_handle = self._fetch_page(
            connection, resource, page, page_size, handle, page_sql, tuple(params)
        )
        total_pages, has_more = self._bounded_total_pages(
            connection, count_sql, page_size, tuple(params)
        )
        return rows, result_handle, total_pages, has_more

    def close_pagination(self, handle: str) -> None:
        session = self._sessions.pop(handle, None)
        if session is not None:
            session.cursor.close()

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
            self._sessions.pop(handle).cursor.close()

    def _fetch_page(
        self,
        connection: sqlite3.Connection,
        resource: str,
        page: int,
        page_size: int,
        handle: str | None,
        query_from_offset: str,
        query_params: tuple = (),
    ) -> tuple[list[tuple[object, ...]], str | None]:
        self._prune_expired_sessions()

        session = self._sessions.get(handle) if handle is not None else None
        reusable = (
            session is not None
            and session.resource == resource
            and session.page_size == page_size
            and session.next_page == page
        )
        if reusable and session is not None and handle is not None:
            rows = session.cursor.fetchmany(page_size)
            session.next_page += 1
            session.last_access = self._now()
            result_handle: str | None = handle
        else:
            # A known handle for the *same* resource/page_size that just isn't the
            # session's next page (a repeat, a backward jump) is superseded, not
            # merely unrelated - close it now rather than waiting out the timeout.
            # A handle that mismatches on resource or page_size might still be a
            # different, still-wanted session under its own handle - leave it for
            # the timeout instead of closing it as a side effect of this call.
            if (
                session is not None
                and handle is not None
                and session.resource == resource
                and session.page_size == page_size
            ):
                self._sessions.pop(handle, None)
                session.cursor.close()

            offset = (page - 1) * page_size
            cursor = connection.execute(query_from_offset, (*query_params, offset))
            rows = cursor.fetchmany(page_size)
            session = _PaginationSession(
                resource=resource,
                page_size=page_size,
                next_page=page + 1,
                cursor=cursor,
                last_access=self._now(),
                query_sql=query_from_offset,
                query_params=query_params,
            )
            result_handle = str(uuid.uuid4())
            self._sessions[result_handle] = session

        if len(rows) < page_size:
            self._sessions.pop(result_handle, None)  # type: ignore[arg-type]
            session.cursor.close()
            result_handle = None

        return rows, result_handle

    def _bounded_total_pages(
        self,
        connection: sqlite3.Connection,
        count_query: str,
        page_size: int,
        count_params: tuple = (),
    ) -> tuple[int | None, bool]:
        row_cap = _PAGE_COUNT_CAP * page_size + 1
        count = connection.execute(
            f"SELECT COUNT(*) FROM ({count_query} LIMIT ?)", (*count_params, row_cap)
        ).fetchone()[0]
        if count > _PAGE_COUNT_CAP * page_size:
            return None, True
        total_pages = -(-count // page_size) if count else 0
        return total_pages, False

    @staticmethod
    def _compute_cover_path(
        library_root: Path, book_path: str | None, has_cover: int | None
    ) -> str | None:
        if not has_cover or not book_path:
            return None
        return str(library_root / book_path.rstrip("/") / "cover.jpg")

    @staticmethod
    def _partition_ids(raw_ids: list[str]) -> tuple[list[str], list[str]]:
        """Dedupe (first-seen order, empty segments dropped); split into
        (deduped_ids, valid_ids) using this backend's id format. deduped_ids
        holds every distinct requested id in original order (valid and
        invalid mixed); valid_ids is the subset safe to place in a SQL
        IN (...) clause, in the same relative order."""
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

    @staticmethod
    def _normalize_pubdate(pubdate: str | None) -> str | None:
        if pubdate is not None and pubdate.startswith(_UNDEFINED_PUBDATE_PREFIX):
            return None
        return pubdate

    def _check_is_calibre_library(self, connection: sqlite3.Connection) -> None:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='books'"
        ).fetchone()
        if table is None:
            raise NotACalibreLibraryError(f"Not a Calibre library: {self._db_path}")
