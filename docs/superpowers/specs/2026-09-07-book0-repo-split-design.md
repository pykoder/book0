# book0 repo split: book0-core, book0-cli, book0-fastapi — design

Date: 2026-09-07
Status: implemented (see plans/2026-09-07-book0-repo-split.md)
Supersedes: nothing
Related: `2026-08-31-grimoire-api-librarygateway-design.md` (API contract),
`2026-08-31-grimoire-pg-schema-design.md` (PG schema)

## Goal

Split the single `book0` repository into three independent repositories so that
alternative backends (starting with a Django implementation, `book0-django`) can serve
the same REST contract as the existing FastAPI service, with all consumers (the CLIs,
the jaquette web UI) working unchanged.

This spec covers the split only. **book0-django itself is a separate sub-project with
its own brainstorming/spec/plan cycle** (recorded in "Out of scope" below).

## Big picture

```
book0-cli      (book0, book0-remote)  ──────────────> book0-core
                                                      (domain + config,
jaquette       (React web UI)                           Python, uv)
   │
   │ REST contract only — no Python dependency
   │ (GET /libraries/{books,authors,publishers}, POST /libraries/books/detail,
   │  GET /libraries/books/{id}/cover, ...)
   │
   v
book0-fastapi  (today's book0_api)    ──────────────> book0-core
book0-django    (future)              ──────────────> book0-core
```

- **book0-cli** and the two backends: Python, depend on **book0-core** (editable path
  dep).
- **jaquette**: TypeScript, depends on nothing Python-side — only on the REST contract
  the backends serve. It must work unchanged against book0-fastapi today and
  book0-django tomorrow.
- The REST contract is the load-bearing interface; book0-core sits below it, invisible
  to jaquette.

Decisions taken during brainstorming:

| Decision | Choice |
|---|---|
| Scope of book0-django (later cycle) | API server only, no CLI duplication |
| book0-django API surface (later cycle) | Reads + PG reads; write routes deferred |
| Domain logic | Extract `book0_core` (+ `book0_config`) into a `book0-core` repo |
| CLI | Extracted into its own `book0-cli` repo |
| Existing repo | Renamed `book0-fastapi` in place (history kept) |
| Cross-repo dependencies | Editable path deps (`[tool.uv.sources]`), like `epub2md`/`calibre_pg_sync` today |
| Git history | Fresh history for the two new repos; book0-fastapi keeps its own |
| Execution | Sequential extraction (Approach 1) |
| Root launchers | `jaquette-fastapi.sh` (renamed from `jaquette.sh`) and future `jaquette-django.sh` |

## Repository topology

```
Grimoire/
├── book0-core/        # new repo, fresh history
├── book0-cli/         # new repo, fresh history
├── book0-fastapi/     # existing book0 repo, renamed in place → history kept
├── book0-django/      # future sub-project, its own spec cycle
└── jaquette/          # existing React web UI, unaffected (one doc-line fix)
```

### book0-core (new repo, fresh history)

- `src/book0_core/` — `models.py`, `errors.py`, `gateway.py` (both Protocols),
  `sqlite_gateway.py`, `pg_gateway.py` — unchanged imports, unchanged code.
- `src/book0_config/` — `config.py` (TOML tag→path resolution, stdlib-only).
- `src/book0_core/testing/` (new) — `build_calibre_metadata_db(path)` builder plus the
  expected `CALIBRE_LIBRARY_BOOKS/AUTHORS/PUBLISHERS/SERIES/...` constants; stdlib +
  sqlite3 only, no test-framework coupling. Single source of truth for the Calibre-shaped
  fixture; each consumer repo's `tests/conftest.py` wraps it in its own fixture.
- `tests/` — gateway/model/config tests moved from book0.
- Dependencies: `psycopg`, editable `epub2md` (used by `pg_gateway.py`). sqlite3 is
  stdlib. `calibre_pg_sync` does NOT move here — only `book0_api/jobs.py` imports it.
- Distribution name `book0-core`; packages `book0_core`, `book0_config`. Ships a
  `py.typed` marker so consumers' `uv run mypy src` keeps working (required now that it
  is an installed dependency rather than a sibling package); the `epub2md` mypy override
  moves here too.

### book0-cli (new repo, fresh history)

- `src/book0_cli/`, `src/book0_cli_remote/`, `src/book0_presentation/` — unchanged
  imports.
- Console scripts `book0` and `book0-remote`.
- Dependencies: `book0-core` (path dep), `httpx`.
- Tests: CLI integration tests, remote-CLI config tests, presentation tests, plus a new
  `HttpLibraryGateway` integration suite against `httpx.MockTransport` (see Tests).
- Own CLAUDE.md + `.claude/rules/` documenting leaf-CLI status, dependency on core only,
  client-side config discovery (`.book0.toml`, `.book0-client.toml`), and the deliberate
  "no shared run loop between the two CLIs" choice.

### book0-fastapi (existing book0 repo, renamed in place — history kept)

- `src/book0_api/` only; console script `book0-api`. Import names do not change.
- Distribution name `book0-fastapi`; the `book0` distribution name disappears.
- Dependencies: `book0-core` (path dep), `fastapi`, `uvicorn`, `calibre-pg-sync`
  (imported by `book0_api/jobs.py`); drops `httpx` and `psycopg`. Dev-only: a path dep
  on `book0-cli` (see Tests — the contract suite drives the real `HttpLibraryGateway`);
  this does not relax the runtime dependency-direction rule.
- `book0-libraries.toml` (with `${VAR}` placeholders), `book0-api.toml`, and the
  `.book0-server.toml` docs stay here (server-side configuration).
- `docs/superpowers/` (specs + plans + TODO.md) stays here as the design archive.
- Own CLAUDE.md + `.claude/rules/` adapted from book0's, minus the CLI packages, with
  the contract-test role of `test_http_gateway.py` called out.

### jaquette (existing repo, unchanged except one doc line)

- No code or dependency changes: it consumes only the REST contract.
- Its CLAUDE.md references `../book0` — updated to `../book0-fastapi`.
- OpenAPI caveat recorded for the future: jaquette's API types are generated from
  FastAPI's `openapi.json` (`pnpm gen:api-types`). Django has no equivalent by default,
  so book0-django will need to serve a compatible schema (e.g. drf-spectacular or
  django-ninja) — a design constraint for that sub-project (see Out of scope).

## Cross-repo wiring

Dependency graph (one-way):

```
book0-cli      ──> book0-core   (editable path dep ../book0-core)
book0-fastapi  ──> book0-core   (editable path dep ../book0-core)
book0-django   ──> book0-core   (future)
```

- `book0-cli` and `book0-fastapi` never depend on each other (same rule as today: the
  API never imports a CLI).
- `[tool.uv.sources]` in both consumers:
  `book0-core = { path = "../book0-core", editable = true }`.
- uv-only tooling discipline per repo; each CLAUDE.md carries the command table for its
  own scripts (`uv run book0 ...` in cli, `uv run book0-api ...` in fastapi,
  `uv run pytest` everywhere).
- ruff/mypy configs copied per repo, each covering only its own `src`.

Entry points after the split:

| Script | Repo |
|---|---|
| `book0`, `book0-remote` | book0-cli |
| `book0-api` | book0-fastapi |

Config-file ownership: client-side `.book0.toml` / `.book0-client.toml` documented and
discovered in book0-cli; server-side `book0-libraries.toml` and `.book0-server.toml` in
book0-fastapi. The `book0_config` loader lives in core so both sides parse identically.

## Tests

### Fixture

`book0_core.testing` (in book0-core) replaces today's shared `tests/conftest.py`
Calibre-shaped DB. Each repo's `tests/conftest.py` imports the builder + expected
constants and exposes them as local fixtures.

### Placement

| Test suite | Repo after split |
|---|---|
| unit: models, errors, config loader | book0-core |
| unit: api schemas, filters | book0-fastapi |
| integration: `test_sqlite_gateway.py`, `test_pg_gateway.py` | book0-core |
| integration: `test_cli_main.py`, `test_cli_remote_config.py`; presentation tests | book0-cli |
| integration: `test_cli_remote_main.py` | book0-cli, **rewritten** against an `httpx.MockTransport` contract stub (`run(argv, client=...)` accepts an injected `httpx.Client`, so no FastAPI import is needed) |
| integration: `test_http_gateway.py` | **book0-fastapi** (it imports `book0_api.main.create_app` + `fastapi.testclient` — it is the API contract test) |
| e2e: API routes | book0-fastapi |

### One behavioral test change

The remote-CLI suites that drove `run()`/`HttpLibraryGateway` against a real
`create_app` split in two:

- book0-fastapi keeps `test_http_gateway.py` as the real-server contract suite. To
  construct the real consumer it adds `book0-cli` as a **dev-only** path dependency;
  runtime code never imports it and the dependency-direction rule is unchanged.
- book0-cli gets a rewritten `test_cli_remote_main.py` whose tests inject
  `httpx.Client(transport=httpx.MockTransport(stub))` into `run(argv, client=...)`,
  where `stub` is a small handler implementing the REST contract's JSON shapes
  (`items`/`page`/`page_size`/`total_pages`/`has_more_than_shown`, `BookOut` fields,
  `{"error": ..., "detail": ...}` bodies for 400/404/500).

No test is weakened or deleted — only moved, or replaced by the MockTransport
equivalent.

## Guidelines and docs split

Each repo gets its own `CLAUDE.md` + `.claude/rules/` (architecture.md,
python-design.md, testing.md, workflow.md) adapted from book0's:

- **All three:** uv-only tooling table (commands adjusted per repo), the absolute
  prohibitions relevant to what they contain, path-scoped `.claude/rules/` mechanism.
- **book0-core:** architecture.md documents the Protocols + two gateways, the
  read-only-metadata.db rule, and "core depends on no project, no web framework" — now
  enforced across repo boundaries.
- **book0-cli:** leaf-CLI status, core-only dependency, no config-loader duplication,
  the no-shared-run-loop deliberate choice, client-side config docs.
- **book0-fastapi:** today's architecture.md minus the CLI packages; contract-test role
  of `test_http_gateway.py` explicit.

TODO.md items follow the code they reference: the `GROUP_CONCAT` bug, id-normalization,
`apply_author_name`/`author_sort`, and jobs items (all reference `book0_core`) move to
book0-core's TODO; the un-wired-remote-filters item (CLI) to book0-cli's; the
pagination-cap item (API) stays in book0-fastapi's. `docs/superpowers/specs/` stays in
book0-fastapi as the archive; the two 2026-08-31 spec files referenced by core's
CLAUDE.md are copied into book0-core's docs.

## Root-level launcher scripts

Two sibling launchers at the Grimoire root, same shape as the existing `jaquette.sh`
(local, uncommitted, parameters at the top — DSN, tag, ports):

| Script | Backend | Status |
|---|---|---|
| `jaquette-fastapi.sh` | book0-fastapi | Renamed from `jaquette.sh`; `cd .../book0` becomes `cd .../book0-fastapi` |
| `jaquette-django.sh` | book0-django | Delivered with the book0-django implementation cycle (identical structure: start Django backend on its port, wait for readiness, launch Vite with `BOOK0_API_URL` pointed at it); recipe documented in the book0-django spec |

The backend swap is invisible to jaquette: both scripts launch the exact same Vite dev
server; only `BOOK0_API_URL` (and the backend process) differs. `check-covers-pg.sh`
gets the same `cd .../book0-fastapi` fix.

## Execution order and verification

Each step ends with every existing repo green (`uv run pytest`, `uv run mypy src`,
`uv run ruff check .` in each).

**Step 1 — Extract book0-core.**
1. Create `Grimoire/book0-core/` (fresh git repo): packages, `book0_core.testing`
   fixture module, moved tests, own pyproject (hatchling; deps: `psycopg`, editable
   `epub2md` + `calibre_pg_sync`), `py.typed`, CLAUDE.md + `.claude/rules/`, README.
2. In `book0`: add the path dep, delete `src/book0_core` + `src/book0_config`, update
   pyproject package list, move core TODO items; verify green.

**Step 2 — Extract book0-cli.**
1. Create `Grimoire/book0-cli/`: CLI packages + presentation, scripts, tests (with the
   new MockTransport `HttpLibraryGateway` suite), path dep on `../book0-core`, own
   CLAUDE.md/rules/README.
2. In `book0`: same wiring, delete those packages; verify green.

**Step 3 — Rename book0 → book0-fastapi and finalize.**
1. `mv book0 book0-fastapi` (directory + pyproject `name`; import names and the
   `book0-api` script unchanged).
2. Move `test_http_gateway.py` into its tests as the contract suite; trim to
   `book0_api` only; adapt CLAUDE.md/rules/README.
3. Rename `jaquette.sh` → `jaquette-fastapi.sh` and fix its `cd` (and
   `check-covers-pg.sh`); fix jaquette's CLAUDE.md `../book0` reference.
4. Final green check across all three repos; commit.

Import names never change (`book0_core`, `book0_config`, `book0_cli`,
`book0_cli_remote`, `book0_presentation`, `book0_api`) — only repositories and
distribution names do, so the code diff in consumers is limited to pyproject wiring and
test imports of the fixture module.

## Out of scope

- **book0-django** — its own brainstorming/spec/plan cycle, consuming this split.
  Known constraints to bring there: serve the same REST contract (including an
  OpenAPI-compatible schema for jaquette's type generation), reads + PG reads first
  with write routes deferred, and the `jaquette-django.sh` launcher. Tracked in this
  repo's `docs/superpowers/TODO.md` until that cycle starts.
- Publishing to a private package index (path deps are sufficient while repos are
  cloned side by side).
- Git-history surgery (filter-repo) — fresh history was chosen for the new repos.
- The open TODO items themselves (they move with their code, they are not actioned).
