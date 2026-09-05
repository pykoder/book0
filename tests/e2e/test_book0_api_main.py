import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from book0_api.main import create_app
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    CALIBRE_LIBRARY_SERIES,
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


def test_list_series_returns_expected_series_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/series", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": series.id, "name": series.name} for series in CALIBRE_LIBRARY_SERIES
    ]


def test_list_series_returns_400_for_an_unknown_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/series", params={"tag": "does-not-exist"})

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_series_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/series", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_series_returns_500_when_configured_path_is_not_a_calibre_library(
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

    response = client.get("/libraries/series", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_series_uses_default_tag_when_tag_is_omitted(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.get("/libraries/series")

    assert response.status_code == 200
    assert len(response.json()) == len(CALIBRE_LIBRARY_SERIES)


def test_list_series_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/series")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_series_accepts_the_whitelisted_name_sort(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/series", params={"tag": "fiction", "sort": "name", "order": "asc"}
    )

    assert response.status_code == 200
    assert response.json() == [
        {"id": series.id, "name": series.name} for series in CALIBRE_LIBRARY_SERIES
    ]


def test_list_series_rejects_desc_order_with_a_422(calibre_metadata_db: Path):
    # La route ne sait trier qu'en asc (ORDER BY name fixe des passerelles) :
    # desc doit être rejeté par la validation FastAPI, pas accepté puis ignoré.
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/series", params={"tag": "fiction", "sort": "name", "order": "desc"}
    )

    assert response.status_code == 422


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


def test_list_series_returns_a_paginated_response_when_page_size_is_given(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/series", params={"tag": "fiction", "page": 1, "page_size": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Series 1", "Series 2"]
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total_pages"] == 4
    assert body["has_more_than_shown"] is False


def test_list_books_routes_through_the_filtered_query_when_a_filter_param_is_given(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction", "ratings": "4"})

    assert response.status_code == 200
    assert [book["title"] for book in response.json()] == ["Dune"]


def test_list_books_expands_a_ratings_range_filter(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "ratings": "3-5"}
    )

    assert response.status_code == 200
    assert all(book["rating"] is not None for book in response.json())


def test_list_books_filters_by_tag_text(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "tags": "sci-fi"}
    )

    assert response.status_code == 200
    assert [book["title"] for book in response.json()] == ["Dune"]


def test_list_books_honors_sort_and_order_through_the_filtered_query(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books",
        params={"tag": "fiction", "sort": "pubdate", "order": "desc"},
    )

    assert response.status_code == 200
    # 1990 first, 1965 second; the NULL-pubdate Hobbit sorts last in DESC.
    assert [book["title"] for book in response.json()] == [
        "Good Omens",
        "Dune",
        "The Hobbit",
    ]


def test_list_books_returns_a_paginated_response_for_a_filtered_query(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books",
        params={"tag": "fiction", "ratings": "4", "page": 1, "page_size": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["items"]] == ["Dune"]
    assert body["page"] == 1
    assert body["page_size"] == 2


def test_list_books_returns_422_for_an_invalid_filter(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "ratings": "5-3"}
    )

    assert response.status_code == 422
    assert response.json()["error"] == "InvalidFilterError"


def test_list_books_returns_422_for_an_unknown_sort(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "sort": "banana"}
    )

    assert response.status_code == 422
    assert response.json()["error"] == "InvalidFilterError"


def test_list_authors_filters_through_the_cascade_query(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/authors", params={"tag": "fiction", "series_id": "1"}
    )

    assert response.status_code == 200
    assert [author["name"] for author in response.json()] == ["Frank Herbert"]


def test_list_authors_returns_422_for_an_invalid_cascade_filter(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/authors", params={"tag": "fiction", "series_id": "1-3"}
    )

    assert response.status_code == 422
    assert response.json()["error"] == "InvalidFilterError"


def test_list_publishers_filters_through_the_cascade_query(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/publishers", params={"tag": "fiction", "tags": "fantasy"}
    )

    assert response.status_code == 200
    assert [publisher["name"] for publisher in response.json()] == ["Gollancz"]


def test_list_series_filters_through_the_cascade_query(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/series", params={"tag": "fiction", "tags": "sci-fi"}
    )

    assert response.status_code == 200
    assert [series["name"] for series in response.json()] == ["Dune Chronicles"]


def test_list_series_empty_cascade_result_when_no_book_matches(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/series", params={"tag": "fiction", "tags": "humor"}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_values_returns_ratings_facet_values(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/values/ratings", params={"tag": "fiction"})

    assert response.status_code == 200
    # Calibre rating 8 (raw) -> 4 stars; only Dune carries a rating.
    assert response.json() == [{"value": "4", "count": 1}]


def test_get_values_returns_tags_facet_values_sorted_by_count_then_name(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/values/tags", params={"tag": "fiction"})

    assert response.status_code == 200
    # All four tags have count 1, so the name tiebreak orders them alphabetically.
    assert response.json() == [
        {"value": "classic", "count": 1},
        {"value": "fantasy", "count": 1},
        {"value": "humor", "count": 1},
        {"value": "sci-fi", "count": 1},
    ]


def test_get_values_returns_languages_facet_values(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/values/languages", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [{"value": "fra", "count": 3}]


def test_get_values_returns_formats_facet_values(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/values/formats", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [{"value": "EPUB", "count": 1}]


def test_get_values_returns_422_for_a_field_outside_the_whitelist(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/values/isbn", params={"tag": "fiction"})

    assert response.status_code == 422
    assert response.json()["error"] == "InvalidFilterError"


def test_get_values_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/values/tags", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_patch_books_returns_501_for_a_sqlite_backed_library(
    calibre_metadata_db: Path,
):
    # SqliteLibraryGateway est en lecture seule par construction : l'édition
    # en masse n'est servie qu'en mode PG (pg_dsn).
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.patch(
        "/libraries/books",
        params={"tag": "fiction"},
        json={"ids": ["1"], "patch": {"rating": 3}},
    )

    assert response.status_code == 501
    assert response.json()["error"] == "NotImplementedError"


def test_get_book_content_returns_501_for_a_sqlite_backed_library(
    calibre_metadata_db: Path,
):
    # get_book_content (conversion epub2md + cache disque) n'est implémenté
    # que sur PgLibraryGateway : le mode SQLite reste en 501.
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/1/content", params={"tag": "fiction"})

    assert response.status_code == 501
    assert response.json()["error"] == "NotImplementedError"


def test_jobs_routes_return_501_for_a_sqlite_backed_library(
    calibre_metadata_db: Path,
):
    # Les jobs (persistance + exécuteur) ne sont servis qu'en mode PG, avant
    # toute résolution de tag.
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    post = client.post(
        "/libraries/jobs", json={"action": "convert-markdown", "book_ids": ["1"]}
    )
    get_list = client.get("/libraries/jobs")
    get_detail = client.get("/libraries/jobs/8f3a9c00-0000-0000-0000-000000000000")

    for response in (post, get_list, get_detail):
        assert response.status_code == 501
        assert response.json()["error"] == "NotImplementedError"
