---
paths:
  - "app/**/*.py"
  - "tests/**/*.py"
---

# Testing requirements

No task is done without tests. This is not optional.

## New code

- Write a **unit test** for every new function/class carrying business logic (mock/fake
  dependencies via `Protocol`/ABC fakes or `unittest.mock`, full isolation from the DB and
  network).
- Write an **integration test** for every new repository method or DB-facing query, against a
  real test database (containerized Postgres, or the project's configured test DB - never
  assert against a mocked ORM session for these).
- Write an **e2e test** for every new endpoint, via `httpx.AsyncClient`/FastAPI `TestClient`,
  exercising the real route, dependency overrides only for external third parties (payment
  providers, external APIs), not for the app's own layers.
- Cover the nominal case, the boundary cases (empty, null/`None`, limits, pagination edges), the
  business-error cases (validation, permissions, inconsistent states -> correct HTTP status),
  and the technical-error cases when relevant (timeout, simulated dependency failure).
- Review every conditional branch and exception path before closing the task.

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
- `tests/integration/` - hits a real (test) database, run before considering a repository/DB
  change done.
- `tests/e2e/` - full app through HTTP, run before considering an endpoint change done.

## Running tests: always through uv

Every invocation goes through `uv run pytest` - never a bare `pytest` (see the tooling table
in the root `CLAUDE.md`; `uv run` guarantees the synced, locked environment is the one under
test):

- All suites: `uv run pytest`
- One suite/path: `uv run pytest tests/unit -v`
- By marker (or the project's actual markers - check `pyproject.toml`/`pytest.ini` for the
  real names and async config (`asyncio_mode`) before assuming these exact ones apply):
  `uv run pytest -m unit`, `uv run pytest -m integration`, `uv run pytest -m e2e`
- With coverage: `uv run pytest --cov=app --cov-report=term-missing`
- A single test: `uv run pytest tests/unit/test_patients_service.py::test_create_patient -v`
