import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


@dataclass(frozen=True)
class LibraryConfig:
    libraries: dict[str, Path]
    default_tag: str | None
    default_page_size: int | None = None


def _expand_env_vars(value: str) -> str:
    return _ENV_VAR_PATTERN.sub(lambda match: os.environ[match.group(1)], value)


def load_libraries(config_path: Path) -> LibraryConfig:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    libraries = {
        tag: Path(_expand_env_vars(path)) for tag, path in data["libraries"].items()
    }
    return LibraryConfig(
        libraries=libraries,
        default_tag=data.get("default-library"),
        default_page_size=data.get("default-page-size"),
    )
