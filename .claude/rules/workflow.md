---
paths:
  - "src/**"
  - "tests/**"
---

# Workflow: understand before writing

Before any change, fix, or addition, always:

1. **Explore the nearby code.** Read the module you are about to touch and its counterpart
   on the other side of the gateway abstraction if relevant (e.g. `sqlite_gateway.py`
   alongside `http_gateway.py` when the domain query/output changes) to identify:
   - the naming conventions actually used;
   - how errors are raised in `book0_core`, mapped to HTTP in `book0_api/main.py`, and
     reconstructed in `book0_cli_remote/http_gateway.py`;
   - how existing tests are written (fixtures in `tests/conftest.py`, `capsys` for CLI
     output, `TestClient` for the API/remote-gateway path);
   - the dependency direction (`architecture.md`'s dependency-direction section - both CLIs
     and the API depend on `book0_core`, never the reverse; neither CLI depends on the other).
2. **Assess the quality of the touched zone**, then apply the zone rule from
   `architecture.md` (align strictly - this project has no legacy zone yet).
3. **Never hallucinate a convention.** If the existing code is ambiguous or contradictory across
   files, report it and propose a reasoned choice. Do not decide silently.

## By intervention type

### Debug
1. Reproduce the bug (a failing test when possible) before looking for the cause.
2. Identify which package it lives in: `book0_core` (wrong query, wrong error type),
   `book0_api` (wrong status/body mapping), `book0_config` (wrong tag-to-path resolution or
   TOML parsing), `book0_cli_remote` (wrong error reconstruction, wrong request), or either
   CLI's `main.py` (path/flag resolution, formatting, exit code).
3. Find the root cause, not just the symptom.
4. Fix at the lowest coherent level. Do not patch a CLI's `main.py` to mask a bug in a
   gateway, and do not patch `HttpLibraryGateway` to mask a bug in `book0_api`.
5. Add or adapt the matching non-regression test.
6. Search the usages of the changed function/class and confirm no other caller breaks - in
   particular, a change to `book0_core.errors` or the `LibraryGateway` Protocol affects both
   gateway implementations, not just the one you were looking at.

### Maintenance / evolution
1. Identify the exact impact scope (files, tests, callers) across every affected package.
2. Check SOLID/KISS/DRY/YAGNI before coding the solution.
3. If the existing code violates these principles in the touched zone: report it, and propose an
   improvement scoped to the request. Do not perform an unrequested massive refactor.
4. Update the relevant design doc under `docs/superpowers/specs/` only if a task explicitly
   asks for a new/updated design doc; otherwise keep documentation changes to this file and
   `CLAUDE.md`.

### New feature
1. Work on a dedicated branch, never directly on `main` - create one before writing any code
   (`git checkout -b <descriptive-name>`), implement and test on it, then open a pull request
   for the feature instead of committing straight to `main`. Debug and maintenance/evolution
   work is not covered by this - only new-feature work requires the branch + PR.
2. Check whether the feature fits `book0_core` (new domain behavior, new gateway method - if
   so, **both** `SqliteLibraryGateway` and `HttpLibraryGateway` need it, plus the
   `book0_api` route that serves it), `book0_presentation` (new output shape used by both
   CLIs), or one CLI specifically (a flag/behavior unique to direct or remote access).
3. Design against the layering in `architecture.md`: both CLIs call into `book0_core`
   through the `LibraryGateway` Protocol; `book0_api` calls `book0_core` directly and
   returns JSON. Never let a CLI open a `sqlite3.Connection` or write SQL directly, and never
   let `book0_api` import a CLI package or `book0_presentation`.
4. Write the code and its tests in parallel, not the tests "afterwards" - see the root
   `CLAUDE.md`'s TDD expectation.
5. Check for duplication with neighboring features (DRY) before creating a new module/helper
   - except the deliberate non-sharing between the two CLIs' `main.py` (see
     `architecture.md`), which is not duplication to fix.
6. A change to `book0_core`'s domain query/output (fields on `Book`, new error type) must be
   reflected in **both** gateway implementations' tests, `book0_api`'s error-mapping table,
   and both CLIs' rendering - not just the one you happened to be testing manually.

### Dispatching review/audit subagents
When dispatching a subagent whose job is to inspect or evaluate rather than change code
(code review before merge, an audit, "just look and report"), always launch it with
`isolation: "worktree"`. A prompt instruction like "read-only, do not mutate the working
tree" is not enforced by anything - a general-purpose subagent has unrestricted tool access
and may ignore it. Worktree isolation means any edit the subagent makes anyway lands in an
isolated copy, never in the real checkout. Confirmed necessary in this project on
2026-08-21: a code-review subagent given explicit read-only instructions applied its own
suggested fixes directly to the working tree as uncommitted changes.

## End-of-task checklist

- [ ] The code follows the style and patterns already present in the touched package.
- [ ] No new abstraction, interface, or config option that the task did not require.
- [ ] No class/function added that has a single caller and no test.
- [ ] `uv run ruff check .` / `uv run ruff format .` applied, `uv run mypy src` run, no new
      type error introduced (never invoked as bare `ruff`/`mypy`).
- [ ] Unit tests written/updated for every touched piece of pure logic.
- [ ] Integration/e2e tests written/updated for every touched gateway method, CLI behavior,
      or API route.
- [ ] All impacted existing tests updated. No red test, no abusive skip.
- [ ] Nominal, boundary, and error cases covered (missing library, non-Calibre file, empty
      library, unconfigured tag, multiple authors, `NULL` pubdate, unreachable server).
- [ ] No regression on the callers of the changed code - if `book0_core` changed, check both
      `book0_cli` and `book0_api`; if the `LibraryGateway` Protocol changed, check both
      `SqliteLibraryGateway` and `HttpLibraryGateway`.
- [ ] Every ambiguity or gap with the existing code reported explicitly to the user.
- [ ] New-feature work happened on a dedicated branch with a pull request opened, not
      committed directly to `main`.
- [ ] Any review/audit subagent was dispatched with `isolation: "worktree"`, not just a
      read-only prompt instruction.
