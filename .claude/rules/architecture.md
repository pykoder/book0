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
│   ├── repository.py            # BookRepository(Protocol): list_books() -> list[Book]
│   └── sqlite_repository.py     # SqliteBookRepository: reads metadata.db read-only
└── book0_cli/
    ├── main.py                  # argparse entry point (`run`/`main`), wires a repository
    └── formatting.py             # renders list[Book] as an aligned plain-text table

tests/
├── unit/                         # book0_cli formatting + book0_core models/errors, no I/O
└── integration/                  # SqliteBookRepository and the CLI against a real temp SQLite file
```

`tests/conftest.py` holds the shared Calibre-shaped SQLite fixture (`calibre_metadata_db`) and
its expected `Book` list (`CALIBRE_LIBRARY_BOOKS`) - both `book0_core` and `book0_cli` tests
build on it rather than each defining their own fixture DB.

## Planned addition: `book0_api`

A FastAPI service is planned to expose the same data over HTTP, plus a second
`BookRepository` implementation (an HTTP client) so a future CLI mode can talk to it instead
of the database directly. Neither exists yet - do not create `book0_api`, FastAPI routes,
Pydantic schemas, or an HTTP-backed repository unless a task explicitly asks for them. When
that work starts, this file must be updated with the real `book0_api` tree before it is used
as a reference.

## Zone rule

- Clean zone (recently written, matches the layout above): align strictly on the existing
  pattern.
- Legacy/inherited zone (inconsistent, pre-dates this convention): do not copy bad practices.
  Propose a compliant version within the requested scope; do not launch an unrequested
  big-bang refactor.
- This project is greenfield - there is no legacy zone yet. If you find one, it was introduced
  after this file was written; report it rather than assuming it is intentional.

## Dependency direction

- `book0_cli` may depend on `book0_core`. `book0_cli/main.py` orchestrates only: parses
  arguments, constructs a repository, calls `formatting.render_table`, prints the result. No
  SQL, no schema knowledge.
- `book0_core` depends on nothing under `book0_cli` and on no web/HTTP framework. This is what
  lets a future `book0_api` reuse `Book`, `BookRepository`, and `SqliteBookRepository`
  unchanged.
- Code that talks to `metadata.db` (SQL, `sqlite3.connect`, schema assumptions) lives only in
  `book0_core/sqlite_repository.py`. Nothing outside it should open a connection or write SQL.
- Anything that consumes books (a CLI command, a future API route) depends on the
  `BookRepository` Protocol, not on `SqliteBookRepository` directly, so a second implementation
  can be substituted without changing the caller.
