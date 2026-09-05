from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

import book0_api.jobs
from book0_api.main import create_app
from book0_core.pg_gateway import PgLibraryGateway
from tests.conftest import GRIMOIRE_TEST_LIBRARY_UUID


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


# --- Jobs de fond + /libraries/jobs + /libraries/books/{id}/content (spec §7.2)
# NB : TestClient exécute les BackgroundTasks de façon synchrone — un POST job
# est donc déjà terminé (done/failed) à la réponse 202.


def test_post_job_convert_markdown_se_termite_done(pg_library, tmp_path: Path):
    app = create_app({}, pg_dsn=pg_library, markdown_cache_dir=tmp_path / "md")
    client = TestClient(app)
    r = client.post(
        "/libraries/jobs",
        params={"tag": "grimoire-test"},
        json={"action": "convert-markdown", "book_ids": ["1"], "params": {"level": 7}},
    )
    assert r.status_code == 202
    job_id = r.json()["id"]
    detail = client.get(f"/libraries/jobs/{job_id}").json()
    assert detail["status"] == "done"
    assert detail["outcome"]["succeeded"] == ["1"]


def test_post_job_convert_markdown_echecs_independants_par_livre(
    pg_library, tmp_path: Path
):
    app = create_app({}, pg_dsn=pg_library, markdown_cache_dir=tmp_path / "md")
    client = TestClient(app)
    # 1 : EPUB présent -> succès ; 2 : pas d'EPUB ; 9999 : livre inconnu.
    r = client.post(
        "/libraries/jobs",
        params={"tag": "grimoire-test"},
        json={"action": "convert-markdown", "book_ids": ["1", "2", "9999"]},
    )
    assert r.status_code == 202
    detail = client.get(f"/libraries/jobs/{r.json()['id']}").json()
    assert detail["status"] == "done"
    assert detail["outcome"]["succeeded"] == ["1"]
    assert detail["outcome"]["failed"] == [
        {"id": "2", "reason": "NoEpubError"},
        {"id": "9999", "reason": "BookNotFoundError"},
    ]


def test_post_job_sync_library_appelle_calibre_syncer(pg_library, monkeypatch):
    calls = []

    class FakeSyncer:
        def __init__(self, sqlite_path: str, pg_dsn: str) -> None:
            calls.append((sqlite_path, pg_dsn))

        def run(self) -> None:
            calls.append(("run",))

    monkeypatch.setattr(book0_api.jobs, "CalibreSyncer", FakeSyncer)
    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)
    r = client.post(
        "/libraries/jobs",
        json={"action": "sync-library", "book_ids": ["1", "2"]},
    )
    assert r.status_code == 202
    detail = client.get(f"/libraries/jobs/{r.json()['id']}").json()
    assert detail["status"] == "done"
    assert detail["outcome"]["succeeded"] == ["1", "2"]
    assert calls[0][0].endswith("metadata.db")
    assert calls[0][1] == pg_library
    assert calls[1] == ("run",)


def test_post_job_sync_library_echec_failed_avec_raison(pg_library, monkeypatch):
    class FailingSyncer:
        def __init__(self, sqlite_path: str, pg_dsn: str) -> None:
            pass

        def run(self) -> None:
            raise RuntimeError("sync catastrophique")

    monkeypatch.setattr(book0_api.jobs, "CalibreSyncer", FailingSyncer)
    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)
    r = client.post(
        "/libraries/jobs",
        json={"action": "sync-library", "book_ids": ["1"]},
    )
    assert r.status_code == 202
    detail = client.get(f"/libraries/jobs/{r.json()['id']}").json()
    assert detail["status"] == "failed"
    assert detail["outcome"]["failed"] == [
        {"id": detail["id"], "reason": "sync catastrophique"}
    ]


def test_post_job_action_inconnue_422(pg_library):
    client = TestClient(create_app({}, pg_dsn=pg_library))
    r = client.post("/libraries/jobs", json={"action": "reindex", "book_ids": []})
    assert r.status_code == 422 and r.json()["error"] == "UnknownJobActionError"


def test_post_job_sqlite_mode_501(calibre_metadata_db: Path):
    app = create_app({"grimoire-test": calibre_metadata_db})
    client = TestClient(app)
    r = client.post(
        "/libraries/jobs",
        json={"action": "convert-markdown", "book_ids": ["1"]},
    )
    assert r.status_code == 501 and r.json()["error"] == "NotImplementedError"


def test_get_jobs_liste_paginee(pg_library):
    client = TestClient(create_app({}, pg_dsn=pg_library))
    r = client.get("/libraries/jobs", params={"page": 1, "page_size": 10})
    assert r.status_code == 200 and "items" in r.json()


def test_get_jobs_filtre_valeur_inconnue_422(pg_library):
    client = TestClient(create_app({}, pg_dsn=pg_library))
    r = client.get("/libraries/jobs", params={"status": "vaporise"})
    assert r.status_code == 422 and r.json()["error"] == "UnknownJobActionError"
    r = client.get("/libraries/jobs", params={"action": "reindex"})
    assert r.status_code == 422 and r.json()["error"] == "UnknownJobActionError"


def test_get_job_inconnu_404(pg_library):
    client = TestClient(create_app({}, pg_dsn=pg_library))
    r = client.get("/libraries/jobs/8f3a9c00-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["error"] == "UnknownJobError"


def test_get_book_content_route(pg_library, tmp_path: Path):
    client = TestClient(
        create_app({}, pg_dsn=pg_library, markdown_cache_dir=tmp_path / "md")
    )
    r = client.get(
        "/libraries/books/1/content", params={"tag": "grimoire-test", "level": 7}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["book_id"] == "1" and "markdown" in body
    assert body["level"] == 7 and body["extract"] is None


def test_get_book_content_route_livre_inconnu_404(pg_library):
    client = TestClient(create_app({}, pg_dsn=pg_library))
    r = client.get("/libraries/books/9999/content", params={"tag": "grimoire-test"})
    assert r.status_code == 404 and r.json()["error"] == "BookNotFoundError"


def test_get_book_content_route_sans_epub_404(pg_library):
    client = TestClient(create_app({}, pg_dsn=pg_library))
    r = client.get("/libraries/books/2/content", params={"tag": "grimoire-test"})
    assert r.status_code == 404 and r.json()["error"] == "NoEpubError"


def test_get_book_content_route_extract_invalide_400(pg_library):
    client = TestClient(create_app({}, pg_dsn=pg_library))
    r = client.get(
        "/libraries/books/1/content",
        params={"tag": "grimoire-test", "extract": "invalide"},
    )
    assert r.status_code == 400 and r.json()["error"] == "InvalidExtractError"


def test_job_running_devient_interrupted_au_demarrage(pg_library):
    # Simule un job interrompu par un arrêt brutal : 'running' en base avant
    # le démarrage de l'app ; le hook lifespan doit le basculer en
    # 'interrupted' (TestClient en context manager déclenche la lifespan).
    job_id = "8f3a9c00-0000-4000-8000-000000000001"
    with psycopg.connect(pg_library) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (id, library_uuid, action, status)"
                " VALUES (%s, %s, 'convert-markdown', 'running')",
                (job_id, GRIMOIRE_TEST_LIBRARY_UUID),
            )
        conn.commit()

    # App démarrée avec un dict de config vide : en mode PG la récupération ne
    # doit PAS dépendre du dict libraries (déploiement PG réel, dict minimal).
    app = create_app({}, pg_dsn=pg_library)
    with TestClient(app):
        detail = TestClient(app).get(f"/libraries/jobs/{job_id}").json()
    assert detail["status"] == "interrupted"
    assert detail["finished_at"] is not None


def test_post_job_echec_create_job_ferme_le_gateway(pg_library, monkeypatch):
    # Si create_job lève après l'ouverture de la connexion, la route ferme le
    # gateway (sinon fuite de connexion) avant de propager l'erreur.
    closed: list[bool] = []
    original_close = PgLibraryGateway.close

    def failing_create_job(self: PgLibraryGateway, request: object) -> object:
        raise RuntimeError("boom create_job")

    def tracking_close(self: PgLibraryGateway) -> None:
        closed.append(True)
        original_close(self)

    monkeypatch.setattr(PgLibraryGateway, "create_job", failing_create_job)
    monkeypatch.setattr(PgLibraryGateway, "close", tracking_close)

    app = create_app({}, default_tag="grimoire-test", pg_dsn=pg_library)
    client = TestClient(app)
    with pytest.raises(RuntimeError):
        client.post(
            "/libraries/jobs",
            json={"action": "convert-markdown", "book_ids": ["1"]},
        )
    assert closed == [True]
