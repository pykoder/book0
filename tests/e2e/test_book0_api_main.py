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


def test_get_book_details_returns_expected_details_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post("/libraries/fiction/books/detail", json={"ids": ["1"]})

    assert response.status_code == 200
    body = response.json()
    assert body["missing_ids"] == []
    assert len(body["books"]) == 1
    assert body["books"][0] == {
        "id": "1",
        "title": "Dune",
        "pubdate": "1965-08-01",
        "authors": ["Frank Herbert"],
        "tags": ["sci-fi", "classic"],
        "publisher": {"id": "1", "name": "Ace Books"},
        "series": {
            "series": {"id": "1", "name": "Dune Chronicles"},
            "index": "1.0",
        },
    }


def test_get_book_details_reports_missing_ids_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/fiction/books/detail", json={"ids": ["1", "999"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["missing_ids"] == ["999"]
    assert len(body["books"]) == 1


def test_get_book_details_returns_all_requested_ids_as_missing_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/does-not-exist/books/detail", json={"ids": ["1", "2"]}
    )

    assert response.status_code == 200
    assert response.json() == {"books": [], "missing_ids": ["1", "2"]}


def test_get_book_details_returns_404_when_configured_path_is_missing(
    tmp_path: Path,
):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.post("/libraries/fiction/books/detail", json={"ids": ["1"]})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_get_book_details_returns_500_when_configured_path_is_not_a_calibre_library(
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

    response = client.post("/libraries/fiction/books/detail", json={"ids": ["1"]})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"
