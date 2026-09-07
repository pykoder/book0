---
paths:
  - "src/**"
  - "tests/**"
---

# Workflow: understand before writing

Before any change, fix, or addition, always:

1. **Explore the nearby code.** Read the module you are about to touch and the
   corresponding gateway method in `../book0-core` if relevant, to identify:
   - the naming conventions actually used;
   - how errors are raised in `book0_core`, mapped to HTTP in `book0_api/main.py`, and
     reconstructed in `../book0-cli`'s `http_gateway.py`;
   - how existing tests are written (`book0_core.testing` fixtures wrapped in
     `tests/conftest.py`, `TestClient` for the API routes, the contract suite for the
     consumer-side view);
   - the dependency direction (`architecture.md` - `book0_api` depends on `book0-core`
     and `book0_config`, never on a CLI; nothing depends on this repo).
2. **Assess the quality of the touched zone**, then apply the zone rule from
   `architecture.md` (align strictly - this project has no legacy zone).
3. **Never hallucinate a convention.** If the existing code is ambiguous or contradictory
   across files, report it and propose a reasoned choice. Do not decide silently.

## By intervention type

### Debug
1. Reproduce the bug (a failing test when possible) before looking for the cause.
2. Identify which repo it lives in: `../book0-core` (wrong query, wrong error type,
   `book0_config` resolution), this repo (`book0_api` - wrong status/body mapping, wrong
   route logic), or `../book0-cli` (wrong error reconstruction, wrong request, client
   config).
3. Find the root cause, not just the symptom.
4. Fix at the lowest coherent level. Do not patch a route to mask a bug in a gateway, and
   do not patch the consumer's gateway to mask a bug in a route.
5. Add or adapt the matching non-regression test (e2e and/or contract suite).
6. Search the usages of the changed function/class and confirm no other caller breaks - a
   change to a `book0_core` error or Protocol affects both gateway implementations and
   every consumer repo.

### Maintenance / evolution
1. Identify the exact impact scope (files, tests, callers) across every affected package
   and repo.
2. Check SOLID/KISS/DRY/YAGNI before coding the solution.
3. If the existing code violates these principles in the touched zone: report it, and
   propose an improvement scoped to the request. Do not perform an unrequested massive
   refactor.
4. Update the relevant design doc under `docs/superpowers/specs/` only if a task
   explicitly asks for a new/updated design doc; otherwise keep documentation changes to
   this file and `CLAUDE.md`.

### New feature
1. Work on a dedicated branch, never directly on `main` - create one before writing any
   code, implement and test on it, then merge with an explicit ask (debug and
   maintenance/evolution work is not covered by this - only new-feature work requires the
   branch).
2. Check whether the feature fits `../book0-core` (new domain behavior, new gateway
   method - if so, **both** `SqliteLibraryGateway` and `PgLibraryGateway` need it, plus
   the route here and `HttpLibraryGateway` in `../book0-cli`) or this repo only (a route,
   a schema, a query param).
3. Design against the layering in `architecture.md`: routes call into `book0-core`
   through the gateway Protocols; the API returns JSON and never imports a CLI or
   `book0_presentation`.
4. Write the code and its tests in parallel, not the tests "afterwards" - see the root
   `CLAUDE.md`'s TDD expectation.
5. Check for duplication with neighboring features (DRY) before creating a new
   module/helper.
6. A change to the domain query/output must be reflected in the error-mapping table, the
   schemas, the e2e suite, the contract suite, and the consumer repos (`../book0-cli`,
   `../book0-core`) - not just the route you happened to be editing. Any JSON shape or
   status-code change is a REST-contract change: coordinate with jaquette and
   `../book0-django` consumers.

## End-of-task checklist

- [ ] The code follows the style and patterns already present in the touched package.
- [ ] No new abstraction, interface, or config option that the task did not require.
- [ ] No class/function added that has a single caller and no test.
- [ ] `uv run ruff check .` / `uv run ruff format .` applied, `uv run mypy src` run, no
      new type error introduced (never invoked as bare `ruff`/`mypy`).
- [ ] Unit tests written/updated for every touched piece of pure logic.
- [ ] E2E tests written/updated for every touched API route.
- [ ] The contract suite (`tests/integration/test_http_gateway.py`) updated for every
      touched JSON shape, status code, or error body.
- [ ] All impacted existing tests updated. No red test, no abusive skip.
- [ ] Nominal, boundary, and error cases covered (missing library, non-Calibre file, empty
      library, unconfigured tag, multiple authors, `NULL` pubdate).
- [ ] No regression on the callers of the changed code - if `book0-core` changed, check
      both gateway implementations and the consumer repos (`../book0-core`,
      `../book0-cli`).
- [ ] Every ambiguity or gap with the existing code reported explicitly to the user.
- [ ] New-feature work happened on a dedicated branch, not committed directly to `main`.
