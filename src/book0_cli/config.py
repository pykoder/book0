import os
from pathlib import Path

LOCAL_CONFIG_FILENAME = ".book0.toml"
_XDG_CONFIG_SUBPATH = Path("book0") / "config.toml"


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
