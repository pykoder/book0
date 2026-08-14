---
paths:
  - "src/**"
  - "tests/**"
---

# Architecture and real source layout

Before touching a file, identify which package it belongs to. Conventions differ by package.

## Current layout

```
book0-libraries.toml            # committed template for book0-api --config: ${VAR_NAME}
                                  # placeholders, never real paths - see book0_config/config.py below
src/
├── book0_core/
│   ├── models.py               # Book: frozen dataclass (id, title, authors, pubdate);
│                                  # Author/Publisher/Series: frozen dataclass (id, name);
│                                  # SeriesItem (series, index); BookDetails (id, title,
│                                  # pubdate, authors, tags, publisher, series);
│                                  # BookDetailsResult (books, missing_ids)
│   ├── errors.py                # LibraryNotFoundError, NotACalibreLibraryError
│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book],
│                                    # list_authors() -> list[Author],
│                                    # list_publishers() -> list[Publisher],
│                                    # get_book_details(ids) -> BookDetailsResult
│   └── sqlite_gateway.py          # SqliteLibraryGateway: reads metadata.db read-only; resolves
│                                    # a configured directory to <directory>/metadata.db itself,
│                                    # so callers may pass either a library directory or a db file
├── book0_presentation/
│   └── tables.py                  # render_book_table(list[Book]) -> str, render_author_table(list[Author]) -> str,
│                                    # render_publisher_table(list[Publisher]) -> str,
│                                    # render_book_details_table(list[BookDetails]) -> str,
│                                    # aligned plain-text tables; order_book_details_by_ids(
│                                    # BookDetailsResult, ids) -> list[BookDetails] and
│                                    # format_missing_ids_message(missing_ids) -> str | None,
│                                    # shared by both CLIs' books-detail dispatch
├── book0_config/
│   └── config.py                  # load_libraries(path) -> LibraryConfig (libraries:
│                                    # dict[str, Path], default_tag: str | None), reads a TOML
│                                    # file (default_tag from an optional top-level
│                                    # `default-library` key); shared by book0_cli and book0_api
├── book0_cli/
│   ├── config.py                  # default_library_path(), xdg_config_path(), find_config_file()
│   └── main.py                    # `book0` entry point: `books`/`authors`/`publishers`/
│                                    # `books-detail` subcommands (books is the default), --tag
│                                    # TAG (optional, falls back to config's default_tag; raises
│                                    # TagRequiredError if neither is set), --ids (books-detail
│                                    # only, required) -> SqliteLibraryGateway
├── book0_api/
│   ├── main.py                    # create_app(libraries: dict[str, Path], default_tag:
│   │                                # str | None = None) -> FastAPI; routes take `tag` as an
│   │                                # optional `?tag=...` query parameter (not a `{tag}` path
│   │                                # segment), falling back to default_tag, raising
│   │                                # TagRequiredError (mapped to 400) if neither is set
│   ├── asgi.py                    # `app` wired from CONFIG_ENV_VAR (BOOK0_API_CONFIG) - the
│   │                                # real uvicorn import target ("book0_api.asgi:app")
│   ├── cli.py                     # `book0-api` entry point: --config PATH (required), --reload,
│   │                                # --host/--port (default 127.0.0.1:8000) OR --uds PATH (a
│   │                                # Unix domain socket, e.g. for nginx via proxy_pass to
│   │                                # unix:PATH) - mutually exclusive with --host/--port -> sets
│   │                                # BOOK0_API_CONFIG, then uvicorn.run(...)
│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate;
│                                    # AuthorOut/PublisherOut/SeriesOut: id, name;
│                                    # SeriesItemOut: series, index; BookDetailsOut: id, title,
│                                    # pubdate, authors, tags, publisher, series;
│                                    # BookDetailsResultOut: books, missing_ids; BookIdsIn: ids
└── book0_cli_remote/
    ├── main.py                    # `book0-remote` entry point: `books`/`authors`/`publishers`/
    │                                `books-detail` subcommands (books is the default),
    │                                --server URL (required), --tag TAG (optional - an omitted
    │                                tag is sent to the server as no `tag` query parameter, and
    │                                book0_api resolves its own server-side default_tag), --ids
    │                                (books-detail only, required) -> HttpLibraryGateway
    └── http_gateway.py             # HttpLibraryGateway: implements LibraryGateway over HTTP
tests/
├── unit/                          # book0_presentation, book0_core models/errors, book0_config's
│                                    # loader, book0_api's schemas - no I/O, no network
├── integration/                    # SqliteLibraryGateway and HttpLibraryGateway against a real
│                                    # temp SQLite file / a real FastAPI app (via TestClient),
│                                    # plus both CLIs' `run()` end to end
└── e2e/                            # book0_api's routes via FastAPI's TestClient
```

`tests/conftest.py` holds the shared Calibre-shaped SQLite fixture (`calibre_metadata_db`) and
its expected `Book` list (`CALIBRE_LIBRARY_BOOKS`), `Author` list (`CALIBRE_LIBRARY_AUTHORS`),
`Publisher` list (`CALIBRE_LIBRARY_PUBLISHERS`), and three named `BookDetails` fixtures
(`DUNE_DETAILS`, `HOBBIT_DETAILS`, `GOOD_OMENS_DETAILS`) - `book0_core`, `book0_api`, and both
CLIs' tests all build on it rather than each defining their own fixture DB.

## Dependency direction

- `book0_core` depends on nothing project-specific and has no web/HTTP dependency.
- `book0_presentation` depends only on `book0_core` (needs `Book`/`Author`/`Publisher`/
  `BookDetails`/`BookDetailsResult` for `render_book_table`'s/`render_author_table`'s/
  `render_publisher_table`'s/`render_book_details_table`'s/`order_book_details_by_ids`'s
  signatures). No CLI, no web framework.
- `book0_config` depends on nothing project-specific - stdlib only (`tomllib`, `os`, `re`,
  `pathlib`).
- `book0_cli` depends on `book0_core`, `book0_presentation`, **and `book0_config`** - directly
  on `book0_core` (for `SqliteLibraryGateway` and the domain errors), not merely transitively
  through `book0_presentation`.
- `book0_api` depends on `book0_core` **and `book0_config`**. Never imports `book0_cli`,
  `book0_cli_remote`, or `book0_presentation` - the API returns JSON, it never renders a
  table.
- `book0_cli_remote` depends on `book0_core` + `book0_presentation` + `httpx`. Never imports
  `book0_api` or `book0_config` - it only knows the REST contract (a URL and a JSON shape),
  not the server's internals or how tags get resolved to paths.
- Nothing depends on `book0_cli` or `book0_cli_remote` - both are leaf packages, and neither
  depends on the other. Each has its own full `main.py`; the only thing that differs between
  them, behaviorally, is which `LibraryGateway` implementation gets constructed and which
  flags feed it (`--tag TAG`, optional and falling back to the config file's `default-library`,
  vs. `--server URL` (required) `--tag TAG` (optional, server resolves its own
  `default-library`)). Neither CLI shares a run loop with the other -
  there is no shared run-loop function between them. That was a deliberate choice, not an
  oversight, so do not "DRY them up" into one without a task that asks for it.
- Code that talks to `metadata.db` (SQL, `sqlite3.connect`, schema assumptions, the
  `metadata.db` filename itself) lives only in `book0_core/sqlite_gateway.py`. Nothing outside
  it should open a connection, write SQL, or resolve a library directory to its db file -
  including `book0_api`, which calls `SqliteLibraryGateway` exactly like `book0_cli` does, and
  both CLIs' config files (`.book0.toml`, `book0-libraries.toml`) may name either a library
  directory or a `metadata.db` file directly - `SqliteLibraryGateway.__init__` resolves that,
  not the callers.
- Anything that consumes books (either CLI, a future third consumer) depends on the
  `LibraryGateway` Protocol, not on a concrete implementation, so a gateway can be substituted
  without changing the caller.

## Zone rule

- Clean zone (recently written, matches the layout above): align strictly on the existing
  pattern.
- Legacy/inherited zone (inconsistent, pre-dates this convention): do not copy bad practices.
  Propose a compliant version within the requested scope; do not launch an unrequested
  big-bang refactor.
- This project is greenfield - there is no legacy zone yet. If you find one, it was introduced
  after this file was written; report it rather than assuming it is intentional.
