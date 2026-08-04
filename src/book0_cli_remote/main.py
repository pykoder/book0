import argparse
import sys

import httpx

from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_presentation.tables import render_table


def run(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book0-remote")
    parser.add_argument("--server", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)

    owns_client = client is None
    if client is None:
        client = httpx.Client(base_url=args.server)

    try:
        gateway = HttpLibraryGateway(client, args.tag)
        try:
            books = gateway.list_books()
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

    print(render_table(books))
    return 0


def main() -> None:
    sys.exit(run())
