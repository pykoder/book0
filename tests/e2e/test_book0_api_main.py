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

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": book.id,
            "title": book.title,
            "authors": list(book.authors),
            "pubdate": book.pubdate,
            "publisher": (
                {"id": book.publisher.id, "name": book.publisher.name}
                if book.publisher is not None
                else None
            ),
            "series": (
                {"id": book.series.id, "name": book.series.name}
                if book.series is not None
                else None
            ),
            "series_index": book.series_index,
            "rating": book.rating,
            "has_cover": book.has_cover,
        }
        for book in CALIBRE_LIBRARY_BOOKS
    ]


def test_list_books_resolves_metadata_db_when_configured_path_is_a_directory(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db.parent})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": book.id,
            "title": book.title,
            "authors": list(book.authors),
            "pubdate": book.pubdate,
            "publisher": (
                {"id": book.publisher.id, "name": book.publisher.name}
                if book.publisher is not None
                else None
            ),
            "series": (
                {"id": book.series.id, "name": book.series.name}
                if book.series is not None
                else None
            ),
            "series_index": book.series_index,
            "rating": book.rating,
            "has_cover": book.has_cover,
        }
        for book in CALIBRE_LIBRARY_BOOKS
    ]


def test_list_books_returns_400_for_an_unknown_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "does-not-exist"})

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_books_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

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

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_books_uses_default_tag_when_tag_is_omitted(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.get("/libraries/books")

    assert response.status_code == 200
    assert len(response.json()) == len(CALIBRE_LIBRARY_BOOKS)


def test_list_books_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_authors_returns_expected_authors_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/authors", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": author.id, "name": author.name} for author in CALIBRE_LIBRARY_AUTHORS
    ]


def test_list_authors_returns_400_for_an_unknown_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/authors", params={"tag": "does-not-exist"})

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_authors_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/authors", params={"tag": "fiction"})

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

    response = client.get("/libraries/authors", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_authors_uses_default_tag_when_tag_is_omitted(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.get("/libraries/authors")

    assert response.status_code == 200
    assert len(response.json()) == len(CALIBRE_LIBRARY_AUTHORS)


def test_list_authors_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/authors")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_publishers_returns_expected_publishers_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/publishers", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": publisher.id, "name": publisher.name}
        for publisher in CALIBRE_LIBRARY_PUBLISHERS
    ]


def test_list_publishers_returns_400_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/publishers", params={"tag": "does-not-exist"})

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_publishers_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/publishers", params={"tag": "fiction"})

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

    response = client.get("/libraries/publishers", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_publishers_uses_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.get("/libraries/publishers")

    assert response.status_code == 200
    assert len(response.json()) == len(CALIBRE_LIBRARY_PUBLISHERS)


def test_list_publishers_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/publishers")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_get_book_details_returns_expected_details_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail", params={"tag": "fiction"}, json={"ids": ["1"]}
    )

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
        "has_cover": True,
    }


def test_get_book_details_reports_missing_ids_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail", params={"tag": "fiction"}, json={"ids": ["1", "999"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["missing_ids"] == ["999"]
    assert len(body["books"]) == 1


def test_get_book_details_returns_400_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail",
        params={"tag": "does-not-exist"},
        json={"ids": ["1", "2"]},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_get_book_details_returns_404_when_configured_path_is_missing(
    tmp_path: Path,
):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail", params={"tag": "fiction"}, json={"ids": ["1"]}
    )

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

    response = client.post(
        "/libraries/books/detail", params={"tag": "fiction"}, json={"ids": ["1"]}
    )

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_get_book_details_uses_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.post("/libraries/books/detail", json={"ids": ["1"]})

    assert response.status_code == 200
    assert len(response.json()["books"]) == 1


def test_get_book_details_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post("/libraries/books/detail", json={"ids": ["1"]})

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_get_book_cover_returns_the_cover_bytes_for_a_known_book(
    calibre_metadata_db: Path,
):
    library_root = calibre_metadata_db.parent
    cover_path = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(b"fake-jpeg-bytes")
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.content == b"fake-jpeg-bytes"
    assert response.headers["content-type"] == "image/jpeg"


def test_get_book_cover_returns_404_for_a_book_with_no_cover(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/2/cover", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "CoverNotFoundError"


def test_get_book_cover_returns_404_when_cover_file_is_missing_on_disk(
    calibre_metadata_db: Path,
):
    # Dune (id 1) has has_cover=1 in the fixture DB, but the fixture never
    # creates a real cover.jpg file on disk - the defensive "file missing"
    # case.
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "CoverNotFoundError"


def test_get_book_cover_returns_404_for_an_unknown_book_id(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/999/cover", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "CoverNotFoundError"


def test_get_book_cover_returns_400_for_an_unconfigured_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover", params={"tag": "does-not-exist"})

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_get_book_cover_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_get_book_cover_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_get_book_cover_returns_500_when_configured_path_is_not_a_calibre_library(
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

    response = client.get("/libraries/books/1/cover", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_books_returns_a_paginated_response_when_page_size_is_given(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page": 1, "page_size": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["items"]] == ["Book 1", "Book 2"]
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total_pages"] == 4
    assert body["has_more_than_shown"] is False


def test_list_books_omitting_page_and_page_size_stays_unpaginated_with_no_server_default(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 7


def test_list_books_server_default_page_size_forces_pagination(many_books_db: Path):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert [item["title"] for item in body["items"]] == ["Book 1", "Book 2"]


def test_list_books_server_default_page_size_caps_a_larger_client_request(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page_size": 100}
    )

    assert response.status_code == 200
    assert response.json()["page_size"] == 2


def test_list_books_client_page_size_smaller_than_server_default_is_honored(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=5)
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction", "page_size": 2})

    assert response.status_code == 200
    assert response.json()["page_size"] == 2


def test_list_books_non_positive_server_default_page_size_is_ignored(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=-5)
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 7


def test_list_books_zero_server_default_page_size_is_ignored(many_books_db: Path):
    app = create_app({"fiction": many_books_db}, default_page_size=0)
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 7


def test_list_books_non_positive_page_is_normalized_to_one(many_books_db: Path):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page": 0, "page_size": 2}
    )

    assert response.status_code == 200
    assert response.json()["page"] == 1


def test_list_books_non_positive_page_size_is_normalized_to_unpaginated(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction", "page_size": 0})

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_books_non_numeric_page_returns_422(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction", "page": "abc"})

    assert response.status_code == 422


def test_list_books_returns_400_for_an_unknown_tag_even_when_page_size_is_given(
    many_books_db: Path,
):
    # Unknown-tag handling (TagRequiredError -> 400) happens in _resolve_db_path,
    # before pagination resolution runs at all - this test just confirms the two
    # features don't interact / pagination params don't bypass tag validation.
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books",
        params={"tag": "does-not-exist", "page": 1, "page_size": 2},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_authors_returns_a_paginated_response_when_page_size_is_given(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/authors", params={"tag": "fiction", "page": 1, "page_size": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Author 1", "Author 2"]


def test_list_publishers_returns_a_paginated_response_when_page_size_is_given(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/publishers", params={"tag": "fiction", "page": 1, "page_size": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Publisher 1", "Publisher 2"]
