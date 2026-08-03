---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Testing requirements

No task is done without tests. This is not optional.

## New code

- Write a **unit test** for every new function/class with no I/O (`book0_cli/formatting.py`,
  `book0_core/models.py`, `book0_core/errors.py`) - pure logic, no database, no filesystem.
- Write an **integration test** for every new/changed `BookRepository` method or CLI behavior,
  against a real temporary SQLite file built with a minimal Calibre-shaped schema (see
  `tests/conftest.py`'s `calibre_metadata_db` fixture) - never assert against a mocked
  `sqlite3.Connection` for these.
- Cover the nominal case, the boundary cases (empty library, `NULL` `pubdate`, a book with
  multiple authors), and the error cases (missing file, file exists but is not a Calibre
  library) for every path that touches the database or the CLI's error handling.
- Review every conditional branch and exception path before closing the task - in particular
  both branches of `_resolve_db_path` (directory vs. file) and both caught exception types in
  `book0_cli/main.py::run`.

## Modified existing code

- Update the existing tests to match the new spec 100%.
- Never leave a test green by accident. Never skip a test (`@pytest.mark.skip`,
  `pytest.mark.xfail` used to bypass a real failure) to work around a failure.
- If a test is obsolete because behavior changed intentionally, rewrite it with a clear
  justification in the commit message / reply. Do not just delete it.
- Report any pre-existing coverage gap you find. Do not fix it without asking first if it is far
  outside the requested scope.

## Verification before handing back

- Run the relevant suite (unit + integration for touched areas) after each change, not only at
  the end.
- For a bugfix, confirm the test is red without the fix and green with it. This proves the test
  actually tests something.
- Do not consider work finished if a test is failing, a test was commented out or deleted without
  justification, or a known business case is left untested.

## Where the suites live

- `tests/unit/` - fast, no I/O, run on every change.
- `tests/integration/` - hits a real (temporary) SQLite file via `SqliteBookRepository`, or
  drives `book0_cli.main.run` end to end; run before considering a repository/CLI change done.
- There is no `tests/e2e/` - this is a CLI tool, not a web app; `tests/integration/` already
  exercises `run()`/`main()` end to end via `capsys`.

## Running tests: always through uv

Every invocation goes through `uv run pytest` - never a bare `pytest` (see the tooling table
in the root `CLAUDE.md`; `uv run` guarantees the synced, locked environment is the one under
test):

- All suites: `uv run pytest`
- One suite/path: `uv run pytest tests/unit -v`
- With coverage: `uv run pytest --cov=src --cov-report=term-missing`
- A single test: `uv run pytest tests/integration/test_sqlite_repository.py::test_missing_file_raises_library_not_found_error -v`
