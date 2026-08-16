# Remote client/server config files — design

## Purpose

`book0` and `book0-remote` should be invokable with the exact same argv (same subcommand,
same `--tag`) so a script or muscle-memory habit doesn't need to know which one it's running.
Today `book0-remote` always requires `--server URL`, so the two command lines never quite
match. This design makes `--server` optional, sourced from a new client-side config file
(`.book0-client.toml`), and symmetrically gives `book0-api` a server-side config file
(`.book0-server.toml`) for its listen address — replacing the CLI's separate `--host`/
`--port`/`--uds` flags with a single `--listen URL` flag whose URL scheme (`http` vs `unix`)
picks the transport, so the same unification applies on both sides of the config.

This closes the "default `--server` URL for `book0-remote`" item explicitly deferred out of
`docs/superpowers/specs/2026-08-13-default-tag-resolution-design.md`'s "Out of scope" (never
promoted to `docs/superpowers/TODO.md`, so there is no line to remove there).

## Config file formats

Both new files are personal/local, like `.book0.toml` — gitignored, never committed as
templates (unlike `book0-libraries.toml`, which is a committable `${VAR}` template because it
has no real paths in it). `.gitignore` gains two lines:

```
.book0-client.toml
.book0-server.toml
```

**`.book0-client.toml`** (read by `book0-remote`), single key:

```toml
server = "http://127.0.0.1:8000"
```

**`.book0-server.toml`** (read by `book0-api`), single key, URL scheme selects the transport:

```toml
listen = "http://127.0.0.1:8000"
```
```toml
# or, for a Unix domain socket:
listen = "unix:///run/book0.sock"
```

Neither file supports `${VAR}` expansion (no concrete need — these aren't paths crossing
environments the way `book0-libraries.toml`'s library directories do). Neither file's schema
is expected to stay single-key forever: both docstrings should say so, the way
`book0-libraries.toml`'s own header comment already documents its `default-library` key as an
optional addition — but no other key is designed here (YAGNI).

## `book0_cli_remote/config.py` (new)

Mirrors `book0_cli/config.py`'s shape exactly — same `xdg_config_path()`/`find_config_file()`
logic, different filename/subpath constants — because `book0_cli_remote` may never depend on
`book0_config` or `book0_cli` (`architecture.md`'s dependency direction), so this cannot be
shared code; it is the same deliberate non-sharing already established between the two CLIs'
`main.py`, extended to their config-discovery helper:

```python
LOCAL_CONFIG_FILENAME = ".book0-client.toml"
_XDG_CONFIG_SUBPATH = Path("book0") / "client.toml"

def xdg_config_path() -> Path: ...   # identical body to book0_cli/config.py's
def find_config_file() -> Path | None: ...   # identical body

def load_server(config_path: Path) -> str:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return data["server"]
```

`load_server` raises `tomllib.TOMLDecodeError`/`KeyError` uncaught, same fail-fast style as
`book0_config.load_libraries` — the caller (`book0_cli_remote/main.py`) catches and prints,
exactly as `book0_cli/main.py` already does around `load_libraries`.

## `book0_cli_remote/main.py`

`--server` drops `required=True` on all four subparsers (stays a plain optional flag).
Resolution is **lazy** — the config file is never looked up or parsed when `--server` is
given explicitly:

```python
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
```

`server` (not `args.server`) then feeds `httpx.Client(base_url=server)` when no `client` is
injected. No new domain error — this is a CLI-level configuration failure, not a
`book0_core`/gateway condition, so it's handled the same way the existing "No book0 config
file found" case is in `book0_cli/main.py` (print + `return 1`), not added to
`book0_core.errors`.

## `book0_api/cli.py`

`--host`, `--port`, and `--uds` are removed outright (no compatibility aliases — greenfield
project, per `CLAUDE.md`). Replaced by:

- `--listen URL` (optional) — `http://host:port` or `unix:///path`.
- `--server-config PATH` (optional, **never auto-discovered** — explicit flag only, since the
  server is started far less often than the CLIs are invoked and typing one extra flag isn't
  the friction this design is solving).

Resolution, also lazy (`--server-config` is never opened when `--listen` is given):

```python
listen = args.listen
if listen is None and args.server_config is not None:
    try:
        with open(args.server_config, "rb") as config_file:
            listen = tomllib.load(config_file)["listen"]
    except FileNotFoundError as error:
        parser.error(str(error))
    except (tomllib.TOMLDecodeError, KeyError) as error:
        parser.error(f"Invalid book0-server config file {args.server_config}: {error}")
if listen is None:
    listen = "http://127.0.0.1:8000"
```

URL → `uvicorn.run(...)` kwargs, via `urllib.parse.urlsplit`:

```python
parsed = urllib.parse.urlsplit(listen)
if parsed.scheme == "unix":
    uvicorn.run("book0_api.asgi:app", uds=parsed.path, reload=args.reload)
elif parsed.scheme == "http":
    uvicorn.run(
        "book0_api.asgi:app",
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 8000,
        reload=args.reload,
    )
else:
    parser.error(f"Unsupported --listen scheme: {parsed.scheme!r} (expected http or unix)")
```

All failure modes use `parser.error(...)` (prints usage + message to stderr, exits 2) — this
already is the file's existing convention for CLI-level validation (the `--uds`/`--host`
mutual-exclusion check it replaces used the same mechanism), so no new error-reporting style
is introduced.

This one-key loader lives directly in `book0_api/cli.py`, not `book0_config` — it has exactly
one caller and one key, no `${VAR}` expansion need, so adding it to the shared package would
be speculative sharing for a consumer that doesn't exist.

## Error handling

| Case | `book0-remote` | `book0-api` |
|---|---|---|
| No explicit flag, no config file found | stderr message + `return 1` | N/A — hardcoded default `http://127.0.0.1:8000` always applies |
| Config file found, invalid TOML / missing key | stderr message + `return 1` | `parser.error(...)`, exit 2 |
| `--server-config` path doesn't exist | — | `parser.error(...)`, exit 2 |
| `--listen`/`listen` has an unsupported URL scheme | — | `parser.error(...)`, exit 2 |

No new `book0_core` error type — every case here is a CLI-configuration failure, not a
library/gateway domain condition.

## Testing

- **Unit**, `tests/unit/test_cli_remote_config.py` (new): mirrors
  `tests/unit/test_cli_config.py` exactly (XDG-home override, XDG fallback, cwd-vs-XDG
  precedence, neither present) for the new filename/subpath; `load_server` unit tests (valid
  TOML, missing `server` key → `KeyError`, invalid TOML → `TOMLDecodeError`).
- **Unit**, `tests/unit/test_book0_api_cli.py`: replace every existing `--host`/`--port`/
  `--uds` test with `--listen` equivalents (`http://host:port`, `http://host` with no port →
  default 8000, `unix:///path`, unsupported scheme → exit 2). Delete the now-impossible
  `--uds`-and-`--host` mutual-exclusion tests (the flags no longer coexist) rather than
  leaving them red or skipped.
- **Integration**, `tests/integration/test_cli_remote_main.py`: `--server` explicit
  (regression, unchanged); `--server` omitted + `.book0-client.toml` present in `tmp_path`
  (`monkeypatch.chdir`) → resolves and is actually used (assert via monkeypatching
  `book0_cli_remote.main.httpx.Client` to capture `base_url`, same technique
  `test_book0_api_cli.py` already uses for `uvicorn.run`); `--server` omitted + nothing found →
  message + exit 1; config file present but invalid → message + exit 1; `--server` given
  explicitly must win even when an invalid `.book0-client.toml` sits in `cwd` (proves the
  laziness — the bad file is never opened).
- **Unit**, `tests/unit/test_book0_api_cli.py` (same file as above — it monkeypatches
  `uvicorn.run` and touches no real I/O beyond a `tmp_path` config file, same as its existing
  tests, so it doesn't move to `tests/integration/`): `--server-config` supplies `listen` when
  `--listen` is omitted; neither given → default `127.0.0.1:8000` (regression); `--listen`
  given explicitly must win even when `--server-config` points at an invalid file (laziness,
  same proof as above).

## Out of scope

- Any key beyond `server`/`listen` in either new file (a client-side default tag, TLS options,
  auth) — no concrete need yet; add if/when one appears, per each file's own doc comment.
- `${VAR}` expansion in either file — no concrete need (unlike `book0-libraries.toml`'s real
  cross-environment paths).
- Auto-discovery for `.book0-server.toml` (explicitly rejected — `--server-config` stays an
  explicit flag).
- Any change to `--tag`/`default-library` resolution (already shipped in
  `docs/superpowers/specs/2026-08-13-default-tag-resolution-design.md`) — orthogonal to this
  design.
