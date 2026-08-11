import sqlite3
from pathlib import Path

import pytest

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.sqlite_gateway import SqliteLibraryGateway
from tests.conftest import CALIBRE_LIBRARY_BOOKS


def test_list_books_returns_books_sorted_by_title_with_authors_and_pubdate(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS


def test_list_books_opens_the_database_read_only(
    calibre_metadata_db: Path, monkeypatch: pytest.MonkeyPatch
):
    real_connect = sqlite3.connect
    captured_calls: list[tuple[str, bool]] = []

    def spying_connect(
        database: str, *args: object, **kwargs: object
    ) -> sqlite3.Connection:
        captured_calls.append((str(database), bool(kwargs.get("uri", False))))
        return real_connect(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlite3, "connect", spying_connect)
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    gateway.list_books()

    assert captured_calls == [(f"file:{calibre_metadata_db}?mode=ro", True)]


def test_calibre_undefined_pubdate_sentinel_is_reported_as_none(tmp_path: Path):
    # Calibre stores "no publication date" as a sentinel timestamp (year 101,
    # calibre.utils.date.UNDEFINED_DATE) rather than SQL NULL.
    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                pubdate TEXT
            );
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                author INTEGER NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO books (id, title, pubdate) VALUES (?, ?, ?)",
            (1, "Mystery Book", "0101-01-01T00:00:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()
    gateway = SqliteLibraryGateway(db_path)

    books = gateway.list_books()

    assert books[0].pubdate is None


def test_missing_file_raises_library_not_found_error(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_books()


def test_non_calibre_sqlite_file_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    gateway = SqliteLibraryGateway(db_path)

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_books()
