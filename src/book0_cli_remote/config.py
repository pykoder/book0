"""Client-side config discovery/loading for `book0-remote`'s `--server` fallback.

Reads `.book0-client.toml`, a personal/local file (gitignored, not committed) holding a
`server = "http://host:port"` key (required) and an optional `cover-cache-dir = "/path"` key
(falls back to an XDG cache directory when absent) - the schema may grow further, but no other
key is designed yet.
"""

import os
import tomllib
from pathlib import Path

LOCAL_CONFIG_FILENAME = ".book0-client.toml"
_XDG_CONFIG_SUBPATH = Path("book0") / "client.toml"
_XDG_CACHE_SUBPATH = Path("book0") / "covers"


def xdg_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return config_home / _XDG_CONFIG_SUBPATH


def xdg_cache_path() -> Path:
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    cache_home = Path(xdg_cache_home) if xdg_cache_home else Path.home() / ".cache"
    return cache_home / _XDG_CACHE_SUBPATH


def find_config_file() -> Path | None:
    local_config = Path.cwd() / LOCAL_CONFIG_FILENAME
    if local_config.is_file():
        return local_config

    candidate = xdg_config_path()
    if candidate.is_file():
        return candidate

    return None


def load_server(config_path: Path) -> str:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return data["server"]


def load_cover_cache_dir(config_path: Path) -> Path | None:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    value = data.get("cover-cache-dir")
    return Path(value) if value is not None else None
