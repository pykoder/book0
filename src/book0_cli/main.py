import argparse
import sys
from pathlib import Path

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.sqlite_gateway import SqliteLibraryGateway
from book0_presentation.tables import render_table


def _resolve_db_path(library_path: Path) -> Path:
    if library_path.is_dir():
        return library_path / "metadata.db"
    return library_path


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book0")
    parser.add_argument("--library", required=True, type=Path)
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args.library)
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
