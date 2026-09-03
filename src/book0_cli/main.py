import argparse
import sys
import tomllib

from book0_cli.config import LOCAL_CONFIG_FILENAME, find_config_file, xdg_config_path
from book0_config.config import load_libraries
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.gateway import ReadLibraryGateway
from book0_core.sqlite_gateway import SqliteLibraryGateway
from book0_presentation.tables import (
    format_missing_ids_message,
    format_page_footer,
    order_book_details_by_ids,
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)

_SUBCOMMANDS = ("books", "authors", "publishers", "books-detail")
_TAG_HELP = (
    "library tag to look up in a .book0.toml config file; "
    "omit to use the config file's default-library, if set"
)


def _resolve_page_size(
    cli_page_size: int | None, config_page_size: int | None
) -> int | None:
    candidate = cli_page_size if cli_page_size is not None else config_page_size
    return candidate if candidate is not None and candidate > 0 else None


def _resolve_page(cli_page: int | None) -> int:
    return cli_page if cli_page is not None and cli_page > 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--tag", help=_TAG_HELP)
    books_parser.add_argument("--page", type=int, default=None)
    books_parser.add_argument("--page-size", type=int, default=None)

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--tag", help=_TAG_HELP)
    authors_parser.add_argument("--page", type=int, default=None)
    authors_parser.add_argument("--page-size", type=int, default=None)

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--tag", help=_TAG_HELP)
    publishers_parser.add_argument("--page", type=int, default=None)
    publishers_parser.add_argument("--page-size", type=int, default=None)

    books_detail_parser = subparsers.add_parser("books-detail")
    books_detail_parser.add_argument(
        "--ids", required=True, help="comma-separated list of book ids"
    )
    books_detail_parser.add_argument("--tag", help=_TAG_HELP)

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

    config_path = find_config_file()
    if config_path is None:
        print(
            f"No book0 config file found (looked for ./{LOCAL_CONFIG_FILENAME} "
            f"and {xdg_config_path()})",
            file=sys.stderr,
        )
        return 1

    try:
        config = load_libraries(config_path)
    except (tomllib.TOMLDecodeError, KeyError) as error:
        print(f"Invalid book0 config file {config_path}: {error}", file=sys.stderr)
        return 1

    try:
        tag = args.tag if args.tag is not None else config.default_tag
        if tag is None:
            raise TagRequiredError(
                f"No --tag given and no default-library configured in {config_path}"
            )

        library_path = config.libraries.get(tag)
        if library_path is None:
            raise TagRequiredError(f"Unknown library tag: {tag!r}")

        gateway: ReadLibraryGateway = SqliteLibraryGateway(library_path)

        if args.command == "books-detail":
            ids = (
                [segment.strip() for segment in args.ids.split(",")] if args.ids else []
            )
            result = gateway.get_book_details(ids)
            ordered_books = order_book_details_by_ids(result, ids)
            print(render_book_details_table(ordered_books))
            missing_ids_message = format_missing_ids_message(result.missing_ids)
            if missing_ids_message is not None:
                print(missing_ids_message)
        else:
            page_size = _resolve_page_size(args.page_size, config.default_page_size)
            page = _resolve_page(args.page)

            if args.command == "authors":
                if page_size is None:
                    print(render_author_table(gateway.list_authors()))
                else:
                    paged_authors = gateway.list_authors_page(page, page_size)
                    print(render_author_table(list(paged_authors.items)))
                    print(
                        format_page_footer(
                            paged_authors.page, paged_authors.total_pages
                        )
                    )
            elif args.command == "publishers":
                if page_size is None:
                    print(render_publisher_table(gateway.list_publishers()))
                else:
                    paged_publishers = gateway.list_publishers_page(page, page_size)
                    print(render_publisher_table(list(paged_publishers.items)))
                    print(
                        format_page_footer(
                            paged_publishers.page, paged_publishers.total_pages
                        )
                    )
            else:
                if page_size is None:
                    print(render_book_table(gateway.list_books()))
                else:
                    paged_books = gateway.list_books_page(page, page_size)
                    print(render_book_table(list(paged_books.items)))
                    print(format_page_footer(paged_books.page, paged_books.total_pages))
    except (LibraryNotFoundError, NotACalibreLibraryError, TagRequiredError) as error:
        print(str(error), file=sys.stderr)
        return 1

    return 0


def main() -> None:
    sys.exit(run())
