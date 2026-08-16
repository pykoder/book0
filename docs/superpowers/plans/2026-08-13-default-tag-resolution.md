# Default Tag Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `book0`'s "no `--tag` → auto-detect Calibre's own default install location"
fallback, replacing it with a `default-library` setting read from configuration — resolved
client-side for `book0` (its own `.book0.toml`), and server-side for `book0-remote` (the
server's `book0-libraries.toml`), since `book0_api` already owns tag resolution today.

**Architecture:** `book0_config.config.load_libraries` changes its return type from
`dict[str, Path]` to a new `LibraryConfig` frozen dataclass (`libraries: dict[str, Path]`,
`default_tag: str | None`) — one parse, shared by both `book0_cli` and `book0_api`. `book0`'s
`run()` always looks up the config file now (previously only when `--tag` was given) and
resolves `args.tag or config.default_tag`; if neither exists, it raises a new
`TagRequiredError` domain error, caught alongside the existing two. All four `book0_api` routes
drop `{tag}` from the URL path and gain it as an optional query parameter instead
(`GET /libraries/books?tag=...`), resolving the same way server-side and mapping
`TagRequiredError` to `400`. `book0-remote`'s `--tag` becomes optional to match, and
`HttpLibraryGateway` sends `tag` as a query parameter only when present, reconstructing
`TagRequiredError` from a 400 response the same way it already reconstructs the other two
domain errors.

**Tech Stack:** Python 3.12, stdlib `sqlite3`/`argparse`/`tomllib`, FastAPI + Pydantic, `httpx`,
`pytest`, `uv`.

## Global Constraints

- Every command goes through `uv run <tool>` — never a bare `python`/`pytest`/`ruff`/`mypy`.
- A tag that's *given but not configured* keeps its existing behavior unchanged everywhere:
  `book0` hard-errors ("unknown library tag"), `book0_api`/`book0-remote` treat it as an empty
  library (200 + empty result) — this is a deliberate, pre-existing anti-enumeration property
  and this plan does not touch it.
- `default-library` naming a tag that isn't in `[libraries]` is **not** separately validated —
  it flows through the existing "unknown tag" error path once resolved, by design (see the
  design doc).
- `create_app`'s new `default_tag` parameter is optional and defaults to `None` — every
  existing test calling `create_app({"fiction": path})` keeps working unchanged.
- `book0_config.config.LibraryConfig` is the single shared shape both `book0_cli` and
  `book0_api` read from the same file parse — no second parse, no separate reader function.
- Each task's commit touches only the files that task's own section below lists. If running
  the full suite reveals a failure outside a task's declared files, report it — do not fix it
  inside that task's commit.
- Every new function/class ships with a test in the same commit.
- Ship no config option, flag, or abstraction the spec did not ask for (no default `--server`
  URL for `book0-remote`, no `--genconfig`, no `--help` completeness work — all explicitly out
  of scope for this plan).
- A recurring issue in this project's plan docs: a markdown code-fence auto-formatter
  sometimes reformats embedded snippets after they're written, occasionally stripping the
  indentation a snippet needs when it's meant for insertion mid-function (seen twice in prior
  plans, both times on a snippet nested two or more levels deep). If a code block in this plan
  looks suspiciously flush-left for where it's being inserted, match the *real file's* existing
  indentation at that location instead of the plan's literal text — don't blindly transcribe
  whitespace that contradicts the surrounding code you're actually editing.
- Design doc: `docs/superpowers/specs/2026-08-13-default-tag-resolution-design.md`.

---

### Task 1: `TagRequiredError` domain error

**Files:**
- Modify: `src/book0_core/errors.py`
- Test: `tests/unit/test_errors.py`

**Interfaces:**
- Produces: `book0_core.errors.TagRequiredError(Exception)`, used by every later task in this
  plan.

- [ ] **Step 1: Write the failing test**

Read `tests/unit/test_errors.py` first to match its existing style, then append a test for the
new exception following the same pattern as the existing `LibraryNotFoundError`/
`NotACalibreLibraryError` tests (e.g. `test_tag_required_error_is_an_exception`, asserting
`isinstance(TagRequiredError("message"), Exception)` — mirror the exact assertion style already
used for the other two).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: FAIL with `ImportError: cannot import name 'TagRequiredError'`

- [ ] **Step 3: Add the exception**

`src/book0_core/errors.py` becomes:

```python
class LibraryNotFoundError(Exception):
    pass


class NotACalibreLibraryError(Exception):
    pass


class TagRequiredError(Exception):
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/errors.py tests/unit/test_errors.py
git commit -m "feat: add TagRequiredError domain error"
```

---

### Task 2: `book0_config.LibraryConfig` + `load_libraries` return-shape change

**Files:**
- Modify: `src/book0_config/config.py`
- Modify: `tests/unit/test_book0_config.py`

**Interfaces:**
- Produces: `book0_config.config.LibraryConfig(libraries: dict[str, Path], default_tag: str |
  None)`, `load_libraries(config_path: Path) -> LibraryConfig`. Used by Task 4 (`book0_cli`)
  and Task 5 (`book0_api`).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_book0_config.py` becomes:

```python
import tomllib
from pathlib import Path

import pytest

from book0_config.config import LibraryConfig, load_libraries


def test_load_libraries_returns_tag_to_path_mapping_with_no_default_tag(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\nwork = "/path/to/work/metadata.db"\n'
    )

    config = load_libraries(config_path)

    assert config == LibraryConfig(
        libraries={
            "fiction": Path("/path/to/fiction/metadata.db"),
            "work": Path("/path/to/work/metadata.db"),
        },
        default_tag=None,
    )


def test_load_libraries_reads_default_library_when_present(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        'default-library = "fiction"\n\n'
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\n'
    )

    config = load_libraries(config_path)

    assert config.default_tag == "fiction"


def test_load_libraries_expands_env_var_placeholders_in_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "${FICTION_LIBRARY_PATH}/metadata.db"\n'
    )
    monkeypatch.setenv("FICTION_LIBRARY_PATH", "/real/fiction")

    config = load_libraries(config_path)

    assert config.libraries == {"fiction": Path("/real/fiction/metadata.db")}


def test_load_libraries_raises_when_referenced_env_var_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text('[libraries]\nfiction = "${FICTION_LIBRARY_PATH}"\n')
    monkeypatch.delenv("FICTION_LIBRARY_PATH", raising=False)

    with pytest.raises(KeyError):
        load_libraries(config_path)


def test_load_libraries_raises_when_file_is_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_libraries(tmp_path / "does-not-exist.toml")


def test_load_libraries_raises_on_malformed_toml(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text("this is not valid toml [[[")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_libraries(config_path)
```

(This replaces the whole file — every existing test's assertion changes from a bare dict to
`LibraryConfig`/`.libraries`, and one new test is added for `default_tag`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'LibraryConfig'`

- [ ] **Step 3: Implement `LibraryConfig` and the new `load_libraries`**

`src/book0_config/config.py` becomes:

```python
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


@dataclass(frozen=True)
class LibraryConfig:
    libraries: dict[str, Path]
    default_tag: str | None


def _expand_env_vars(value: str) -> str:
    return _ENV_VAR_PATTERN.sub(lambda match: os.environ[match.group(1)], value)


def load_libraries(config_path: Path) -> LibraryConfig:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    libraries = {
        tag: Path(_expand_env_vars(path)) for tag, path in data["libraries"].items()
    }
    return LibraryConfig(libraries=libraries, default_tag=data.get("default-library"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_config.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_config/config.py tests/unit/test_book0_config.py
git commit -m "refactor: change load_libraries to return LibraryConfig with an optional default_tag"
```

---

### Task 3: Remove `book0_cli/config.py::default_library_path` (dead code)

**Files:**
- Modify: `src/book0_cli/config.py`
- Modify: `tests/unit/test_cli_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing — this task only removes a function that will have no remaining caller
  after Task 4 lands. Doing it as its own task keeps the "delete dead code" commit separate
  and reviewable on its own, ahead of the behavior change that makes it dead.

- [ ] **Step 1: Remove the function and its test**

In `src/book0_cli/config.py`, delete the `default_library_path` function entirely:

```python
import os
from pathlib import Path

LOCAL_CONFIG_FILENAME = ".book0.toml"
_XDG_CONFIG_SUBPATH = Path("book0") / "config.toml"


def xdg_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return config_home / _XDG_CONFIG_SUBPATH


def find_config_file() -> Path | None:
    local_config = Path.cwd() / LOCAL_CONFIG_FILENAME
    if local_config.is_file():
        return local_config

    candidate = xdg_config_path()
    if candidate.is_file():
        return candidate

    return None
```

In `tests/unit/test_cli_config.py`, remove `default_library_path` from the import line and
delete `test_default_library_path_is_calibre_library_under_home` entirely:

```python
from book0_cli.config import find_config_file, xdg_config_path
```

(Every other test in that file is untouched.)

- [ ] **Step 2: Run tests to verify the remaining ones still pass**

Run: `uv run pytest tests/unit/test_cli_config.py -v`
Expected: PASS (6 tests — 7 existing minus the one deleted)

Note: this task deliberately leaves `book0_cli/main.py` still importing and calling
`default_library_path` — **this will break `book0_cli/main.py`'s own import** until Task 4
lands. Run only `tests/unit/test_cli_config.py` in this task's own verification, not the full
suite; a red full suite between Task 3 and Task 4 is expected and is not a regression to chase
down here.

- [ ] **Step 3: Commit**

```bash
git add src/book0_cli/config.py tests/unit/test_cli_config.py
git commit -m "refactor: remove default_library_path (Calibre install-path auto-detection)"
```

---

### Task 4: `book0` (local CLI) — new tag resolution

**Files:**
- Modify: `src/book0_cli/main.py`
- Modify: `tests/integration/test_cli_main.py`

**Interfaces:**
- Consumes: `TagRequiredError` (Task 1), `LibraryConfig`/`load_libraries` (Task 2) — `Task 3`'s
  removal of `default_library_path` (this task removes the last caller, making the full suite
  green again).
- Produces: `book0`'s new tag-resolution behavior — no more Calibre-default-path fallback;
  `default-library` from config used when `--tag` is omitted; `TagRequiredError` when neither
  is available.

- [ ] **Step 1: Write the failing tests**

In `tests/integration/test_cli_main.py`:

Remove these four tests entirely (they test the now-removed Calibre-default-path fallback):
`test_run_prints_table_using_default_library_path_when_tag_is_omitted`,
`test_run_reports_missing_library_at_default_path`,
`test_run_prints_author_table_using_default_library_path_when_tag_is_omitted`,
`test_run_prints_publisher_table_using_default_library_path_when_tag_is_omitted`.

Replace them with these three (same location, right before
`test_run_prints_table_when_tag_resolves_via_local_config_file`):

```python
def test_run_uses_default_library_when_tag_is_omitted(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-library = "fiction"\n\n'
        f'[libraries]\nfiction = "{calibre_metadata_db}"\n'
    )

    exit_code = run([])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_missing_config_file_when_tag_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    exit_code = run([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_no_default_tag_configured_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", tmp_path / "fiction.db")

    exit_code = run([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""
```

(`_write_config`'s existing signature is `_write_config(config_path, tag, library_path)` — the
call above writes a config file with a `[libraries]` entry but no `default-library` key, which
is exactly what this test needs. The library path itself is never actually opened, since
`run([])` should fail during tag resolution — before any `SqliteLibraryGateway` is
constructed — so any placeholder path works.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: FAIL — `test_run_uses_default_library_when_tag_is_omitted` gets the "unknown tag"/old
default-path behavior instead of resolving `default-library`; the other two may also fail or
error depending on current behavior.

- [ ] **Step 3: Implement the new tag resolution**

`src/book0_cli/main.py` becomes:

```python
import argparse
import sys
import tomllib

from book0_cli.config import LOCAL_CONFIG_FILENAME, find_config_file, xdg_config_path
from book0_config.config import load_libraries
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.sqlite_gateway import SqliteLibraryGateway
from book0_presentation.tables import (
    format_missing_ids_message,
    order_book_details_by_ids,
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)

_SUBCOMMANDS = ("books", "authors", "publishers", "books-detail")
_TAG_HELP = (
    "library tag to look up in a .book0.toml config file; "
    "omit to use the config file's default-library, if set"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--tag", help=_TAG_HELP)

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--tag", help=_TAG_HELP)

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--tag", help=_TAG_HELP)

    books_detail_parser = subparsers.add_parser("books-detail")
    books_detail_parser.add_argument(
        "--ids", required=True, help="comma-separated list of book ids"
    )
    books_detail_parser.add_argument("--tag", help=_TAG_HELP)

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in ("-h", "--help"):
        return argv
    if not argv or argv[0] not in _SUBCOMMANDS:
        return ["books", *argv]
    return argv


def run(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(_normalize_argv(raw_argv))

    config_path = find_config_file()
    if config_path is None:
        print(
            f"No book0 config file found (looked for ./{LOCAL_CONFIG_FILENAME} "
            f"and {xdg_config_path()})",
            file=sys.stderr,
        )
        return 1

    try:
        config = load_libraries(config_path)
    except (tomllib.TOMLDecodeError, KeyError) as error:
        print(f"Invalid book0 config file {config_path}: {error}", file=sys.stderr)
        return 1

    try:
        tag = args.tag if args.tag is not None else config.default_tag
        if tag is None:
            raise TagRequiredError(
                f"No --tag given and no default-library configured in {config_path}"
            )

        library_path = config.libraries.get(tag)
        if library_path is None:
            print(f"Unknown library tag: {tag!r}", file=sys.stderr)
            return 1

        gateway = SqliteLibraryGateway(library_path)

        if args.command == "authors":
            print(render_author_table(gateway.list_authors()))
        elif args.command == "publishers":
            print(render_publisher_table(gateway.list_publishers()))
        elif args.command == "books-detail":
            ids = args.ids.split(",") if args.ids else []
            result = gateway.get_book_details(ids)
            ordered_books = order_book_details_by_ids(result, ids)
            print(render_book_details_table(ordered_books))
            missing_ids_message = format_missing_ids_message(result.missing_ids)
            if missing_ids_message is not None:
                print(missing_ids_message)
        else:
            print(render_book_table(gateway.list_books()))
    except (LibraryNotFoundError, NotACalibreLibraryError, TagRequiredError) as error:
        print(str(error), file=sys.stderr)
        return 1

    return 0


def main() -> None:
    sys.exit(run())
```

(Note the tag-resolution-and-raise now lives *inside* the same `try` block as the gateway
calls, so `TagRequiredError` is caught by the same `except` clause as the other two domain
errors — this is a deliberate restructuring, not equivalent to bolting an extra `if` onto the
old structure. `library_path.get(tag)` returning `None` for an "unknown tag" still prints
directly and returns 1 without raising, matching existing behavior exactly.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_main.py tests/unit/test_cli_config.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS — this is the point where Task 3's temporarily-broken import gets fixed, so the
full suite should be green again from here on.

- [ ] **Step 6: Commit**

```bash
git add src/book0_cli/main.py tests/integration/test_cli_main.py
git commit -m "feat: resolve book0's default tag from config instead of Calibre's install path"
```

---

### Task 5: `book0_api` (server) — query-param tag, server-side default resolution

**Files:**
- Modify: `src/book0_api/main.py`
- Modify: `src/book0_api/asgi.py`
- Modify: `tests/e2e/test_book0_api_main.py`

**Interfaces:**
- Consumes: `TagRequiredError` (Task 1), `LibraryConfig`/`load_libraries` (Task 2).
- Produces: `create_app(libraries: dict[str, Path], default_tag: str | None = None) -> FastAPI`
  (grows one defaulted parameter — every existing test call keeps working unchanged); all four
  routes take `tag` as an optional query parameter instead of a path segment; `TagRequiredError`
  → `400`. Used by Task 6 (`HttpLibraryGateway` must send requests matching this new shape).

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/e2e/test_book0_api_main.py` in full — every existing test's URL changes from the
path-segment shape to the query-parameter shape, and 8 new tests are added (2 per route:
default-tag resolves, `TagRequiredError` when no tag and no default):

```python
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from book0_api.main import create_app
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)


def test_list_books_returns_expected_books_for_a_known_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": book.id,
            "title": book.title,
            "authors": list(book.authors),
            "pubdate": book.pubdate,
        }
        for book in CALIBRE_LIBRARY_BOOKS
    ]


def test_list_books_resolves_metadata_db_when_configured_path_is_a_directory(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db.parent})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": book.id,
            "title": book.title,
            "authors": list(book.authors),
            "pubdate": book.pubdate,
        }
        for book in CALIBRE_LIBRARY_BOOKS
    ]


def test_list_books_returns_empty_list_for_an_unknown_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "does-not-exist"})

    assert response.status_code == 200
    assert response.json() == []


def test_list_books_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_books_returns_500_when_configured_path_is_not_a_calibre_library(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    app = create_app({"fiction": db_path})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_books_uses_default_tag_when_tag_is_omitted(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.get("/libraries/books")

    assert response.status_code == 200
    assert len(response.json()) == len(CALIBRE_LIBRARY_BOOKS)


def test_list_books_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_authors_returns_expected_authors_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/authors", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": author.id, "name": author.name} for author in CALIBRE_LIBRARY_AUTHORS
    ]


def test_list_authors_returns_empty_list_for_an_unknown_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/authors", params={"tag": "does-not-exist"})

    assert response.status_code == 200
    assert response.json() == []


def test_list_authors_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/authors", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_authors_returns_500_when_configured_path_is_not_a_calibre_library(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    app = create_app({"fiction": db_path})
    client = TestClient(app)

    response = client.get("/libraries/authors", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_authors_uses_default_tag_when_tag_is_omitted(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.get("/libraries/authors")

    assert response.status_code == 200
    assert len(response.json()) == len(CALIBRE_LIBRARY_AUTHORS)


def test_list_authors_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/authors")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_publishers_returns_expected_publishers_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/publishers", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": publisher.id, "name": publisher.name}
        for publisher in CALIBRE_LIBRARY_PUBLISHERS
    ]


def test_list_publishers_returns_empty_list_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/publishers", params={"tag": "does-not-exist"})

    assert response.status_code == 200
    assert response.json() == []


def test_list_publishers_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/publishers", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_publishers_returns_500_when_configured_path_is_not_a_calibre_library(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    app = create_app({"fiction": db_path})
    client = TestClient(app)

    response = client.get("/libraries/publishers", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_list_publishers_uses_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.get("/libraries/publishers")

    assert response.status_code == 200
    assert len(response.json()) == len(CALIBRE_LIBRARY_PUBLISHERS)


def test_list_publishers_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/publishers")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_get_book_details_returns_expected_details_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail", params={"tag": "fiction"}, json={"ids": ["1"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["missing_ids"] == []
    assert len(body["books"]) == 1
    assert body["books"][0] == {
        "id": "1",
        "title": "Dune",
        "pubdate": "1965-08-01",
        "authors": ["Frank Herbert"],
        "tags": ["sci-fi", "classic"],
        "publisher": {"id": "1", "name": "Ace Books"},
        "series": {
            "series": {"id": "1", "name": "Dune Chronicles"},
            "index": "1.0",
        },
    }


def test_get_book_details_reports_missing_ids_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail", params={"tag": "fiction"}, json={"ids": ["1", "999"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["missing_ids"] == ["999"]
    assert len(body["books"]) == 1


def test_get_book_details_returns_all_requested_ids_as_missing_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail",
        params={"tag": "does-not-exist"},
        json={"ids": ["1", "2"]},
    )

    assert response.status_code == 200
    assert response.json() == {"books": [], "missing_ids": ["1", "2"]}


def test_get_book_details_returns_404_when_configured_path_is_missing(
    tmp_path: Path,
):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail", params={"tag": "fiction"}, json={"ids": ["1"]}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_get_book_details_returns_500_when_configured_path_is_not_a_calibre_library(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    app = create_app({"fiction": db_path})
    client = TestClient(app)

    response = client.post(
        "/libraries/books/detail", params={"tag": "fiction"}, json={"ids": ["1"]}
    )

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"


def test_get_book_details_uses_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    client = TestClient(app)

    response = client.post("/libraries/books/detail", json={"ids": ["1"]})

    assert response.status_code == 200
    assert len(response.json()["books"]) == 1


def test_get_book_details_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post("/libraries/books/detail", json={"ids": ["1"]})

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: FAIL — every URL now 404s against the old `/libraries/{tag}/...` routes.

- [ ] **Step 3: Implement the new routes**

`src/book0_api/main.py` becomes:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from book0_api.schemas import (
    AuthorOut,
    BookDetailsResultOut,
    BookIdsIn,
    BookOut,
    PublisherOut,
)
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.sqlite_gateway import SqliteLibraryGateway


def create_app(libraries: dict[str, Path], default_tag: str | None = None) -> FastAPI:
    app = FastAPI()

    def _resolve_db_path(tag: str | None) -> Path | None:
        resolved_tag = tag if tag is not None else default_tag
        if resolved_tag is None:
            raise TagRequiredError(
                "No tag given and no default-library configured for this server"
            )
        return libraries.get(resolved_tag)

    @app.get("/libraries/books", response_model=None)
    def list_books(tag: str | None = None) -> list[BookOut] | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        if db_path is None:
            return []

        gateway = SqliteLibraryGateway(db_path)
        try:
            books = gateway.list_books()
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )
        except NotACalibreLibraryError as error:
            return JSONResponse(
                status_code=500,
                content={"error": "NotACalibreLibraryError", "detail": str(error)},
            )

        return [BookOut.from_book(book) for book in books]

    @app.get("/libraries/authors", response_model=None)
    def list_authors(tag: str | None = None) -> list[AuthorOut] | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        if db_path is None:
            return []

        gateway = SqliteLibraryGateway(db_path)
        try:
            authors = gateway.list_authors()
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )
        except NotACalibreLibraryError as error:
            return JSONResponse(
                status_code=500,
                content={"error": "NotACalibreLibraryError", "detail": str(error)},
            )

        return [AuthorOut.from_author(author) for author in authors]

    @app.get("/libraries/publishers", response_model=None)
    def list_publishers(tag: str | None = None) -> list[PublisherOut] | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        if db_path is None:
            return []

        gateway = SqliteLibraryGateway(db_path)
        try:
            publishers = gateway.list_publishers()
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )
        except NotACalibreLibraryError as error:
            return JSONResponse(
                status_code=500,
                content={"error": "NotACalibreLibraryError", "detail": str(error)},
            )

        return [PublisherOut.from_publisher(publisher) for publisher in publishers]

    @app.post("/libraries/books/detail", response_model=None)
    def get_book_details(
        body: BookIdsIn, tag: str | None = None
    ) -> BookDetailsResultOut | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        if db_path is None:
            return BookDetailsResultOut(books=[], missing_ids=body.ids)

        gateway = SqliteLibraryGateway(db_path)
        try:
            result = gateway.get_book_details(body.ids)
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )
        except NotACalibreLibraryError as error:
            return JSONResponse(
                status_code=500,
                content={"error": "NotACalibreLibraryError", "detail": str(error)},
            )

        return BookDetailsResultOut.from_book_details_result(result)

    return app
```

`src/book0_api/asgi.py` unpacks the new `LibraryConfig`:

```python
import os
from pathlib import Path

from book0_api.cli import CONFIG_ENV_VAR
from book0_api.main import create_app
from book0_config.config import load_libraries

config = load_libraries(Path(os.environ[CONFIG_ENV_VAR]))
app = create_app(config.libraries, config.default_tag)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: PASS (26 tests: 18 existing shape-updated + 8 new)

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/main.py src/book0_api/asgi.py tests/e2e/test_book0_api_main.py
git commit -m "feat: move tag to a query parameter and resolve a server-side default"
```

---

### Task 6: `HttpLibraryGateway` — optional tag, query parameters, `TagRequiredError`

**Files:**
- Modify: `src/book0_cli_remote/http_gateway.py`
- Modify: `tests/integration/test_http_gateway.py`

**Interfaces:**
- Consumes: the new route shape from Task 5, `TagRequiredError` from Task 1.
- Produces: `HttpLibraryGateway.__init__(client: httpx.Client, tag: str | None) -> None` (`tag`
  becomes optional); all four methods send `tag` as a query parameter only when not `None`;
  `TagRequiredError` reconstructed from a `400` response. Used by Task 7 (`book0-remote`'s
  `--tag` becomes optional).

- [ ] **Step 1: Write the failing tests**

In `tests/integration/test_http_gateway.py`, every call site building a URL by hand
(`f"/libraries/{tag}/books"`, etc.) is gone — replaced by `params={"tag": ...}` sent through
`HttpLibraryGateway`'s public methods, so no test in this file changes its *own* URL
construction (it never built URLs directly — `_client_for`/`HttpLibraryGateway` already
encapsulate that). What does change: the `HttpLibraryGateway(client, "fiction")` constructor
calls that pass a tag stay as-is (positional `str` still works since the type only widens to
`str | None`), and new tests are added for the optional-tag case. Add these after
`test_http_gateway_satisfies_the_library_gateway_protocol`:

```python
def test_list_books_uses_server_side_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db}, default_tag="fiction")
    gateway = HttpLibraryGateway(client, None)

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS


def test_list_books_raises_tag_required_error_when_no_default_configured(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, None)

    with pytest.raises(TagRequiredError):
        gateway.list_books()
```

Change the `_client_for` helper to accept the new optional `default_tag` and pass it through:

```python
def _client_for(
    libraries: dict[str, Path], default_tag: str | None = None
) -> httpx.Client:
    return TestClient(create_app(libraries, default_tag))
```

Change the model-error import line:

```python
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: FAIL — `HttpLibraryGateway(client, None)` currently type-hints `tag: str`, and
`list_books()` builds `f"/libraries/{self._tag}/books"` which becomes the literal string
`/libraries/None/books`, a 404 against the new route shape, not `TagRequiredError`.

- [ ] **Step 3: Implement the optional-tag gateway**

`src/book0_cli_remote/http_gateway.py` becomes:

```python
import httpx

from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    Publisher,
    Series,
    SeriesItem,
)

_ERROR_TYPES = {
    "LibraryNotFoundError": LibraryNotFoundError,
    "NotACalibreLibraryError": NotACalibreLibraryError,
    "TagRequiredError": TagRequiredError,
}


def _book_details_from_json(row: dict[str, object]) -> BookDetails:
    publisher_row = row["publisher"]
    publisher = (
        Publisher(id=publisher_row["id"], name=publisher_row["name"])  # type: ignore[index]
        if publisher_row is not None
        else None
    )
    series_row = row["series"]
    series = (
        SeriesItem(
            series=Series(
                id=series_row["series"]["id"],  # type: ignore[index]
                name=series_row["series"]["name"],  # type: ignore[index]
            ),
            index=series_row["index"],  # type: ignore[index]
        )
        if series_row is not None
        else None
    )
    return BookDetails(
        id=row["id"],  # type: ignore[arg-type]
        title=row["title"],  # type: ignore[arg-type]
        pubdate=row["pubdate"],  # type: ignore[arg-type]
        authors=tuple(row["authors"]),  # type: ignore[arg-type]
        tags=tuple(row["tags"]),  # type: ignore[arg-type]
        publisher=publisher,
        series=series,
    )


class HttpLibraryGateway:
    def __init__(self, client: httpx.Client, tag: str | None) -> None:
        self._client = client
        self._tag = tag

    def _params(self) -> dict[str, str]:
        return {"tag": self._tag} if self._tag is not None else {}

    def list_books(self) -> list[Book]:
        response = self._client.get("/libraries/books", params=self._params())

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [
            Book(
                id=row["id"],
                title=row["title"],
                authors=tuple(row["authors"]),
                pubdate=row["pubdate"],
            )
            for row in response.json()
        ]

    def list_authors(self) -> list[Author]:
        response = self._client.get("/libraries/authors", params=self._params())

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [Author(id=row["id"], name=row["name"]) for row in response.json()]

    def list_publishers(self) -> list[Publisher]:
        response = self._client.get("/libraries/publishers", params=self._params())

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [Publisher(id=row["id"], name=row["name"]) for row in response.json()]

    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        response = self._client.post(
            "/libraries/books/detail", params=self._params(), json={"ids": ids}
        )

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        body = response.json()
        return BookDetailsResult(
            books=tuple(_book_details_from_json(row) for row in body["books"]),
            missing_ids=tuple(body["missing_ids"]),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: PASS (20 tests: 18 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/http_gateway.py tests/integration/test_http_gateway.py
git commit -m "feat: make HttpLibraryGateway's tag optional, send it as a query parameter"
```

---

### Task 7: `book0-remote` (remote CLI) — `--tag` becomes optional

**Files:**
- Modify: `src/book0_cli_remote/main.py`
- Modify: `tests/integration/test_cli_remote_main.py`

**Interfaces:**
- Consumes: `HttpLibraryGateway`'s optional-tag constructor (Task 6), `TagRequiredError`
  (Task 1).
- Produces: `book0-remote [books|authors|publishers|books-detail] --server URL [--tag TAG]` —
  `--tag` no longer required.

- [ ] **Step 1: Write the failing tests**

Add `TagRequiredError` to the existing `from book0_core.errors import (...)` import line in
`tests/integration/test_cli_remote_main.py`. Append, after
`test_run_help_mentions_the_books_detail_subcommand`:

```python
def test_run_uses_server_side_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(
        create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    )

    exit_code = run(["--server", "unused"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_tag_required_error_on_stderr_and_exits_with_status_1(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["--server", "unused"], client=client)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: FAIL — `run(["--server", "unused"], client=client)` currently exits 2 (argparse:
`--tag` is required) before ever reaching the gateway.

- [ ] **Step 3: Make `--tag` optional on every subparser**

In `src/book0_cli_remote/main.py`, remove `required=True` from all four `--tag` arguments
(the four `books_detail_parser`/`books_parser`/`authors_parser`/`publishers_parser` lines each
currently read `.add_argument("--tag", required=True)`; each becomes `.add_argument("--tag")`).
`--server` stays `required=True` everywhere — no change there.

Change the model import:

```python
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
```

And widen the `except` clause inside `run()`'s inner `try` block — this is nested two levels
deep (inside `run()`'s outer `try`, then its own `try`), matching the indentation of the
existing `try:`/`if args.command == "authors":` lines directly above it in the same function:

```python
        except (
            LibraryNotFoundError,
            NotACalibreLibraryError,
            TagRequiredError,
        ) as error:
            print(str(error), file=sys.stderr)
            return 1
        except (httpx.ConnectError, httpx.TimeoutException) as error:
```

(Only the tuple of caught exception types changes — `TagRequiredError` added as a third
member; the body of that `except` block, and the `httpx.ConnectError`/`TimeoutException`
`except` clause right after it, are unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite, lint, format, and type-check**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all pass, no new warnings

- [ ] **Step 6: Commit**

```bash
git add src/book0_cli_remote/main.py tests/integration/test_cli_remote_main.py
git commit -m "feat: make book0-remote's --tag optional, let the server resolve a default"
```

---

### Task 8: Update `CLAUDE.md`, `.claude/rules/architecture.md`, and `README.md`

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.claude/rules/architecture.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by another task — this is the last task.

- [ ] **Step 1: Update `CLAUDE.md`**

The "Project context" section currently says `book0_api` exposes
`` `GET /libraries/{tag}/{books,authors,publishers}` ``. Update it to reflect the query-param
shape and the new POST route:

```
-  `GET /libraries/{tag}/{books,authors,publishers}`. See `.claude/rules/architecture.md` for
+  `GET /libraries/{books,authors,publishers}?tag=...` and
+  `POST /libraries/books/detail?tag=...`, `tag` optional with a server-side
+  `default-library` fallback. See `.claude/rules/architecture.md` for
```

- [ ] **Step 2: Update `.claude/rules/architecture.md`**

Update the `book0_cli/main.py`, `book0_api/main.py`, and `book0_cli_remote/main.py` tree
comments to mention `--tag` is now optional everywhere and resolved via `default-library`; note
`book0_config.config.py`'s new `LibraryConfig`/`default_tag` in its own tree comment; note the
new route shape (`?tag=...` instead of `{tag}` path segment) in `book0_api/main.py`'s comment.
Read the file first and match its existing terse, single-line-per-symbol style rather than
padding these into new paragraphs.

- [ ] **Step 3: Update `README.md`**

- Document the new `default-library = "tag"` key in the `.book0.toml`/`book0-libraries.toml`
  example blocks (both CLIs' config sections use the same `[libraries]` example today — add
  `default-library` above it in both).
- Update the "no flag" usage line for `book0` (currently implies falling back to "Calibre's
  default library") to describe the new default-tag-from-config behavior, and the corresponding
  error case (no config file, or config file with no `default-library`, when `--tag` is
  omitted).
- Update `book0-remote`'s usage examples to show `--tag` is now optional, and document that an
  omitted tag relies on the *server's* `default-library`, not any client-side setting.
- Update the example route URLs anywhere they're shown (if any) to the new
  `?tag=...`-query-parameter shape.

- [ ] **Step 4: Verify the full suite, lint, and type-check still pass**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all pass, no new warnings

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md .claude/rules/architecture.md README.md
git commit -m "docs: document default-library config and the query-parameter tag shape"
```

---

## Out of scope (see design doc)

- `--genconfig` (printing a template config file, redirectable to a real file).
- Ensuring every subcommand/flag appears in `--help`/`-h` output (separate follow-up).
- A default `--server` URL for `book0-remote`.
- The book-id normalization/dedup plan and the far-future multi-library `(tag, id)` identity
  direction (tracked in `docs/superpowers/TODO.md`).
