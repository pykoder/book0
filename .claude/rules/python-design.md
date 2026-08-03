---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Python design rules

## SOLID

- Give each module one responsibility: `sqlite_repository.py` reads the database, `main.py`
  orchestrates the CLI, `formatting.py` renders text. Do not let one module do two of these.
- Depend on the `BookRepository` `Protocol` from callers (`book0_cli`), never on
  `SqliteBookRepository` directly - that is the seam that lets a future HTTP-backed repository
  be substituted without touching `book0_cli`.
- Keep any future second `BookRepository` implementation substitutable: it must raise the same
  `book0_core.errors` exceptions for the same conditions, not a different exception type just
  because the underlying transport (HTTP vs. SQLite) differs.
- Prefer one small `Protocol` (`BookRepository` has a single method) over a catch-all
  interface. Do not add methods to it "for later" - extend it only when a task needs them.

## KISS / DRY / YAGNI

- Ship the simplest solution that meets the real need. This is a single-purpose CLI - resist
  turning it into a framework.
- Do not add configuration, flags, or abstraction layers "just in case" (e.g. a plugin system
  for output formats, a config file format) without a concrete requirement in the task.
- Do not build the `book0_api` package, an HTTP client repository, or async code ahead of a
  task that actually asks for them - the Protocol seam exists so that work is additive later,
  not so it should be pre-built now.

## Typing

- Type-hint every function signature (params + return); the codebase has no bare `Any`.
- `Book` is a frozen `dataclass` (`@dataclass(frozen=True)`), not a Pydantic model - there is
  no HTTP boundary yet to justify Pydantic's validation/serialization machinery. If/when
  `book0_api` is built, its request/response schemas are the place for Pydantic, not
  `book0_core`.
- Use `Path` (not `str`) for filesystem paths in function signatures; convert at the outermost
  layer only (`argparse.add_argument(..., type=Path)`).

## SQLite access

- All SQL lives in `book0_core/sqlite_repository.py`. One query per repository method; no
  building SQL from string concatenation with untrusted input (there is none today - keep it
  that way if this ever changes).
- Every connection to a Calibre `metadata.db` is opened read-only
  (`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`). Never open it for write.
- Check for the expected schema (`sqlite_master`) before assuming a file is a Calibre library;
  raise `book0_core.errors.NotACalibreLibraryError` rather than letting a raw
  `sqlite3.OperationalError` surface to the CLI.

## Coding standards

- The authoritative style/lint ruleset is **Ruff** (`pyproject.toml`) for both linting and
  formatting, plus **mypy** for type checking. Read the config before writing; conform to it.
- Never leave `print()` debugging behind. `book0_cli/main.py` prints intentionally (it is the
  CLI's output and error channel) - that is not debugging output and stays.
- This project is managed with **uv** - every command goes through `uv run`, never a bare
  binary (see the tooling table in the root `CLAUDE.md`). After changes, run:
  - `uv run ruff check .` and `uv run ruff format .`
  - `uv run mypy src`
  and fix every new report before considering the task done.
- Adding or removing a dependency goes through `uv add <package>` / `uv add --dev <package>` /
  `uv remove <package>` - never hand-edit `pyproject.toml`'s dependency list and never `pip
  install` directly, or the lockfile (`uv.lock`) drifts from what is actually installed.
