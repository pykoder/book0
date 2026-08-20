import tomllib
from pathlib import Path

import pytest

from book0_config.config import LibraryConfig, load_libraries


def test_load_libraries_returns_tag_to_path_mapping_with_no_default_tag(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\nwork = "/path/to/work/metadata.db"\n'
    )

    config = load_libraries(config_path)

    assert config == LibraryConfig(
        libraries={
            "fiction": Path("/path/to/fiction/metadata.db"),
            "work": Path("/path/to/work/metadata.db"),
        },
        default_tag=None,
    )


def test_load_libraries_reads_default_library_when_present(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        'default-library = "fiction"\n\n'
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\n'
    )

    config = load_libraries(config_path)

    assert config.default_tag == "fiction"


def test_load_libraries_expands_env_var_placeholders_in_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "${FICTION_LIBRARY_PATH}/metadata.db"\n'
    )
    monkeypatch.setenv("FICTION_LIBRARY_PATH", "/real/fiction")

    config = load_libraries(config_path)

    assert config.libraries == {"fiction": Path("/real/fiction/metadata.db")}


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


def test_load_libraries_returns_none_default_page_size_when_absent(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text('[libraries]\nfiction = "/path/to/fiction/metadata.db"\n')

    config = load_libraries(config_path)

    assert config.default_page_size is None


def test_load_libraries_reads_default_page_size_when_present(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        "default-page-size = 25\n\n"
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\n'
    )

    config = load_libraries(config_path)

    assert config.default_page_size == 25
