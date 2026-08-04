---
paths:
  - "src/**"
  - "tests/**"
---

# Architecture and real source layout

Before touching a file, identify which package it belongs to. Conventions differ by package.

## Current layout

```
src/
├── book0_core/
│   ├── models.py               # Book: frozen dataclass (id, title, authors, pubdate)
│   ├── errors.py                # LibraryNotFoundError, NotACalibreLibraryError
│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book]
│   └── sqlite_gateway.py          # SqliteLibraryGateway: reads metadata.db read-only
├── book0_presentation/
│   └── tables.py                  # render_table(list[Book]) -> str, aligned plain-text table
├── book0_cli/
│   └── main.py                    # `book0` entry point: --library PATH -> SqliteLibraryGateway
├── book0_api/
│   ├── main.py                    # create_app(libraries: dict[str, Path]) -> FastAPI
│   ├── asgi.py                    # `app` wired from BOOK0_API_CONFIG - the real uvicorn entry point
│   ├── config.py                  # load_libraries(path) -> dict[str, Path], reads a TOML file
│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate
└── book0_cli_remote/
    ├── main.py                    # `book0-remote` entry point: --server URL --tag TAG -> HttpLibraryGateway
    └── http_gateway.py             # HttpLibraryGateway: implements LibraryGateway over HTTP

tests/
├── unit/                          # book0_presentation, book0_core models/errors, book0_api
│                                    # config/schemas - no I/O, no network
├── integration/                    # SqliteLibraryGateway and HttpLibraryGateway against a real
│                                    # temp SQLite file / a real FastAPI app (via TestClient),
│                                    # plus both CLIs' `run()` end to end
└── e2e/                            # book0_api's routes via FastAPI's TestClient
```

`tests/conftest.py` holds the shared Calibre-shaped SQLite fixture (`calibre_metadata_db`) and
its expected `Book` list (`CALIBRE_LIBRARY_BOOKS`) - `book0_core`, `book0_api`, and both CLIs'
tests all build on it rather than each defining their own fixture DB.

## Dependency direction

```
book0_core  <──  book0_presentation  <──┬──  book0_cli
    ↑                                    └──  book0_cli_remote
    │
    └──────────  book0_api
```

- `book0_core` depends on nothing project-specific and has no web/HTTP dependency.
- `book0_presentation` depends only on `book0_core` (needs `Book` for `render_table`'s
  signature). No CLI, no web framework.
- `book0_cli` depends on `book0_core` + `book0_presentation`.
- `book0_api` depends on `book0_core` only. Never imports `book0_cli`, `book0_cli_remote`, or
  `book0_presentation` - the API returns JSON, it never renders a table.
- `book0_cli_remote` depends on `book0_core` + `book0_presentation` + `httpx`. Never imports
  `book0_api` - it only knows the REST contract (a URL and a JSON shape), not the server's
  internals.
- Nothing depends on `book0_cli` or `book0_cli_remote` - both are leaf packages, and neither
  depends on the other. Each has its own full `main.py`; the only thing that differs between
  them, behaviorally, is which `LibraryGateway` implementation gets constructed and which
  flags feed it (`--library PATH` vs. `--server URL --tag TAG`). There is no shared run-loop
  function between them - that was a deliberate choice, not an oversight, so do not "DRY them
  up" into one without a task that asks for it.
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
