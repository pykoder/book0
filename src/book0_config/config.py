import os
import re
import tomllib
from pathlib import Path

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _expand_env_vars(value: str) -> str:
    return _ENV_VAR_PATTERN.sub(lambda match: os.environ[match.group(1)], value)


def load_libraries(config_path: Path) -> dict[str, Path]:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return {
        tag: Path(_expand_env_vars(path)) for tag, path in data["libraries"].items()
    }
