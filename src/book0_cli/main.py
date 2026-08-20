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
from book0_core.sqlite_gateway import SqliteLibraryGateway
from book0_presentation.tables import (
    format_missing_ids_message,
    order_book_details_by_ids,
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_page_footer,
    render_publisher_table,
)

_SUBCOMMANDS = ("books", "authors", "publishers", "books-detail")
_TAG_HELP = (
    "library tag to look up in a .book0.toml config file; "
    "omit to use the config file's default-library, if set"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--tag", help=_TAG_HELP)
    books_parser.add_argument("--page", type=int, help="page number (1-based)")
    books_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--tag", help=_TAG_HELP)
    authors_parser.add_argument("--page", type=int, help="page number (1-based)")
    authors_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--tag", help=_TAG_HELP)
    publishers_parser.add_argument("--page", type=int, help="page number (1-based)")
    publishers_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

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

        gateway = SqliteLibraryGateway(library_path)

        page_size = getattr(args, "page_size", None)
        if page_size is None:
            page_size = config.default_page_size
        if page_size is not None and page_size <= 0:
            page_size = None
        page = getattr(args, "page", None)
        if page is None:
            page = 1
        if page <= 0:
            page = 1

        if args.command == "authors":
            if page_size is not None:
                paged_authors = gateway.list_authors_page(page, page_size)
                print(render_author_table(list(paged_authors.items)))
                print(render_page_footer(paged_authors.page, paged_authors.total_pages))
            else:
                print(render_author_table(gateway.list_authors()))
        elif args.command == "publishers":
            if page_size is not None:
                paged_publishers = gateway.list_publishers_page(page, page_size)
                print(render_publisher_table(list(paged_publishers.items)))
                print(
                    render_page_footer(
                        paged_publishers.page, paged_publishers.total_pages
                    )
                )
            else:
                print(render_publisher_table(gateway.list_publishers()))
        elif args.command == "books-detail":
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
            if page_size is not None:
                paged_books = gateway.list_books_page(page, page_size)
                print(render_book_table(list(paged_books.items)))
                print(render_page_footer(paged_books.page, paged_books.total_pages))
            else:
                print(render_book_table(gateway.list_books()))
    except (LibraryNotFoundError, NotACalibreLibraryError, TagRequiredError) as error:
        print(str(error), file=sys.stderr)
        return 1

    return 0


def main() -> None:
    sys.exit(run())
