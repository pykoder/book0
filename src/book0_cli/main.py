import argparse
import sys
from pathlib import Path

from book0_cli.config import (
    LOCAL_CONFIG_FILENAME,
    default_library_path,
    find_config_file,
    xdg_config_path,
)
from book0_config.config import load_libraries
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.sqlite_gateway import SqliteLibraryGateway
from book0_presentation.tables import render_table


def _resolve_db_path(library_path: Path) -> Path:
    if library_path.is_dir():
        return library_path / "metadata.db"
    return library_path


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book0")
    parser.add_argument("--tag")
    args = parser.parse_args(argv)

    if args.tag is None:
        library_path = default_library_path()
    else:
        config_path = find_config_file()
        if config_path is None:
            print(
                f"No book0 config file found (looked for ./{LOCAL_CONFIG_FILENAME} "
                f"and {xdg_config_path()})",
                file=sys.stderr,
            )
            return 1

        tagged_library_path = load_libraries(config_path).get(args.tag)
        if tagged_library_path is None:
            print(f"Unknown library tag: {args.tag!r}", file=sys.stderr)
            return 1
        library_path = tagged_library_path

    db_path = _resolve_db_path(library_path)
    gateway = SqliteLibraryGateway(db_path)

    try:
        books = gateway.list_books()
    except (LibraryNotFoundError, NotACalibreLibraryError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print(render_table(books))
    return 0


def main() -> None:
    sys.exit(run())
