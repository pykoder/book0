"""Client-side config discovery/loading for `book0-remote`'s `--server` fallback.

Reads `.book0-client.toml`, a personal/local file (gitignored, not committed) holding a
single `server = "http://host:port"` key today - the schema may grow beyond that one key
later, but no other key is designed yet.
"""

import os
import tomllib
from pathlib import Path

LOCAL_CONFIG_FILENAME = ".book0-client.toml"
_XDG_CONFIG_SUBPATH = Path("book0") / "client.toml"


def xdg_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return config_home / _XDG_CONFIG_SUBPATH


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
