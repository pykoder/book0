import re
import secrets
import sqlite3
import time
from collections.abc import Callable, Generator
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
    PagedPublishersResult,
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

_COUNT_BOOKS_QUERY = "SELECT COUNT(*) FROM (SELECT id FROM books LIMIT ?)"
_COUNT_AUTHORS_QUERY = "SELECT COUNT(*) FROM (SELECT id FROM authors LIMIT ?)"
_COUNT_PUBLISHERS_QUERY = "SELECT COUNT(*) FROM (SELECT id FROM publishers LIMIT ?)"

_DEFAULT_MAX_COUNTED_PAGES = 100
_SESSION_TIMEOUT_SECONDS = 60.0


@dataclass
class _PaginationSession:
    resource: str
    page_size: int
    expected_next_page: int
    rows_generator: Generator[list[tuple[object, ...]], None, None]
    last_access: float


class SqliteLibraryGateway:
    def __init__(
        self,
        library_path: Path,
        *,
        max_counted_pages: int = _DEFAULT_MAX_COUNTED_PAGES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db_path = (
            library_path / "metadata.db" if library_path.is_dir() else library_path
        )
        self._connection: sqlite3.Connection | None = None
        self._max_counted_pages = max_counted_pages
        self._clock = clock
        self._sessions: dict[str, _PaginationSession] = {}

    def _connect(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise LibraryNotFoundError(f"Calibre library not found: {self._db_path}")
        if self._connection is None:
            self._connection = sqlite3.connect(
                f"file:{self._db_path}?mode=ro", uri=True
            )
            self._check_is_calibre_library(self._connection)
        return self._connection

    def list_books(self) -> list[Book]:
        connection = self._connect()
        rows = connection.execute(_LIST_BOOKS_QUERY).fetchall()
        return [self._row_to_book(row) for row in rows]

    def _row_to_book(self, row: tuple[object, ...]) -> Book:
        return Book(
            id=str(row[0]),
            title=row[1],  # type: ignore[arg-type]
            authors=tuple(row[2].split(", ")) if row[2] else (),  # type: ignore[attr-defined]
            pubdate=self._normalize_pubdate(row[3]),  # type: ignore[arg-type]
        )

    def list_authors(self) -> list[Author]:
        connection = self._connect()
        rows = connection.execute(_LIST_AUTHORS_QUERY).fetchall()
        return [Author(id=str(row[0]), name=row[1]) for row in rows]

    def list_publishers(self) -> list[Publisher]:
        connection = self._connect()
        rows = connection.execute(_LIST_PUBLISHERS_QUERY).fetchall()
        return [Publisher(id=str(row[0]), name=row[1]) for row in rows]

    def list_books_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult:
        rows, out_handle, total_pages, has_more = self._paged_rows(
            resource="books",
            query=_LIST_BOOKS_QUERY,
            count_query=_COUNT_BOOKS_QUERY,
            page=page,
            page_size=page_size,
            handle=handle,
        )
        return PagedBooksResult(
            items=tuple(self._row_to_book(row) for row in rows),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=out_handle,
        )

    def list_authors_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult:
        rows, out_handle, total_pages, has_more = self._paged_rows(
            resource="authors",
            query=_LIST_AUTHORS_QUERY,
            count_query=_COUNT_AUTHORS_QUERY,
            page=page,
            page_size=page_size,
            handle=handle,
        )
        return PagedAuthorsResult(
            items=tuple(
                Author(id=str(row[0]), name=row[1])  # type: ignore[arg-type]
                for row in rows
            ),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=out_handle,
        )

    def list_publishers_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult:
        rows, out_handle, total_pages, has_more = self._paged_rows(
            resource="publishers",
            query=_LIST_PUBLISHERS_QUERY,
            count_query=_COUNT_PUBLISHERS_QUERY,
            page=page,
            page_size=page_size,
            handle=handle,
        )
        return PagedPublishersResult(
            items=tuple(
                Publisher(id=str(row[0]), name=row[1])  # type: ignore[arg-type]
                for row in rows
            ),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=out_handle,
        )

    def close_pagination(self, handle: str) -> None:
        session = self._sessions.pop(handle, None)
        if session is not None:
            session.rows_generator.close()

    def _paged_rows(
        self,
        *,
        resource: str,
        query: str,
        count_query: str,
        page: int,
        page_size: int,
        handle: str | None,
    ) -> tuple[list[tuple[object, ...]], str | None, int | None, bool]:
        connection = self._connect()
        self._expire_stale_sessions()

        session = self._sessions.get(handle) if handle is not None else None
        if (
            session is not None
            and session.resource == resource
            and session.page_size == page_size
            and session.expected_next_page == page
        ):
            assert handle is not None  # the session lookup above guarantees this
            rows = next(session.rows_generator)
            session.expected_next_page += 1
            session.last_access = self._clock()
            active_handle = handle
        else:
            generator = self._paged_rows_generator(connection, query, page_size, page)
            rows = next(generator)
            active_handle = secrets.token_hex(16)
            self._sessions[active_handle] = _PaginationSession(
                resource=resource,
                page_size=page_size,
                expected_next_page=page + 1,
                rows_generator=generator,
                last_access=self._clock(),
            )

        total_pages, has_more = self._count_pages(connection, count_query, page_size)
        out_handle: str | None = active_handle
        if total_pages is not None and page >= total_pages:
            out_handle = None
        if out_handle is None:
            self.close_pagination(active_handle)
        return rows, out_handle, total_pages, has_more

    @staticmethod
    def _paged_rows_generator(
        connection: sqlite3.Connection, query: str, page_size: int, start_page: int
    ) -> Generator[list[tuple[object, ...]], None, None]:
        # First page: one bounded LIMIT/OFFSET query, seeked directly to start_page -
        # no more expensive than today's unpaginated query, just bounded. The first
        # continuation (i.e. the caller reusing this generator's handle for page
        # start_page + 1) costs one more query: opening the live, unbounded-from-here
        # cursor via LIMIT -1 OFFSET ?. That cursor is opened lazily - only once the
        # caller actually continues past the first page, not on every fresh fetch.
        # Every continuation after that (second-and-later reuse of the same handle)
        # is then truly free: it pulls the next slice straight off that already-open
        # cursor via fetchmany, with no new SELECT at all.
        offset = (start_page - 1) * page_size
        first_rows = connection.execute(
            f"{query} LIMIT ? OFFSET ?", (page_size, offset)
        ).fetchall()
        yield first_rows

        cursor = connection.execute(f"{query} LIMIT -1 OFFSET ?", (offset + page_size,))
        try:
            while True:
                yield cursor.fetchmany(page_size)
        finally:
            # Runs both when the generator is explicitly .close()'d (close_pagination,
            # session expiry) and if it's simply garbage-collected without being
            # closed - either way, don't leave a live cursor open on the shared
            # connection past the session's lifetime.
            cursor.close()

    def _count_pages(
        self, connection: sqlite3.Connection, count_query: str, page_size: int
    ) -> tuple[int | None, bool]:
        cap = self._max_counted_pages * page_size
        count = connection.execute(count_query, (cap,)).fetchone()[0]
        if count >= cap:
            return None, True
        return -(-count // page_size), False

    def _expire_stale_sessions(self) -> None:
        now = self._clock()
        expired = [
            handle
            for handle, session in self._sessions.items()
            if now - session.last_access > _SESSION_TIMEOUT_SECONDS
        ]
        for handle in expired:
            self._sessions.pop(handle).rows_generator.close()

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
