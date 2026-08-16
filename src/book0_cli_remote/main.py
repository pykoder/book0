import argparse
import sys
import tomllib

import httpx

from book0_cli_remote.config import (
    LOCAL_CONFIG_FILENAME,
    find_config_file,
    load_server,
    xdg_config_path,
)
from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_presentation.tables import (
    format_missing_ids_message,
    order_book_details_by_ids,
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)

_SUBCOMMANDS = ("books", "authors", "publishers", "books-detail")
_SERVER_HELP = (
    "book0-api server URL; omit to use .book0-client.toml's server setting, if found"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0-remote")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--server", help=_SERVER_HELP)
    books_parser.add_argument("--tag")

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--server", help=_SERVER_HELP)
    authors_parser.add_argument("--tag")

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--server", help=_SERVER_HELP)
    publishers_parser.add_argument("--tag")

    books_detail_parser = subparsers.add_parser("books-detail")
    books_detail_parser.add_argument(
        "--ids", required=True, help="comma-separated list of book ids"
    )
    books_detail_parser.add_argument("--server", help=_SERVER_HELP)
    books_detail_parser.add_argument("--tag")

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

    server = args.server
    if server is None:
        config_path = find_config_file()
        if config_path is None:
            print(
                f"No --server given and no book0-remote client config file found "
                f"(looked for ./{LOCAL_CONFIG_FILENAME} and {xdg_config_path()})",
                file=sys.stderr,
            )
            return 1
        try:
            server = load_server(config_path)
        except (tomllib.TOMLDecodeError, KeyError) as error:
            print(
                f"Invalid book0-remote client config file {config_path}: {error}",
                file=sys.stderr,
            )
            return 1

    owns_client = client is None
    if client is None:
        client = httpx.Client(base_url=server)

    try:
        gateway = HttpLibraryGateway(client, args.tag)
        try:
            if args.command == "authors":
                print(render_author_table(gateway.list_authors()))
            elif args.command == "publishers":
                print(render_publisher_table(gateway.list_publishers()))
            elif args.command == "books-detail":
                ids = (
                    [segment.strip() for segment in args.ids.split(",")]
                    if args.ids
                    else []
                )
                result = gateway.get_book_details(ids)
                ordered_books = order_book_details_by_ids(result, ids)
                print(render_book_details_table(ordered_books))
                missing_ids_message = format_missing_ids_message(result.missing_ids)
                if missing_ids_message is not None:
                    print(missing_ids_message)
            else:
                print(render_book_table(gateway.list_books()))
        except (
            LibraryNotFoundError,
            NotACalibreLibraryError,
            TagRequiredError,
        ) as error:
            print(str(error), file=sys.stderr)
            return 1
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            print(
                f"Could not reach the book0 server at {server}: {error}",
                file=sys.stderr,
            )
            return 1
    finally:
        if owns_client:
            client.close()

    return 0


def main() -> None:
    sys.exit(run())
