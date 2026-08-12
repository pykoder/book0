import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from book0_api.main import create_app
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)


def test_list_books_returns_expected_books_for_a_known_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/fiction/books")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": book.id,
            "title": book.title,
            "authors": list(book.authors),
            "pubdate": book.pubdate,
        }
        for book in CALIBRE_LIBRARY_BOOKS
    ]


def test_list_books_resolves_metadata_db_when_configured_path_is_a_directory(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db.parent})
    client = TestClient(app)

    response = client.get("/libraries/fiction/books")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": book.id,
            "title": book.title,
            "authors": list(book.authors),
            "pubdate": book.pubdate,
        }
        for book in CALIBRE_LIBRARY_BOOKS
    ]


def test_list_books_returns_empty_list_for_an_unknown_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/does-not-exist/books")

    assert response.status_code == 200
    assert response.json() == []


def test_list_books_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/fiction/books")

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_books_returns_500_when_configured_path_is_not_a_calibre_library(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    app = create_app({"fiction": db_path})
    client = TestClient(app)

    response = client.get("/libraries/fiction/books")

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_authors_returns_expected_authors_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/fiction/authors")

    assert response.status_code == 200
    assert response.json() == [
        {"id": author.id, "name": author.name} for author in CALIBRE_LIBRARY_AUTHORS
    ]


def test_list_authors_returns_empty_list_for_an_unknown_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/does-not-exist/authors")

    assert response.status_code == 200
    assert response.json() == []


def test_list_authors_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/fiction/authors")

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_authors_returns_500_when_configured_path_is_not_a_calibre_library(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    app = create_app({"fiction": db_path})
    client = TestClient(app)

    response = client.get("/libraries/fiction/authors")

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_publishers_returns_expected_publishers_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/fiction/publishers")

    assert response.status_code == 200
    assert response.json() == [
        {"id": publisher.id, "name": publisher.name}
        for publisher in CALIBRE_LIBRARY_PUBLISHERS
    ]


def test_list_publishers_returns_empty_list_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/does-not-exist/publishers")

    assert response.status_code == 200
    assert response.json() == []


def test_list_publishers_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/fiction/publishers")

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_publishers_returns_500_when_configured_path_is_not_a_calibre_library(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    app = create_app({"fiction": db_path})
    client = TestClient(app)

    response = client.get("/libraries/fiction/publishers")

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"
