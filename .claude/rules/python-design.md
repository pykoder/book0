---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Python design rules

## SOLID

- Give each module one responsibility: `sqlite_gateway.py` reads the database,
  `http_gateway.py` talks HTTP, `main.py` (either CLI) orchestrates, `tables.py` renders,
  `book0_api/main.py` routes requests. Do not let one module do two of these.
- Depend on the `LibraryGateway` `Protocol` from callers, never on `SqliteLibraryGateway` or
  `HttpLibraryGateway` directly - that is the seam that let the HTTP-backed gateway and
  `book0-remote` be added without touching `book0_core` or `book0_cli`.
- Keep every `LibraryGateway` implementation substitutable: `HttpLibraryGateway` must raise
  the exact same `book0_core.errors` exceptions for the same conditions as
  `SqliteLibraryGateway` (a 404 with an `"error": "LibraryNotFoundError"` body becomes a
  `LibraryNotFoundError`, not a generic `HTTPStatusError`) - that substitutability is the
  entire point of the abstraction, not an incidental detail.
- Prefer one small `Protocol` (`LibraryGateway` has a single method) over a catch-all
  interface. Do not add methods to it "for later" - extend it only when a task needs them,
  and when you do, every existing implementation must grow the same method.

## KISS / DRY / YAGNI

- Ship the simplest solution that meets the real need. This is a small pair of CLIs plus a
  minimal API - resist turning it into a framework.
- Do not add configuration, flags, or abstraction layers "just in case" (auth on `book0_api`,
  config hot-reload, a plugin system for output formats) without a concrete requirement in
  the task - see the design docs' "out of scope" sections before assuming something is
  missing by oversight.
- `book0_cli` and `book0_cli_remote` intentionally do not share a run-loop function (see
  `architecture.md`) - do not "fix" this duplication without an explicit task asking for it;
  it was a deliberate design call, not an accident.

## Typing

- Type-hint every function signature (params + return); the codebase has no bare `Any`.
- `book0_core.Book` is a frozen `dataclass` (`@dataclass(frozen=True)`), not a Pydantic model
  - there is no HTTP boundary inside `book0_core`. `book0_api.schemas.BookOut` is where
    Pydantic earns its place: it is the actual wire format for `GET /libraries/{tag}/books`,
    which is the first (and so far only) real HTTP boundary in this project.
- Use `Path` (not `str`) for filesystem paths in function signatures; convert at the
  outermost layer only (`argparse.add_argument(..., type=Path)`, `Path(os.environ[...])` in
  `book0_api/asgi.py`).

## SQLite access

- All SQL lives in `book0_core/sqlite_gateway.py`. One query per gateway method; no building
  SQL from string concatenation with untrusted input (there is none today - keep it that
  way if this ever changes).
- Every connection to a Calibre `metadata.db` is opened read-only
  (`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`). Never open it for write. This
  applies whether the caller is `book0_cli` or `book0_api` - both go through the same
  `SqliteLibraryGateway`.
- Check for the expected schema (`sqlite_master`) before assuming a file is a Calibre library;
  raise `book0_core.errors.NotACalibreLibraryError` rather than letting a raw
  `sqlite3.OperationalError` surface to a caller.

## FastAPI / async correctness

- `book0_api`'s routes are plain `def`, not `async def` - `SqliteLibraryGateway` performs
  blocking `sqlite3` calls, and the project's absolute prohibitions bar blocking I/O inside
  `async def`. FastAPI runs sync `def` routes in a worker thread automatically, which is the
  correct fit here, not a workaround to "fix" later.
- A route that needs to return something other than its declared Pydantic model (e.g. a
  `JSONResponse` with a custom status code alongside a normal `list[BookOut]` on the success
  path) needs `response_model=None` on the route decorator, or FastAPI's automatic response
  model generation raises at import time (`FastAPIError: Invalid args for response field`).
  See `book0_api/main.py::list_books` for the pattern.
- `book0_api/main.py` exposes `create_app(libraries: dict[str, Path]) -> FastAPI` and takes
  no dependency on environment variables or the filesystem beyond that explicit argument -
  all env var / config-file reading lives in `book0_api/asgi.py`. This is what lets tests
  build an app with an arbitrary in-memory `libraries` mapping without touching
  `BOOK0_API_CONFIG` at all. Do not move config loading into `main.py` "for convenience".
- `book0_config/config.py::load_libraries` expands `${VAR_NAME}` placeholders in each path value
  against `os.environ` before returning - this is what lets `book0-libraries.toml` be
  committed with no real filesystem paths in it. A placeholder referencing an unset env var
  raises `KeyError` (uncaught, same "fail fast" philosophy as the missing/malformed config
  file cases) rather than silently leaving the literal `${VAR_NAME}` text in the path or
  falling back to some default.

## Coding standards

- The authoritative style/lint ruleset is **Ruff** (`pyproject.toml`) for both linting and
  formatting, plus **mypy** for type checking. Read the config before writing; conform to it.
- Never leave `print()` debugging behind. Both CLIs' `main.py` print intentionally (it is
  their output and error channel) - that is not debugging output and stays.
- This project is managed with **uv** - every command goes through `uv run`, never a bare
  binary (see the tooling table in the root `CLAUDE.md`). After changes, run:
  - `uv run ruff check .` and `uv run ruff format .`
  - `uv run mypy src`
  and fix every new report before considering the task done.
- Adding or removing a dependency goes through `uv add <package>` / `uv add --dev <package>` /
  `uv remove <package>` - never hand-edit `pyproject.toml`'s dependency list and never `pip
  install` directly, or the lockfile (`uv.lock`) drifts from what is actually installed.
