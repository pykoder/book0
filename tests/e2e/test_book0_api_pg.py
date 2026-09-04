from fastapi.testclient import TestClient

from book0_api.main import create_app


def test_api_pg_list_books(pg_library):
    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)

    response = client.get("/libraries/books")

    assert response.status_code == 200
    assert {book["title"] for book in response.json()} >= {"Dune"}


def test_api_pg_list_books_avec_filtre_et_pagination(pg_library):
    app = create_app({}, pg_dsn=pg_library)
    client = TestClient(app)

    response = client.get(
        "/libraries/books",
        params={"tag": "grimoire-test", "ratings": "3-5", "page": 1, "page_size": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert "items" in body and "total_pages" in body
    assert [book["title"] for book in body["items"]] == ["Dune"]


def test_api_pg_series_route(pg_library):
    app = create_app({}, pg_dsn=pg_library)
    client = TestClient(app)

    response = client.get("/libraries/series", params={"tag": "grimoire-test"})

    assert response.status_code == 200
    assert response.json() == [{"id": "1", "name": "Dune Chronicles"}]


def test_api_pg_unknown_tag_returns_404(pg_library):
    app = create_app({}, pg_dsn=pg_library)
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "does-not-exist"})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"
