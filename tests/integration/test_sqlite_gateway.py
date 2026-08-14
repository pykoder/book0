import sqlite3
from pathlib import Path

import pytest

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.gateway import LibraryGateway
from book0_core.sqlite_gateway import SqliteLibraryGateway
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    DUNE_DETAILS,
    GOOD_OMENS_DETAILS,
    HOBBIT_DETAILS,
)


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


def test_list_books_resolves_metadata_db_when_given_a_directory(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db.parent)

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS


def test_list_authors_returns_authors_sorted_by_name(calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    assert gateway.list_authors() == CALIBRE_LIBRARY_AUTHORS


def test_list_authors_opens_the_database_read_only(
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

    gateway.list_authors()

    assert captured_calls == [(f"file:{calibre_metadata_db}?mode=ro", True)]


def test_missing_file_raises_library_not_found_error_for_authors(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_authors()


def test_non_calibre_sqlite_file_raises_not_a_calibre_library_error_for_authors(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    gateway = SqliteLibraryGateway(db_path)

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_authors()


def test_list_publishers_returns_publishers_sorted_by_name(calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_list_publishers_opens_the_database_read_only(
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

    gateway.list_publishers()

    assert captured_calls == [(f"file:{calibre_metadata_db}?mode=ro", True)]


def test_list_publishers_resolves_metadata_db_when_given_a_directory(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db.parent)

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_missing_file_raises_library_not_found_error_for_publishers(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_publishers()


def test_non_calibre_sqlite_file_raises_not_a_calibre_library_error_for_publishers(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    gateway = SqliteLibraryGateway(db_path)

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_publishers()


def test_sqlite_gateway_satisfies_the_library_gateway_protocol(
    calibre_metadata_db: Path,
):
    gateway: LibraryGateway = SqliteLibraryGateway(calibre_metadata_db)

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_get_book_details_returns_details_for_a_book_with_everything(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1"])

    assert result.books == (DUNE_DETAILS,)
    assert result.missing_ids == ()


def test_get_book_details_returns_details_for_a_book_with_nothing_linked(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["2"])

    assert result.books == (HOBBIT_DETAILS,)
    assert result.missing_ids == ()


def test_get_book_details_returns_details_for_a_book_with_only_some_fields(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["3"])

    assert result.books == (GOOD_OMENS_DETAILS,)
    assert result.missing_ids == ()


def test_get_book_details_returns_all_requested_books_regardless_of_order(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["3", "1", "2"])

    assert set(result.books) == {DUNE_DETAILS, HOBBIT_DETAILS, GOOD_OMENS_DETAILS}
    assert result.missing_ids == ()


def test_get_book_details_reports_unknown_ids_as_missing(calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "999", "abc"])

    assert result.books == (DUNE_DETAILS,)
    assert set(result.missing_ids) == {"999", "abc"}


def test_get_book_details_treats_numeric_affinity_aliases_as_distinct_missing_ids(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["01", " 1", "1.0", "+1", "1e0"])

    assert result.books == ()
    assert result.missing_ids == ("01", " 1", "1.0", "+1", "1e0")


def test_get_book_details_handles_duplicates_invalid_and_unknown_ids_together(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "01", "999", "1"])

    assert result.books == (DUNE_DETAILS,)
    assert result.missing_ids == ("01", "999")


def test_get_book_details_returns_all_ids_as_missing_when_none_are_valid(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["abc", "def"])

    assert result.books == ()
    assert result.missing_ids == ("abc", "def")


def test_get_book_details_silently_drops_empty_id_segments(calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "", "2"])

    assert set(result.books) == {DUNE_DETAILS, HOBBIT_DETAILS}
    assert result.missing_ids == ()


def test_get_book_details_returns_empty_result_for_empty_ids_list(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details([])

    assert result.books == ()
    assert result.missing_ids == ()


def test_get_book_details_opens_the_database_read_only(
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

    gateway.get_book_details(["1"])

    assert captured_calls == [(f"file:{calibre_metadata_db}?mode=ro", True)]


def test_missing_file_raises_library_not_found_error_for_book_details(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.get_book_details(["1"])


def test_non_calibre_sqlite_file_raises_not_a_calibre_library_error_for_book_details(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    gateway = SqliteLibraryGateway(db_path)

    with pytest.raises(NotACalibreLibraryError):
        gateway.get_book_details(["1"])
