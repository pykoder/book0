---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Testing requirements

No task is done without tests. This is not optional.

## New code

- Write a **unit test** for every new function/class with no I/O
  (`book0_presentation/tables.py`, `book0_core/models.py`, `book0_core/errors.py`,
  `book0_config/config.py`'s loader, `book0_api/schemas.py`'s `BookOut.from_book`) - pure logic,
  no database, no network, no filesystem beyond a temp file the test itself creates.
- Write an **integration test** for every new/changed `LibraryGateway` method or CLI
  behavior, against a real temporary SQLite file built with a minimal Calibre-shaped schema
  (see `tests/conftest.py`'s `calibre_metadata_db` fixture) - never assert against a mocked
  `sqlite3.Connection` or a mocked `httpx` response for these.
- Write an **e2e test** for every new/changed `book0_api` route, via FastAPI's `TestClient`
  (`fastapi.testclient.TestClient`) driving the real ASGI app - never assert against a
  mocked route function.
- To drive `HttpLibraryGateway` or `book0_cli_remote.main.run` against a real `book0_api` app
  without a real socket, pass a `fastapi.testclient.TestClient(app)` instance as the
  `client`/`httpx.Client` argument - it subclasses `httpx.Client` and bridges to the ASGI app
  synchronously. Plain `httpx.Client(transport=httpx.ASGITransport(app=app))` does **not**
  work for this - `ASGITransport` only implements the async transport interface, and both
  gateways are sync.
- Cover the nominal case, the boundary cases (empty library, an unconfigured tag treated as
  an empty library (book0_api/book0-remote only - book0_cli's --tag reports an unconfigured
  tag as an error), `NULL` `pubdate`, a book with multiple authors), and the error cases
  (missing file, file exists but is not a Calibre library, and for the remote path: the
  matching HTTP status/body, plus an unreachable server) for every path that touches the
  database, the API, or either CLI's error handling.
- Review every conditional branch and exception path before closing the task - in
  particular `book0_cli/main.py::run`'s tag-resolution branches (`--tag` omitted vs.
  given, config file found vs. not found, tag present vs. absent in a found config
  file), both branches of `SqliteLibraryGateway.__init__`'s directory-vs-file resolution,
  both caught exception types in either CLI's `run()`, and all three response branches in
  each of `book0_api/main.py`'s routes (`list_books`, `list_authors`, `list_publishers`
  today) - unknown tag, `LibraryNotFoundError`, `NotACalibreLibraryError` - and
  `book0_api/cli.py::run`'s argument branches (`--config` missing, `--reload` given vs.
  omitted, `--host`/`--port` given vs. defaulted, `--uds` given alone vs. combined with
  `--host`/`--port` - the latter must be rejected).

## Modified existing code

- Update the existing tests to match the new spec 100%.
- Never leave a test green by accident. Never skip a test (`@pytest.mark.skip`,
  `pytest.mark.xfail` used to bypass a real failure) to work around a failure.
- If a test is obsolete because behavior changed intentionally, rewrite it with a clear
  justification in the commit message / reply. Do not just delete it.
- Report any pre-existing coverage gap you find. Do not fix it without asking first if it is far
  outside the requested scope.

## Verification before handing back

- Run the relevant suite (unit + integration + e2e for touched areas) after each change, not
  only at the end.
- For a bugfix, confirm the test is red without the fix and green with it. This proves the test
  actually tests something.
- Do not consider work finished if a test is failing, a test was commented out or deleted without
  justification, or a known business case is left untested.

## Where the suites live

- `tests/unit/` - fast, no I/O, run on every change.
- `tests/integration/` - hits a real (temporary) SQLite file via `SqliteLibraryGateway`, or a
  real FastAPI app (via `TestClient`) via `HttpLibraryGateway`, or drives either CLI's
  `run()` end to end; run before considering a gateway/CLI change done.
- `tests/e2e/` - drives `book0_api`'s routes directly via `TestClient`; run before
  considering an API change done.

## Running tests: always through uv

Every invocation goes through `uv run pytest` - never a bare `pytest` (see the tooling table
in the root `CLAUDE.md`; `uv run` guarantees the synced, locked environment is the one under
test):

- All suites: `uv run pytest`
- One suite/path: `uv run pytest tests/unit -v`
- With coverage: `uv run pytest --cov=src --cov-report=term-missing`
- A single test: `uv run pytest tests/integration/test_sqlite_gateway.py::test_missing_file_raises_library_not_found_error -v`
