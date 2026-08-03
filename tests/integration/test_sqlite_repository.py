import sqlite3
from pathlib import Path

import pytest

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.sqlite_repository import SqliteBookRepository
from tests.conftest import CALIBRE_LIBRARY_BOOKS


def test_list_books_returns_books_sorted_by_title_with_authors_and_pubdate(
    calibre_metadata_db: Path,
):
    repository = SqliteBookRepository(calibre_metadata_db)

    assert repository.list_books() == CALIBRE_LIBRARY_BOOKS


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
    repository = SqliteBookRepository(calibre_metadata_db)

    repository.list_books()

    assert captured_calls == [(f"file:{calibre_metadata_db}?mode=ro", True)]


def test_missing_file_raises_library_not_found_error(tmp_path: Path):
    repository = SqliteBookRepository(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        repository.list_books()


def test_non_calibre_sqlite_file_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    repository = SqliteBookRepository(db_path)

    with pytest.raises(NotACalibreLibraryError):
        repository.list_books()
