---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Python design rules

## SOLID

- Give each module one responsibility: `sqlite_gateway.py` (in book0-core) reads the
  database, `main.py` routes requests, `schemas.py` defines the wire format,
  `filters.py` parses filter params, `cli.py` wires uvicorn. Do not let one module do two
  of these.
- Depend on the `ReadLibraryGateway`/`MutableLibraryGateway` Protocols from book0-core in
  callers, never on a concrete implementation where the abstraction matters - the routes
  construct `SqliteLibraryGateway`/`PgLibraryGateway` at exactly one point
  (`_resolve_gateway`), which is the seam a future backend swap would touch.
- The API is substitutable for nothing - it is a leaf server. Its contract
  substitutability flows the other way: it must emit shapes that let `HttpLibraryGateway`
  (in `../book0-cli`) reconstruct the exact domain exceptions client-side.

## KISS / DRY / YAGNI

- Ship the simplest solution that meets the real need. This is a minimal API - resist
  turning it into a framework.
- Do not add configuration, flags, or abstraction layers "just in case" (auth on
  `book0_api`, config hot-reload, a plugin system for output formats) without a concrete
  requirement in the task - see the design docs' "out of scope" sections before assuming
  something is missing by oversight.
- `book0_api` returns JSON and never renders text tables - never import
  `book0_presentation` "to reuse formatting".

## Typing

- Type-hint every function signature (params + return); the codebase has no bare `Any`.
- `book0_core.Book` is a frozen `dataclass`, not a Pydantic model - there is no HTTP
  boundary inside `book0_core`. `book0_api/schemas.py` is where Pydantic earns its place:
  it is the actual wire format for every route.
- A route that needs to return something other than its declared Pydantic model (e.g. a
  `JSONResponse` with a custom status code alongside a normal `list[BookOut]` on the
  success path) needs `response_model=None` on the route decorator, or FastAPI's automatic
  response model generation raises at import time. See `book0_api/main.py::list_books` for
  the pattern.
- Use `Path` (not `str`) for filesystem paths in function signatures; convert at the
  outermost layer only (`Path(os.environ[...])` in `book0_api/asgi.py`,
  `Path(_expand_env_vars(path))` in `book0_config/config.py::load_libraries`).

## SQLite access

- All SQL lives in `book0-core`'s `sqlite_gateway.py` (SQLite) and `pg_gateway.py` (PG).
  Never open a connection, write SQL, or resolve a library directory to its db file in
  this repo.
- Every connection to a Calibre `metadata.db` is opened read-only by the gateway. Never
  open it for write.
- A non-Calibre file must surface as `book0_core.errors.NotACalibreLibraryError` (mapped
  to 500 with the error body), never a raw `sqlite3.OperationalError`.

## FastAPI / async correctness

- `book0_api`'s routes are plain `def`, not `async def` - the gateways perform blocking
  I/O, and the project's absolute prohibitions bar blocking I/O inside `async def`.
  FastAPI runs sync `def` routes in a worker thread automatically, which is the correct
  fit here, not a workaround to "fix" later.
- `create_app(libraries, default_tag, default_page_size, pg_dsn, markdown_cache_dir)`
  takes no dependency on environment variables or the filesystem beyond its explicit
  arguments - all env var / config-file reading lives in `book0_api/asgi.py` and
  `book0_api/cli.py`. This is what lets tests build an app with an arbitrary in-memory
  `libraries` mapping without touching `BOOK0_API_CONFIG` at all. Do not move config
  loading into `main.py` "for convenience".
- `book0_config/config.py::load_libraries` expands `${VAR_NAME}` placeholders in each path
  value against `os.environ` before returning - this is what lets `book0-libraries.toml`
  be committed with no real filesystem paths in it. A placeholder referencing an unset env
  var raises `KeyError` (uncaught, same "fail fast" philosophy as the missing/malformed
  config file cases) rather than silently leaving the literal `${VAR_NAME}` text in the
  path.

## Coding standards

- The authoritative style/lint ruleset is **Ruff** (`pyproject.toml`) for both linting and
  formatting, plus **mypy** for type checking. Read the config before writing; conform to
  it.
- Never leave `print()` debugging behind. `book0_api/cli.py` prints intentionally (it is
  the launcher's output channel) - that is not debugging output and stays.
- This project is managed with **uv** - every command goes through `uv run`, never a bare
  binary (see the tooling table in the root `CLAUDE.md`). After changes, run:
  - `uv run ruff check .` and `uv run ruff format .`
  - `uv run mypy src`
  and fix every new report before considering the task done.
- Adding or removing a dependency goes through `uv add <package>` / `uv add --dev
  <package>` / `uv remove <package>` - never hand-edit `pyproject.toml`'s dependency list
  and never `pip install` directly, or the lockfile (`uv.lock`) drifts from what is
  actually installed.
