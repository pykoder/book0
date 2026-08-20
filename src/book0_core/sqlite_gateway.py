import re
import sqlite3
from pathlib import Path

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
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


class SqliteLibraryGateway:
    def __init__(self, library_path: Path) -> None:
        self._db_path = (
            library_path / "metadata.db" if library_path.is_dir() else library_path
        )
        self._connection: sqlite3.Connection | None = None

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
