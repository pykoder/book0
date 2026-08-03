---
paths:
  - "src/**"
  - "tests/**"
---

# Workflow: understand before writing

Before any change, fix, or addition, always:

1. **Explore the nearby code.** Read the module you are about to touch and its direct
   neighbor in the other package (e.g. `sqlite_repository.py` alongside `main.py`) to identify:
   - the naming conventions actually used;
   - how errors are raised in `book0_core` and turned into CLI-facing messages in
     `book0_cli/main.py`;
   - how existing tests are written (fixtures in `tests/conftest.py`, `capsys` for CLI output);
   - the dependency direction (`book0_cli` -> `book0_core`, never the reverse).
2. **Assess the quality of the touched zone**, then apply the zone rule from
   `architecture.md` (align strictly - this project has no legacy zone yet).
3. **Never hallucinate a convention.** If the existing code is ambiguous or contradictory across
   files, report it and propose a reasoned choice. Do not decide silently.

## By intervention type

### Debug
1. Reproduce the bug (a failing test when possible) before looking for the cause.
2. Identify which package it lives in: `book0_core` (data/domain: wrong query, wrong error
   type) or `book0_cli` (path resolution, formatting, exit code).
3. Find the root cause, not just the symptom.
4. Fix at the lowest coherent level. Do not patch `main.py` to mask a query bug in
   `sqlite_repository.py`.
5. Add or adapt the matching non-regression test.
6. Search the usages of the changed function/class and confirm no other caller breaks.

### Maintenance / evolution
1. Identify the exact impact scope (files, tests, callers) across both packages.
2. Check SOLID/KISS/DRY/YAGNI before coding the solution.
3. If the existing code violates these principles in the touched zone: report it, and propose an
   improvement scoped to the request. Do not perform an unrequested massive refactor.
4. Update `docs/superpowers/specs/` only if a task explicitly asks for a new design doc;
   otherwise keep documentation changes to this file and `CLAUDE.md`.

### New feature
1. Check whether the feature fits `book0_core` (new domain behavior, new repository method) or
   `book0_cli` (new flag, new output shape), or genuinely needs a new module.
2. Design against the layering in `architecture.md`: `book0_cli` calls `book0_core` through the
   `BookRepository` Protocol. Never let `book0_cli` open a `sqlite3.Connection` or write SQL
   directly.
3. Write the code and its tests in parallel, not the tests "afterwards" - see the root
   `CLAUDE.md`'s TDD expectation.
4. Check for duplication with neighboring features (DRY) before creating a new module/helper.
5. If the feature changes `book0`'s command-line contract (new flag, changed output format),
   keep `docs/superpowers/specs/2026-08-03-calibre-book-lister-design.md` in mind as the record
   of the original design - note the divergence in your reply, do not silently drift from it.

## End-of-task checklist

- [ ] The code follows the style and patterns already present in the touched package.
- [ ] No new abstraction, interface, or config option that the task did not require.
- [ ] No class/function added that has a single caller and no test.
- [ ] `uv run ruff check .` / `uv run ruff format .` applied, `uv run mypy src` run, no new
      type error introduced (never invoked as bare `ruff`/`mypy`).
- [ ] Unit tests written/updated for every touched piece of pure logic
      (`book0_core/models.py`, `book0_cli/formatting.py`).
- [ ] Integration tests written/updated for every touched repository method or CLI behavior.
- [ ] All impacted existing tests updated. No red test, no abusive skip.
- [ ] Nominal, boundary, and error cases covered (missing library, non-Calibre file, empty
      library, multiple authors, `NULL` pubdate).
- [ ] No regression on the callers of the changed code (`book0_cli/main.py` if `book0_core`
      changed; any future `book0_api` note if the `BookRepository` Protocol changes).
- [ ] Every ambiguity or gap with the existing code reported explicitly to the user.
