import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from book0_api.cli import CONFIG_ENV_VAR


def test_asgi_app_resolves_default_tag_from_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_path = tmp_path / "book0-libraries.toml"
    config_path.write_text(
        f'default-library = "fiction"\n\n'
        f'[libraries]\nfiction = "{calibre_metadata_db}"\n'
    )
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_path))

    from book0_api import asgi

    importlib.reload(asgi)

    client = TestClient(asgi.app)
    response = client.get("/libraries/books")

    assert response.status_code == 200
