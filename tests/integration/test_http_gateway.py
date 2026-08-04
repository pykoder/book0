import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from book0_api.main import create_app
from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from tests.conftest import CALIBRE_LIBRARY_BOOKS


def _client_for(libraries: dict[str, Path]) -> httpx.Client:
    return TestClient(create_app(libraries))


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
