import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    PagedAuthorsResult,
    PagedBooksResult,
    Publisher,
    Series,
    SeriesItem,
)

_LIST_BOOKS_QUERY = """
    SELECT
        books.id,
        books.title,
        GROUP_CONCAT(authors.name, ', ') AS authors,
        books.pubdate
    FROM books
    LEFT JOIN books_authors_link ON books_authors_link.book = books.id
    LEFT JOIN authors ON authors.id = books_authors_link.author
    GROUP BY books.id
    ORDER BY books.title
"""

_LIST_AUTHORS_QUERY = "SELECT id, name FROM authors ORDER BY name"

_LIST_PUBLISHERS_QUERY = "SELECT id, name FROM publishers ORDER BY name"

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


@dataclass
class _PaginationSession:
    resource: str
    page_size: int
    next_page: int
    cursor: sqlite3.Cursor
    last_access: float


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

        return [
            Book(
                id=str(row[0]),
                title=row[1],
                authors=tuple(row[2].split(", ")) if row[2] else (),
                pubdate=self._normalize_pubdate(row[3]),
            )
            for row in rows
        ]

    def list_authors(self) -> list[Author]:
        connection = self._connect()
        rows = connection.execute(_LIST_AUTHORS_QUERY).fetchall()

        return [Author(id=str(row[0]), name=row[1]) for row in rows]

    def list_publishers(self) -> list[Publisher]:
        connection = self._connect()
        rows = connection.execute(_LIST_PUBLISHERS_QUERY).fetchall()

        return [Publisher(id=str(row[0]), name=row[1]) for row in rows]

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
        books = tuple(
            Book(
                id=str(row[0]),
                title=row[1],  # type: ignore[arg-type]
                authors=tuple(row[2].split(", ")) if row[2] else (),  # type: ignore[attr-defined]
                pubdate=self._normalize_pubdate(row[3]),  # type: ignore[arg-type]
            )
            for row in rows
        )
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
            cursor = connection.execute(query_from_offset, (offset,))
            rows = cursor.fetchmany(page_size)
            session = _PaginationSession(
                resource=resource,
                page_size=page_size,
                next_page=page + 1,
                cursor=cursor,
                last_access=self._now(),
            )
            result_handle = str(uuid.uuid4())
            self._sessions[result_handle] = session

        if len(rows) < page_size:
            self._sessions.pop(result_handle, None)  # type: ignore[arg-type]
            session.cursor.close()
            result_handle = None

        return rows, result_handle

    def _bounded_total_pages(
        self, connection: sqlite3.Connection, count_query: str, page_size: int
    ) -> tuple[int | None, bool]:
        row_cap = _PAGE_COUNT_CAP * page_size + 1
        count = connection.execute(
            f"SELECT COUNT(*) FROM ({count_query} LIMIT ?)", (row_cap,)
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
