import argparse
import sys

import httpx

from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_presentation.tables import render_author_table, render_book_table

_SUBCOMMANDS = ("books", "authors")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0-remote")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--server", required=True)
    books_parser.add_argument("--tag", required=True)

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--server", required=True)
    authors_parser.add_argument("--tag", required=True)

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in ("-h", "--help"):
        return argv
    if not argv or argv[0] not in _SUBCOMMANDS:
        return ["books", *argv]
    return argv


def run(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(_normalize_argv(raw_argv))

    owns_client = client is None
    if client is None:
        client = httpx.Client(base_url=args.server)

    try:
        gateway = HttpLibraryGateway(client, args.tag)
        try:
            if args.command == "authors":
                print(render_author_table(gateway.list_authors()))
            else:
                print(render_book_table(gateway.list_books()))
        except (LibraryNotFoundError, NotACalibreLibraryError) as error:
            print(str(error), file=sys.stderr)
            return 1
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            print(
                f"Could not reach the book0 server at {args.server}: {error}",
                file=sys.stderr,
            )
            return 1
    finally:
        if owns_client:
            client.close()

    return 0


def main() -> None:
    sys.exit(run())
