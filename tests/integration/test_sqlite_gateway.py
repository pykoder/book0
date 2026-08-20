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


def test_list_books_then_list_authors_reuse_the_same_connection(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    gateway.list_books()
    first_connection = gateway._connection
    gateway.list_authors()
    second_connection = gateway._connection

    assert first_connection is not None
    assert first_connection is second_connection


def test_list_books_page_returns_the_first_page_directly(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_books_page(1, 2)

    assert [book.title for book in result.items] == ["Book 01", "Book 02"]
    assert result.page == 1
    assert result.page_size == 2
    assert result.total_pages == 4
    assert result.has_more_than_shown is False
    assert result.handle is not None


def test_list_books_page_handle_reuse_pulls_from_the_open_cursor_without_a_new_select(
    paginated_calibre_metadata_db: Path,
):
    # The first page always costs one bounded LIMIT/OFFSET query, and continuing to
    # the very next page costs one more (opening the continuation cursor lazily) - so
    # the *third* page from the same session is where reuse becomes provably free:
    # only reading further from that already-open cursor via fetchmany, no new SELECT.
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    first = gateway.list_books_page(1, 2)
    second = gateway.list_books_page(2, 2, handle=first.handle)

    # sqlite3.Connection.execute is a read-only attribute on the built-in C type -
    # it cannot be reassigned to a counting wrapper. set_trace_callback is sqlite3's
    # own hook for observing every SQL statement actually prepared/executed on this
    # connection, and (unlike connection.execute) fetchmany() against an
    # already-open cursor does NOT re-trigger it - only a fresh execute() does. That
    # makes it the right signal for "was a new SELECT issued", without needing to
    # monkeypatch anything.
    connection = gateway._connect()
    traced_statements: list[str] = []
    connection.set_trace_callback(traced_statements.append)

    third = gateway.list_books_page(3, 2, handle=second.handle)

    assert [book.title for book in third.items] == ["Book 05", "Book 06"]
    # _count_pages always runs its own COUNT query, every call - filter that out and
    # assert no *list*-query SELECT was newly issued for this reused page:
    list_query_statements = [
        statement for statement in traced_statements if "COUNT" not in statement
    ]
    assert list_query_statements == []


def test_list_books_page_falls_back_correctly_when_handle_is_out_of_range(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    first = gateway.list_books_page(1, 2)

    # Page 4, not page 2 - out of the "exactly next page" range this handle covers.
    result = gateway.list_books_page(4, 2, handle=first.handle)

    assert [book.title for book in result.items] == ["Book 07"]
    assert result.handle is None  # last page, nothing more to serve


def test_list_books_page_falls_back_when_handle_is_from_a_different_page_size(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    first = gateway.list_books_page(1, 2)

    result = gateway.list_books_page(2, 3, handle=first.handle)

    assert [book.title for book in result.items] == ["Book 04", "Book 05", "Book 06"]


def test_list_authors_page_falls_back_when_handle_is_from_a_different_resource(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    books_handle = gateway.list_books_page(1, 2)

    # A handle minted by list_books_page's session ("books", page_size=2) handed to
    # list_authors_page ("authors", page_size=3) must not be honored - resource
    # mismatch means a fresh fetch, not authors read off the books session/cursor.
    result = gateway.list_authors_page(2, 3, handle=books_handle.handle)

    assert [author.name for author in result.items] == [
        "Author 04",
        "Author 05",
        "Author 06",
    ]


def test_list_books_page_falls_back_when_handle_is_unknown(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_books_page(2, 2, handle="not-a-real-handle")

    assert [book.title for book in result.items] == ["Book 03", "Book 04"]


def test_list_books_page_cold_jump_to_a_later_page_returns_correct_rows(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_books_page(3, 2)

    assert [book.title for book in result.items] == ["Book 05", "Book 06"]
    assert result.page == 3


def test_list_books_page_total_pages_is_none_past_the_counted_cap(
    paginated_calibre_metadata_db: Path,
):
    # 7 books, page_size=2, max_counted_pages=2 -> cap = 4 rows, count (7) >= cap.
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db, max_counted_pages=2)

    result = gateway.list_books_page(1, 2)

    assert result.total_pages is None
    assert result.has_more_than_shown is True


def test_list_authors_page_returns_the_first_page(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_authors_page(1, 3)

    assert [author.name for author in result.items] == [
        "Author 01",
        "Author 02",
        "Author 03",
    ]
    assert result.total_pages == 3


def test_list_publishers_page_returns_the_first_page(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_publishers_page(1, 3)

    assert [publisher.name for publisher in result.items] == [
        "Publisher 01",
        "Publisher 02",
        "Publisher 03",
    ]
    assert result.total_pages == 3


def test_close_pagination_releases_the_session(paginated_calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    first = gateway.list_books_page(1, 2)

    gateway.close_pagination(first.handle)

    assert first.handle not in gateway._sessions
    # Behaves as if the handle was never given - falls back to a correct direct fetch:
    result = gateway.list_books_page(2, 2, handle=first.handle)
    assert [book.title for book in result.items] == ["Book 03", "Book 04"]


def test_close_pagination_is_silent_on_an_unknown_handle(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.close_pagination("not-a-real-handle")

    assert result is None  # did not raise, degraded silently


def test_list_books_page_expires_a_session_after_the_timeout(
    paginated_calibre_metadata_db: Path,
):
    fake_time = [0.0]
    gateway = SqliteLibraryGateway(
        paginated_calibre_metadata_db, clock=lambda: fake_time[0]
    )
    first = gateway.list_books_page(1, 2)
    assert first.handle in gateway._sessions

    fake_time[0] = 61.0  # past the 60s session timeout
    result = gateway.list_books_page(2, 2, handle=first.handle)

    # The expired session was dropped before the handle could even be checked - this
    # call fell back to a correct fresh fetch, not a resumed one.
    assert first.handle not in gateway._sessions
    assert [book.title for book in result.items] == ["Book 03", "Book 04"]


def test_list_books_page_raises_library_not_found_error(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_books_page(1, 2)
