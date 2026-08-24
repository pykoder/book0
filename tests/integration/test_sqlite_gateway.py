import sqlite3
from pathlib import Path

import pytest

from book0_core import sqlite_gateway
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.gateway import LibraryGateway
from book0_core.sqlite_gateway import SqliteLibraryGateway
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
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


def test_gateway_reuses_the_same_connection_across_multiple_method_calls(
    calibre_metadata_db: Path, monkeypatch: pytest.MonkeyPatch
):
    real_connect = sqlite3.connect
    captured_calls: list[str] = []

    def spying_connect(
        database: str, *args: object, **kwargs: object
    ) -> sqlite3.Connection:
        captured_calls.append(str(database))
        return real_connect(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlite3, "connect", spying_connect)
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    gateway.list_books()
    gateway.list_authors()
    gateway.list_publishers()

    assert captured_calls == [f"file:{calibre_metadata_db}?mode=ro"]


def test_get_book_details_returns_details_for_a_book_with_everything(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1"])

    assert result.books == (dune_details,)
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
    expected_book_details: tuple,
):
    _, _, good_omens_details = expected_book_details
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["3"])

    assert result.books == (good_omens_details,)
    assert result.missing_ids == ()


def test_get_book_details_returns_all_requested_books_regardless_of_order(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, hobbit_details, good_omens_details = expected_book_details
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["3", "1", "2"])

    assert set(result.books) == {dune_details, hobbit_details, good_omens_details}
    assert result.missing_ids == ()


def test_get_book_details_reports_unknown_ids_as_missing(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "999", "abc"])

    assert result.books == (dune_details,)
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
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "01", "999", "1"])

    assert result.books == (dune_details,)
    assert result.missing_ids == ("01", "999")


def test_get_book_details_returns_all_ids_as_missing_when_none_are_valid(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["abc", "def"])

    assert result.books == ()
    assert result.missing_ids == ("abc", "def")


def test_get_book_details_silently_drops_empty_id_segments(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, hobbit_details, _ = expected_book_details
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "", "2"])

    assert set(result.books) == {dune_details, hobbit_details}
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


def test_list_books_page_returns_the_requested_page_in_title_order(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(1, 2)

    assert [book.title for book in result.items] == ["Book 1", "Book 2"]
    assert result.page == 1
    assert result.page_size == 2


def test_list_books_page_cold_jump_to_a_later_page_returns_correct_rows(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(3, 2)

    assert [book.title for book in result.items] == ["Book 5", "Book 6"]


def test_list_books_page_last_page_has_fewer_items_and_no_handle(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(4, 2)

    assert [book.title for book in result.items] == ["Book 7"]
    assert result.handle is None


def test_list_books_page_reports_exact_total_pages_under_the_cap(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(1, 2)

    assert result.total_pages == 4
    assert result.has_more_than_shown is False


def test_list_books_page_reports_many_when_count_exceeds_the_cap(
    many_books_db: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(sqlite_gateway, "_PAGE_COUNT_CAP", 2)
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(1, 2)

    assert result.total_pages is None
    assert result.has_more_than_shown is True


def test_list_books_page_reports_zero_total_pages_for_an_empty_library(
    calibre_metadata_db: Path,
):
    db_path = calibre_metadata_db.parent / "empty" / "metadata.db"
    db_path.parent.mkdir()
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                pubdate TEXT, series_index REAL, path TEXT, has_cover INTEGER);
            CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL, author INTEGER NOT NULL);
            """
        )
        connection.commit()
    finally:
        connection.close()
    gateway = SqliteLibraryGateway(db_path)

    result = gateway.list_books_page(1, 2)

    assert result.items == ()
    assert result.total_pages == 0
    assert result.handle is None


def test_list_books_page_reuses_the_session_for_the_immediate_next_page(
    many_books_db: Path,
):
    # sqlite3.Connection is a C-extension type - its methods can't be monkeypatched
    # directly (monkeypatch.setattr(sqlite3.Connection, "execute", ...) raises
    # TypeError: cannot set 'execute' attribute of immutable type). Use the
    # connection's own set_trace_callback instead: it receives the SQL text of
    # every statement actually executed on it, which is exactly what "no new
    # OFFSET query for the reused page" needs to observe.
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    traced_sql: list[str] = []
    gateway._connect().set_trace_callback(traced_sql.append)
    second = gateway.list_books_page(2, 2, handle=first.handle)

    assert [book.title for book in second.items] == ["Book 3", "Book 4"]
    assert not any("OFFSET" in sql for sql in traced_sql)


def test_list_books_page_falls_back_to_a_fresh_fetch_outside_the_reusable_range(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    # Requesting page 1 again (not the session's next page, 2) must not reuse it.
    repeated = gateway.list_books_page(1, 2, handle=first.handle)

    assert [book.title for book in repeated.items] == ["Book 1", "Book 2"]


def test_list_books_page_closes_the_superseded_session_on_a_same_stream_fallback(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    assert first.handle in gateway._sessions
    gateway.list_books_page(1, 2, handle=first.handle)  # repeats page 1, not next

    assert first.handle not in gateway._sessions


def test_list_books_page_falls_back_when_handle_is_unknown(many_books_db: Path):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(2, 2, handle="not-a-real-handle")

    assert [book.title for book in result.items] == ["Book 3", "Book 4"]


def test_list_books_page_falls_back_when_page_size_does_not_match_the_session(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    result = gateway.list_books_page(2, 3, handle=first.handle)

    assert [book.title for book in result.items] == ["Book 4", "Book 5", "Book 6"]


# (The "handle belongs to a different resource" fallback case needs a second real
# resource type to be meaningful - list_authors_page doesn't exist until Task 4, so
# that test lives there instead, once both methods exist to cross-check against
# each other.)


def test_close_pagination_releases_the_session(many_books_db: Path):
    gateway = SqliteLibraryGateway(many_books_db)
    first = gateway.list_books_page(1, 2)
    assert first.handle is not None

    gateway.close_pagination(first.handle)
    second = gateway.list_books_page(2, 2, handle=first.handle)

    # A fresh fetch for page 2 gets its own new handle, distinct from the closed one.
    assert second.handle != first.handle
    assert [book.title for book in second.items] == ["Book 3", "Book 4"]


def test_close_pagination_is_silent_and_idempotent_for_an_unknown_handle(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    gateway.close_pagination("never-issued")
    gateway.close_pagination("never-issued")  # idempotent, no exception


def test_list_books_page_expires_a_session_after_the_timeout(
    many_books_db: Path, monkeypatch: pytest.MonkeyPatch
):
    fake_now = [1000.0]
    monkeypatch.setattr(SqliteLibraryGateway, "_now", lambda self: fake_now[0])
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    fake_now[0] += 61
    result = gateway.list_books_page(2, 2, handle=first.handle)

    assert [book.title for book in result.items] == ["Book 3", "Book 4"]


def test_list_authors_page_returns_the_requested_page_in_name_order(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_authors_page(1, 2)

    assert [author.name for author in result.items] == ["Author 1", "Author 2"]
    assert result.total_pages == 4


def test_list_authors_page_reuses_the_session_for_the_immediate_next_page(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_authors_page(1, 2)
    second = gateway.list_authors_page(2, 2, handle=first.handle)

    assert [author.name for author in second.items] == ["Author 3", "Author 4"]


def test_list_authors_page_last_page_has_no_handle(many_books_db: Path):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_authors_page(4, 2)

    assert [author.name for author in result.items] == ["Author 7"]
    assert result.handle is None


def test_list_books_page_falls_back_when_handle_belongs_to_a_different_resource(
    many_books_db: Path,
):
    # Moved here from Task 3: this fallback case needs two real resource types to
    # be meaningful, and list_authors_page didn't exist yet in Task 3.
    gateway = SqliteLibraryGateway(many_books_db)

    authors_first = gateway.list_authors_page(1, 2)
    result = gateway.list_books_page(2, 2, handle=authors_first.handle)

    assert [book.title for book in result.items] == ["Book 3", "Book 4"]
