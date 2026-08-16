# TODO

Work deliberately deferred during brainstorming, code review, or implementation - not
forgotten, just not actioned yet. See `CLAUDE.md`'s "Deferred work" section for the convention:
brainstorming appends here when a design doc's "Out of scope" section defers something
concrete; the commit or plan that resolves an item removes its line.

- [ ] **Comma-splitting bug in `GROUP_CONCAT`-based aggregation.** `list_books` and
  `get_book_details` (`src/book0_core/sqlite_gateway.py`) both aggregate many-to-many fields
  via `GROUP_CONCAT(name, ', ')` + Python `.split(", ")`. A name containing the literal
  substring `", "` (e.g. Calibre's own `"Lastname, Firstname"` convention) gets silently split
  into two. Confirmed empirically during the book-details feature's final review
  (2026-08-13). Fix both queries together in one pass (fixing only one would create a second
  inconsistency) — likely `json_group_array(name)` + `json.loads()`, or an unambiguous
  delimiter instead of `", "`. See
  `docs/superpowers/specs/2026-08-12-book-details-design.md`.

- [ ] **Normalize/dedupe book ids before they reach the Gateway.** Fixes two Minor findings
  from the same final review: SQLite's numeric affinity aliases several string forms to the
  same row (`"01"`, `" 1"`, `"1.0"`, `"+1"`, `"1e0"` all match id `"1"`), and duplicate
  requested ids produce duplicate rendered rows (a CLI-level artifact, not a SQL one — `IN (1,
  1)` doesn't itself duplicate rows). Design agreed (2026-08-13): a single function in
  `book0_core`, called once in each CLI immediately after parsing `--ids`, splitting the raw
  list into valid ids (regex `[1-9]\d*`, deduped, first-seen order preserved) passed to the
  Gateway, and invalid ids that never reach the DB at all but still land in `missing_ids` —
  same user-visible treatment an unknown id already gets today. Not implemented; explicitly
  scoped for later.

- [ ] **`LibraryGateway` Protocol conformance is never statically checked.** Neither
  `SqliteLibraryGateway` nor `HttpLibraryGateway` is ever assigned to a `LibraryGateway`-typed
  variable anywhere in `src/`, and `uv run mypy src` never visits `tests/` (confirmed via
  `mypy src --verbose`'s file list, twice, in two separate sessions) — so nothing catches
  either implementation drifting from the Protocol. An earlier attempt added
  `gateway: LibraryGateway = ...` annotations inside `tests/integration/test_sqlite_gateway.py`
  and `test_http_gateway.py`; confirmed inert (never type-checked by the project's mandated
  invocation), don't repeat that fix. Real fix: annotate the actual gateway construction site
  as `LibraryGateway` inside `book0_cli/main.py`'s and `book0_cli_remote/main.py`'s `run()` —
  that's what `mypy src` actually walks. Worth doing before or during the next
  `LibraryGateway`-method-adding feature.

- [ ] **(far future, undesigned) Multi-library support.** Identify a book by `(tag, id)`
  rather than a bare id, to support: a tag meaning a virtual library (a saved
  search/collection) rather than a physical one; a non-Calibre backend with its own native id
  scheme; a single tag spanning several physical libraries, with consequences for what the "id
  space" means for that tag. Raised as motivating context for the item above, not as a request
  to design the multi-library architecture itself — no design exists yet. Revisit via
  brainstorming when picked up.

- [ ] **`book0_api`'s unknown-tag `books-detail` path echoes raw, un-deduped ids.** Found
  during the final-review of the book-id-normalization fix (2026-08-14):
  `src/book0_api/main.py`'s `get_book_details` route, on an unknown/unconfigured tag, returns
  `BookDetailsResultOut(books=[], missing_ids=body.ids)` — the raw request body ids verbatim,
  not deduped/whitespace-stripped/order-normalized the way the known-tag path's
  `SqliteLibraryGateway.get_book_details` now is. `book0-remote --tag <unknown>` with a
  duplicated or malformed id list would print the ids back exactly as sent, disagreeing with
  what the same ids would produce against a known tag. Low impact (the unknown-tag path is
  already a deliberately degenerate anti-enumeration case), and fixing it would mean either
  duplicating partition logic in `book0_api` or expanding that plan's file list — deferred
  rather than folded into that fix wave.

- [ ] **(undesigned) `books-detail` response projection + pagination.** Raised during
  brainstorming for the id-normalization fix (2026-08-14) and deliberately split off rather
  than folded in. The user's personal Calibre library can hold tens of thousands of books, so
  `get_book_details`'s join cost genuinely matters, and a simple `--ids-only` boolean flag
  isn't enough: concrete near-future needs include returning just found/missing ids, a book's
  file path (possibly triggering a download), description/abstract text, and pagination over
  large result sets — all without multiplying round-trips. Needs its own design: how a caller
  specifies "which fields"/mode (fixed enum vs. open field-selection list), how pagination
  composes with an `--ids`-scoped request, how a future file-path/download field and
  description/abstract fit the same request/response shape, and whether real query-level
  savings (skipping SQL joins per requested scope) requires forking `BookDetailsResult`'s
  shape or the `LibraryGateway` Protocol itself. No design exists yet; revisit via
  brainstorming when picked up.

- [ ] **(undesigned) Remote cover download and local cache.** `book0-remote` runs on a different
  machine from the server, so the absolute `cover_path` returned by `book0_api` is useless to
  the client. A future design should: (a) add a server endpoint to serve the cover file bytes
  (e.g. `GET /libraries/books/{id}/cover`), (b) have `book0_api` include a stable cache-key in
  the response (not the server-side filesystem path), (c) have `book0-remote` download covers
  to a local cache directory on first request, (d) return an anticipated local cache path so
  the caller can check whether a cover has arrived without re-querying. No design exists yet;
  revisit via brainstorming when picked up.
