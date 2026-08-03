# CLAUDE.md - Working guide for this project

> This file is loaded automatically at the start of every session. Keep it **short**: it
> holds only what must be known at all times. Everything task-specific lives in
> `.claude/rules/`, whose files load **on their own** when you touch matching paths (see
> the note at the bottom). Do not grow this file - add a rule under `.claude/rules/` instead.

## Project context

- **Stack**: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic migrations,
  pytest. *(Adapt to the real stack: swap SQLAlchemy for another ORM/driver, add Celery/RQ,
  message brokers, etc. as the project actually uses them.)*
- **Domain**: *(fill in - one or two sentences on what this service does and who calls it:
  internal API, public API, background worker, which personas/consumers.)*
- **Architecture**: layered by default - `api/` (routers), `services/` (business logic),
  `repositories/` (data access), `schemas/` (Pydantic I/O models), `models/` (ORM entities).
  If the project grows a DDD-style split instead (`domain/`, `application/`,
  `infrastructure/`), update `.claude/rules/architecture.md` to match and delete this note.
- **Age**: *(fill in once real - greenfield has no technical debt yet; keep it that way.
  Once the project ages, note here where debt tends to accumulate.)*
- **Cross-cutting goal**: every change must reduce or hold technical debt, never increase it,
  even under deadline pressure.

## Tooling: uv only

This project is run and managed with **[uv](https://docs.astral.sh/uv/)**. Every Python or
Python-tooling invocation goes through `uv` - never call a bare `python`, `pip`, `pytest`,
`ruff`, `mypy`, etc. from the shell, and never activate a virtualenv manually. `uv run`
resolves and syncs the environment on the fly, so there is no separate "activate" step.

| Task | Command |
|---|---|
| Install/sync all deps from the lockfile | `uv sync` |
| Add a runtime dependency | `uv add fastapi` |
| Add a dev-only dependency | `uv add --dev pytest ruff mypy` |
| Remove a dependency | `uv remove <package>` |
| Run the app (dev, autoreload) | `uv run fastapi dev app/main.py` |
| Run the app (prod-style) | `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Run the test suite | `uv run pytest` |
| Run a test subset | `uv run pytest tests/unit -v` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type-check | `uv run mypy app` |
| Run an Alembic migration | `uv run alembic upgrade head` |
| Generate an Alembic revision | `uv run alembic revision --autogenerate -m "<message>"` |
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
- Never perform blocking I/O (sync DB driver calls, `requests`, `time.sleep`) inside an
  `async def` route or service - it blocks the whole event loop.
- Never invoke `python`, `pip`, `pytest`, `ruff`, `mypy`, `alembic`, etc. directly - always
  through `uv run <tool>` (see the tooling table above), so the locked, synced environment is
  always the one that runs.
- Never touch code unrelated to the requested change "while you're in there" - keep diffs
  surgical; a bug fix or feature request is not an invitation to also reformat, rename, or
  refactor code the task did not ask about.
- Never declare a task done without checking the result against the original request - re-read
  what was asked and confirm the change actually satisfies it before handing back.
- *(Add project-specific frozen/deprecated zones here as they appear, the way `med` flags
  `src/Repository/StoppedProducts/` as never a style reference.)*

## How the rest of the guide loads

`.claude/rules/` files use Claude Code's native path-scoped rules. Each file declares a
`paths:` frontmatter and loads **automatically** when you read or edit a matching file - you
do not need to open them by hand.

| Rule file | Loads when you touch | Covers |
|---|---|---|
| `.claude/rules/architecture.md` | `app/**`, `tests/**` | Real source tree, layering, dependency direction |
| `.claude/rules/python-design.md` | `app/**/*.py`, `tests/**/*.py` | SOLID, KISS/DRY/YAGNI, patterns, typing + style tooling |
| `.claude/rules/testing.md` | `app/**/*.py`, `tests/**/*.py` | Unit + integration + e2e test requirements |
| `.claude/rules/workflow.md` | `app/**`, `tests/**` | Per-intervention workflow and end-of-task checklist |
