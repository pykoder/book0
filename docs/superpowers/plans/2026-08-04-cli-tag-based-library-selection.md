# book0_cli Tag-Based Library Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `book0`'s required `--library <path>` flag with an optional `--tag <tag>` flag, resolved through the same TOML tag→path config format `book0_api` already uses, falling back to Calibre's own default library location when `--tag` is omitted.

**Architecture:** Extract the existing TOML tag→path loader out of `book0_api/config.py` into a new stdlib-only `book0_config` package so both `book0_cli` and `book0_api` can depend on it without `book0_cli` depending on `book0_api`. Add a `book0_cli`-only `config.py` for the CLI-specific concerns (default Calibre path, XDG-style config-file discovery). Update `book0_cli/main.py`'s argument parsing and resolution logic on top of those two building blocks; everything downstream (`_resolve_db_path`, `SqliteLibraryGateway`, error handling, table rendering) is untouched.

**Tech Stack:** Python 3.12, stdlib `tomllib`/`argparse`/`pathlib`, `pytest` + `pytest`'s `monkeypatch`/`tmp_path` fixtures, `uv` for all tooling invocations.

## Global Constraints

- Every command goes through `uv run <tool>` - never a bare `python`/`pytest`/`ruff`/`mypy` (CLAUDE.md).
- Every function signature is fully type-hinted; no bare `Any` (`.claude/rules/python-design.md`).
- `book0_core` must never depend on `book0_cli`, `book0_cli_remote`, `book0_api`, `argparse`, or any web framework (CLAUDE.md absolute prohibitions) - this plan does not touch `book0_core` at all, so this is satisfied by construction.
- `book0_cli` and `book0_cli_remote` intentionally do not share a run-loop function - do not introduce one (`.claude/rules/python-design.md`).
- No mutable default arguments; no new abstraction/config option beyond what the spec requires (CLAUDE.md, YAGNI).
- Every new function/class with no I/O gets a unit test; every changed CLI behavior gets an integration test against a real temporary SQLite file (`.claude/rules/testing.md`) - no mocked `sqlite3.Connection`.
- Never leave a test red, skipped, or commented out to make the suite pass (CLAUDE.md absolute prohibitions).
- After every task: `uv run ruff check .`, `uv run ruff format .`, `uv run mypy src` must report no new issue.
- `book0_api`'s unconfigured-tag behavior (`GET /libraries/{tag}/books` for an unknown tag returns `200 []`) is explicitly out of scope - do not touch `book0_api/main.py`'s route logic in this plan, even though it now differs from `book0_cli`'s new error-and-exit-1 behavior for the equivalent case. See the spec's "Known gap" section.
- Reference spec: `docs/superpowers/specs/2026-08-04-cli-tag-based-library-selection-design.md`.

---

## File Structure

```
src/
├── book0_config/                  # NEW package
│   ├── __init__.py                 # NEW, empty (matches every other package's __init__.py)
│   └── config.py                   # NEW: load_libraries, moved verbatim from book0_api/config.py
├── book0_cli/
│   ├── config.py                   # NEW: default_library_path, xdg_config_path, find_config_file
│   └── main.py                     # MODIFIED: --tag replaces --library
├── book0_api/
│   ├── asgi.py                     # MODIFIED: import load_libraries from book0_config
│   └── config.py                   # DELETED (Task 2)
tests/
├── unit/
│   ├── test_book0_config.py        # NEW (Task 1), moved from test_book0_api_config.py
│   ├── test_book0_api_config.py    # DELETED (Task 2)
│   └── test_cli_config.py          # NEW (Task 3)
└── integration/
    └── test_cli_main.py            # REWRITTEN (Task 4): --library tests replaced by --tag tests
pyproject.toml                      # MODIFIED (Task 1): wheel packages list gains src/book0_config
CLAUDE.md                           # MODIFIED (Task 5): tooling table row
.claude/rules/architecture.md       # MODIFIED (Task 5): tree + dependency direction
.claude/rules/testing.md            # MODIFIED (Task 5): end-of-task checklist branch list
```

---

### Task 1: Create the `book0_config` package

**Files:**
- Create: `src/book0_config/__init__.py`
- Create: `src/book0_config/config.py`
- Create: `tests/unit/test_book0_config.py`
- Modify: `pyproject.toml:22-28`

**Interfaces:**
- Produces: `book0_config.config.load_libraries(config_path: Path) -> dict[str, Path]` - identical signature and behavior to today's `book0_api.config.load_libraries` (used by Task 2 and Task 4).

- [ ] **Step 1: Write the failing test file**

Create `tests/unit/test_book0_config.py` with the exact test bodies from the existing `tests/unit/test_book0_api_config.py`, only the import changed:

```python
import tomllib
from pathlib import Path

import pytest

from book0_config.config import load_libraries


def test_load_libraries_returns_tag_to_path_mapping(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\nwork = "/path/to/work/metadata.db"\n'
    )

    libraries = load_libraries(config_path)

    assert libraries == {
        "fiction": Path("/path/to/fiction/metadata.db"),
        "work": Path("/path/to/work/metadata.db"),
    }


def test_load_libraries_expands_env_var_placeholders_in_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "${FICTION_LIBRARY_PATH}/metadata.db"\n'
    )
    monkeypatch.setenv("FICTION_LIBRARY_PATH", "/real/fiction")

    libraries = load_libraries(config_path)

    assert libraries == {"fiction": Path("/real/fiction/metadata.db")}


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

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_book0_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'book0_config'`

- [ ] **Step 3: Create the `book0_config` package**

Create `src/book0_config/__init__.py` (empty file, matching every other package's `__init__.py`).

Create `src/book0_config/config.py` with exactly today's `src/book0_api/config.py` content:

```python
import os
import re
import tomllib
from pathlib import Path

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _expand_env_vars(value: str) -> str:
    return _ENV_VAR_PATTERN.sub(lambda match: os.environ[match.group(1)], value)


def load_libraries(config_path: Path) -> dict[str, Path]:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return {
        tag: Path(_expand_env_vars(path)) for tag, path in data["libraries"].items()
    }
```

- [ ] **Step 4: Register the new package with hatchling**

Modify `pyproject.toml`'s `[tool.hatch.build.targets.wheel]` packages list:

```toml
[tool.hatch.build.targets.wheel]
packages = [
    "src/book0_core",
    "src/book0_presentation",
    "src/book0_config",
    "src/book0_cli",
    "src/book0_api",
    "src/book0_cli_remote",
]
```

Run: `uv sync`
Expected: syncs cleanly, `book0_config` becomes importable in the project's environment.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_book0_config.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Lint, format, type-check**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/book0_config tests/unit/test_book0_config.py pyproject.toml
git commit -m "feat: add book0_config package with the tag-to-path TOML loader"
```

---

### Task 2: Switch `book0_api` to `book0_config`, remove `book0_api/config.py`

**Files:**
- Modify: `src/book0_api/asgi.py`
- Delete: `src/book0_api/config.py`
- Delete: `tests/unit/test_book0_api_config.py`

**Interfaces:**
- Consumes: `book0_config.config.load_libraries` (from Task 1).
- Produces: nothing new - `book0_api`'s public behavior (`create_app`, the `/libraries/{tag}/books` route) is unchanged; only where `load_libraries` is imported from changes.

- [ ] **Step 1: Update `book0_api/asgi.py`'s import**

Modify `src/book0_api/asgi.py`:

```python
import os
from pathlib import Path

from book0_api.main import create_app
from book0_config.config import load_libraries

app = create_app(load_libraries(Path(os.environ["BOOK0_API_CONFIG"])))
```

(Only the import line changes: `from book0_api.config import load_libraries` becomes `from book0_config.config import load_libraries`.)

- [ ] **Step 2: Delete the now-superseded files**

```bash
git rm src/book0_api/config.py tests/unit/test_book0_api_config.py
```

- [ ] **Step 3: Confirm nothing else references `book0_api.config`**

Run: `grep -rn "book0_api.config\|book0_api import config" src tests`
Expected: no output

- [ ] **Step 4: Run the full unit and e2e suites**

Run: `uv run pytest tests/unit tests/e2e -v`
Expected: PASS - in particular `tests/e2e/test_book0_api_main.py` still passes unchanged, proving `book0_api`'s behavior didn't move.

- [ ] **Step 5: Lint, format, type-check**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "refactor: point book0_api at book0_config, drop book0_api/config.py"
```

---

### Task 3: `book0_cli/config.py` - default path and config-file discovery

**Files:**
- Create: `src/book0_cli/config.py`
- Create: `tests/unit/test_cli_config.py`

**Interfaces:**
- Produces:
  - `book0_cli.config.LOCAL_CONFIG_FILENAME: str` (the literal `".book0.toml"`, exported so `main.py`'s error message can reference it without duplicating the literal - used by Task 4)
  - `book0_cli.config.default_library_path() -> Path` (used by Task 4)
  - `book0_cli.config.xdg_config_path() -> Path` (used by Task 4)
  - `book0_cli.config.find_config_file() -> Path | None` (used by Task 4)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cli_config.py`:

```python
from pathlib import Path

import pytest

from book0_cli.config import default_library_path, find_config_file, xdg_config_path


def test_default_library_path_is_calibre_library_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_library_path() == tmp_path / "Calibre Library"


def test_xdg_config_path_uses_xdg_config_home_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    xdg_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))

    assert xdg_config_path() == xdg_home / "book0" / "config.toml"


def test_xdg_config_path_falls_back_to_home_dot_config_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert xdg_config_path() == tmp_path / ".config" / "book0" / "config.toml"


def test_find_config_file_returns_none_when_neither_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert find_config_file() is None


def test_find_config_file_returns_local_file_when_it_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    local_config = tmp_path / ".book0.toml"
    local_config.write_text("[libraries]\n")

    assert find_config_file() == local_config


def test_find_config_file_returns_xdg_file_when_local_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    xdg_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))
    xdg_config = xdg_home / "book0" / "config.toml"
    xdg_config.parent.mkdir(parents=True)
    xdg_config.write_text("[libraries]\n")

    assert find_config_file() == xdg_config


def test_find_config_file_prefers_local_over_xdg_when_both_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    local_config = tmp_path / ".book0.toml"
    local_config.write_text("[libraries]\n")
    xdg_config = home / ".config" / "book0" / "config.toml"
    xdg_config.parent.mkdir(parents=True)
    xdg_config.write_text("[libraries]\n")

    assert find_config_file() == local_config
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'book0_cli.config'`

- [ ] **Step 3: Implement `book0_cli/config.py`**

Create `src/book0_cli/config.py`:

```python
import os
from pathlib import Path

LOCAL_CONFIG_FILENAME = ".book0.toml"
_XDG_CONFIG_SUBPATH = Path("book0") / "config.toml"


def default_library_path() -> Path:
    return Path.home() / "Calibre Library"


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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_config.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Lint, format, type-check**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/book0_cli/config.py tests/unit/test_cli_config.py
git commit -m "feat: add book0_cli config discovery (default path, local/XDG config lookup)"
```

---

### Task 4: `book0_cli/main.py` - `--tag` replaces `--library`

**Files:**
- Modify: `src/book0_cli/main.py`
- Modify (full rewrite): `tests/integration/test_cli_main.py`

**Interfaces:**
- Consumes: `book0_cli.config.{LOCAL_CONFIG_FILENAME, default_library_path, find_config_file, xdg_config_path}` (Task 3), `book0_config.config.load_libraries` (Task 1).
- Produces: `book0_cli.main.run(argv: list[str] | None = None) -> int` - same signature as today; `--tag` (optional) replaces `--library` (required) as the only CLI flag.

- [ ] **Step 1: Write the failing/rewritten integration tests**

Replace the full contents of `tests/integration/test_cli_main.py`:

```python
import shutil
import sqlite3
from pathlib import Path

import pytest

from book0_cli.main import run
from book0_presentation.tables import render_table
from tests.conftest import CALIBRE_LIBRARY_BOOKS


def _write_config(config_path: Path, tag: str, library_path: Path) -> None:
    config_path.write_text(f'[libraries]\n{tag} = "{library_path}"\n')


def test_run_prints_table_using_default_library_path_when_tag_is_omitted(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    default_library_dir = home / "Calibre Library"
    default_library_dir.mkdir(parents=True)
    shutil.copy(calibre_metadata_db, default_library_dir / "metadata.db")
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run([])

    assert exit_code == 0
    assert capsys.readouterr().out == render_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_missing_library_at_default_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_prints_table_when_tag_resolves_via_local_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["--tag", "fiction"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_prints_table_when_tag_resolves_to_the_library_directory(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db.parent)

    exit_code = run(["--tag", "fiction"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_prints_table_when_tag_resolves_via_xdg_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    config_path = home / ".config" / "book0" / "config.toml"
    config_path.parent.mkdir(parents=True)
    _write_config(config_path, "fiction", calibre_metadata_db)

    exit_code = run(["--tag", "fiction"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_missing_config_file_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_unknown_tag_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", tmp_path / "fiction.db")

    exit_code = run(["--tag", "work"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_empty_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, pubdate TEXT);
            CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY, book INTEGER, author INTEGER
            );
            """
        )
        connection.commit()
    finally:
        connection.close()
    _write_config(tmp_path / ".book0.toml", "empty", db_path)

    exit_code = run(["--tag", "empty"])

    assert exit_code == 0
    assert capsys.readouterr().out == "No books found.\n"


def test_run_reports_non_calibre_library_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    _write_config(tmp_path / ".book0.toml", "bad", db_path)

    exit_code = run(["--tag", "bad"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: FAIL - `argparse` rejects `--tag` (unrecognized argument) since `main.py` still only defines `--library`, and calling `run([])` fails because `--library` is still required.

- [ ] **Step 3: Rewrite `book0_cli/main.py`**

Replace `src/book0_cli/main.py`:

```python
import argparse
import sys
from pathlib import Path

from book0_cli.config import (
    LOCAL_CONFIG_FILENAME,
    default_library_path,
    find_config_file,
    xdg_config_path,
)
from book0_config.config import load_libraries
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.sqlite_gateway import SqliteLibraryGateway
from book0_presentation.tables import render_table


def _resolve_db_path(library_path: Path) -> Path:
    if library_path.is_dir():
        return library_path / "metadata.db"
    return library_path


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book0")
    parser.add_argument("--tag")
    args = parser.parse_args(argv)

    if args.tag is None:
        library_path = default_library_path()
    else:
        config_path = find_config_file()
        if config_path is None:
            print(
                f"No book0 config file found (looked for ./{LOCAL_CONFIG_FILENAME} "
                f"and {xdg_config_path()})",
                file=sys.stderr,
            )
            return 1

        library_path = load_libraries(config_path).get(args.tag)
        if library_path is None:
            print(f"Unknown library tag: {args.tag!r}", file=sys.stderr)
            return 1

    db_path = _resolve_db_path(library_path)
    gateway = SqliteLibraryGateway(db_path)

    try:
        books = gateway.list_books()
    except (LibraryNotFoundError, NotACalibreLibraryError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print(render_table(books))
    return 0


def main() -> None:
    sys.exit(run())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest`
Expected: PASS - confirms no regression in `book0_core`, `book0_presentation`, `book0_api`, or `book0_cli_remote` tests.

- [ ] **Step 6: Lint, format, type-check**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/book0_cli/main.py tests/integration/test_cli_main.py
git commit -m "feat: replace book0's --library flag with --tag"
```

---

### Task 5: Update project documentation

**Files:**
- Modify: `CLAUDE.md:45`
- Modify: `.claude/rules/architecture.md`
- Modify: `.claude/rules/testing.md:36`

**Interfaces:** none (documentation only, no code).

- [ ] **Step 1: Update `CLAUDE.md`'s tooling table**

In `CLAUDE.md`, change line 45 from:

```
| Run the direct CLI | `uv run book0 --library <path>` |
```

to:

```
| Run the direct CLI | `uv run book0 [--tag <tag>]` |
```

- [ ] **Step 2: Update `.claude/rules/architecture.md`'s tree**

Replace the `## Current layout` code block with:

```
book0-libraries.toml            # committed template for BOOK0_API_CONFIG: ${VAR_NAME}
                                  # placeholders, never real paths - see book0_config/config.py below
src/
├── book0_core/
│   ├── models.py               # Book: frozen dataclass (id, title, authors, pubdate)
│   ├── errors.py                # LibraryNotFoundError, NotACalibreLibraryError
│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book]
│   └── sqlite_gateway.py          # SqliteLibraryGateway: reads metadata.db read-only
├── book0_presentation/
│   └── tables.py                  # render_table(list[Book]) -> str, aligned plain-text table
├── book0_config/
│   └── config.py                  # load_libraries(path) -> dict[str, Path], reads a TOML file;
│                                    # shared by book0_cli and book0_api
├── book0_cli/
│   ├── config.py                  # default_library_path(), xdg_config_path(), find_config_file()
│   └── main.py                    # `book0` entry point: --tag TAG (optional) -> SqliteLibraryGateway
├── book0_api/
│   ├── main.py                    # create_app(libraries: dict[str, Path]) -> FastAPI
│   ├── asgi.py                    # `app` wired from BOOK0_API_CONFIG - the real uvicorn entry point
│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate
└── book0_cli_remote/
    ├── main.py                    # `book0-remote` entry point: --server URL --tag TAG -> HttpLibraryGateway
    └── http_gateway.py             # HttpLibraryGateway: implements LibraryGateway over HTTP
```

- [ ] **Step 3: Update `.claude/rules/architecture.md`'s dependency direction section**

Replace the `## Dependency direction` section's diagram and bullets with:

```
- `book0_core` depends on nothing project-specific and has no web/HTTP dependency.
- `book0_presentation` depends only on `book0_core` (needs `Book` for `render_table`'s
  signature). No CLI, no web framework.
- `book0_config` depends on nothing project-specific - stdlib only (`tomllib`, `os`, `re`,
  `pathlib`).
- `book0_cli` depends on `book0_core`, `book0_presentation`, **and `book0_config`** - directly
  on `book0_core` (for `SqliteLibraryGateway` and the domain errors), not merely transitively
  through `book0_presentation`.
- `book0_api` depends on `book0_core` **and `book0_config`**. Never imports `book0_cli`,
  `book0_cli_remote`, or `book0_presentation` - the API returns JSON, it never renders a
  table.
- `book0_cli_remote` depends on `book0_core` + `book0_presentation` + `httpx`. Never imports
  `book0_api` or `book0_config` - it only knows the REST contract (a URL and a JSON shape),
  not the server's internals or how tags get resolved to paths.
- Nothing depends on `book0_cli` or `book0_cli_remote` - both are leaf packages, and neither
  depends on the other. Each has its own full `main.py`; the only thing that differs between
  them, behaviorally, is which `LibraryGateway` implementation gets constructed and which
  flags feed it (`--tag TAG`, optional and defaulting to Calibre's own default library path,
  vs. `--server URL --tag TAG`, both required).
- Code that talks to `metadata.db` (SQL, `sqlite3.connect`, schema assumptions) lives only in
  `book0_core/sqlite_gateway.py`. Nothing outside it should open a connection or write SQL -
  including `book0_api`, which calls `SqliteLibraryGateway` exactly like `book0_cli` does.
- Anything that consumes books (either CLI, a future third consumer) depends on the
  `LibraryGateway` Protocol, not on a concrete implementation, so a gateway can be substituted
  without changing the caller.
```

- [ ] **Step 4: Update `.claude/rules/testing.md`'s end-of-task checklist**

Change line 36 from:

```
- [ ] No regression on the callers of the changed code - if `book0_core` changed, check both
      `book0_cli` and `book0_api`; if the `LibraryGateway` Protocol changed, check both
      `SqliteLibraryGateway` and `HttpLibraryGateway`.
```

Find and replace the line above it in the same bullet (the one naming `_resolve_db_path`):

```
- [ ] Nominal, boundary, and error cases covered (missing library, non-Calibre file, empty
      library, unconfigured tag, multiple authors, `NULL` pubdate, unreachable server).
- [ ] No regression on the callers of the changed code - if `book0_core` changed, check both
```

to:

```
- [ ] Review every conditional branch and exception path before closing the task - in
      particular `book0_cli/main.py::run`'s tag-resolution branches (`--tag` omitted vs.
      given, config file found vs. not found, tag present vs. absent in a found config
      file), both branches of `_resolve_db_path` (directory vs. file), both caught
      exception types in either CLI's `run()`, and all three response branches in
      `book0_api/main.py::list_books` (unknown tag, `LibraryNotFoundError`,
      `NotACalibreLibraryError`).
- [ ] Nominal, boundary, and error cases covered (missing library, non-Calibre file, empty
      library, unconfigured tag, multiple authors, `NULL` pubdate, unreachable server).
- [ ] No regression on the callers of the changed code - if `book0_core` changed, check both
```

(This merges the existing "Review every conditional branch..." bullet's content, updated for the new `book0_cli` branches, without duplicating the unrelated `book0_api` checklist items already present elsewhere in the file.)

- [ ] **Step 5: Verify no stale reference remains**

Run: `grep -rn -- "--library" CLAUDE.md .claude/rules/ README.md 2>/dev/null`
Expected: no output (confirms every doc reference to the old flag was updated).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md .claude/rules/architecture.md .claude/rules/testing.md
git commit -m "docs: update architecture/testing docs for book0_config and book0_cli --tag"
```

---

## Final Verification

- [ ] Run the entire suite once more end to end: `uv run pytest -v`
- [ ] Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` with zero findings
- [ ] Manually run `uv run book0 --tag <a-tag-in-a-real-.book0.toml>` and `uv run book0` (no flag) against a real or sample Calibre library to confirm the CLI behaves as designed end to end
