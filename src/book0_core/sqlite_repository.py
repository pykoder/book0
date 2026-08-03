import sqlite3
from pathlib import Path

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.models import Book

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


class SqliteBookRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def list_books(self) -> list[Book]:
        if not self._db_path.exists():
            raise LibraryNotFoundError(f"Calibre library not found: {self._db_path}")

        connection = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            self._check_is_calibre_library(connection)
            rows = connection.execute(_LIST_BOOKS_QUERY).fetchall()
        finally:
            connection.close()

        return [
            Book(
                id=row[0],
                title=row[1],
                authors=tuple(row[2].split(", ")) if row[2] else (),
                pubdate=row[3],
            )
            for row in rows
        ]

    def _check_is_calibre_library(self, connection: sqlite3.Connection) -> None:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='books'"
        ).fetchone()
        if table is None:
            raise NotACalibreLibraryError(f"Not a Calibre library: {self._db_path}")
