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


# --- PATCH /libraries/books : édition en masse avec dry_run (spec §7.1) ---
# Seed pg_library (identique à la fixture SQLite) : publisher local_id 1 =
# Ace Books, 2 = Gollancz ; Dune a la note 4 étoiles et les tags
# ["sci-fi", "classic"].


def test_api_pg_patch_books_nominal(pg_library):
    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)

    response = client.patch(
        "/libraries/books",
        json={
            "ids": ["1", "2"],
            "patch": {"publisher_id": "2", "rating": 4},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"updated": ["1", "2"], "missing_ids": []}

    books = {book["title"]: book for book in client.get("/libraries/books").json()}
    assert books["Dune"]["rating"] == 4
    assert books["The Hobbit"]["rating"] == 4
    detail = client.post("/libraries/books/detail", json={"ids": ["1"]}).json()
    assert detail["books"][0]["publisher"]["name"] == "Gollancz"


def test_api_pg_patch_books_ids_inconnus_dans_missing(pg_library):
    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)

    response = client.patch(
        "/libraries/books",
        json={"ids": ["1", "9999"], "patch": {"rating": 2}},
    )

    assert response.status_code == 200
    assert response.json() == {"updated": ["1"], "missing_ids": ["9999"]}
    books = {book["title"]: book for book in client.get("/libraries/books").json()}
    assert books["Dune"]["rating"] == 2


def test_api_pg_patch_books_dry_run_n_ecrit_rien(pg_library):
    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)

    response = client.patch(
        "/libraries/books",
        json={
            "ids": ["1"],
            "patch": {
                "publisher_id": "2",
                "tags": ["nouveau"],
                "rating": 1,
                "comments": "brouillon",
            },
            "dry_run": True,
        },
    )

    # Même réponse qu'une exécution réelle...
    assert response.status_code == 200
    assert response.json() == {"updated": ["1"], "missing_ids": []}

    # ...mais aucune écriture.
    books = {book["title"]: book for book in client.get("/libraries/books").json()}
    assert books["Dune"]["rating"] == 4
    detail = client.post("/libraries/books/detail", json={"ids": ["1"]}).json()
    assert detail["books"][0]["publisher"]["name"] == "Ace Books"
    assert detail["books"][0]["tags"] == ["sci-fi", "classic"]


def test_api_pg_patch_books_patch_vide_returns_422(pg_library):
    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)

    response = client.patch(
        "/libraries/books",
        json={"ids": ["1"], "patch": {}},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "InvalidPatchError"
    assert "detail" in body


def test_api_pg_patch_books_ids_vides_returns_422(pg_library):
    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)

    response = client.patch(
        "/libraries/books",
        json={"ids": [], "patch": {"rating": 3}},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "InvalidPatchError"
    assert "detail" in body


def test_api_pg_patch_books_unknown_tag_returns_404(pg_library):
    app = create_app({}, pg_dsn=pg_library)
    client = TestClient(app)

    response = client.patch(
        "/libraries/books",
        params={"tag": "does-not-exist"},
        json={"ids": ["1"], "patch": {"rating": 3}},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_api_pg_patch_books_missing_tag_returns_400(pg_library):
    app = create_app({}, pg_dsn=pg_library)
    client = TestClient(app)

    response = client.patch(
        "/libraries/books",
        json={"ids": ["1"], "patch": {"rating": 3}},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"
