# Remote cover download and local cache — design

## Purpose

`book0_core.sqlite_gateway.SqliteLibraryGateway._compute_cover_path` resolves a book's cover
to a real absolute filesystem path (`<library_root>/<book_path>/cover.jpg`), which is directly
usable by `book0_cli` since it runs on the same machine as the library. `book0_api` currently
serializes that same path verbatim into `BookDetailsOut.cover_path`, and `book0_cli_remote`'s
`HttpLibraryGateway` echoes it back unchanged — a path on a different machine, useless to a
`book0-remote` caller. This closes item 7 of `docs/superpowers/TODO.md` ("Remote cover
download and local cache"): a real server endpoint to serve cover bytes, a local cache on the
client, and a way to know locally whether a given book's cover is actually available.

## Scope

`book0_core` stays untouched except one field's type (below). `book0_cli` (direct) is
unaffected — it already has real paths and gains no new flag. Everything else changes at the
HTTP boundary: `book0_api`'s wire contract, and `book0_cli_remote`'s gateway/CLI/config.

## `book0_core.BookDetails.cover_path` becomes a tri-state

```python
cover_path: str | None | Literal[False] = None
```

- `None` — no cover exists for this book.
- `str` — a locally-readable path exists (always true for `SqliteLibraryGateway` when a cover
  exists; for `HttpLibraryGateway` only once the file is actually present in the local cache).
- `False` — the server has a cover, but it is not locally available. Covers every other case
  uniformly: `--with-covers` was never passed, a cache miss with the flag off, or a fetch that
  failed with the flag on. `SqliteLibraryGateway` never produces this value — it always has
  direct filesystem access, so its only two outcomes are `str` and `None`, exactly as today.

## `book0_api`: new cover-serving endpoint

`GET /libraries/books/{id}/cover?tag=...` in `book0_api/main.py`, following the same
`_resolve_db_path`/error-mapping shape as the existing routes, reusing
`SqliteLibraryGateway.get_book_details([id])` — no new `book0_core` method, no new SQL, no new
domain error type:

```python
@app.get("/libraries/books/{id}/cover", response_model=None)
def get_book_cover(id: str, tag: str | None = None) -> Response | JSONResponse:
    try:
        db_path = _resolve_db_path(tag)
    except TagRequiredError as error:
        return JSONResponse(
            status_code=400,
            content={"error": "TagRequiredError", "detail": str(error)},
        )
    if db_path is None:
        return _cover_not_found(id)

    gateway = SqliteLibraryGateway(db_path)
    try:
        result = gateway.get_book_details([id])
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

    if not result.books:
        return _cover_not_found(id)
    cover_path = result.books[0].cover_path
    if cover_path is None or not Path(cover_path).is_file():
        return _cover_not_found(id)

    return Response(content=Path(cover_path).read_bytes(), media_type="image/jpeg")


def _cover_not_found(id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "CoverNotFoundError", "detail": f"No cover found for book {id}"},
    )
```

`LibraryNotFoundError`/`NotACalibreLibraryError`/`TagRequiredError` map exactly like the other
routes, because they're real `book0_core` domain errors that can genuinely occur here (a
missing/corrupt `metadata.db`). `CoverNotFoundError` is **not** a `book0_core.errors` class and
is never added to `http_gateway.py`'s `_ERROR_TYPES` reconstruction table — it's a route-local
404 body for "nothing to return" (unconfigured tag, unknown id, no cover, or file missing on
disk), the same anti-enumeration posture the listing routes already take by returning an empty
result for an unconfigured tag rather than a distinguishable error. `HttpLibraryGateway`'s
cover-fetch code (below) only checks `status_code == 200`, so this body's exact shape is for
documentation/manual debugging, not for client-side branching.

Media type is hardcoded to `image/jpeg` — `_compute_cover_path` always targets `cover.jpg`,
Calibre never produces another cover format.

## `book0_api/schemas.py`: wire contract change (breaking, deliberately)

`BookDetailsOut.cover_path: str | None` → `BookDetailsOut.has_cover: bool`. The server never
again echoes a raw filesystem path over HTTP; it only reports whether a cover exists to fetch.
`BookOut`/`BookDetails` (domain) are unaffected — this is a schema-only rename in
`from_book_details`:

```python
class BookDetailsOut(BaseModel):
    ...
    has_cover: bool

    @classmethod
    def from_book_details(cls, book_details: BookDetails) -> "BookDetailsOut":
        return cls(
            ...
            has_cover=book_details.cover_path is not None,
        )
```

Note this reads the *server-side* `BookDetails.cover_path`, which on the server is always
produced by `SqliteLibraryGateway` — always `str` or `None`, never `False` — so
`is not None` is an exact, unambiguous "does a cover exist" check at this boundary.

## `book0_cli_remote/http_gateway.py`: cache-aware resolution

`HttpLibraryGateway` gains two constructor parameters (constructors are already
implementation-specific — `SqliteLibraryGateway` takes a path, this one already takes a
server client and tag — so this is not a `LibraryGateway` Protocol change):

```python
def __init__(
    self,
    client: httpx.Client,
    tag: str | None,
    *,
    with_covers: bool = False,
    cache_dir: Path | None = None,
) -> None:
    self._client = client
    self._tag = tag
    self._with_covers = with_covers
    self._cache_dir = cache_dir
```

`_book_details_from_json` becomes an instance method (needs `self` to resolve covers) and reads
`has_cover` instead of `cover_path` from the wire body:

```python
def _book_details_from_json(self, row: dict[str, object]) -> BookDetails:
    # publisher/series parsing unchanged from today
    ...
    return BookDetails(
        id=row["id"],  # type: ignore[arg-type]
        title=row["title"],  # type: ignore[arg-type]
        pubdate=row["pubdate"],  # type: ignore[arg-type]
        authors=tuple(row["authors"]),  # type: ignore[arg-type]
        tags=tuple(row["tags"]),  # type: ignore[arg-type]
        publisher=publisher,
        series=series,
        cover_path=self._resolve_cover(row["id"], row["has_cover"]),  # type: ignore[arg-type]
    )
```

Its one call site, inside `get_book_details`, moves from a list comprehension calling the free
function to one calling `self._book_details_from_json`; no other change to that method.

```python
def _resolve_cover(self, book_id: str, has_cover: bool) -> str | None | Literal[False]:
    if not has_cover:
        return None
    if self._cache_dir is None:
        return False

    cache_path = self._cover_cache_path(book_id)
    if cache_path.is_file():
        return str(cache_path)
    if not self._with_covers:
        return False

    try:
        response = self._client.get(
            f"/libraries/books/{book_id}/cover", params=self._params()
        )
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(response.content)
    return str(cache_path)

def _cover_cache_path(self, book_id: str) -> Path:
    return self._cache_dir / (self._tag or "_default") / f"{book_id}.jpg"  # type: ignore[operator]
```

`_resolve_cover` treats an unresolved `cache_dir` (`None`) the same as "no local file, fetch
disabled" — `False`, never a crash. In practice `book0_cli_remote/main.py` always resolves and
supplies `cache_dir` for every `books-detail` call (see below), so this path is a defensive
fallback for any other caller (a test, a future consumer) that constructs `HttpLibraryGateway`
without one — `get_book_details` must never raise over a caching concern.

Two behaviors worth calling out explicitly, both following directly from "check the cache
before ever asking the network," already agreed:

1. **The cache is checked unconditionally**, whether or not `--with-covers` is passed. If a
   cover happens to already be cached from an earlier `--with-covers` run, a later plain
   `books-detail` call reports it (`str`) rather than hiding it behind `False`. Only the
   *network fetch* on a cache miss is gated behind the flag.
2. Because of (1), `book0_cli_remote/main.py` resolves `cache_dir` for every `books-detail`
   call, not only when `--with-covers` is given (detailed below) — `books`/`authors`/
   `publishers` never touch `cover_path` at all, so they never resolve it.

A failed fetch (non-200, or a network-level `httpx.HTTPError`) returns `False` rather than
raising — this is the "silent partial degrade" already agreed for individual covers, matching
how `missing_ids` already lets `get_book_details` succeed overall despite some ids not being
found.

`self._tag` is `None` whenever `--tag` is omitted (server resolves its own `default-library`).
The client cannot know that resolved tag's name, so it caches under a fixed `"_default"`
segment for that case — if a user sometimes passes an explicit `--tag` for what is in fact
their server's default library and sometimes omits it, those two invocations get separate
cache namespaces. This mirrors an existing property of `--tag` resolution (the client already
doesn't know the server's resolved default tag today) and isn't fixed here — flagged in Out of
scope.

## `book0_cli_remote/config.py`: optional cache-dir key + XDG default

New optional key (`.get()`, not `data[...]` — unlike `server`, which is required):

```python
def load_cover_cache_dir(config_path: Path) -> Path | None:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    value = data.get("cover-cache-dir")
    return Path(value) if value is not None else None
```

New XDG-cache default, mirroring the existing `xdg_config_path()` shape:

```python
_XDG_CACHE_SUBPATH = Path("book0") / "covers"


def xdg_cache_path() -> Path:
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    cache_home = Path(xdg_cache_home) if xdg_cache_home else Path.home() / ".cache"
    return cache_home / _XDG_CACHE_SUBPATH
```

`.book0-client.toml`'s doc comment gains a line documenting `cover-cache-dir` as optional,
alongside the existing `server` key.

## `book0_cli_remote/main.py`

`books-detail`'s subparser gains `--with-covers` (`action="store_true"`, default `False`) — no
other subcommand gets it, since only `books-detail` touches `cover_path`.

Cache dir resolution happens for every `books-detail` call (see the "checked unconditionally"
point above), lazily — the config file is opened only if `find_config_file()` finds one, and
only `books-detail` calls this path at all:

```python
config_path = find_config_file()
cache_dir = None
if config_path is not None:
    try:
        cache_dir = load_cover_cache_dir(config_path)
    except tomllib.TOMLDecodeError as error:
        print(
            f"Invalid book0-remote client config file {config_path}: {error}",
            file=sys.stderr,
        )
        return 1
if cache_dir is None:
    cache_dir = xdg_cache_path()
```

This reuses `find_config_file()` a second time independently of the `--server` fallback's own
call to it (already lazy, already conditional on `--server` being omitted) — the same
minimal-per-key-loader style `load_server` already established, not a shared combined loader.
A `tomllib.TOMLDecodeError` here reuses the exact same message shape as the `--server`
fallback's own error handling; a missing `cover-cache-dir` key is not an error (`.get()`
default, then the XDG fallback applies).

`HttpLibraryGateway` construction for `books-detail` becomes:

```python
gateway = HttpLibraryGateway(
    client, tag, with_covers=args.with_covers, cache_dir=cache_dir
)
```

## `book0_presentation/tables.py`

`render_book_details_table` needs a three-way branch for the Cover Path column. `_or_empty`
stays as-is (still used by the `publisher`/`series`/`series_index` columns, which are genuine
`str | None`); a new, separate helper handles the tri-state column instead of overloading
`_or_empty`'s signature:

```python
def _cover_path_cell(cover_path: str | None | Literal[False]) -> str:
    if cover_path is False:
        return "(unavailable)"
    return _or_empty(cover_path)
```

Used in place of `_or_empty(book.cover_path)` at the Cover Path column's row-tuple position.
`BookDetails.cover_path`'s new type (`str | None | Literal[False]`) makes `_or_empty`'s own
signature (`str | None`) still valid for that call after the `is False` branch narrows it out.

## Error handling

| Case | `book0_api` | `book0_cli_remote` |
|---|---|---|
| Unconfigured tag | `GET .../cover` → 404 `CoverNotFoundError` | n/a (route handles it) |
| Unknown book id | 404 `CoverNotFoundError` | n/a |
| Book exists, no cover | 404 `CoverNotFoundError` | n/a |
| Cover file missing on disk despite `has_cover` | 404 `CoverNotFoundError` | n/a |
| No `--tag`, no server `default-library` | 400 `TagRequiredError` (existing pattern) | never reaches `_resolve_cover` — `get_book_details`'s own request uses the same `tag`, so this fails (and is reconstructed as `TagRequiredError`, the existing pattern) before any book rows exist to resolve covers for |
| `--with-covers` fetch fails for any reason, including a hypothetical 400/404/500 from the cover route itself | any status | `_resolve_cover` does **not** parse or reconstruct the body — every non-200 response and every `httpx.HTTPError` is treated identically as `cover_path = False` for that one book; the command does not fail |
| Invalid `.book0-client.toml` (`cover-cache-dir` present but file unparseable) | — | stderr message + `return 1`, same shape as the `--server` fallback's own error |

No new `book0_core` error type. `CoverNotFoundError` is a `book0_api`-local JSON body key, not
a `book0_core.errors` class, and is deliberately excluded from `http_gateway.py`'s
`_ERROR_TYPES`.

## Testing

- **Unit**, `tests/unit/test_tables.py`: `render_book_details_table` with `cover_path` = each
  of `None`/`str`/`False` → `""`/the path/`"(unavailable)"`.
- **Unit**, `tests/unit/test_book0_api_schemas.py`: `BookDetailsOut.from_book_details` with
  `cover_path` set vs `None` → `has_cover` `True`/`False`.
- **Unit**, `tests/unit/test_cli_remote_config.py`: `load_cover_cache_dir` (key present, key
  absent → `None`, invalid TOML → `TOMLDecodeError`); `xdg_cache_path` (`XDG_CACHE_HOME` set vs
  unset, mirroring the existing `xdg_config_path` tests).
- **Integration**, `tests/integration/test_sqlite_gateway.py`: no change expected —
  `_compute_cover_path` is untouched.
- **Integration**, `tests/integration/test_http_gateway.py`: `_resolve_cover`/
  `get_book_details` against a real `TestClient`-backed app: `has_cover=False` → `None`;
  `has_cover=True`, not cached, `with_covers=False` → `False`, no request made to the cover
  route (assert via a `TestClient` request-count or a monkeypatched client); `has_cover=True`,
  not cached, `with_covers=True` → fetches, writes to `tmp_path` cache dir, returns that path,
  file contents match; `has_cover=True`, already cached (pre-seed `tmp_path`) → returns the
  cached path **without** an HTTP request, `with_covers` either way; `with_covers=True` but the
  cover route itself 404s (race: book deleted between calls) → `False`, command doesn't raise.
- **Integration**, `tests/integration/test_cli_remote_main.py`: `books-detail` without
  `--with-covers` → unchanged output for books with no cover, `"(unavailable)"` for books with
  one; `--with-covers` → downloads into a `tmp_path`-based cache (via `HOME`/`XDG_CACHE_HOME`
  monkeypatching, matching the existing config tests' technique), Cover Path column shows the
  local path; a second run with the same cache populated makes no HTTP request for covers
  (only the `books/detail` POST).
- **E2E**, `tests/e2e/test_book0_api.py`: new `GET /libraries/books/{id}/cover` route —
  nominal (200, correct bytes, correct `Content-Type`), unconfigured tag → 404, unknown id →
  404, book with no cover → 404, `TagRequiredError` case (no tag, no server default) → 400,
  `LibraryNotFoundError`/`NotACalibreLibraryError` cases (existing fixtures) → 404/500.

## Out of scope

- Cache invalidation / eviction. The cache key is the book id alone (agreed) — if a cover is
  replaced in Calibre without the book's id changing, a stale cached image is served
  indefinitely. Not addressed here; revisit via brainstorming if it becomes a real problem.
- Background/async download. `book0-remote` stays a one-shot, synchronous CLI — `--with-covers`
  blocks until every requested cover is resolved or has failed.
- A distinct cache namespace for a `--tag`-omitted invocation that happens to resolve to the
  same server-side default library as some other explicit `--tag`. Both are cached separately
  (`"_default"` vs the explicit tag name) — a pre-existing property of how `--tag` resolution
  already works, not introduced by this design.
- Any `book0_cli` (direct) change — it already has real, always-current local paths and gains
  no flag, no cache, no behavior change.
- Configurable cache eviction size/TTL, or a `book0-remote` subcommand to clear the cache.
