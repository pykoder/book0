# book0_cli tag-based library selection (design)

## Overview

`book0` (the direct CLI) and `book0-remote` currently select a library two
different ways: `book0 --library <path>` takes a raw filesystem path,
`book0-remote --server <url> --tag <tag>` takes a tag resolved server-side
against a TOML config. This is confusing for a person switching between the
two - the same mental concept ("which library do I mean?") is spelled two
different ways.

This changes `book0` to also select a library by `--tag`, resolved the same
way `book0_api` already resolves tags: a TOML file with a `[libraries]` table
mapping tag -> path, `${VAR_NAME}` placeholders expanded against the
environment. `--tag` is optional; omitting it falls back to Calibre's own
default library location, so the common single-library case still needs zero
configuration.

`book0-remote` is unchanged - it already has `--tag`, and it never reads the
TOML file itself (it calls `book0_api` over HTTP, which does the resolving).

## Architecture

A new package, **`book0_config`**, holds the TOML tag -> path loader. It is
moved out of `book0_api/config.py` rather than left there, because
`book0_cli` needs the same loader and is not allowed to depend on `book0_api`
(see the project's one-way dependency direction). `book0_config` depends on
nothing project-specific (stdlib only: `tomllib`, `re`, `os`, `pathlib`), so
both `book0_cli` and `book0_api` can depend on it without creating a new edge
between leaf packages.

```
src/
├── book0_core/                    # unchanged
├── book0_presentation/            # unchanged
├── book0_config/
│   └── config.py                  # load_libraries(path) -> dict[str, Path], moved from book0_api/config.py
├── book0_cli/
│   ├── config.py                  # NEW: default_library_path(), find_config_file() - CLI-only concerns
│   └── main.py                    # --tag (optional) replaces --library
├── book0_api/
│   ├── main.py                    # unchanged
│   ├── asgi.py                    # import load_libraries from book0_config instead of book0_api.config
│   └── schemas.py                 # unchanged
│       (config.py deleted)
└── book0_cli_remote/              # unchanged
```

### Dependency direction

Listing edges directly rather than as a single diagram, since a compressed
arrow-chain diagram previously implied `book0_cli` only reaches `book0_core`
transitively through `book0_presentation` - it does not; both are direct
dependencies:

- `book0_core` - depends on nothing project-specific (unchanged).
- `book0_presentation` - depends on `book0_core` only (unchanged).
- `book0_config` (new) - depends on nothing project-specific, stdlib only.
- `book0_cli` - depends on `book0_core`, `book0_presentation`, **and
  `book0_config`** (new edge).
- `book0_cli_remote` - depends on `book0_core`, `book0_presentation`,
  `httpx` (**unchanged** - it never reads the TOML itself; it calls
  `book0_api` over HTTP for everything, including tag resolution).
- `book0_api` - depends on `book0_core` **and `book0_config`** (new edge,
  replacing its own `config.py`). Still never imports `book0_cli`,
  `book0_cli_remote`, or `book0_presentation`.

## `book0_config` (new package)

- `config.py` contains exactly today's `book0_api/config.py` content
  (`load_libraries`, `_expand_env_vars`, `_ENV_VAR_PATTERN`), moved rather
  than rewritten. Same behavior: `${VAR_NAME}` placeholders expanded against
  `os.environ`; missing file, malformed TOML, or an unset referenced env var
  all raise (fail fast), same as today.
- `book0_api/config.py` is deleted; `book0_api/asgi.py`'s only change is the
  import source (`from book0_config.config import load_libraries`).
- `pyproject.toml`'s `[tool.hatch.build.targets.wheel]` package list gains
  `src/book0_config`, alongside the existing five entries.

## `book0_cli` changes

### `config.py` (new)

CLI-only helpers, not shared with `book0_api` (which has no notion of XDG
paths or a "default Calibre library" - it always requires an explicit
`BOOK0_API_CONFIG`):

- `default_library_path() -> Path` - returns `Path.home() / "Calibre
  Library"`. This is the same default folder name Calibre itself creates on
  first run, on every OS Calibre supports - no per-OS branching needed.
- `find_config_file() -> Path | None` - searches, in order:
  1. `./.book0.toml` (current working directory).
  2. `$XDG_CONFIG_HOME/book0/config.toml`, falling back to
     `~/.config/book0/config.toml` if `XDG_CONFIG_HOME` is unset.

  Returns the first path that exists as a file, or `None` if neither does.

### `main.py`

- `--library PATH` (required) is replaced by `--tag TAG` (optional,
  `default=None`).
- Resolution logic:
  - `--tag` omitted -> `library_path = default_library_path()`.
  - `--tag TAG` given -> `find_config_file()`; if `None`, print
    `No book0 config file found (looked for ./.book0.toml and
    <resolved XDG path>)` to stderr and exit 1. Otherwise
    `load_libraries(config_path).get(TAG)`; if `None` (tag not listed),
    print `Unknown library tag: '<TAG>'` to stderr and exit 1.
- `_resolve_db_path` (directory vs. file) and everything downstream
  (`SqliteLibraryGateway`, `LibraryNotFoundError` /
  `NotACalibreLibraryError` handling, table rendering) is unchanged - only
  how `library_path` gets produced changes.

## Known gap, explicitly out of scope

`book0_api` currently treats an *unconfigured* tag as an **empty library**
(`200 []`), which will now differ from `book0_cli`'s new behavior for the
same situation (error, exit 1). This was flagged during design: returning an
explicit not-found error from the API for an unknown tag could be read as
information leakage (confirming/denying which tags exist), so it isn't a
straightforward copy of the CLI's behavior - it needs its own decision, not a
reflexive match. Deferred to future `LibraryGateway`/`book0_api` work,
alongside the related idea of an endpoint to list configured library tags
(e.g. `GET /libraries`).

## Testing

- **`book0_config`**: `tests/unit/test_book0_api_config.py` moves to
  `tests/unit/test_book0_config.py`, same test bodies, importing from
  `book0_config.config` instead of `book0_api.config`.
- **`book0_cli.config`** (new `tests/unit/` cases): `default_library_path()`
  returns `Path.home() / "Calibre Library"`. `find_config_file()`: only the
  local file exists; only the XDG file exists; both exist (local wins);
  neither exists (`None`); `XDG_CONFIG_HOME` set vs. unset. Driven via
  `monkeypatch.chdir(tmp_path)`, `monkeypatch.setenv`/`delenv`, and
  `monkeypatch.setattr(Path, "home", ...)` - no real home directory or cwd
  touched.
- **`book0_cli` integration** (`tests/integration/test_cli_main.py`,
  rewritten from `--library` to `--tag`):
  - No `--tag`: resolves to `default_library_path()` - nominal (a Calibre
    library actually at that patched "home" path) and missing-library error,
    both via the same `monkeypatch.setattr(Path, "home", ...)` trick.
  - `--tag` resolving via a local `./.book0.toml`.
  - `--tag` resolving via the XDG config path.
  - `--tag` given, no config file found anywhere -> stderr message, exit 1.
  - `--tag` given, config file found, tag not listed -> stderr message,
    exit 1.
  - Existing downstream cases (empty library, non-Calibre file) carried
    over against a resolved path, since that behavior doesn't change.
- `tests/e2e/test_book0_api_main.py`, `tests/integration/test_http_gateway.py`,
  and `tests/integration/test_cli_remote_main.py` are untouched - neither
  `book0_api`'s route contract nor `book0_cli_remote` changes.

## `.claude` configuration updates

- `CLAUDE.md`: tooling table's "Run the direct CLI" row updates from
  `uv run book0 --library <path>` to `uv run book0 [--tag <tag>]`.
- `.claude/rules/architecture.md`: tree and dependency-direction sections
  updated to add `book0_config` and `book0_cli/config.py`, and to state
  `book0_cli`'s direct dependency on `book0_core` explicitly rather than via
  a compressed diagram.
- `.claude/rules/testing.md`: end-of-task checklist's list of
  `book0_cli/main.py` branches to review is updated for the new
  `--tag`/config-resolution branches, replacing the old
  `_resolve_db_path` directory-vs-file-only list.

## New dependencies

None - `book0_config` and `book0_cli/config.py` use only the stdlib
(`tomllib`, `os`, `pathlib`).

## Out of scope for this task

- Changing `book0_api`'s unconfigured-tag behavior (see "Known gap" above).
- A `GET /libraries` listing endpoint on `book0_api`.
- Any `--config`-style explicit override flag on `book0_cli` - config
  discovery is convention-based only (local file, then XDG path).
- Packaging/distribution changes.
