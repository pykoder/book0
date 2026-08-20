# List pagination — design

## Purpose

`list_books`/`list_authors`/`list_publishers` return every row unconditionally — no `LIMIT`,
no `OFFSET`, nothing. Both `book0_cli` and `book0_api` currently materialize and print/serialize
the entire library on every call. For a personal Calibre library that can hold tens of thousands
of books, this is unusable at scale (an unbounded JSON response from `book0_api`, an unusable
terminal dump from `book0_cli`) and, for `book0_api` specifically, an unbounded per-request cost
with no way for a server operator to cap it. This design adds paginated variants of all three
list methods, plus the composition pattern that motivated it: paginate a books listing, then
feed that page's ids into the existing `get_book_details`/`--ids` flow to get full details (and,
per the already-shipped cover-cache feature, covers) for a bounded number of books at a time.

This absorbs and replaces `docs/superpowers/TODO.md`'s item on "`books-detail` response
projection + pagination" for the pagination half of that item; the field-projection half (an
`--ids-only` mode, a future file-path/download field, description/abstract text) is deliberately
**not** covered here and gets refiled as its own, narrower TODO item once this design lands (see
Out of scope).

## Scope

Touches `book0_core` (new `LibraryGateway` Protocol methods, new result types, `SqliteLibraryGateway`
internals), `book0_config` (a new optional config key shared by `.book0.toml`/`book0-libraries.toml`),
`book0_cli_remote/config.py` (the same key, `.book0-client.toml`'s own loader), `book0_api` (new
query params, new wire schemas), `book0_cli_remote/http_gateway.py`, and both CLIs' `main.py`.
`get_book_details`/`books-detail` itself is unchanged — pagination composes with it by the
caller passing the page's ids into the existing `--ids` flag, not by `books-detail` gaining its
own pagination.

## `LibraryGateway` Protocol: three new methods, existing four untouched

```python
def list_books_page(self, page: int, page_size: int, handle: str | None = None) -> PagedBooksResult: ...
def list_authors_page(self, page: int, page_size: int, handle: str | None = None) -> PagedAuthorsResult: ...
def list_publishers_page(self, page: int, page_size: int, handle: str | None = None) -> PagedPublishersResult: ...
def close_pagination(self, handle: str) -> None: ...
```

`list_books`/`list_authors`/`list_publishers`/`get_book_details` keep their exact current
signatures and return types — zero risk to any existing caller or test. New methods instead of
new optional params on the old ones, because a paginated result is a genuinely different return
type (items *plus* page metadata), and Python typing has no clean way to make a method's return
type depend on whether an optional argument was passed.

## `book0_core.models`: three concrete result types, not a generic one

```python
@dataclass(frozen=True)
class PagedBooksResult:
    items: tuple[Book, ...]
    page: int
    page_size: int
    total_pages: int | None  # exact, if the query has ≤100 pages of results
    has_more_than_shown: bool  # True when total_pages is None ("many" - see below)
    handle: str | None  # set iff there may be a next page; None once exhausted
```

`PagedAuthorsResult`/`PagedPublishersResult` mirror this exactly, swapping `Book` for
`Author`/`Publisher`. Three concrete dataclasses rather than one `PagedResult[Generic[T]]`,
because nothing in this codebase uses `Generic` today (`BookDetailsResult` etc. are all
concrete) — matching that existing convention over introducing a new typing pattern for this
one feature.

**Bounded page-count, not an exact count:** with `page_size` items per page, `total_pages` is
computed by counting up to `100 * page_size` rows (a `COUNT(*)`-shaped query capped with its own
`LIMIT`, not a full table scan). If the true count is ≤ that cap, `total_pages` is exact and
`has_more_than_shown` is `False`. If the cap is hit, `total_pages` is `None` and
`has_more_than_shown` is `True` — the caller sees "many" rather than a number, and the query
never scans more than 100 pages' worth of rows to find out. This applies identically in
`SqliteLibraryGateway` and `book0_api`/`SqliteLibraryGateway`-on-the-server — consistency was
chosen deliberately over exploiting local SQLite's cheap exact-count capability, so both
backends report page counts the same way.

## The handle: advisory, never required

A handle from a previous `PagedResult` may be passed to a later call to reuse whatever
already-open resource that handle refers to, whenever the requested page falls within the range
that resource can currently serve — not only the exact immediate-next page. **Exactly which
requests count as "in range" (how far ahead/behind a held session can serve from, how much it
buffers, whether it's a strictly-forward generator or something with more slack) is an
implementation detail, not part of this contract.** What every implementation must guarantee:
a handle is always optional; an implementation is always free to decide a given handle isn't
useful for a given request (unknown/expired handle, wrong resource/page-size, a page outside
whatever range it's willing to serve) and fall back to a fresh, direct, correct fetch for
exactly the requested page — transparently, never as an error. Handle reuse is purely an
optimization; no caller-visible behavior depends on whether a given call happened to reuse a
session or not, only on getting the right page back.

`close_pagination(handle)` releases whatever resource is tied to a handle early, for a caller
that stops iterating before reaching the end. Idempotent and silent on an unknown handle (no
exception) — same advisory posture as everything else about handles.

## `SqliteLibraryGateway`: persistent connection + generator-backed sessions

Two changes to the existing class, both internal (no change to any existing method's public
signature or return type):

1. **The connection becomes lazy and persistent for the gateway instance's lifetime**, instead
   of the current per-method-call open/close. `list_books`, `list_authors`, `list_publishers`,
   and `get_book_details` all switch to a shared `self._connect()` that opens once and is
   reused by every subsequent call on the same instance — this is what makes "list a page of
   books, then `get_book_details` for that page's ids" cheap when both happen through one
   gateway instance, independent of the handle mechanism (which only ever helps same-resource
   paging within whatever range a held session can serve, not this cross-method reuse). No new
   public method for this: adding a
   connection-level `close()` was considered and rejected, because it would exist on
   `SqliteLibraryGateway` but not on the `LibraryGateway` Protocol, breaking the moment TODO
   item 3 (annotating gateway construction sites as `LibraryGateway`-typed) is addressed. The
   connection is released implicitly — process exit for `book0_cli`'s short-lived invocations,
   garbage collection for any longer-lived consumer (a script holding a `SqliteLibraryGateway`
   instance directly) — matching this project's existing absence of any explicit CLI-level
   cleanup/shutdown logic.
2. **A small table of live pagination sessions**, keyed by handle, each backed by a Python
   generator (`yield`-based) for one resource type, plus a last-access timestamp.
   `list_books_page` (etc.) looks up the session for a given handle; if the implementation
   judges the requested page servable from that session's current state (same resource, same
   `page_size`, and whatever range check `writing-plans` settles on — the simplest version
   being "exactly the next page a forward-only generator would yield," a more capable version
   buffering a small window so a slight back-step or a repeat of the last page or two is also
   servable without a re-query), it pulls the requested rows from there; otherwise it starts a
   fresh generator seeked directly to the requested page (still just a `LIMIT`/`OFFSET` query —
   a "fresh" fetch is not more expensive than today's unpaginated query, just bounded).
   `close_pagination(handle)` calls `.close()` on that session's generator (releasing whatever
   cursor/resources it holds via its own `finally` block) and drops it from the table.
3. **Lazy timeout expiry**: before consulting the session table, sessions whose last-access
   timestamp is more than 60 seconds old are treated as already closed (generator `.close()`'d,
   dropped) — a check performed on the next call that touches the table, not a background
   timer/thread. A fixed constant, not a config option — no concrete need for it to be tunable
   yet.

The exact internal shape of the session table and generator bookkeeping is an implementation
detail for `writing-plans` to pin down precisely; the contract above (handle semantics, timeout
behavior, `close_pagination` existing on the Protocol) is what every test and caller depends on.

## `HttpLibraryGateway`/`book0_api`: stateless, no caching, bounded count only

`HttpLibraryGateway`'s implementations of the three paginated methods and `close_pagination` are
deferred to a stateless shape: every call is a fresh HTTP GET with `page`/`page_size` query
params (any `handle` argument is accepted for Protocol conformance but ignored — never sent over
the wire), and `close_pagination` is a no-op. `book0_api`'s routes gain `page: int | None = None`
and `page_size: int | None = None` query params; when both are omitted, behavior is identical to
today (every row, no pagination). The bounded-count computation described above applies
server-side too, redone on every request — no server-side caching or session state, by design,
for this iteration.

New wire schemas (`book0_api/schemas.py`), one per resource, not exposing `handle` at all — since
the server does nothing with a client-supplied handle yet, committing to a wire shape for it now
would be speculative:

```python
class PagedBooksOut(BaseModel):
    items: list[BookOut]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool

    @classmethod
    def from_paged_result(cls, result: PagedBooksResult) -> "PagedBooksOut":
        return cls(
            items=[BookOut.from_book(book) for book in result.items],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
            has_more_than_shown=result.has_more_than_shown,
        )
```

(`PagedAuthorsOut`/`PagedPublishersOut` mirror this exactly.)

## Page-size resolution

**`book0_cli` (single local config, no client/server split):** effective `page_size` =
`--page-size` if given, else `.book0.toml`'s `default-page-size` if set, else `None`
(unpaginated — today's "everything" behavior, `list_books()` used as-is rather than
`list_books_page`). `page` defaults to `1` whenever pagination is in effect and `--page` was
omitted — `page` has no persisted config default, it is always just a parameter.

**`book0_api`/`book0-remote` (client + server, server protects itself) — two separate
resolution steps, one on each side of the wire:**

**Client-side, `book0-remote` deciding what to put on the request** (this is the only place
`.book0-client.toml`'s `default-page-size` is consulted): `--page-size` if given, else
`.book0-client.toml`'s `default-page-size` if set, else the `page_size` query param is omitted
entirely. This is exactly the same three-step resolution `book0_cli` uses locally — the
difference is what happens next, server-side, which `book0_cli` has no equivalent of.

**Server-side, `book0_api` deciding the effective size for the query it actually runs**, given
whatever `page_size` value it received (or didn't) on the request:

1. `book0-libraries.toml` gains an optional `default-page-size` — a server-operator-set
   *ceiling*, not merely a fallback-when-absent value.
2. If the server has `default-page-size` set: effective size = `min(received page_size, server
   default)` if the request had one; **or the server default alone, forcing pagination even
   when the request had no `page_size` param at all** — deliberate server-side protection
   against an unbounded query, applying unconditionally whenever the operator has configured
   it. In this forcing case, `page` defaults to `1` exactly as it does everywhere else in this
   design when pagination is in effect and no page was requested.
3. If the server has no `default-page-size` configured: no cap is imposed; effective size = the
   request's `page_size` if present, else unbounded (today's behavior — the request never
   becomes paginated on the server's own initiative).

`.book0.toml` and `book0-libraries.toml` share their `default-page-size` key through the
existing shared loader (`book0_config.config.load_libraries`/`LibraryConfig`, already used by
both `book0_cli` and `book0_api` for `libraries`/`default-library`) — `LibraryConfig` gains one
new field, `default_page_size: int | None = None`, read via `data.get("default-page-size")`,
same optional-key style `load_cover_cache_dir` already established for `.book0-client.toml`.
The `= None` default matters, not just as a style choice: `tests/unit/test_book0_config.py`
already constructs `LibraryConfig(...)` for an equality comparison against `load_libraries`'
return value without a third argument — giving the new field a default keeps that comparison
correct with no change to the test at all (both sides resolve to `default_page_size=None` when
the key is absent), rather than requiring every existing call site to be touched.
`.book0-client.toml`'s own `default-page-size` key is read by a small new function in
`book0_cli_remote/config.py`, mirroring `load_cover_cache_dir`'s shape exactly (its own file,
never shared with `book0_config` per the existing dependency-direction rule).

## Both CLIs: `--page`/`--page-size`

Added to the `books`, `authors`, and `publishers` subparsers of both `book0` and `book0-remote`
(not `books-detail`, which is unchanged). Both flags are plain optional `int` args with no
argparse-level default (`None`), resolved against config exactly as described above. When the
resolved `page_size` is `None`, the CLI calls the existing unpaginated method
(`list_books()`/etc.) exactly as today; when it resolves to a value, the CLI calls the new
paginated method instead and renders a page.

Rendering (`book0_presentation/tables.py`): the existing `render_book_table`/`render_author_table`/
`render_publisher_table` keep working on the page's `items` unchanged (they already take a
`list[Book]`/etc.). A new small helper formats the page-footer line printed after the table,
e.g. `Page 3 of 12` or `Page 3 of many` — exact wording decided during planning, not a
requirement this spec needs to pin down further.

## Error handling

| Case | `book0_cli` | `book0_api` |
|---|---|---|
| `--page`/`page` given without a resolvable `page_size` (config and flag both absent) | Not an error — behaves as if pagination wasn't requested at all (unpaginated); `page` alone is meaningless without a size, so it's silently ignored rather than rejected | Same: `page` without an effective `page_size` (no client value, no server default) has no effect |
| `page` ≤ 0, or non-numeric | argparse's own `int` type validation already rejects non-numeric (existing pattern, exit code 2); `page <= 0` treated as `page = 1` — CLI-level normalization, not a new domain error | FastAPI's own query-param validation rejects non-numeric (422, existing framework behavior for typed query params); `page <= 0` normalized to `1` in the route, same as the CLI |
| `page_size` ≤ 0 | Normalized to `None` (unpaginated) — a zero-or-negative page size has no sensible paginated meaning | Same normalization, server-side |
| Stale/unknown/mismatched `handle` (`SqliteLibraryGateway` only — `HttpLibraryGateway` never sends one) | Silently treated as absent; never raises | N/A |
| `close_pagination` on an unknown handle | Silently no-op | N/A (server-side implementation is already a no-op for every handle) |

No new `book0_core.errors` class — every case above degrades gracefully rather than raising.

## Testing

- **Unit**, `book0_core.models`: `PagedBooksResult`/`PagedAuthorsResult`/`PagedPublishersResult`
  construction (pure dataclasses, no I/O).
- **Unit**, `book0_config`: `load_libraries` with `default-page-size` present/absent, matching
  the existing `default-library` test shapes.
- **Unit**, `book0_cli_remote/config.py`: the new `.book0-client.toml` loader, mirroring
  `load_cover_cache_dir`'s existing tests.
- **Unit**, `book0_api/schemas.py`: `PagedBooksOut.from_paged_result` (and the author/publisher
  equivalents) field-by-field mapping.
- **Integration**, `SqliteLibraryGateway`: against the real fixture DB (needs a larger fixture
  library than today's 3-book one to exercise more than one page — a new fixture with enough
  rows to produce at least 3 pages at a small page size). Cover: page 1 direct; a page the
  implementation's own range logic considers servable from a valid handle actually reuses the
  existing session rather than starting a fresh one (the connection itself is shared by every
  call regardless, paginated or not, so the observable signal has to be the session/generator
  specifically — e.g. an instrumented query count showing no new `SELECT` for the reused page,
  only continued pulling from the already-open cursor; exactly which page(s) count as "in
  range" is whatever `writing-plans` settles on, and the test should assert against that actual
  behavior, not a hardcoded assumption of "next page only"); a request outside whatever range
  the session covers falls back to a correct fresh fetch, still returning the right rows; a
  handle from a *different* resource or `page_size` always falls back too, regardless of range
  (that part is a hard contract requirement, not implementation-defined); a cold jump (e.g. page
  5 with no handle at all) returns the correct rows; `total_pages` exact under the 100-page cap
  and `None`/`has_more_than_shown=True` over it (may need a smaller cap injected for
  testability rather than the real 100, or a fixture library sized to actually exceed it —
  decide during planning); `close_pagination` actually releases (a subsequent call with that
  handle behaves as if it was never given); timeout expiry (inject a controllable clock rather
  than sleeping 60 real seconds in a test).
- **Integration**, `HttpLibraryGateway`: against a real `TestClient`-backed app — page
  params round-trip correctly; a `handle` passed by the caller is never sent over the wire
  (assert on the actual request, not just the response); server-side `default-page-size`
  capping (client requests a larger size than the server allows → server's cap wins) and
  forcing (client requests nothing, server has a default → paginated response anyway).
- **Integration**, both CLIs' `main.py::run`: `--page`/`--page-size` end to end, page-footer
  line rendered, config-file default-page-size picked up when flags are omitted, `--page-size`
  flag overriding a config default.
- **E2E**, `book0_api`'s routes via `TestClient`: the three paginated list routes' query-param
  handling and response shape, plus the server-cap/server-force cases above at the HTTP-boundary
  level (not just through `HttpLibraryGateway`).

## Out of scope

- `books-detail`'s own field projection (an `--ids-only` mode, a future file-path/download
  field, description/abstract text) — the part of the old TODO item this design does not
  absorb. Refile as its own TODO item once this lands; revisit via brainstorming when picked up.
- Server-side caching of paginated results / handle-based session reuse over HTTP. Explicitly
  deferred — `HttpLibraryGateway`'s handle handling is a stub today, and the wire schema
  doesn't expose a handle field, precisely so this can be added later without a breaking wire
  change (a new optional field, not a replaced one).
- A configurable pagination-session timeout (currently a fixed 60s constant) — no concrete need
  yet.
- Cursor/keyset-based pagination — offset+limit was chosen for this project's scale and KISS
  bias; revisit only if the offset/limit correctness weakness (skipped/duplicated rows under
  concurrent Calibre-side edits) becomes a real reported problem.
- Any change to `get_book_details`/`books-detail`'s own signature, error handling, or wire
  shape — composition with pagination happens entirely by the caller passing a page's ids into
  the existing `--ids` flag/`BookIdsIn` body, nothing about that path changes.
