---
paths:
  - "app/**"
  - "tests/**"
---

# Workflow: understand before writing

Before any change, fix, or addition, always:

1. **Explore the nearby code.** Read 2-3 similar files (same resource/layer - router, service,
   repository, schema) to identify:
   - the naming conventions actually used (project habits, not just PEP8: suffixes, prefixes,
     responsibility splitting);
   - the patterns already in place (Repository, CQRS, dependency injection style);
   - how existing tests are written (structure, naming, fixtures, factories, mocks);
   - how dependencies are wired (`Depends()` providers in `api/deps.py`, constructor injection
     in services).
2. **Assess the quality of the touched zone**, then apply the zone rule from
   `architecture.md` (align strictly in a clean zone; do not copy bad practices in an
   inherited/legacy zone).
3. **Never hallucinate a convention.** If the existing code is ambiguous or contradictory across
   files, report it and propose a reasoned choice. Do not decide silently.

## By intervention type

### Debug
1. Reproduce the bug (a failing test when possible) before looking for the cause.
2. Explore the context (which layer: router? service? repository? ORM/session? Pydantic
   validation?).
3. Find the root cause, not just the symptom.
4. Fix at the lowest coherent level. Do not patch in a router to mask a service bug.
5. Add or adapt the matching non-regression test.
6. Search the usages of the changed function/class and confirm no other caller breaks.

### Maintenance / evolution
1. Identify the exact impact scope (files, tests, callers).
2. Check SOLID/KISS/DRY/YAGNI before coding the solution.
3. If the existing code violates these principles in the touched zone: report it, and propose an
   improvement scoped to the request. Do not perform an unrequested massive refactor.
4. Update the technical docs if they exist (docstrings only where they explain *why*, OpenAPI
   descriptions, module README).

### New feature
1. Check whether the feature fits an existing resource/module, or needs a new one under
   `api/`, `services/`, `repositories/`, `schemas/`, `models/`.
2. Design against the layering in `architecture.md`: router -> service -> repository -> model.
   Never let a router call a repository or ORM session directly.
3. Write the code and its tests in parallel, not the tests "afterwards".
4. Check for duplication with neighboring features (DRY) before creating a new service/helper.
5. If the endpoint changes the public contract, update the OpenAPI schema/docs (FastAPI
   generates this from the Pydantic schemas and route metadata - keep them accurate).

## End-of-task checklist

- [ ] The code follows the style and patterns already present in the touched zone.
- [ ] No new abstraction, interface, or config option that the task did not require.
- [ ] No class/function added that has a single caller and no test.
- [ ] `uv run ruff check .` / `uv run ruff format .` applied, `uv run mypy app` run, no new
      type error introduced (never invoked as bare `ruff`/`mypy`).
- [ ] Unit tests written/updated for every touched piece of business logic.
- [ ] Integration/e2e tests written/updated for every touched endpoint or DB-facing behavior.
- [ ] All impacted existing tests updated. No red test, no abusive skip.
- [ ] Nominal, boundary, and error cases covered (including validation errors -> HTTP 422/4xx).
- [ ] No regression on the callers of the changed code.
- [ ] Every ambiguity or gap with the existing code reported explicitly to the user.
