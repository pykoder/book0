import argparse
import sys
import tomllib
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
from book0_presentation.tables import render_author_table, render_book_table

_SUBCOMMANDS = ("books", "authors")
_TAG_HELP = (
    "library tag to look up in a .book0.toml config file; "
    "omit to use Calibre's default library"
)


def _resolve_db_path(library_path: Path) -> Path:
    if library_path.is_dir():
        return library_path / "metadata.db"
    return library_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--tag", help=_TAG_HELP)

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--tag", help=_TAG_HELP)

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in ("-h", "--help"):
        return argv
    if not argv or argv[0] not in _SUBCOMMANDS:
        return ["books", *argv]
    return argv


def run(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(_normalize_argv(raw_argv))

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

        try:
            libraries = load_libraries(config_path)
        except (tomllib.TOMLDecodeError, KeyError) as error:
            print(f"Invalid book0 config file {config_path}: {error}", file=sys.stderr)
            return 1

        tagged_library_path = libraries.get(args.tag)
        if tagged_library_path is None:
            print(f"Unknown library tag: {args.tag!r}", file=sys.stderr)
            return 1
        library_path = tagged_library_path

    db_path = _resolve_db_path(library_path)
    gateway = SqliteLibraryGateway(db_path)

    try:
        if args.command == "authors":
            print(render_author_table(gateway.list_authors()))
        else:
            print(render_book_table(gateway.list_books()))
    except (LibraryNotFoundError, NotACalibreLibraryError) as error:
        print(str(error), file=sys.stderr)
        return 1

    return 0


def main() -> None:
    sys.exit(run())
