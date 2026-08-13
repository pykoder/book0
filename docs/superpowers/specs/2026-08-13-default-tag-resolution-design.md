# Default tag resolution — design

## Purpose

`book0` and `book0-remote` behave inconsistently today: `book0-remote` always requires an
explicit `--tag`, while `book0` silently falls back to auto-detecting Calibre's own default
install location whenever `--tag` is omitted, bypassing configuration entirely. This design
removes that fallback and replaces it with a `default-library` setting in configuration —
resolved client-side for `book0` (its own `.book0.toml`), and **server-side** for
`book0-remote` (the server's own `book0-libraries.toml`), since the server already owns tag
resolution and the client shouldn't need its own copy of that logic. Reaching this required
changing how `book0_api` receives a tag at all: from a required path segment to an optional
query parameter, on all four existing routes.

## Config file format

Both config files — `book0`'s local `.book0.toml` and the server's `book0-libraries.toml` —
gain the same top-level key, alongside the existing `[libraries]` table:

```toml
default-library = "fiction"

[libraries]
fiction = "/path/to/fiction"
work = "/path/to/work"
```

`default-library` names a tag that must appear in `[libraries]`. If it names a tag that
*isn't* there, this is deliberately **not** validated separately — resolving `tag =
args.tag or default_tag` and then looking that value up in `[libraries]` reuses the existing
"unknown tag" error path unchanged. The error message will say "unknown library tag: X"
rather than "your `default-library` setting is wrong," which is a known, accepted rough edge
in exchange for not adding a second validation path for what's fundamentally the same
condition (a tag string not present in `[libraries]`).

## `book0_config` changes

`book0_config/config.py::load_libraries` changes its return type from `dict[str, Path]` to a
new frozen dataclass:

```python
@dataclass(frozen=True)
class LibraryConfig:
    libraries: dict[str, Path]
    default_tag: str | None
```

Both `book0_cli` and `book0_api` — the two existing consumers — now get the `default-library`
value from the same single parse, rather than either re-parsing the file or leaving one
consumer without access to it. `default_tag` is `None` when the key is absent from the file
(not an error — a config file with no `default-library` is completely valid, it just means
"no default").

## `book0` (local CLI)

`run()`'s tag resolution simplifies rather than growing more branches — the
`if args.tag is None: use Calibre's default install path` branch is deleted outright, and the
config-file lookup that today only runs when `--tag` is given now always runs:

- No config file found at all (neither local `./.book0.toml` nor the XDG fallback) → same
  existing message and exit code as today ("No book0 config file found (looked for ...)"),
  now reachable whether or not `--tag` was given.
- Config found, `--tag` given → unchanged: look it up in `libraries`, existing "unknown
  library tag" error if absent.
- Config found, `--tag` omitted, `default_tag` is set → resolve that tag through
  `libraries`, exactly as if `--tag <default_tag>` had been typed.
- Config found, `--tag` omitted, `default_tag` is `None` → new `TagRequiredError` (see Error
  handling), caught alongside the existing two in `run()`'s `except` clause, printed to
  stderr, exit 1.

`book0_cli/config.py::default_library_path()` (Calibre install-path auto-detection) has no
remaining caller and is deleted as dead code.

## `book0_api` (server)

All four existing routes drop `{tag}` from the URL path and gain it as an **optional query
parameter** instead:

- `GET /libraries/books?tag=...` (was `GET /libraries/{tag}/books`)
- `GET /libraries/authors?tag=...` (was `GET /libraries/{tag}/authors`)
- `GET /libraries/publishers?tag=...` (was `GET /libraries/{tag}/publishers`)
- `POST /libraries/books/detail?tag=...` (was `POST /libraries/{tag}/books/detail`) — request
  body is unchanged (`{"ids": [...]}`); tag is not part of the body, matching the same
  "query param identifies the resource scope, body carries the operation payload" split used
  for the other three routes even though they have no body at all.

Query parameter over a path segment because an empty/absent path segment isn't a clean HTTP
idiom (ruled out during design); query parameter over putting tag in the POST body because a
single rule ("tag always travels the same way, regardless of HTTP method") beats a
method-dependent one, and it keeps `BookIdsIn` from mixing "which library" with "what to
fetch."

`create_app`'s signature grows one new, defaulted parameter rather than being replaced by
`LibraryConfig` wholesale — every existing test calling `create_app({"fiction": path})` keeps
working unchanged:

```python
def create_app(
    libraries: dict[str, Path], default_tag: str | None = None
) -> FastAPI: ...
```

`book0_api/asgi.py` unpacks the new `LibraryConfig` from `load_libraries(...)` into this
two-argument call.

Per-route behavior when `tag` is omitted: if `default_tag` is set, resolve it through
`libraries` (identical treatment to a tag that was actually supplied); if not, raise
`TagRequiredError` → mapped to `400 {"error": "TagRequiredError", "detail": "..."}`, same
error-body shape (`{"error": ..., "detail": ...}`) every existing 404/500 mapping already
uses.

A **given-but-unconfigured** tag keeps its existing behavior unchanged: `200` + empty
result/list. This is a deliberate, pre-existing anti-enumeration property (an attacker probing
tag values can't distinguish "wrong guess" from "right guess, empty library") and this design
does not touch it. The new `TagRequiredError` case is a different, tag-*independent* code
path — it only fires when the query parameter is absent entirely, never as a function of which
tag string was guessed, so giving it a distinct status code reveals nothing about which tags
exist on the server.

## `book0-remote` (remote CLI)

- `--tag` becomes optional on all four subcommands (currently `required=True` on each
  subparser) — `--server` stays required; no change there.
- `HttpLibraryGateway`'s four methods send `tag` as a query parameter when the CLI supplied
  one, and omit it entirely when not (letting the server's own `default-library` resolve
  it).
- `HttpLibraryGateway` reconstructs `TagRequiredError` from a `400` response via the same
  `_ERROR_TYPES` dict already used for 404/500 (`_ERROR_TYPES` grows a third entry; the
  `if response.status_code in (404, 500)` checks grow to include 400).
- `book0_cli_remote/main.py::run()` catches `TagRequiredError` alongside its existing two
  domain errors.

## Error handling

One new domain error, `TagRequiredError`, added to `book0_core/errors.py` alongside
`LibraryNotFoundError` and `NotACalibreLibraryError`. Raised identically by both resolution
paths (local CLI, server route) for the same condition (no tag, no default configured), and
reconstructed identically by `HttpLibraryGateway` — the same "same domain error, both Gateway
implementations, both CLIs" pattern the other two errors already establish, extended to a
third member rather than inventing a new mechanism.

## Testing

- Every existing route/CLI/`HttpLibraryGateway` test asserting against the old
  `/libraries/{tag}/...` path shape updates to the new `?tag=...` query-parameter shape.
- `book0_config`: `load_libraries` returns `LibraryConfig` with `default_tag` populated when
  present, `None` when absent; existing "malformed TOML"/"missing file" error cases
  unchanged.
- `book0` (local): default-tag resolution when `--tag` omitted; `TagRequiredError` when
  omitted and no default configured; no-config-file case now reachable without `--tag`;
  explicit `--tag` behavior unchanged (regression coverage).
- `book0_api`: default-tag resolution per route when `tag` query param omitted;
  `TagRequiredError` → 400 when omitted and no default configured; given-but-unconfigured tag
  still 200 + empty (regression coverage, now under the new URL shape); `create_app`'s new
  parameter defaults correctly for every pre-existing call site.
- `book0-remote`: same default-tag/`TagRequiredError` cases via a real
  `TestClient`-backed app; `--tag` genuinely optional now (regression: explicit `--tag` still
  works).

## Out of scope

- `--genconfig` (printing a template config file, redirectable to a real file) and ensuring
  every subcommand/flag appears in `--help`/`-h` output — both real, both requested in the
  same conversation that raised this design, but scoped as their own follow-up rather than
  bundled in here.
- A default `--server` URL for `book0-remote` (raised during design, explicitly deferred) —
  `--server` stays a required flag.
- The `[1-9]\d*`-style book-id normalization/dedup plan and the far-future multi-library
  `(tag, id)` identity direction (tracked in `docs/superpowers/TODO.md`) — unrelated to this
  design.
