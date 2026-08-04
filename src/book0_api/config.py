import tomllib
from pathlib import Path


def load_libraries(config_path: Path) -> dict[str, Path]:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return {tag: Path(path) for tag, path in data["libraries"].items()}
