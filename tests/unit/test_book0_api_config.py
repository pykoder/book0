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


def test_load_libraries_raises_when_file_is_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_libraries(tmp_path / "does-not-exist.toml")


def test_load_libraries_raises_on_malformed_toml(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text("this is not valid toml [[[")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_libraries(config_path)
