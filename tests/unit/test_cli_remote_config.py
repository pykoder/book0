import tomllib
from pathlib import Path

import pytest

from book0_cli_remote.config import find_config_file, load_server, xdg_config_path


def test_xdg_config_path_uses_xdg_config_home_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    xdg_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))

    assert xdg_config_path() == xdg_home / "book0" / "client.toml"


def test_xdg_config_path_falls_back_to_home_dot_config_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert xdg_config_path() == tmp_path / ".config" / "book0" / "client.toml"


def test_find_config_file_returns_none_when_neither_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert find_config_file() is None


def test_find_config_file_returns_local_file_when_it_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    local_config = tmp_path / ".book0-client.toml"
    local_config.write_text('server = "http://127.0.0.1:8000"\n')

    assert find_config_file() == local_config


def test_find_config_file_returns_xdg_file_when_local_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    xdg_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))
    xdg_config = xdg_home / "book0" / "client.toml"
    xdg_config.parent.mkdir(parents=True)
    xdg_config.write_text('server = "http://127.0.0.1:8000"\n')

    assert find_config_file() == xdg_config


def test_find_config_file_prefers_local_over_xdg_when_both_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    local_config = tmp_path / ".book0-client.toml"
    local_config.write_text('server = "http://127.0.0.1:8000"\n')
    xdg_config = home / ".config" / "book0" / "client.toml"
    xdg_config.parent.mkdir(parents=True)
    xdg_config.write_text('server = "http://127.0.0.1:8000"\n')

    assert find_config_file() == local_config


def test_load_server_returns_the_server_value(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text('server = "http://192.168.1.5:9000"\n')

    assert load_server(config_path) == "http://192.168.1.5:9000"


def test_load_server_raises_key_error_when_server_key_is_missing(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text("other = 1\n")

    with pytest.raises(KeyError):
        load_server(config_path)


def test_load_server_raises_toml_decode_error_for_invalid_toml(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text("not valid toml === \n")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_server(config_path)
