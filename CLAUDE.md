# CLAUDE.md - Working guide for this project

> This file is loaded automatically at the start of every session. Keep it **short**: it
> holds only what must be known at all times. Everything task-specific lives in
> `.claude/rules/`, whose files load **on their own** when you touch matching paths (see
> the note at the bottom). Do not grow this file - add a rule under `.claude/rules/` instead.

## Project context

- **Stack**: Python 3.12+, stdlib `sqlite3` (no ORM), stdlib `argparse` (no web framework),
  `pytest`, managed with `uv`. No SQLAlchemy, no Alembic, no Pydantic, no FastAPI - this is a
  small CLI tool, not a web service.
- **Domain**: a command-line tool that lists the books in a Calibre library by reading the
  library's `metadata.db` SQLite file directly (read-only) - no dependency on `calibredb` or
  the Calibre Content Server. Single consumer: a person running `book0 --library <path>` in a
  terminal.
- **Architecture**: two packages under `src/`, `book0_core` (domain: `Book`, the
  `BookRepository` `Protocol`, the SQLite implementation, domain errors) and `book0_cli`
  (argparse entry point + plain-text table formatting). `book0_cli` depends on `book0_core`;
  `book0_core` depends on nothing project-specific and has no web/HTTP dependency. A future
  `book0_api` (FastAPI) package is planned to expose the same data over HTTP behind a second
  `BookRepository` implementation - it does not exist yet. See
  `.claude/rules/architecture.md` for the real tree and dependency direction.
- **Age**: greenfield, no technical debt yet. Keep it that way.
- **Cross-cutting goal**: every change must reduce or hold technical debt, never increase it,
  even under deadline pressure.

## Tooling: uv only

This project is run and managed with **[uv](https://docs.astral.sh/uv/)**. Every Python or
Python-tooling invocation goes through `uv` - never call a bare `python`, `pytest`, `ruff`,
`mypy`, etc. from the shell, and never activate a virtualenv manually. `uv run` resolves and
syncs the environment on the fly, so there is no separate "activate" step.

| Task | Command |
|---|---|
| Install/sync all deps from the lockfile | `uv sync` |
| Add a runtime dependency | `uv add <package>` |
| Add a dev-only dependency | `uv add --dev <package>` |
| Remove a dependency | `uv remove <package>` |
| Run the CLI | `uv run book0 --library <path>` |
| Run the test suite | `uv run pytest` |
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
- Never let `book0_core` open a Calibre library for write - `SqliteBookRepository` connects
  read-only (`mode=ro`); this tool must never modify a user's Calibre database.
- Never let `book0_core` depend on `book0_cli`, on `argparse`, or on any future web framework -
  the dependency direction is one-way (`book0_cli` -> `book0_core`), so `book0_core` can be
  reused by a future `book0_api` unchanged.
- Never invoke `python`, `pytest`, `ruff`, `mypy`, etc. directly - always through
  `uv run <tool>` (see the tooling table above), so the locked, synced environment is always
  the one that runs.
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
| `.claude/rules/testing.md` | `src/**/*.py`, `tests/**/*.py` | Unit + integration test requirements |
| `.claude/rules/workflow.md` | `src/**`, `tests/**` | Per-intervention workflow and end-of-task checklist |
