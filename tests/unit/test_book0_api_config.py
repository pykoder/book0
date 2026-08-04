import tomllib
from pathlib import Path

import pytest

from book0_api.config import load_libraries


def test_load_libraries_returns_tag_to_path_mapping(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\nwork = "/path/to/work/metadata.db"\n'
    )

    libraries = load_libraries(config_path)

    assert libraries == {
        "fiction": Path("/path/to/fiction/metadata.db"),
        "work": Path("/path/to/work/metadata.db"),
    }


def test_load_libraries_expands_env_var_placeholders_in_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "${FICTION_LIBRARY_PATH}/metadata.db"\n'
    )
    monkeypatch.setenv("FICTION_LIBRARY_PATH", "/real/fiction")

    libraries = load_libraries(config_path)

    assert libraries == {"fiction": Path("/real/fiction/metadata.db")}


def test_load_libraries_raises_when_referenced_env_var_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text('[libraries]\nfiction = "${FICTION_LIBRARY_PATH}"\n')
    monkeypatch.delenv("FICTION_LIBRARY_PATH", raising=False)

    with pytest.raises(KeyError):
        load_libraries(config_path)


def test_load_libraries_raises_when_file_is_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_libraries(tmp_path / "does-not-exist.toml")


def test_load_libraries_raises_on_malformed_toml(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text("this is not valid toml [[[")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_libraries(config_path)
