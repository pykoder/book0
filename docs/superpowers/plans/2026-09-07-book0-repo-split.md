# book0 Repo Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the `book0` repository into three independent repos (`book0-core`, `book0-cli`, `book0-fastapi`) wired by editable path deps, so a future Django backend can serve the same REST contract.

**Architecture:** Sequential extraction (spec Approach 1): extract book0-core first, rewire book0 onto it; extract book0-cli, rewire; rename book0 → book0-fastapi in place. Import names never change — only repositories, distribution names, and pyproject wiring.

**Tech Stack:** Python 3.12, uv (path deps), pytest, ruff, mypy, hatchling. Spec: `docs/superpowers/specs/2026-09-07-book0-repo-split-design.md`.

## Global Constraints

- Every Python invocation goes through `uv run` — never bare `python`, `pytest`, `ruff`, `mypy`.
- Import names stay exactly: `book0_core`, `book0_config`, `book0_cli`, `book0_cli_remote`, `book0_presentation`, `book0_api`. Console scripts: `book0`/`book0-remote` → book0-cli; `book0-api` → book0-fastapi.
- New repos get **fresh git history** (`git init -b main`). book0 keeps its history (renamed in place, branch `repo-split` for the work).
- book0-core deps: `psycopg[binary]>=3.2`, editable `epub2md` (`../epub2md`). NOT `calibre_pg_sync` (only `book0_api/jobs.py` imports it).
- book0-cli deps: `book0-core` (editable path `../book0-core`), `httpx`.
- book0-fastapi deps: `book0-core` (editable path), `fastapi`, `uvicorn`, `calibre-pg-sync` (editable `../calibre_pg_sync`); dev-only `book0-cli` path dep for the contract suite.
- book0-core ships `src/book0_core/py.typed`.
- The shared test fixture lives in `book0_core.testing` (single source of truth); each repo's `tests/conftest.py` wraps it into pytest fixtures.
- Never weaken or delete a test — only move it or replace it with the MockTransport equivalent.
- In the book0 repo, commit ONLY files a task touched (several unrelated files have uncommitted modifications — never `git add .` / `-A`).
- Verification at the end of every repo-touching task: `uv run pytest`, `uv run mypy src`, `uv run ruff check .` — all green before commit.

---

### Task 1: Work branch in book0

**Files:** none (git only)

- [ ] **Step 1: Create the branch**

```bash
cd /home/kriss/dev/github/Grimoire/book0 && git checkout -b repo-split
```

---

### Task 2: book0-core repo skeleton with the testing module

**Files:**
- Create: `/home/kriss/dev/github/Grimoire/book0-core/pyproject.toml`
- Create: `/home/kriss/dev/github/Grimoire/book0-core/.gitignore`, `.python-version`
- Create: `src/book0_core/py.typed`
- Create: `src/book0_core/testing/__init__.py`, `src/book0_core/testing/sqlite_fixtures.py`, `src/book0_core/testing/pg_fixtures.py`
- Copy (unchanged): `src/book0_core/{__init__,models,errors,gateway,sqlite_gateway,pg_gateway}.py`, `src/book0_config/{__init__,config}.py` from `/home/kriss/dev/github/Grimoire/book0/src/`

**Interfaces:**
- Produces (consumed by every later task): `build_calibre_metadata_db(db_path: Path) -> Path`, `build_many_books_db(db_path: Path) -> Path`, constants `CALIBRE_LIBRARY_BOOKS`, `CALIBRE_LIBRARY_AUTHORS`, `CALIBRE_LIBRARY_PUBLISHERS`, `CALIBRE_LIBRARY_SERIES`, `DUNE_DETAILS`, `HOBBIT_DETAILS`, `GOOD_OMENS_DETAILS`, `expected_details_with_cover(library_root: Path) -> tuple[BookDetails, BookDetails, BookDetails]`, `PG_SCHEMA_SQL: str`, `GRIMOIRE_TEST_LIBRARY_UUID: str`, `PG_DUNE_EPUB_RELATIVE: Path`, `write_minimal_epub(path: Path) -> None`, `free_pg_port() -> int`, `start_test_pg() -> tuple[str, str]`, `stop_test_pg(name: str) -> None`, `reset_pg_schema(dsn: str) -> None`, `seed_pg_library(dsn: str, library_root: Path) -> str`.

- [ ] **Step 1: Create the repo and copy packages**

```bash
cd /home/kriss/dev/github/Grimoire
mkdir book0-core && cd book0-core && git init -b main
mkdir -p src/book0_core/testing src/book0_config tests
cp ../book0/src/book0_core/__init__.py ../book0/src/book0_core/models.py \
   ../book0/src/book0_core/errors.py ../book0/src/book0_core/gateway.py \
   ../book0/src/book0_core/sqlite_gateway.py ../book0/src/book0_core/pg_gateway.py \
   src/book0_core/
cp ../book0/src/book0_config/__init__.py ../book0/src/book0_config/config.py src/book0_config/
touch src/book0_core/py.typed
cp ../book0/.gitignore ../book0/.python-version .
cp ../book0/.claude . -r   # replaced per-repo in Task 4; keep permissions settings for now
rm -rf .claude/rules .claude/settings.local.json
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "book0-core"
version = "0.1.0"
description = "Framework-agnostic domain layer for the book0 Calibre tools"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "epub2md",
    "psycopg[binary]>=3.2",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = [
    "src/book0_core",
    "src/book0_config",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.uv.sources]
epub2md = { path = "../epub2md", editable = true }

[dependency-groups]
dev = [
    "ebooklib>=0.20",
    "mypy>=2.3.0",
    "pytest>=9.1.1",
    "ruff>=0.16.1",
]

[tool.mypy]
# epub2md (dépendance editable locale) ne publie pas de marqueur py.typed.
[[tool.mypy.overrides]]
module = "epub2md.*"
ignore_missing_imports = true
```

- [ ] **Step 3: Write `src/book0_core/testing/sqlite_fixtures.py`**

Move (verbatim where possible) from `book0/tests/conftest.py` lines 1–161 and the two fixture bodies (163–319, 330–403), turning fixtures into plain functions taking the target db path:

```python
"""Shared Calibre-shaped SQLite fixtures and expected domain objects.

Single source of truth for every book0 repo's test suite (spec
2026-09-07-book0-repo-split-design.md). Stdlib + book0_core only.
"""

import sqlite3
from pathlib import Path

from book0_core.models import (
    Author,
    Book,
    BookDetails,
    Publisher,
    Series,
    SeriesItem,
)

# Books as inserted into the fixture DB, already in the order list_books()
# is expected to return them (sorted by title). (verbatim from conftest)
CALIBRE_LIBRARY_BOOKS = [ ... ]  # verbatim: conftest.py lines 26-60
CALIBRE_LIBRARY_AUTHORS = [ ... ]  # verbatim: lines 64-69
CALIBRE_LIBRARY_PUBLISHERS = [ ... ]  # verbatim: lines 75-78
CALIBRE_LIBRARY_SERIES = [ ... ]  # verbatim: lines 82-84
DUNE_DETAILS = ...  # verbatim: lines 89-98
HOBBIT_DETAILS = ...  # verbatim: lines 100-109
GOOD_OMENS_DETAILS = ...  # verbatim: lines 111-120


# Expected BookDetails with absolute cover_path values, computed from a library root.
# (verbatim from conftest.py lines 124-160, renamed without leading underscore)
def expected_details_with_cover(
    library_root: Path,
) -> tuple[BookDetails, BookDetails, BookDetails]:
    ...


def build_calibre_metadata_db(db_path: Path) -> Path:
    """Crée une metadata.db Calibre minimale seedée de 3 livres (Dune, The
    Hobbit, Good Omens) - corps verbatim de l'ancienne fixture
    calibre_metadata_db, avec db_path en paramètre au lieu de tmp_path."""
    # verbatim: conftest.py lines 165-319, replacing `db_path = tmp_path / "metadata.db"`
    ...

def build_many_books_db(db_path: Path) -> Path:
    """7 books/authors/publishers, deliberately unlinked - pagination fixture.
    Corps verbatim de l'ancienne fixture many_books_db."""
    # verbatim: conftest.py lines 331-403, same replacement
    ...
```

(Each `... verbatim: lines N-M` marker above means: copy those exact lines from `book0/tests/conftest.py` — the implementing engineer reads that file; the only mechanical change is `db_path = tmp_path / "metadata.db"` → `db_path` parameter and dropping the `@pytest.fixture` decorators.)

- [ ] **Step 4: Write `src/book0_core/testing/pg_fixtures.py`**

Same treatment for the PG half of conftest.py (lines 406–914): constants verbatim, fixtures become functions:

```python
"""Shared PostgreSQL (calibre_pg_sync schema) test helpers.

`write_minimal_epub` needs ebooklib - imported lazily so consumers whose
tests never touch PG don't need it at runtime.
"""

import socket
import subprocess
import time
import uuid as uuid_module
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from book0_core.testing.sqlite_fixtures import PG_DUNE_EPUB_RELATIVE  # no — see note

# NOTE: PG_DUNE_EPUB_RELATIVE, PG_SCHEMA_SQL, GRIMOIRE_TEST_LIBRARY_UUID are
# defined HERE (moved verbatim from conftest.py lines 413-626, 698, 711) -
# sqlite_fixtures.py must NOT import from this module.

def free_pg_port() -> int:
    # verbatim: conftest.py lines 629-632 (_free_port body)
    ...

def start_test_pg() -> tuple[str, str]:
    """Démarre un docker postgres:16-alpine jetable, attend qu'il réponde.
    Retourne (dsn, nom_du_conteneur). Verbatim du corps de pg_dsn
    (conftest.py lines 635-658), sans le try/finally ni le yield."""
    ...

def stop_test_pg(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)

def reset_pg_schema(dsn: str) -> None:
    """DROP/CREATE public + applique PG_SCHEMA_SQL. Corps verbatim de
    pg_schema (conftest.py lines 674-692), connexion fermée ici."""
    ...

def seed_pg_library(dsn: str, library_root: Path) -> str:
    """Bibliothèque PG 'grimoire-test' seedée à l'identique de
    calibre_metadata_db. Corps verbatim de pg_library (conftest.py lines
    739-874) : écrit l'EPUB minimal, insère libraries/books/links, commit,
    retourne le dsn."""
    ...

def seed_sentinel_pubdate_book(dsn: str) -> str:
    """Ajoute le 4e livre à pubdate sentinelle Calibre (an 101). Corps
    verbatim de pg_library_with_sentinel_pubdate (conftest.py lines 877-914)."""
    ...

def _write_minimal_epub(path: Path) -> None:
    # verbatim: conftest.py lines 714-736, but with the ebooklib import
    # moved INSIDE the function:
    #     from ebooklib import epub
    ...
```

- [ ] **Step 5: Write `src/book0_core/testing/__init__.py`**

```python
"""Shared test fixtures for the book0 repos (see testing/sqlite_fixtures.py)."""

from book0_core.testing.pg_fixtures import (
    GRIMOIRE_TEST_LIBRARY_UUID,
    PG_DUNE_EPUB_RELATIVE,
    PG_SCHEMA_SQL,
    free_pg_port,
    reset_pg_schema,
    seed_pg_library,
    seed_sentinel_pubdate_book,
    start_test_pg,
    stop_test_pg,
    write_minimal_epub,
)
from book0_core.testing.sqlite_fixtures import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    CALIBRE_LIBRARY_SERIES,
    DUNE_DETAILS,
    GOOD_OMENS_DETAILS,
    HOBBIT_DETAILS,
    build_calibre_metadata_db,
    build_many_books_db,
    expected_details_with_cover,
)

__all__ = [ ... ]  # the 18 names above, alphabetical
```

(`write_minimal_epub` is the public name; `_write_minimal_epub` in Step 4 loses its underscore.)

- [ ] **Step 6: Write a placeholder README.md** (replaced in Task 4)

```markdown
# book0-core

Framework-agnostic domain layer for the book0 Calibre tools (README: Task 4).
```

- [ ] **Step 7: Sync and verify the skeleton**

```bash
cd /home/kriss/dev/github/Grimoire/book0-core
uv sync && uv run ruff check . && uv run ruff format . && uv run mypy src
```

Expected: clean (no tests yet).

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: book0-core skeleton - domain, config, shared testing fixtures"
```

---

### Task 3: book0-core tests

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`, `tests/integration/__init__.py`
- Copy+adapt from `book0/tests/`: `unit/test_models.py`, `unit/test_errors.py`, `unit/test_book0_config.py`, `integration/test_sqlite_gateway.py`, `integration/test_pg_gateway.py`

- [ ] **Step 1: Copy the test files**

```bash
cd /home/kriss/dev/github/Grimoire/book0-core
mkdir -p tests/unit tests/integration
touch tests/unit/__init__.py tests/integration/__init__.py
cp ../book0/tests/unit/test_models.py ../book0/tests/unit/test_errors.py \
   ../book0/tests/unit/test_book0_config.py tests/unit/
cp ../book0/tests/integration/test_sqlite_gateway.py \
   ../book0/tests/integration/test_pg_gateway.py tests/integration/
```

- [ ] **Step 2: Write `tests/conftest.py`** — thin fixture wrappers over `book0_core.testing`

```python
from pathlib import Path

import psycopg
import pytest

from book0_core.testing import (
    GRIMOIRE_TEST_LIBRARY_UUID,
    PG_DUNE_EPUB_RELATIVE,
    build_calibre_metadata_db,
    build_many_books_db,
    expected_details_with_cover,
    reset_pg_schema,
    seed_pg_library,
    seed_sentinel_pubdate_book,
    start_test_pg,
    stop_test_pg,
)
from book0_core.models import BookDetails


@pytest.fixture
def calibre_metadata_db(tmp_path: Path) -> Path:
    return build_calibre_metadata_db(tmp_path / "metadata.db")


@pytest.fixture
def many_books_db(tmp_path: Path) -> Path:
    return build_many_books_db(tmp_path / "metadata.db")


@pytest.fixture
def expected_book_details(
    calibre_metadata_db: Path,
) -> tuple[BookDetails, BookDetails, BookDetails]:
    """Expected BookDetails with absolute cover_path values for the fixture library."""
    return expected_details_with_cover(calibre_metadata_db.parent)


@pytest.fixture(scope="session")
def pg_dsn():
    """PostgreSQL docker jetable (postgres:16-alpine, port libre, 60 s max)."""
    import time

    dsn, name = start_test_pg()
    try:
        yield dsn
    finally:
        stop_test_pg(name)


@pytest.fixture
def pg_schema(pg_dsn):
    """Réinitialise le schéma public et applique la DDL calibre_pg_sync."""
    reset_pg_schema(pg_dsn)
    yield pg_dsn


@pytest.fixture
def pg_library_root(tmp_path: Path) -> Path:
    """Répertoire racine de la bibliothèque PG seedée (pour les cover_path)."""
    root = tmp_path / "grimoire-test"
    root.mkdir()
    return root


@pytest.fixture
def pg_library(pg_dsn, pg_schema, pg_library_root: Path) -> str:
    """Bibliothèque PG 'grimoire-test' seedée à l'identique de calibre_metadata_db."""
    return seed_pg_library(pg_dsn, pg_library_root)


@pytest.fixture
def pg_library_with_sentinel_pubdate(pg_library):
    """pg_library + un 4e livre à pubdate sentinelle Calibre (année 101)."""
    return seed_sentinel_pubdate_book(pg_library)
```

Note: `pg_schema` yields the dsn (not a live connection) — `reset_pg_schema` opens/commits/closes internally; the old fixture yielded a connection only so tests could re-use the cursor, but `test_pg_gateway.py` uses the `pg_library`/`pg_schema` fixtures for setup, never the connection object itself (verify: grep `pg_schema` in the copied test — if any test uses it as a cursor-providing connection, adapt `reset_pg_schema` to return the connection and close it in the fixture's finally).

- [ ] **Step 3: Fix test imports** — replace any `from tests.conftest import ...` with `from book0_core.testing import ...` in the copied test files:

```bash
grep -rn "from tests.conftest\|tests\.conftest" tests/ || true
```

For each hit, replace the import source with `book0_core.testing` (same names: `CALIBRE_LIBRARY_*`, `DUNE_DETAILS`, etc.). Everything else in the test files is unchanged.

- [ ] **Step 4: Run the suite**

```bash
uv run pytest -v
```

Expected: PASS (requires docker for the PG tests, same as book0 today). Then:

```bash
uv run ruff check . && uv run ruff format . && uv run mypy src
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "test: gateway/model/config suites + conftest wrapping book0_core.testing"
```

---

### Task 4: book0-core documentation

**Files:**
- Create: `CLAUDE.md`, `.claude/rules/architecture.md`, README.md
- Copy+adapt: `.claude/rules/python-design.md`, `testing.md`, `workflow.md` (from `../book0/.claude/rules/`)
- Copy: `../book0/docs/superpowers/specs/2026-08-31-grimoire-api-librarygateway-design.md` and `2026-08-31-grimoire-pg-schema-design.md` into `docs/superpowers/specs/`
- Create: `docs/superpowers/TODO.md` (items moved from book0 — see Task 5 Step 3 for the split rule; core items listed below)

- [ ] **Step 1: Write `CLAUDE.md`**

```markdown
# CLAUDE.md - Working guide for book0-core

> Loaded at session start. Keep it short; task-specific rules live in `.claude/rules/`.

## Project context

- **Stack**: Python 3.12+, stdlib `sqlite3` (no ORM), `psycopg` (PG), `epub2md`
  (markdown conversion, editable local dep), `pytest`, managed with `uv`.
- **Domain**: the framework-agnostic domain layer shared by every book0 consumer
  (`book0-cli`, `book0-fastapi`, future `book0-django`): `Book`/`Author`/... frozen
  dataclasses, the `ReadLibraryGateway`/`MutableLibraryGateway` Protocols (spec
  2026-08-31 §8, copy in `docs/superpowers/specs/`), their SQLite and PG implementations,
  domain errors, and `book0_config` (TOML tag→path resolution, stdlib-only).
- **Architecture**: depends on nothing project-specific and no web/HTTP framework.
  All SQL over Calibre's `metadata.db` lives in `book0_core/sqlite_gateway.py`;
  `pg_gateway.py` speaks the calibre_pg_sync PG schema (spec copy in docs). See
  `.claude/rules/architecture.md`.
- **Consumers**: `../book0-cli` and `../book0-fastapi` consume this repo as an editable
  path dependency. A change here must keep all consumers green: run their suites too
  when you change models, errors, or the Protocols.
- **Shared test fixtures**: `book0_core/testing/` is the single source of truth for the
  Calibre-shaped SQLite DB, the PG seed, and the expected domain objects. Consumer repos'
  conftest.py wrap these - never duplicate a fixture in a consumer.

## Tooling: uv only

| Task | Command |
|---|---|
| Install/sync | `uv sync` |
| Run tests | `uv run pytest` |
| Lint / format | `uv run ruff check .` / `uv run ruff format .` |
| Type-check | `uv run mypy src` |

## Absolute prohibitions

- Never ship code without an associated test.
- Never open a Calibre library for write - `SqliteLibraryGateway` connects read-only
  (`mode=ro`).
- Never depend on a web framework, argparse, or any book0 consumer - dependency
  direction is one-way (consumers → core, never the reverse).
- Never add a Protocol method without updating BOTH gateway implementations (and then
  the consumers' HttpLibraryGateway + API routes in their own repos).
- Never invoke `python`/`pytest`/`ruff`/`mypy` directly - always `uv run <tool>`.
- Never use a mutable default argument.

## Deferred work

`docs/superpowers/TODO.md` tracks deliberately deferred work (same convention as the
other book0 repos). Check it before brainstorming a new subject.

## How the rest of the guide loads

`.claude/rules/` files load automatically on matching paths (see the table in each
file's frontmatter).
```

- [ ] **Step 2: Write `.claude/rules/architecture.md`**

```markdown
---
paths:
  - "src/**"
  - "tests/**"
---

# Architecture and real source layout

```
src/
├── book0_core/
│   ├── models.py                   # frozen dataclasses: Book, Author, Publisher, Series,
│   │                               # SeriesItem, BookDetails, BookDetailsResult,
│   │                               # Paged*Result, BookQuery, Job*, ...
│   ├── errors.py                   # domain errors (LibraryNotFoundError,
│   │                               # NotACalibreLibraryError, TagRequiredError, ...)
│   ├── gateway.py                  # ReadLibraryGateway / MutableLibraryGateway Protocols
│   ├── sqlite_gateway.py           # SqliteLibraryGateway: metadata.db read-only (mode=ro);
│   │                               # resolves a directory to <dir>/metadata.db itself
│   ├── pg_gateway.py               # PgLibraryGateway: calibre_pg_sync PG schema
│   ├── py.typed
│   └── testing/                    # shared test fixtures (see below)
│       ├── sqlite_fixtures.py      # build_calibre_metadata_db, build_many_books_db,
│       │                           # CALIBRE_LIBRARY_* constants, expected *Details,
│       │                           # expected_details_with_cover
│       └── pg_fixtures.py          # PG_SCHEMA_SQL, seed_pg_library, start/stop_test_pg,
│                                   # write_minimal_epub (lazy ebooklib import)
└── book0_config/
    └── config.py                   # load_libraries(path) -> LibraryConfig; TOML,
                                    # ${VAR_NAME} env expansion, default-library /
                                    # default-page-size keys; stdlib only
```

## Dependency direction

- `book0_core` and `book0_config` depend on nothing project-specific, no web/HTTP
  framework, no CLI package.
- Consumers (`../book0-cli`, `../book0-fastapi`, future `../book0-django`) depend on this
  repo; it never depends on them. When you change models, errors, or a Protocol, run the
  consumers' test suites (they are siblings: `cd ../book0-cli && uv run pytest`, etc.).
- `testing/` is import-only test support: stdlib + book0_core + lazy ebooklib. No pytest
  dependency - fixtures are defined in each consumer's conftest.py.

## Zone rule

This project is greenfield - align strictly on the pattern above. If you find an
inconsistency, report it rather than assuming it is intentional.
```

- [ ] **Step 3: Adapt the other three rules files**

Copy from `../book0/.claude/rules/` and apply these exact edits:

- `python-design.md`: delete the "FastAPI / async correctness" section entirely; in "SQLite access", keep as-is; in "Typing", delete the two sentences about `book0_api.schemas.BookOut` (that package no longer exists here); in "Coding standards" keep as-is.
- `testing.md`: replace references to `book0_api`/`TestClient` requirements — delete the e2e bullet and the TestClient bullet (no API here); replace "see `tests/conftest.py`'s `calibre_metadata_db` fixture" with "see `book0_core.testing`"; keep everything else, including the uv-only section.
- `workflow.md`: in "New feature" step 2, replace the package list mapping with: core change → both gateway implementations + consumer repos (`book0-cli`'s `HttpLibraryGateway`, `book0-fastapi`'s routes); keep the rest verbatim including the worktree-isolation rule for review subagents.

```bash
mkdir -p .claude/rules docs/superpowers/specs
cp ../book0/.claude/rules/python-design.md ../book0/.claude/rules/testing.md \
   ../book0/.claude/rules/workflow.md .claude/rules/
cp ../book0/docs/superpowers/specs/2026-08-31-grimoire-api-librarygateway-design.md \
   ../book0/docs/superpowers/specs/2026-08-31-grimoire-pg-schema-design.md \
   docs/superpowers/specs/
# then apply the edits above
```

- [ ] **Step 4: Write `docs/superpowers/TODO.md`**

```markdown
# TODO (book0-core)

Work deliberately deferred - moved here from book0's TODO.md by the repo split
(spec 2026-09-07-book0-repo-split-design.md). Same convention: resolved = removed.

- [ ] **Comma-splitting bug in `GROUP_CONCAT`-based aggregation** (moved verbatim from
  book0's TODO, 2026-08-13 entry, unchanged content)
- [ ] **Normalize/dedupe book ids before they reach the Gateway** (moved verbatim,
  2026-08-13 entry)
- [ ] **(far future, undesigned) Multi-library support** (moved verbatim, 2026-08-13)
- [ ] **(undesigned) `books-detail`'s own field projection** (moved verbatim, 2026-08-20)
- [ ] **Scalar config keys should live in a `[general]` TOML section** (moved verbatim,
  2026-08-28; affects `book0_config/config.py`)
- [ ] **epub2md's `parse_extract_spec` should raise a domain error instead of
  `argparse.ArgumentTypeError`** (moved verbatim, 2026-09-03)
- [ ] **`apply_author_name` ne met pas à jour `books.author_sort`** (moved verbatim,
  2026-09-03)
```

("moved verbatim" = copy the full original bullet text from `../book0/docs/superpowers/TODO.md` — the engineer reads that file and copies each named item unchanged.)

- [ ] **Step 5: Write the real README.md**

Adapt `../book0/README.md`: keep Install (`uv sync`) and Development sections; replace the CLI/API usage sections with a short "Consumers" section naming `book0-cli` and `book0-fastapi` and pointing to the specs in `docs/superpowers/specs/`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "docs: CLAUDE.md, rules, TODO, specs archive, README"
```

---

### Task 5: Rewire book0 onto book0-core

**Files:**
- Modify: `pyproject.toml` (deps + wheel packages + mypy overrides)
- Delete: `src/book0_core/`, `src/book0_config/`
- Delete: `tests/unit/test_models.py`, `tests/unit/test_errors.py`, `tests/unit/test_book0_config.py`, `tests/integration/test_sqlite_gateway.py`, `tests/integration/test_pg_gateway.py`
- Modify: `tests/conftest.py` (replace with thin wrappers, keep ONLY the fixtures still used by remaining tests: `calibre_metadata_db`, `many_books_db`, `expected_book_details` — delete the PG fixtures from conftest, they moved to book0-core)
- Modify: `docs/superpowers/TODO.md` (remove the items moved to book0-core)

- [ ] **Step 1: Delete the moved packages and tests**

```bash
cd /home/kriss/dev/github/Grimoire/book0
git rm -r src/book0_core src/book0_config
git rm tests/unit/test_models.py tests/unit/test_errors.py tests/unit/test_book0_config.py \
       tests/integration/test_sqlite_gateway.py tests/integration/test_pg_gateway.py
```

- [ ] **Step 2: Add the path dependency, remove the moved ones**

```bash
uv add --editable ../book0-core
uv remove psycopg epub2md
```

Then edit `pyproject.toml` by hand (allowed here for build metadata, not deps):
- `[tool.hatch.build.targets.wheel] packages`: remove `"src/book0_core"` and `"src/book0_config"`.
- `[tool.mypy.overrides]`: delete the `epub2md.*` override, keep `calibre_pg_sync.*`.

- [ ] **Step 3: Replace `tests/conftest.py`**

```python
from pathlib import Path

import pytest
from book0_core.testing import (
    build_calibre_metadata_db,
    build_many_books_db,
    expected_details_with_cover,
)
from book0_core.models import BookDetails


@pytest.fixture
def calibre_metadata_db(tmp_path: Path) -> Path:
    return build_calibre_metadata_db(tmp_path / "metadata.db")


@pytest.fixture
def many_books_db(tmp_path: Path) -> Path:
    return build_many_books_db(tmp_path / "metadata.db")


@pytest.fixture
def expected_book_details(
    calibre_metadata_db: Path,
) -> tuple[BookDetails, BookDetails, BookDetails]:
    """Expected BookDetails with absolute cover_path values for the fixture library."""
    return expected_details_with_cover(calibre_metadata_db.parent)
```

- [ ] **Step 4: Update `docs/superpowers/TODO.md`** — delete the seven items now in book0-core (list in Task 4 Step 4); keep: jobs `book_ids`, jobs mono-serveur, filtres non câblés book0-remote, plafond 100k, book0-django. Add one line at the top of the file: note that core-related deferred items moved to `../book0-core/docs/superpowers/TODO.md` (2026-09-07).

- [ ] **Step 5: Verify green**

```bash
uv sync && uv run pytest && uv run mypy src && uv run ruff check .
```

If any remaining test imported `from tests.conftest import PG_SCHEMA_SQL` etc., switch it to `book0_core.testing` (grep first). Expected: full suite PASS.

- [ ] **Step 6: Cross-check book0-core consumers** — none exist yet besides this repo; skip.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock tests/conftest.py docs/superpowers/TODO.md
git commit -m "refactor: extract book0-core into its own repo (editable path dep)"
```

---

### Task 6: book0-cli repo skeleton

**Files:**
- Create: `/home/kriss/dev/github/Grimoire/book0-cli/{pyproject.toml,.gitignore,.python-version,CLAUDE.md placeholder}`
- Copy: `src/book0_cli/{__init__,config,main}.py`, `src/book0_cli_remote/{__init__,config,http_gateway,main}.py`, `src/book0_presentation/{__init__,tables}.py`

- [ ] **Step 1: Create and copy**

```bash
cd /home/kriss/dev/github/Grimoire
mkdir book0-cli && cd book0-cli && git init -b main
mkdir -p src/book0_cli src/book0_cli_remote src/book0_presentation tests
cp ../book0/src/book0_cli/*.py src/book0_cli/
cp ../book0/src/book0_cli_remote/*.py src/book0_cli_remote/
cp ../book0/src/book0_presentation/*.py src/book0_presentation/
cp ../book0/.gitignore ../book0/.python-version .
cp -r ../book0/.claude . && rm -rf .claude/rules .claude/settings.local.json
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "book0-cli"
version = "0.1.0"
description = "Terminal CLIs for listing a Calibre library (direct and HTTP-backed)"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "book0-core",
    "httpx>=0.28.1",
]

[project.scripts]
book0 = "book0_cli.main:main"
book0-remote = "book0_cli_remote.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = [
    "src/book0_cli",
    "src/book0_cli_remote",
    "src/book0_presentation",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.uv.sources]
book0-core = { path = "../book0-core", editable = true }

[dependency-groups]
dev = [
    "mypy>=2.3.0",
    "pytest>=9.1.1",
    "ruff>=0.16.1",
]
```

- [ ] **Step 3: Verify the skeleton compiles**

```bash
echo "# book0-cli" > README.md && uv sync && uv run mypy src && uv run ruff check .
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: book0-cli skeleton - both CLIs + presentation, path dep on book0-core"
```

---

### Task 7: book0-cli tests with the contract stub

**Files:**
- Create: `tests/conftest.py`, `tests/helpers/__init__.py`, `tests/helpers/contract_stub.py`
- Copy+adapt: `tests/unit/{__init__,test_tables,test_cli_config,test_cli_remote_config}.py`, `tests/integration/{__init__,test_cli_main}.py`
- Rewrite: `tests/integration/test_cli_remote_main.py` (from `../book0/tests/integration/test_cli_remote_main.py`)

**Interfaces:**
- Consumes: `book0_core.testing` fixtures; `book0_cli_remote.main.run(argv, client=None)`.
- Produces: `stub_client(libraries: dict[str, Path], default_tag: str | None = None, default_page_size: int | None = None) -> httpx.Client` — drop-in replacement for `TestClient(create_app(...))` in remote-CLI tests.

- [ ] **Step 1: Copy the unchanged test files**

```bash
cd /home/kriss/dev/github/Grimoire/book0-cli
mkdir -p tests/unit tests/integration tests/helpers
touch tests/unit/__init__.py tests/integration/__init__.py tests/helpers/__init__.py
cp ../book0/tests/unit/test_tables.py ../book0/tests/unit/test_cli_config.py \
   ../book0/tests/unit/test_cli_remote_config.py tests/unit/
cp ../book0/tests/integration/test_cli_main.py tests/integration/
cp ../book0/tests/integration/test_cli_remote_main.py tests/integration/
```

- [ ] **Step 2: Write `tests/conftest.py`** — identical to Task 5 Step 3's conftest (same three fixtures; copy that file's content).

- [ ] **Step 3: Write `tests/helpers/contract_stub.py`** — a reference implementation of the REST contract with no FastAPI:

```python
"""Reference stub of the book0_api REST contract over httpx.MockTransport.

Mimics exactly the JSON shapes and status codes book0_api produces (schemas.py,
main.py error mapping) but is driven by SqliteLibraryGateway directly - no
FastAPI, preserving book0-cli's independence. Used by the remote-CLI tests.
"""

from pathlib import Path

import httpx

from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.models import Book
from book0_core.sqlite_gateway import SqliteLibraryGateway


def _book_json(book: Book) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "authors": list(book.authors),
        "pubdate": book.pubdate,
        "publisher": (
            {"id": book.publisher.id, "name": book.publisher.name}
            if book.publisher is not None
            else None
        ),
        "series": (
            {"id": book.series.id, "name": book.series.name}
            if book.series is not None
            else None
        ),
        "series_index": book.series_index,
        "rating": book.rating,
        "has_cover": book.has_cover,
    }


def _error(status: int, name: str, detail: str) -> httpx.Response:
    return httpx.Response(status, json={"error": name, "detail": detail})


def _paged(items: list[dict], page: int, page_size: int, total_count: int) -> dict:
    import math

    total_pages = math.ceil(total_count / page_size) if page_size else None
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_more_than_shown": False,
    }


def stub_client(
    libraries: dict[str, Path],
    default_tag: str | None = None,
    default_page_size: int | None = None,
) -> httpx.Client:
    """An httpx.Client whose transport serves the contract for `libraries`,
    shaped like create_app(libraries, default_tag, default_page_size)."""

    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/").removeprefix("")  # /libraries/...
        params = dict(request.url.params)
        tag = params.get("tag", default_tag)
        if tag is None:
            return _error(400, "TagRequiredError", "no tag given and no default-library")
        if tag not in libraries:
            return _error(404, "LibraryNotFoundError", f"unknown library {tag!r}")
        try:
            gateway = SqliteLibraryGateway(libraries[tag])
        except NotACalibreLibraryError as error:
            return _error(500, "NotACalibreLibraryError", str(error))
        except LibraryNotFoundError as error:
            return _error(404, "LibraryNotFoundError", str(error))

        try:
            if request.method == "GET" and request.url.path in (
                "/libraries/books",
                "/libraries/authors",
                "/libraries/publishers",
                "/libraries/series",
            ):
                return _listing(gateway, request.url.path, params, default_page_size)
            if request.method == "POST" and request.url.path == "/libraries/books/detail":
                ids = request.read() and __import__("json").loads(request.read())
                result = gateway.get_book_details(ids["ids"])
                return httpx.Response(
                    200,
                    json={
                        "books": [_details_json(d) for d in result.books],
                        "missing_ids": list(result.missing_ids),
                    },
                )
            if request.method == "GET" and "/cover" in request.url.path:
                book_id = request.url.path.rsplit("/", 2)[-2]
                books = {b.id: b for b in gateway.list_books()}
                if book_id in books and books[book_id].has_cover:
                    return httpx.Response(200, content=b"stub-cover-bytes")
                return _error(404, "CoverNotFoundError", f"no cover for {book_id}")
            return _error(500, "NotImplementedError", f"stub: {request.url.path}")
        finally:
            gateway.close_pagination  # no-op; gateway holds no pagination state

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://stub")
```

Notes for the implementer, to be resolved against the real code while writing (read `src/book0_api/main.py`'s routes and `src/book0_cli_remote/http_gateway.py` for exact semantics):
- `_listing` reads `page`/`page_size` query params (ints, optional). If `page` given or `page_size` given (or `default_page_size` set — cap the requested size down to it, and force pagination when the client sent none): return `_paged(...)` from the gateway's `list_{books,authors,publishers,series}_page(page, page_size)` result (`items` via the same JSON mapping as `_book_json`/`{"id","name"}` for authors/publishers/series); otherwise return the plain JSON array (unpaginated), matching `list_books()`'s shape.
- `_details_json(d)` mirrors `BookDetailsOut` exactly: `id, title, pubdate, authors, tags, publisher, series ({"series": {...}, "index"}), has_cover` (bool from `cover_path is not None`).
- Simplify the `POST .../detail` body parse: `json.loads(request.content)` with `import json` at module top (the sketch above is not idiomatic — clean it up).
- Drop the pointless `finally: gateway.close_pagination` line — the stub gateway holds no state.
- If a copied test exercises behavior this stub doesn't implement, extend the stub — never weaken the test.

- [ ] **Step 4: Rewrite `tests/integration/test_cli_remote_main.py`**

Mechanical transformation of every test, applied uniformly:
- Replace `from fastapi.testclient import TestClient` and `from book0_api.main import create_app` with `from tests.helpers.contract_stub import stub_client`.
- Replace each `client = TestClient(create_app({"fiction": calibre_metadata_db}))` with `client = stub_client({"fiction": calibre_metadata_db})` (same argument mapping for `default_tag=`/`default_page_size=`).
- Keep every assertion, every `run([...], client=client)` call, every expected output byte-for-byte.
- For unreachable-server tests (which construct `httpx.Client(base_url=...)` against a dead port): keep as-is — no stub needed.

Example (first test of the file, transformed):

```python
def test_books_default_subcommand(calibre_metadata_db, capsys):
    client = stub_client({"fiction": calibre_metadata_db})
    exit_code = run(["--server", "http://stub", "--tag", "fiction"], client=client)
    assert exit_code == 0
    # ... same assertions as the original
```

- [ ] **Step 5: Fix remaining imports and run**

```bash
grep -rn "from tests.conftest\|book0_api\|fastapi" tests/ || true   # must return nothing
uv sync && uv run pytest -v
```

Expected: PASS. Then `uv run ruff check . && uv run ruff format . && uv run mypy src`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "test: suites moved from book0; remote-CLI tests on a MockTransport contract stub"
```

---

### Task 8: book0-cli documentation

**Files:** `CLAUDE.md`, `.claude/rules/`, `README.md`, `docs/superpowers/TODO.md`

- [ ] **Step 1: Write `CLAUDE.md`** — same skeleton as Task 4 Step 1 with these substitutions: Stack = `httpx`, no psycopg/epub2md; Domain = "the two terminal CLIs (`book0` direct, `book0-remote` HTTP-backed) plus the shared plain-text table rendering (`book0_presentation`)"; Architecture = "leaf repo: depends only on `book0-core` (path dep); never depends on `book0-fastapi` or any server - `book0-remote` knows only the REST contract (a URL and a JSON shape)"; add "the two CLIs deliberately share no run-loop code - do not DRY them up"; Tooling table rows `uv run book0 ...`, `uv run book0-remote ...`; Deferred work pointing at `docs/superpowers/TODO.md`.

- [ ] **Step 2: Write `.claude/rules/architecture.md`** — new content: tree of the three packages (`book0_cli/main.py` + `config.py`, `book0_cli_remote/{main,config,http_gateway}.py`, `book0_presentation/tables.py`), dependency direction (cli → core only; presentation → core only; cli_remote never imports book0_cli or book0_config; no shared run loop between the CLIs — deliberate), client-side config discovery (`.book0.toml`, `.book0-client.toml` with XDG fallbacks), zone rule (greenfield).

- [ ] **Step 3: Adapt rules files** — copy `python-design.md`, `testing.md`, `workflow.md` from `../book0/.claude/rules/` with the same style of edits as Task 4 Step 3, plus: testing.md replaces the TestClient guidance with "drive `run()`/`HttpLibraryGateway` via `httpx.Client(transport=httpx.MockTransport(stub))` from `tests/helpers/contract_stub.py` — never import FastAPI"; workflow.md's feature-impact mapping becomes "cli behavior → both CLIs' `main.py` unaffected unless shared; contract change in core → check `http_gateway.py`".

- [ ] **Step 4: Write `docs/superpowers/TODO.md`** — move the "Filtres structurés et facettes jamais câblés côté `book0-remote`" item verbatim from book0's TODO.md (and delete it there in Task 9).

- [ ] **Step 5: Write README.md** — adapt book0's README: keep only the `book0` and `book0-remote` sections (install, subcommands, pagination, config files, covers) and the Development section; drop everything about `book0_api`/server-side config.

- [ ] **Step 6: Commit**: `git add -A && git commit -m "docs: CLAUDE.md, rules, TODO, README"`

---

### Task 9: Trim book0 to the API only

**Files:**
- Delete: `src/book0_cli/`, `src/book0_cli_remote/`, `src/book0_presentation/`, `tests/unit/test_tables.py`, `tests/unit/test_cli_config.py`, `tests/unit/test_cli_remote_config.py`, `tests/integration/test_cli_main.py`, `tests/integration/test_cli_remote_main.py`
- Modify: `pyproject.toml` (scripts + packages + drop httpx), `docs/superpowers/TODO.md` (remove cli item)

- [ ] **Step 1: Delete moved packages and tests**

```bash
cd /home/kriss/dev/github/Grimoire/book0
git rm -r src/book0_cli src/book0_cli_remote src/book0_presentation
git rm tests/unit/test_tables.py tests/unit/test_cli_config.py tests/unit/test_cli_remote_config.py \
       tests/integration/test_cli_main.py tests/integration/test_cli_remote_main.py
```

Keep `tests/integration/test_http_gateway.py` — it stays in this repo permanently as the contract suite. It imports `book0_cli_remote`, which this repo no longer ships, so this task also adds the dev-only path dependency (spec: test-only, the runtime dependency-direction rule is unchanged).

- [ ] **Step 2: Update pyproject and deps**

```bash
uv add --editable ../book0-cli --group dev
uv remove httpx
```

Hand-edit `pyproject.toml`: `[project.scripts]` keeps only `book0-api = "book0_api.cli:main"`; wheel `packages` keeps only `"src/book0_api"`.

- [ ] **Step 3: Verify green**

```bash
uv sync && uv run pytest && uv run mypy src && uv run ruff check .
```

`test_http_gateway.py` resolves its `book0_cli_remote` import through the new dev path dep. Expected: full suite PASS.

- [ ] **Step 4: TODO** — remove the "Filtres structurés ... book0-remote" item (now in book0-cli's TODO).

- [ ] **Step 5: Commit**

```bash
uv run pytest && uv run mypy src && uv run ruff check .
git add -A && git commit -m "refactor: extract book0-cli; book0 keeps book0_api only"
```

---

### Task 10: Rename book0 → book0-fastapi, finalize

**Files:**
- Rename: `/home/kriss/dev/github/Grimoire/book0` → `/home/kriss/dev/github/Grimoire/book0-fastapi`
- Modify: `pyproject.toml` (name only — deps were settled in Task 9), `CLAUDE.md`, `.claude/rules/architecture.md`, `README.md`

- [ ] **Step 1: Rename the directory and distribution**

```bash
cd /home/kriss/dev/github/Grimoire && mv book0 book0-fastapi && cd book0-fastapi
```

Edit `pyproject.toml`: `name = "book0-fastapi"`. Import names and the `book0-api` script are unchanged. Runtime deps: `book0-core` (path), `fastapi`, `uvicorn`, `calibre-pg-sync` (path `../calibre_pg_sync`); dev group additionally has `book0-cli` (added in Task 9).

- [ ] **Step 2: Verify the contract suite still runs after the rename**

```bash
uv sync && uv run pytest tests/integration/test_http_gateway.py -v
```

Its imports (`book0_api.main.create_app`, `book0_cli_remote.http_gateway.HttpLibraryGateway`, `tests.conftest`) all resolve: book0_api locally, book0_cli_remote via the dev path dep, conftest via book0_core.testing (Task 5's conftest). Expected: PASS.

- [ ] **Step 4: Rewrite CLAUDE.md and architecture.md** — adapt book0's CLAUDE.md: Stack without httpx/argparse-CLI mentions; Domain = "the FastAPI HTTP service (`book0_api`) serving the book0 REST contract to `book0-remote`, jaquette, and a future Django backend"; Architecture = the book0_api tree only (main/asgi/cli/schemas/filters/jobs) + dependency direction (api → core + config; dev-only path dep on book0-cli for the contract suite — runtime never imports it); keep the prohibitions about error mapping (400/404/500 JSON bodies), sync `def` routes, `create_app(libraries, ...)` purity. architecture.md: keep the `book0_api` section of book0's tree, replace the rest with the contract-suite note. Update the rules table.

- [ ] **Step 5: Update README.md** — keep only the server-side sections (`book0-api`, PG mode, nginx, restricting access), fix any `book0` self-references to `book0-fastapi`, point CLI readers at `../book0-cli`.

- [ ] **Step 6: Full green**

```bash
uv sync && uv run pytest && uv run mypy src && uv run ruff check .
```

- [ ] **Step 7: Commit and merge**

```bash
git add -A && git commit -m "refactor: rename book0 to book0-fastapi; contract suite via dev dep on book0-cli"
git checkout main && git merge --no-ff repo-split -m "merge: repo split - core/cli/fastapi extraction"
```

---

### Task 11: Launchers and jaquette doc fix

**Files:**
- Rename: `/home/kriss/dev/github/Grimoire/jaquette.sh` → `jaquette-fastapi.sh` (uncommitted local file)
- Modify: `jaquette-fastapi.sh` (cd path), `check-covers-pg.sh` (cd path), `jaquette/CLAUDE.md` (one line)

- [ ] **Step 1: Rename and fix the launchers**

```bash
cd /home/kriss/dev/github/Grimoire
mv jaquette.sh jaquette-fastapi.sh
```

In `jaquette-fastapi.sh`, change `cd "$GRIMOIRE_ROOT/book0"` → `cd "$GRIMOIRE_ROOT/book0-fastapi"`. In `check-covers-pg.sh`, same replacement. In `jaquette/CLAUDE.md`, replace the `../book0` reference with `../book0-fastapi` (grep first — there may be several; update all that denote the API repo).

- [ ] **Step 2: Smoke the launcher** (requires the PG to exist and media mounts; skip gracefully if environment is unavailable — in that case verify only the path resolution):

```bash
bash -n jaquette-fastapi.sh && bash -n check-covers-pg.sh   # syntax check
```

- [ ] **Step 3: Commit** — nothing to commit in any git repo (both scripts are uncommitted local files by design; jaquette has its own repo, commit there):

```bash
cd jaquette && git add CLAUDE.md && git commit -m "docs: point at book0-fastapi after the repo split"
```

---

### Task 12: Final cross-repo verification

- [ ] **Step 1: All suites green**

```bash
cd /home/kriss/dev/github/Grimoire/book0-core    && uv sync && uv run pytest && uv run mypy src && uv run ruff check .
cd /home/kriss/dev/github/Grimoire/book0-cli     && uv sync && uv run pytest && uv run mypy src && uv run ruff check .
cd /home/kriss/dev/github/Grimoire/book0-fastapi && uv sync && uv run pytest && uv run mypy src && uv run ruff check .
```

- [ ] **Step 2: End-to-end smoke against a real fixture library**

```bash
cd /home/kriss/dev/github/Grimoire/book0-cli && uv run book0 --tag fiction 2>&1 | head -3  # expect config error or table, NOT ImportError
cd /home/kriss/dev/github/Grimoire/book0-fastapi && uv run book0-api --help | head -3       # expect usage, NOT ImportError
```

- [ ] **Step 3: Update the split spec's status line** in `book0-fastapi/docs/superpowers/specs/2026-09-07-book0-repo-split-design.md`: `Status: implemented (see plans/2026-09-07-book0-repo-split.md)`. Commit in book0-fastapi.

- [ ] **Step 4: Remove the branch**

```bash
cd /home/kriss/dev/github/Grimoire/book0-fastapi && git branch -d repo-split
```
