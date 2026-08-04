# book0_api + remote CLI (design)

## Overview

A second, parallel way to list the books in a Calibre library: a FastAPI server
(`book0_api`) that exposes the same data over HTTP, and a second CLI
(`book0-remote`) that talks to that server via REST instead of touching
`metadata.db` directly. The existing `book0` CLI is untouched in behavior and
keeps reading SQLite directly.

Both CLIs produce identical output for the same underlying data - same table
layout, same "No books found." message, same one-line-stderr-and-exit-1 shape
for errors - because both go through the same abstraction (`LibraryGateway`)
and the same table renderer (`book0_presentation`), just with a different
`LibraryGateway` implementation wired in.

This supersedes the "out of scope" note in
`docs/superpowers/specs/2026-08-03-calibre-book-lister-design.md` that deferred
`book0_api` and a second CLI to later work.

## Architecture

```
src/
├── book0_core/
│   ├── models.py               # Book: id, title, authors (tuple[str, ...]), pubdate (str | None)
│   ├── errors.py                # LibraryNotFoundError, NotACalibreLibraryError
│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book]
│   └── sqlite_gateway.py          # SqliteLibraryGateway(db_path: Path) implementing LibraryGateway
├── book0_presentation/
│   └── tables.py                  # render_table(list[Book]) -> str, aligned plain-text table
├── book0_cli/
│   └── main.py                    # `book0` entry point: --library PATH -> SqliteLibraryGateway
├── book0_api/
│   ├── main.py                    # FastAPI app: GET /libraries/{tag}/books
│   ├── config.py                  # loads BOOK0_API_CONFIG (TOML) -> dict[str, Path]
│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate
└── book0_cli_remote/
    ├── main.py                    # `book0-remote` entry point: --server URL --tag TAG -> HttpLibraryGateway
    └── http_gateway.py             # HttpLibraryGateway(base_url, tag) implementing LibraryGateway
```

Renames from the original design (already-shipped code, no external
consumers yet, so renaming in place is safe):

- `book0_core/repository.py` -> `book0_core/gateway.py`
- `BookRepository` (Protocol) -> `LibraryGateway`
- `book0_core/sqlite_repository.py` -> `book0_core/sqlite_gateway.py`
- `SqliteBookRepository` -> `SqliteLibraryGateway`
- `book0_cli/formatting.py` -> `book0_presentation/tables.py` (new package)
- Matching test files/imports updated throughout.

### Dependency direction

- `book0_core` depends on nothing project-specific and has no web/HTTP
  dependency (unchanged).
- `book0_presentation` depends only on `book0_core` (needs `Book` for
  `render_table`'s signature). No CLI, no web framework.
- `book0_cli` depends on `book0_core` + `book0_presentation`.
- `book0_api` depends on `book0_core` only. Never imports `book0_cli`,
  `book0_cli_remote`, or `book0_presentation` (the API returns JSON, it
  doesn't render tables).
- `book0_cli_remote` depends on `book0_core` + `book0_presentation` +
  `httpx`. Never imports `book0_api` - it only knows the REST contract
  (a URL and a JSON shape), not the server's internals.
- Nothing depends on `book0_cli` or `book0_cli_remote` - both are leaf
  packages. Neither CLI shares a run loop with the other; each has its own
  full `main.py`. The only thing that differs between them, behaviorally, is
  which `LibraryGateway` implementation gets constructed and which
  command-line flags feed it.

## `book0_core` changes

- `repository.py` renamed to `gateway.py`; `BookRepository` renamed to
  `LibraryGateway`, same single method: `list_books(self) -> list[Book]`.
- `sqlite_repository.py` renamed to `sqlite_gateway.py`;
  `SqliteBookRepository` renamed to `SqliteLibraryGateway`. Behavior
  unchanged (read-only connection, `sqlite_master` check,
  `LibraryNotFoundError` / `NotACalibreLibraryError`).
- `models.py` and `errors.py` unchanged.

## `book0_presentation` (new package)

- `tables.py` contains exactly today's `book0_cli/formatting.py` content
  (`render_table`), moved rather than rewritten. `book0_cli/formatting.py` is
  deleted; `book0_cli/main.py` imports `render_table` from
  `book0_presentation.tables` instead.

## `book0_cli` changes

- `main.py` behavior is unchanged. Only its imports change:
  `LibraryGateway`/`SqliteLibraryGateway` from `book0_core`,
  `render_table` from `book0_presentation.tables`.

## `book0_api` (new package)

- Config: `BOOK0_API_CONFIG` environment variable holds the path to a TOML
  file, read once at process startup with the stdlib `tomllib` (no new
  dependency for parsing):

  ```toml
  [libraries]
  fiction = "/path/to/fiction/metadata.db"
  work = "/path/to/work/metadata.db"
  ```

  `config.py` exposes a function that loads this file into
  `dict[str, Path]` (tag -> `metadata.db` path). Missing/unset
  `BOOK0_API_CONFIG`, or a file that fails to parse, is a startup-time
  error (the process should fail fast, not serve with an empty map
  silently) - raised as an unhandled exception at import/startup time, per
  the project's existing "let unexpected errors propagate" philosophy.

- `schemas.py`: `BookOut` (Pydantic `BaseModel`) - `id: int`, `title: str`,
  `authors: list[str]` (JSON has no tuples), `pubdate: str | None`. A small
  `BookOut.from_book(book: Book) -> BookOut` classmethod converts.

- `main.py`: one route, `GET /libraries/{tag}/books`.
  - Route handler is a plain `def` (not `async def`) - `SqliteLibraryGateway`
    performs blocking `sqlite3` I/O, and CLAUDE.md's absolute prohibitions
    bar blocking I/O inside `async def`; FastAPI runs sync `def` routes in a
    worker thread automatically, which is the correct fit here rather than a
    special case.
  - `tag` not present in the loaded config -> respond `200` with `[]`,
    exactly like an empty library. This is a deliberate simplification: an
    unconfigured tag is not distinguished from a configured-but-empty
    library at the API level.
  - `tag` present, `SqliteLibraryGateway(path).list_books()` succeeds ->
    `200` with a JSON array of `BookOut`.
  - `tag` present, gateway raises `LibraryNotFoundError` (configured path
    missing on disk) -> `404`, JSON body
    `{"error": "LibraryNotFoundError", "detail": "<message>"}`.
  - `tag` present, gateway raises `NotACalibreLibraryError` (configured path
    is not a valid Calibre library) -> `500`, JSON body
    `{"error": "NotACalibreLibraryError", "detail": "<message>"}`. This is a
    server misconfiguration, not a client mistake, hence 500 rather than a
    4xx.
  - Any other exception is not caught by the route - it propagates to
    FastAPI's default handling (a 500 with no special body), consistent with
    "unexpected exceptions are not swallowed."

## `book0_cli_remote` (new package)

- `http_gateway.py`: `HttpLibraryGateway` - constructor takes a base server
  URL and a tag; implements `LibraryGateway.list_books()` by calling
  `GET {base_url}/libraries/{tag}/books` via `httpx`.
  - `200` -> parse the JSON array into `Book` objects (`authors` list ->
    tuple).
  - `404` with an `"error": "LibraryNotFoundError"` body -> raise
    `book0_core.errors.LibraryNotFoundError(detail)`.
  - `500` with an `"error": "NotACalibreLibraryError"` body -> raise
    `book0_core.errors.NotACalibreLibraryError(detail)`.
  - Any other HTTP status, or a response body that doesn't match the
    expected error shape, is not specially handled - it surfaces as an
    unhandled exception (`httpx.HTTPStatusError` or similar), same
    "don't mask real bugs" philosophy as the rest of the project.
  - A connection failure or timeout (`httpx.ConnectError`,
    `httpx.TimeoutException`) is *not* wrapped in a `book0_core` error -
    there is no equivalent condition for the direct/SQLite gateway, so this
    is handled directly in `book0_cli_remote/main.py`, not invented as a new
    domain error type.

- `main.py`: entry point `book0-remote`, two required arguments:
  `--server URL` and `--tag TAG`.
  - Builds an `HttpLibraryGateway(server, tag)`, calls `list_books()`,
    renders with `book0_presentation.tables.render_table`, prints to
    stdout - mirroring `book0_cli/main.py`'s structure.
  - Catches `LibraryNotFoundError` / `NotACalibreLibraryError` the same way
    `book0_cli` does: one-line message to stderr, exit code 1.
  - Additionally catches `httpx.ConnectError` / `httpx.TimeoutException`:
    one-line "could not reach the book0 server at `<url>`" message to
    stderr, exit code 1.
  - Any other unexpected exception propagates.

## Testing

- **`book0_core`**: existing tests renamed/updated in place
  (`test_sqlite_repository.py` -> `test_sqlite_gateway.py`, imports and
  class names updated to `LibraryGateway`/`SqliteLibraryGateway`). Coverage
  unchanged: multi-author book, `NULL` pubdate, missing file, non-Calibre
  file, read-only connection.
- **`book0_presentation`**: `tests/unit/test_formatting.py` moves to
  `tests/unit/test_tables.py`, importing `book0_presentation.tables`. Same
  two cases (aligned table, empty-library message).
- **`book0_api`** (new `tests/unit/` cases): `config.py`'s loader against a
  temporary TOML file - valid file returns the expected `dict[str, Path]`;
  missing file or malformed TOML raises. `schemas.py`'s
  `BookOut.from_book` - a `Book` with multiple authors and a `Book` with
  `pubdate=None` both convert as expected (tuple -> list, `None` stays
  `None`).
- **`book0_api`** (new `tests/e2e/` suite): FastAPI `TestClient` against a
  temporary Calibre-shaped SQLite file and a temporary TOML config file
  (`BOOK0_API_CONFIG` pointed at it via `monkeypatch.setenv`). Cases: known
  tag returns the expected `BookOut` list; unknown tag returns `200 []`;
  configured tag with a missing file returns `404` with the
  `LibraryNotFoundError` body; configured tag with a non-Calibre file
  returns `500` with the `NotACalibreLibraryError` body.
- **`book0_cli_remote`** (new `tests/integration/` cases): drive
  `HttpLibraryGateway` / `book0_cli_remote.main.run` against the same
  FastAPI app via `httpx.Client(transport=httpx.ASGITransport(app=app))` -
  no real socket, no separate server process. Cases mirror `book0_cli`'s
  existing tests: known-tag table output, unknown-tag empty message, the
  two error paths (404 -> `LibraryNotFoundError`, 500 ->
  `NotACalibreLibraryError`), and one test for an unreachable server
  (a bogus URL, no ASGI transport) asserting the stderr message and exit
  code 1.

## `.claude` configuration updates

- `CLAUDE.md`: stack line gains FastAPI + httpx; project-context bullet
  describes both CLIs and the API; tooling table gains
  `uv run fastapi dev src/book0_api/main.py` (or
  `uv run uvicorn book0_api.main:app --reload`) and
  `uv run book0-remote --server <url> --tag <tag>`.
- `.claude/rules/architecture.md`: tree updated to the layout above;
  dependency-direction rules extended for `book0_api`, `book0_cli_remote`,
  and `book0_presentation`.
- `.claude/rules/python-design.md`: `LibraryGateway` substitutability rule
  restated for the second real implementation; `BookOut` noted as the first
  legitimate use of Pydantic in this project (HTTP boundary now exists),
  while `book0_core.Book` stays a plain frozen dataclass; async-correctness
  rule gets a concrete example (sync `def` routes for blocking SQLite
  calls).
- `.claude/rules/testing.md`: reinstates `tests/e2e/` for the FastAPI app;
  documents the `ASGITransport` pattern for testing `book0_cli_remote`
  without a real server.
- `.claude/rules/workflow.md`: "New feature" section notes that a change to
  the domain query/output should usually be reflected in both gateways'
  tests, not just one.
- `.claude/settings.local.json`: adds permissions for
  `Bash(uv run fastapi dev *)`, `Bash(uv run uvicorn *)`, and
  `Bash(uv run book0-remote *)`.

## New dependencies

- Runtime: `fastapi`, `uvicorn` (or `fastapi[standard]`), `httpx`.
- No new dev dependency - `httpx`/FastAPI's `TestClient` cover e2e testing.

## Out of scope for this task

- Authentication/authorization on `book0_api`.
- Any transport other than plain HTTP (no TLS setup, no HTTP/2 tuning).
- Config hot-reload (the TOML file is read once at startup).
- Any Calibre metadata beyond id/title/authors/pubdate (unchanged from the
  original design).
- Packaging/distribution.
