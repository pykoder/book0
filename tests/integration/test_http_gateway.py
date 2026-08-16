import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from book0_api.main import create_app
from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.gateway import LibraryGateway
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)


def _client_for(
    libraries: dict[str, Path], default_tag: str | None = None
) -> httpx.Client:
    return TestClient(create_app(libraries, default_tag))


def test_list_books_returns_expected_books_for_a_known_tag(calibre_metadata_db: Path):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS


def test_list_books_returns_empty_list_for_an_unknown_tag(calibre_metadata_db: Path):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    assert gateway.list_books() == []


def test_list_books_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_books()


def test_list_books_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_books()


def test_list_authors_returns_expected_authors_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_authors() == CALIBRE_LIBRARY_AUTHORS


def test_list_authors_returns_empty_list_for_an_unknown_tag(calibre_metadata_db: Path):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    assert gateway.list_authors() == []


def test_list_authors_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_authors()


def test_list_authors_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_authors()


def test_list_publishers_returns_expected_publishers_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_list_publishers_returns_empty_list_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    assert gateway.list_publishers() == []


def test_list_publishers_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_publishers()


def test_list_publishers_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_publishers()


def test_http_gateway_satisfies_the_library_gateway_protocol(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway: LibraryGateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_list_books_uses_server_side_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db}, default_tag="fiction")
    gateway = HttpLibraryGateway(client, None)

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS


def test_list_books_raises_tag_required_error_when_no_default_configured(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, None)

    with pytest.raises(TagRequiredError):
        gateway.list_books()


def test_get_book_details_uses_server_side_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db}, default_tag="fiction")
    gateway = HttpLibraryGateway(client, None)

    result = gateway.get_book_details(["1"])

    assert result.books == (dune_details,)
    assert result.missing_ids == ()


def test_get_book_details_returns_expected_details_for_a_known_tag(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, hobbit_details, good_omens_details = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.get_book_details(["3", "1", "2"])

    assert set(result.books) == {dune_details, hobbit_details, good_omens_details}
    assert result.missing_ids == ()


def test_get_book_details_reports_missing_ids_for_a_known_tag(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.get_book_details(["1", "999"])

    assert result.books == (dune_details,)
    assert result.missing_ids == ("999",)


def test_get_book_details_treats_unknown_tag_as_all_missing(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    result = gateway.get_book_details(["1", "2"])

    assert result.books == ()
    assert set(result.missing_ids) == {"1", "2"}


def test_get_book_details_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.get_book_details(["1"])


def test_get_book_details_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.get_book_details(["1"])
