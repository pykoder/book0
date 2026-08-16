# Remote Client/Server Config Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `book0-remote`'s `--server` optional (sourced from a new `.book0-client.toml`),
and replace `book0-api`'s `--host`/`--port`/`--uds` with a single `--listen URL` flag backed
by a new, explicit `--server-config` (`.book0-server.toml`) — so `book0` and `book0-remote`
can be invoked with identical argv.

**Architecture:** A new `book0_cli_remote/config.py` mirrors `book0_cli/config.py`'s
cwd-then-XDG discovery exactly (duplicated by design — `book0_cli_remote` may never depend on
`book0_config` or `book0_cli`), plus a one-key TOML loader. `book0_cli_remote/main.py` uses it
lazily: only consulted when `--server` is omitted. `book0_api/cli.py` gains a `urlsplit`-based
`--listen` parser (scheme `http` → host/port, scheme `unix` → uds) and an explicit,
never-auto-discovered `--server-config` fallback, both replacing the old three-flag interface
outright (no compatibility aliases).

**Tech Stack:** Python 3.12, stdlib `argparse`/`tomllib`/`urllib.parse`, `httpx`, `pytest`, `uv`.

## Global Constraints

- Every command goes through `uv run <tool>` — never a bare `python`/`pytest`/`ruff`/`mypy`.
- `.book0-client.toml` and `.book0-server.toml` are personal/local files, like `.book0.toml`
  — gitignored, never committed as templates.
- Both new files are single-key for now (`server` / `listen`) — no `${VAR}` expansion, no
  other keys; do not add speculative fields.
- `book0_cli_remote` must never import `book0_config` or `book0_cli` — its config-discovery
  module is a deliberate duplicate of `book0_cli/config.py`'s shape, not a shared import.
- Resolution is lazy in both CLIs: the config file is never looked up or parsed when the
  corresponding explicit flag (`--server` / `--listen`) is already given.
- `book0_api/cli.py`'s `--host`, `--port`, `--uds` are removed outright — no deprecated
  aliases, no transition period (greenfield project).
- No new `book0_core` error type — every failure mode introduced here is a CLI-configuration
  failure, not a domain/gateway condition.
- Design doc: `docs/superpowers/specs/2026-08-16-remote-config-files-design.md`.

---

### Task 1: `book0_cli_remote/config.py` — client-side config discovery + loader

**Files:**
- Create: `src/book0_cli_remote/config.py`
- Test: `tests/unit/test_cli_remote_config.py`

**Interfaces:**
- Produces: `book0_cli_remote.config.LOCAL_CONFIG_FILENAME` (`str`, value
  `".book0-client.toml"`); `book0_cli_remote.config.xdg_config_path() -> Path`;
  `book0_cli_remote.config.find_config_file() -> Path | None`;
  `book0_cli_remote.config.load_server(config_path: Path) -> str` (raises
  `tomllib.TOMLDecodeError` or `KeyError` uncaught). Used by Task 2.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cli_remote_config.py`:

```python
import tomllib
from pathlib import Path

import pytest

from book0_cli_remote.config import find_config_file, load_server, xdg_config_path


def test_xdg_config_path_uses_xdg_config_home_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    xdg_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))

    assert xdg_config_path() == xdg_home / "book0" / "client.toml"


def test_xdg_config_path_falls_back_to_home_dot_config_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert xdg_config_path() == tmp_path / ".config" / "book0" / "client.toml"


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
    local_config = tmp_path / ".book0-client.toml"
    local_config.write_text('server = "http://127.0.0.1:8000"\n')

    assert find_config_file() == local_config


def test_find_config_file_returns_xdg_file_when_local_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    xdg_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))
    xdg_config = xdg_home / "book0" / "client.toml"
    xdg_config.parent.mkdir(parents=True)
    xdg_config.write_text('server = "http://127.0.0.1:8000"\n')

    assert find_config_file() == xdg_config


def test_find_config_file_prefers_local_over_xdg_when_both_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    local_config = tmp_path / ".book0-client.toml"
    local_config.write_text('server = "http://127.0.0.1:8000"\n')
    xdg_config = home / ".config" / "book0" / "client.toml"
    xdg_config.parent.mkdir(parents=True)
    xdg_config.write_text('server = "http://127.0.0.1:8000"\n')

    assert find_config_file() == local_config


def test_load_server_returns_the_server_value(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text('server = "http://192.168.1.5:9000"\n')

    assert load_server(config_path) == "http://192.168.1.5:9000"


def test_load_server_raises_key_error_when_server_key_is_missing(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text("other = 1\n")

    with pytest.raises(KeyError):
        load_server(config_path)


def test_load_server_raises_toml_decode_error_for_invalid_toml(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text("not valid toml === \n")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_server(config_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_remote_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'book0_cli_remote.config'`

- [ ] **Step 3: Write the implementation**

Create `src/book0_cli_remote/config.py`:

```python
import os
import tomllib
from pathlib import Path

LOCAL_CONFIG_FILENAME = ".book0-client.toml"
_XDG_CONFIG_SUBPATH = Path("book0") / "client.toml"


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


def load_server(config_path: Path) -> str:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return data["server"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_remote_config.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/config.py tests/unit/test_cli_remote_config.py
git commit -m "feat: add book0-remote client config discovery and loader"
```

---

### Task 2: Wire `.book0-client.toml` into `book0-remote`'s `--server` resolution

**Files:**
- Modify: `src/book0_cli_remote/main.py`
- Modify: `.gitignore`
- Test: `tests/integration/test_cli_remote_main.py`

**Interfaces:**
- Consumes: `book0_cli_remote.config.LOCAL_CONFIG_FILENAME`,
  `find_config_file() -> Path | None`, `load_server(config_path: Path) -> str`,
  `xdg_config_path() -> Path` (Task 1).

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_cli_remote_main.py` (imports at the top of that file already
include `Path`, `pytest`, `TestClient`, `create_app`, `run`, the table renderers, and the
`tests.conftest` fixtures used below — no new imports needed):

```python
def test_run_resolves_server_from_book0_client_toml_when_server_flag_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text('server = "http://127.0.0.1:1"\n')

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Could not reach the book0 server at http://127.0.0.1:1" in captured.err


def test_run_prefers_explicit_server_flag_over_book0_client_toml(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text("not valid toml === \n")
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["--server", "unused", "--tag", "fiction"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_error_when_server_flag_omitted_and_no_client_config_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "No --server given and no book0-remote client config file found" in (
        captured.err
    )


def test_run_reports_error_for_invalid_book0_client_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text("not valid toml === \n")

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Invalid book0-remote client config file" in captured.err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: FAIL — `argparse.ArgumentError` / `SystemExit(2)` on the first new test, since
`--server` is still `required=True`.

- [ ] **Step 3: Write the implementation**

Replace `src/book0_cli_remote/main.py` in full:

```python
import argparse
import sys
import tomllib

import httpx

from book0_cli_remote.config import (
    LOCAL_CONFIG_FILENAME,
    find_config_file,
    load_server,
    xdg_config_path,
)
from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_presentation.tables import (
    format_missing_ids_message,
    order_book_details_by_ids,
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)

_SUBCOMMANDS = ("books", "authors", "publishers", "books-detail")
_SERVER_HELP = (
    "book0-api server URL; omit to use .book0-client.toml's server setting, if found"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0-remote")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--server", help=_SERVER_HELP)
    books_parser.add_argument("--tag")

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--server", help=_SERVER_HELP)
    authors_parser.add_argument("--tag")

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--server", help=_SERVER_HELP)
    publishers_parser.add_argument("--tag")

    books_detail_parser = subparsers.add_parser("books-detail")
    books_detail_parser.add_argument(
        "--ids", required=True, help="comma-separated list of book ids"
    )
    books_detail_parser.add_argument("--server", help=_SERVER_HELP)
    books_detail_parser.add_argument("--tag")

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in ("-h", "--help"):
        return argv
    if not argv or argv[0] not in _SUBCOMMANDS:
        return ["books", *argv]
    return argv


def run(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(_normalize_argv(raw_argv))

    server = args.server
    if server is None:
        config_path = find_config_file()
        if config_path is None:
            print(
                f"No --server given and no book0-remote client config file found "
                f"(looked for ./{LOCAL_CONFIG_FILENAME} and {xdg_config_path()})",
                file=sys.stderr,
            )
            return 1
        try:
            server = load_server(config_path)
        except (tomllib.TOMLDecodeError, KeyError) as error:
            print(
                f"Invalid book0-remote client config file {config_path}: {error}",
                file=sys.stderr,
            )
            return 1

    owns_client = client is None
    if client is None:
        client = httpx.Client(base_url=server)

    try:
        gateway = HttpLibraryGateway(client, args.tag)
        try:
            if args.command == "authors":
                print(render_author_table(gateway.list_authors()))
            elif args.command == "publishers":
                print(render_publisher_table(gateway.list_publishers()))
            elif args.command == "books-detail":
                ids = (
                    [segment.strip() for segment in args.ids.split(",")]
                    if args.ids
                    else []
                )
                result = gateway.get_book_details(ids)
                ordered_books = order_book_details_by_ids(result, ids)
                print(render_book_details_table(ordered_books))
                missing_ids_message = format_missing_ids_message(result.missing_ids)
                if missing_ids_message is not None:
                    print(missing_ids_message)
            else:
                print(render_book_table(gateway.list_books()))
        except (
            LibraryNotFoundError,
            NotACalibreLibraryError,
            TagRequiredError,
        ) as error:
            print(str(error), file=sys.stderr)
            return 1
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            print(
                f"Could not reach the book0 server at {server}: {error}",
                file=sys.stderr,
            )
            return 1
    finally:
        if owns_client:
            client.close()

    return 0


def main() -> None:
    sys.exit(run())
```

Note the unreachable-server message now interpolates `server` (the resolved value), not
`args.server` (which is `None` in the config-file-resolved case) — this is required for
`test_run_resolves_server_from_book0_client_toml_when_server_flag_is_omitted` to see the
right URL in the message.

Add to `.gitignore` (new line, next to the existing `.book0.toml`):

```
.book0-client.toml
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_remote_main.py tests/unit/test_cli_remote_config.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `uv run pytest -q`
Expected: PASS, no regressions elsewhere

- [ ] **Step 6: Commit**

```bash
git add src/book0_cli_remote/main.py .gitignore tests/integration/test_cli_remote_main.py
git commit -m "feat: make book0-remote's --server optional via .book0-client.toml"
```

---

### Task 3: Replace `book0-api`'s `--host`/`--port`/`--uds` with `--listen URL`

**Files:**
- Modify: `src/book0_api/cli.py`
- Modify: `tests/unit/test_book0_api_cli.py`

**Interfaces:**
- Produces: `book0_api.cli._listen_kwargs(listen: str, parser: argparse.ArgumentParser) -> dict[str, str | int]` (private, used by Task 4).

- [ ] **Step 1: Update the tests**

In `tests/unit/test_book0_api_cli.py`:

Keep unchanged: `test_run_sets_config_env_var_from_config_flag`,
`test_run_starts_uvicorn_on_the_asgi_app_without_reload_by_default`,
`test_run_enables_reload_when_reload_flag_is_passed`,
`test_run_exits_with_status_2_when_config_flag_is_missing` (none of these reference
`--host`/`--port`/`--uds`).

Replace `test_run_passes_through_custom_host_and_port_flags` with:

```python
def test_run_passes_through_a_custom_listen_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(["--config", str(config_path), "--listen", "http://0.0.0.0:9000"])

    assert calls == [
        (("book0_api.asgi:app",), {"host": "0.0.0.0", "port": 9000, "reload": False})
    ]


def test_run_defaults_the_port_when_listen_url_omits_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(["--config", str(config_path), "--listen", "http://0.0.0.0"])

    assert calls == [
        (("book0_api.asgi:app",), {"host": "0.0.0.0", "port": 8000, "reload": False})
    ]
```

Replace `test_run_passes_uds_path_to_uvicorn_when_uds_flag_is_given` with:

```python
def test_run_passes_uds_path_to_uvicorn_for_a_unix_listen_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    socket_path = tmp_path / "book0-api.sock"
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(["--config", str(config_path), "--listen", f"unix://{socket_path}"])

    assert calls == [
        (("book0_api.asgi:app",), {"uds": str(socket_path), "reload": False})
    ]
```

Delete `test_run_exits_with_status_2_when_uds_and_host_are_both_given` and
`test_run_exits_with_status_2_when_uds_and_port_are_both_given` — `--host`/`--port`/`--uds`
no longer coexist, so this mutual-exclusion case is gone, not merely untested.

Add:

```python
def test_run_exits_with_status_2_for_an_unsupported_listen_scheme(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    config_path = tmp_path / "book0-libraries.toml"
    monkeypatch.setattr("book0_api.cli.uvicorn.run", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        run(["--config", str(config_path), "--listen", "ftp://host:21"])

    assert exc_info.value.code == 2
    assert "Unsupported --listen scheme" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_api_cli.py -v`
Expected: FAIL — `error: unrecognized arguments: --listen ...` on the new/replaced tests
(`--listen` doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Replace `src/book0_api/cli.py` in full:

```python
import argparse
import os
import sys
import urllib.parse

import uvicorn

CONFIG_ENV_VAR = "BOOK0_API_CONFIG"
_DEFAULT_LISTEN = "http://127.0.0.1:8000"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0-api")
    parser.add_argument(
        "--config", required=True, help="path to the libraries TOML config file"
    )
    parser.add_argument(
        "--reload", action="store_true", help="enable uvicorn's auto-reload"
    )
    parser.add_argument(
        "--listen",
        default=None,
        help=(
            "URL to listen on: http://host:port or unix:///path/to/socket "
            f"(default: {_DEFAULT_LISTEN})"
        ),
    )
    return parser


def _listen_kwargs(
    listen: str, parser: argparse.ArgumentParser
) -> dict[str, str | int]:
    parsed = urllib.parse.urlsplit(listen)
    if parsed.scheme == "unix":
        return {"uds": parsed.path}
    if parsed.scheme == "http":
        return {"host": parsed.hostname or "127.0.0.1", "port": parsed.port or 8000}
    parser.error(
        f"Unsupported --listen scheme: {parsed.scheme!r} (expected http or unix)"
    )
    raise AssertionError("unreachable")  # parser.error always exits


def run(argv: list[str] | None = None) -> None:
    raw_argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    os.environ[CONFIG_ENV_VAR] = args.config

    listen = args.listen if args.listen is not None else _DEFAULT_LISTEN

    uvicorn.run(
        "book0_api.asgi:app",
        reload=args.reload,
        **_listen_kwargs(listen, parser),
    )


def main() -> None:
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_api_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/cli.py tests/unit/test_book0_api_cli.py
git commit -m "feat: replace book0-api's --host/--port/--uds with a single --listen URL"
```

---

### Task 4: Add `--server-config` fallback for `--listen`

**Files:**
- Modify: `src/book0_api/cli.py`
- Modify: `.gitignore`
- Test: `tests/unit/test_book0_api_cli.py`

**Interfaces:**
- Consumes: `_listen_kwargs` (Task 3), `_DEFAULT_LISTEN` (Task 3).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_book0_api_cli.py`:

```python
def test_run_uses_listen_value_from_server_config_when_listen_flag_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    server_config_path = tmp_path / ".book0-server.toml"
    server_config_path.write_text('listen = "http://0.0.0.0:9000"\n')
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(
        [
            "--config",
            str(config_path),
            "--server-config",
            str(server_config_path),
        ]
    )

    assert calls == [
        (("book0_api.asgi:app",), {"host": "0.0.0.0", "port": 9000, "reload": False})
    ]


def test_run_prefers_listen_flag_over_server_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    server_config_path = tmp_path / ".book0-server.toml"
    server_config_path.write_text("not valid toml === \n")
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(
        [
            "--config",
            str(config_path),
            "--listen",
            "http://0.0.0.0:9000",
            "--server-config",
            str(server_config_path),
        ]
    )

    assert calls == [
        (("book0_api.asgi:app",), {"host": "0.0.0.0", "port": 9000, "reload": False})
    ]


def test_run_exits_with_status_2_when_server_config_path_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    monkeypatch.setattr("book0_api.cli.uvicorn.run", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        run(
            [
                "--config",
                str(config_path),
                "--server-config",
                str(tmp_path / "does-not-exist.toml"),
            ]
        )

    assert exc_info.value.code == 2


def test_run_exits_with_status_2_when_server_config_is_invalid_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    config_path = tmp_path / "book0-libraries.toml"
    server_config_path = tmp_path / ".book0-server.toml"
    server_config_path.write_text("not valid toml === \n")
    monkeypatch.setattr("book0_api.cli.uvicorn.run", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        run(
            [
                "--config",
                str(config_path),
                "--server-config",
                str(server_config_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "Invalid book0-server config file" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_api_cli.py -v`
Expected: FAIL — `error: unrecognized arguments: --server-config ...`

- [ ] **Step 3: Write the implementation**

In `src/book0_api/cli.py`, add `import tomllib` to the imports, add the new argument to
`_build_parser`:

```python
    parser.add_argument(
        "--server-config",
        default=None,
        help=(
            "path to a .book0-server.toml file providing --listen when it is "
            "omitted (never auto-discovered)"
        ),
    )
```

(placed after the `--listen` argument, before `return parser`), and replace `run`'s body:

```python
def run(argv: list[str] | None = None) -> None:
    raw_argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    os.environ[CONFIG_ENV_VAR] = args.config

    listen = args.listen
    if listen is None and args.server_config is not None:
        try:
            with open(args.server_config, "rb") as config_file:
                listen = tomllib.load(config_file)["listen"]
        except FileNotFoundError as error:
            parser.error(str(error))
        except (tomllib.TOMLDecodeError, KeyError) as error:
            parser.error(
                f"Invalid book0-server config file {args.server_config}: {error}"
            )
    if listen is None:
        listen = _DEFAULT_LISTEN

    uvicorn.run(
        "book0_api.asgi:app",
        reload=args.reload,
        **_listen_kwargs(listen, parser),
    )
```

Add to `.gitignore` (next to the `.book0-client.toml` line added in Task 2):

```
.book0-server.toml
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_api_cli.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/cli.py .gitignore tests/unit/test_book0_api_cli.py
git commit -m "feat: add --server-config fallback for book0-api's --listen"
```

---

### Task 5: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Lint**

Run: `uv run ruff check .`
Expected: no errors (fix any and re-run if there are)

- [ ] **Step 2: Format**

Run: `uv run ruff format .`
Expected: no diffs, or only whitespace/quote-style diffs from the new code above — if it
reformats anything, re-run Step 1 and the affected test files from Tasks 1-4 to confirm
nothing broke, then amend the affected commit's changes into a new `style: ruff format`
commit.

- [ ] **Step 3: Type-check**

Run: `uv run mypy src`
Expected: no errors. Pay particular attention to `book0_api/cli.py::_listen_kwargs`'s return
type against every call site, and `book0_cli_remote/config.py::find_config_file`'s
`Path | None` return against its one caller in `book0_cli_remote/main.py`.

- [ ] **Step 4: Full test suite**

Run: `uv run pytest -q`
Expected: all tests pass, including every test from Tasks 1-4 and every pre-existing test
(no regressions in `book0`, `book0_api`'s routes, or `HttpLibraryGateway`).

- [ ] **Step 5: Commit (only if Steps 1-3 produced changes)**

```bash
git add -A
git commit -m "style: ruff format after --listen/config-file changes"
```
