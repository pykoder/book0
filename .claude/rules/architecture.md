---
paths:
  - "src/**"
  - "tests/**"
---

# Architecture and real source layout

Before touching a file, identify which package it belongs to. Conventions differ by package.

## Current layout

```
book0-libraries.toml            # committed template for BOOK0_API_CONFIG: ${VAR_NAME}
                                  # placeholders, never real paths - see book0_config/config.py below
src/
├── book0_core/
│   ├── models.py               # Book: frozen dataclass (id, title, authors, pubdate)
│   ├── errors.py                # LibraryNotFoundError, NotACalibreLibraryError
│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book]
│   └── sqlite_gateway.py          # SqliteLibraryGateway: reads metadata.db read-only
├── book0_presentation/
│   └── tables.py                  # render_table(list[Book]) -> str, aligned plain-text table
├── book0_config/
│   └── config.py                  # load_libraries(path) -> dict[str, Path], reads a TOML file;
│                                    # shared by book0_cli and book0_api
├── book0_cli/
│   ├── config.py                  # default_library_path(), xdg_config_path(), find_config_file()
│   └── main.py                    # `book0` entry point: --tag TAG (optional) -> SqliteLibraryGateway
├── book0_api/
│   ├── main.py                    # create_app(libraries: dict[str, Path]) -> FastAPI
│   ├── asgi.py                    # `app` wired from BOOK0_API_CONFIG - the real uvicorn entry point
│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate
└── book0_cli_remote/
    ├── main.py                    # `book0-remote` entry point: --server URL --tag TAG -> HttpLibraryGateway
    └── http_gateway.py             # HttpLibraryGateway: implements LibraryGateway over HTTP
```

`tests/conftest.py` holds the shared Calibre-shaped SQLite fixture (`calibre_metadata_db`) and
its expected `Book` list (`CALIBRE_LIBRARY_BOOKS`) - `book0_core`, `book0_api`, and both CLIs'
tests all build on it rather than each defining their own fixture DB.

## Dependency direction

- `book0_core` depends on nothing project-specific and has no web/HTTP dependency.
- `book0_presentation` depends only on `book0_core` (needs `Book` for `render_table`'s
  signature). No CLI, no web framework.
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
  flags feed it (`--tag TAG`, optional and defaulting to Calibre's own default library path,
  vs. `--server URL --tag TAG`, both required).
- Code that talks to `metadata.db` (SQL, `sqlite3.connect`, schema assumptions) lives only in
  `book0_core/sqlite_gateway.py`. Nothing outside it should open a connection or write SQL -
  including `book0_api`, which calls `SqliteLibraryGateway` exactly like `book0_cli` does.
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
