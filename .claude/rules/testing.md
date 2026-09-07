---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Testing requirements

No task is done without tests. This is not optional.

## New code

- Write a **unit test** for every new function/class with no I/O (`book0_api/schemas.py`'s
  `from_*` constructors, `filters.py` parsers, `main.py`'s param-normalization helpers) -
  pure logic, no database, no network, no filesystem beyond a temp file the test itself
  creates.
- Write an **e2e test** for every new/changed `book0_api` route, via FastAPI's
  `TestClient` (`fastapi.testclient.TestClient`) driving the real ASGI app built with
  `create_app(...)` - never assert against a mocked route function.
- Write/extend a **contract-suite test** in `tests/integration/test_http_gateway.py` for
  every change to a JSON shape, status code, or error body: it drives the real
  `HttpLibraryGateway` (from the `book0-cli` dev path dep) against the real app, exactly
  like the production consumer does. If the contract suite passes but an e2e test fails
  (or vice versa), the divergence IS the bug.
- To drive the routes or `HttpLibraryGateway` without a real socket, pass a
  `fastapi.testclient.TestClient(app)` instance as the `client`/`httpx.Client` argument -
  it subclasses `httpx.Client` and bridges to the ASGI app synchronously. Plain
  `httpx.Client(transport=httpx.ASGITransport(app=app))` does **not** work for this -
  `ASGITransport` only implements the async transport interface, and the gateway is sync.
- Cover the nominal case, the boundary cases (empty library, an unconfigured tag reported
  as `TagRequiredError`, `NULL` `pubdate`, a book with multiple authors), and the error
  cases (missing file, file exists but is not a Calibre library, and the matching HTTP
  status/body for each) for every route that touches a database.
- Review every conditional branch and exception path before closing the task - in
  particular all response branches in each route (success / `TagRequiredError` 400 /
  `LibraryNotFoundError` 404 / `NotACalibreLibraryError` 500), the `page`/`page_size`/
  `default_page_size` normalization branches, and `book0_api/cli.py::run`'s argument
  branches (`--config` missing, `--reload` given vs. omitted, `--listen` given vs.
  defaulted, `--listen` with an unsupported scheme, `--server-config` given vs. omitted,
  `--server-config` pointing at a missing/unreadable/invalid file, `--listen` taking
  precedence over `--server-config` when both are given).

## Modified existing code

- Update the existing tests to match the new spec 100%.
- Never leave a test green by accident. Never skip a test (`@pytest.mark.skip`,
  `pytest.mark.xfail` used to bypass a real failure) to work around a failure.
- If a test is obsolete because behavior changed intentionally, rewrite it with a clear
  justification in the commit message / reply. Do not just delete it.
- Report any pre-existing coverage gap you find. Do not fix it without asking first if it
  is far outside the requested scope.

## Verification before handing back

- Run the relevant suite (unit + integration + e2e for touched areas) after each change,
  not only at the end.
- For a bugfix, confirm the test is red without the fix and green with it. This proves the
  test actually tests something.
- Do not consider work finished if a test is failing, a test was commented out or deleted
  without justification, or a known business case is left untested.
- When `book0-core`'s models, errors, or Protocols changed, run this repo's suite AND the
  sibling consumers' suites (`cd ../book0-core && uv run pytest`,
  `cd ../book0-cli && uv run pytest`) - a domain change must keep every consumer green.

## Where the suites live

- `tests/unit/` - fast, no I/O, run on every change.
- `tests/integration/test_http_gateway.py` - the REST contract suite
  (`HttpLibraryGateway` vs the real app); run before considering any route/schema change
  done.
- `tests/e2e/` - drives `book0_api`'s routes directly via `TestClient`; run before
  considering an API change done.

## Running tests: always through uv

Every invocation goes through `uv run pytest` - never a bare `pytest` (see the tooling
table in the root `CLAUDE.md`; `uv run` guarantees the synced, locked environment is the
one under test):

- All suites: `uv run pytest`
- One suite/path: `uv run pytest tests/unit -v`
- The contract suite: `uv run pytest tests/integration/test_http_gateway.py -v`
- A single test: `uv run pytest tests/e2e/test_book0_api_main.py::test_books_default_subcommand -v`
