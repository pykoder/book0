# CLAUDE.md - Working guide for book0-fastapi

> This file is loaded automatically at the start of every session. Keep it **short**: it
> holds only what must be known at all times. Everything task-specific lives in
> `.claude/rules/`, whose files load **on their own** when you touch matching paths (see
> the note at the bottom). Do not grow this file - add a rule under `.claude/rules/` instead.

## Project context

- **Stack**: Python 3.12+, stdlib `sqlite3` (no ORM), stdlib `tomllib`, FastAPI + Pydantic
  (for the HTTP boundary only), `psycopg` (PG mode, via `book0-core`), `pytest`, managed
  with `uv`. No SQLAlchemy, no Alembic - there is no database to migrate, `metadata.db` is
  Calibre's, read-only.
- **Domain**: the FastAPI HTTP service (`book0_api`) serving the book0 REST contract to
  `book0-remote` (see `../book0-cli`), jaquette, and a future Django backend
  (`../book0-django`): `GET /libraries/{books,authors,publishers,series}?tag=...`,
  `POST /libraries/books/detail?tag=...`, `GET /libraries/books/{id}/cover`, plus the
  PG-only write routes. `tag` is optional with a server-side `default-library` fallback
  from `book0-libraries.toml`.
- **Architecture**: `book0_api` is the only package. It depends on `book0-core`
  (`ReadLibraryGateway`/`MutableLibraryGateway` Protocols, `SqliteLibraryGateway`/
  `PgLibraryGateway`, `book0_config` for tag-to-path TOML resolution) as an editable path
  dep, and never imports a CLI or `book0_presentation` - the API returns JSON, it never
  renders a table. The dev group additionally has a path dep on `book0-cli`, used only by
  the REST contract suite (`tests/integration/test_http_gateway.py` drives
  `HttpLibraryGateway` against the real app); the runtime dependency direction is
  unchanged - nothing depends on `book0-cli` at runtime. See
  `.claude/rules/architecture.md`.
- **Age**: greenfield, no technical debt yet. Keep it that way.
- **Cross-cutting goal**: every change must reduce or hold technical debt, never increase it,
  even under deadline pressure.

## Deferred work

`docs/superpowers/TODO.md` tracks work deliberately deferred during brainstorming, code
review, or implementation - bugs identified but not fixed, future directions raised but not
designed, anything explicitly put off rather than actioned. Before starting brainstorming on a
new subject, check it: if any open item looks related to the new subject, or to another open
item, mention it and ask whether to consider them together rather than silently proceeding as
if it weren't there - do not merge or combine items automatically, that decision is made fresh
each time. Brainstorming appends a new line when a design doc's "Out of scope" section defers
something concrete enough to act on later. The commit or plan that actually resolves an item
removes its line - do not let resolved items linger.

## Tooling: uv only

This project is run and managed with **[uv](https://docs.astral.sh/uv/)**. Every Python or
Python-tooling invocation goes through `uv` - never call a bare `python`, `pytest`, `ruff`,
`mypy`, `uvicorn`, `fastapi`, etc. from the shell, and never activate a virtualenv manually.
`uv run` resolves and syncs the environment on the fly, so there is no separate "activate"
step.

| Task | Command |
|---|---|
| Install/sync all deps from the lockfile | `uv sync` |
| Add a runtime dependency | `uv add <package>` |
| Add a dev-only dependency | `uv add --dev <package>` |
| Remove a dependency | `uv remove <package>` |
| Run the API server | `<ENV VARS FOR EACH LIBRARY> uv run book0-api --config book0-libraries.toml --reload` |
| Run the test suite | `uv run pytest` (PG tests need docker) |
| Run a test subset | `uv run pytest tests/unit -v` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type-check | `uv run mypy src` |
| Pin the Python version | `uv python pin 3.12` |
| Run an arbitrary one-off script | `uv run python <script.py>` |

## Absolute prohibitions (always in force, no exception)

These are the single source of truth for the project's hard "never" rules:

- Never ship code without an associated test, even for a "small fix".
- Never disable, comment out, or weaken an existing test to make it pass.
- Never assume a convention without verifying it in the project's real code.
- Never add a pattern or abstraction "because it is cleaner in theory" without a concrete
  need in the requested task (YAGNI).
- Never copy a legacy anti-pattern under the excuse of "consistency with the existing code":
  report the gap and propose better, within the scope requested.
- Never use a mutable default argument (`def f(x: list = [])`) - use `None` + a guard.
- Never let a gateway open a Calibre library for write - `SqliteLibraryGateway` connects
  read-only (`mode=ro`); this tool must never modify a user's Calibre database.
- Never import `book0_cli`, `book0_cli_remote`, or `book0_presentation` in `book0_api` (and
  never make the dev-only `book0-cli` path dep a runtime dependency) - the API depends only
  on `book0-core`; the dependency direction is one-way, so the domain layer stays reusable
  by any future consumer unchanged.
- Never let `book0_api` return a raw `sqlite3.OperationalError` or unmapped 500 for a
  `book0_core` domain error it recognizes (`LibraryNotFoundError`,
  `NotACalibreLibraryError`, `TagRequiredError`) - map it to the documented status code +
  error body so `HttpLibraryGateway` (in `../book0-cli`) can reconstruct the same exception
  client-side.
- Never invoke `python`, `pytest`, `ruff`, `mypy`, `uvicorn`, `fastapi`, etc. directly - always
  through `uv run <tool>` (see the tooling table above), so the locked, synced environment is
  always the one that runs.
- Never perform blocking I/O (a synchronous `sqlite3` call, `requests`, `time.sleep`) inside an
  `async def` FastAPI route - `book0_api`'s routes are plain `def` on purpose, since
  `SqliteLibraryGateway` does blocking I/O and FastAPI runs sync `def` routes in a worker
  thread automatically.
- Never touch code unrelated to the requested change "while you're in there" - keep diffs
  surgical; a bug fix or feature request is not an invitation to also reformat, rename, or
  refactor code the task did not ask about.
- Never declare a task done without checking the result against the original request - re-read
  what was asked and confirm the change actually satisfies it before handing back.

## How the rest of the guide loads

`.claude/rules/` files use Claude Code's native path-scoped rules. Each file declares a
`paths:` frontmatter and loads **automatically** when you read or edit a matching file - you
do not need to open them by hand.

| Rule file | Loads when you touch | Covers |
|---|---|---|
| `.claude/rules/architecture.md` | `src/**`, `tests/**` | Real source tree, layering, dependency direction |
| `.claude/rules/python-design.md` | `src/**/*.py`, `tests/**/*.py` | SOLID, KISS/DRY/YAGNI, patterns, typing + style tooling |
| `.claude/rules/testing.md` | `src/**/*.py`, `tests/**/*.py` | Unit + integration + e2e test requirements |
| `.claude/rules/workflow.md` | `src/**`, `tests/**` | Per-intervention workflow and end-of-task checklist |
