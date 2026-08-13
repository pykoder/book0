# Book details — design

## Purpose

Add a way to fetch rich, joined details for an explicit list of book ids — publisher, series
(with the book's position in it), authors, and tags — as opposed to the existing `list_books`
(a flat summary of every book in the library). This is a new call *shape* on the existing
`LibraryGateway` Protocol (id-list in, richer joined data out), not a new Gateway class or a
new Protocol: it is still "asking a Library for information," just a different pattern of
asking.

**Depends on** `docs/superpowers/specs/2026-08-12-opaque-string-ids-design.md` landing first —
every id-typed field here (`BookDetails.id`, `Series.id`, the `ids` parameter, `missing_ids`)
is `str` from the start, consistent with that retrofit. Do not start this feature until that
one is merged and green.

## Domain model

```python
@dataclass(frozen=True)
class Series:
    id: str
    name: str


@dataclass(frozen=True)
class SeriesItem:
    series: Series
    index: str | None


@dataclass(frozen=True)
class BookDetails:
    id: str
    title: str
    pubdate: str | None
    authors: tuple[str, ...]
    tags: tuple[str, ...]
    publisher: Publisher | None
    series: SeriesItem | None


@dataclass(frozen=True)
class BookDetailsResult:
    books: tuple[BookDetails, ...]
    missing_ids: tuple[str, ...]
```

- `title`/`pubdate` are included even though a caller likely already has them from a prior
  `list_books()` call — book ids are meant to stand on their own (a future way to obtain ids,
  e.g. "all book ids by a given author," may not go through `list_books` first), so
  `BookDetails` must be self-sufficient.
- `Series` (id, name) is the reusable entity — same shape as `Publisher`, and the natural model
  for a future standalone Series listing. `SeriesItem` couples it with `index`, which is
  meaningless without a series, so the two travel together rather than as two independent
  optional fields on `BookDetails` that could drift out of sync (an `index` set while `series`
  is `None`).
- `index` is `str`, not Calibre's native `float` (`series_index`) — Calibre's float
  representation is a poor fit for series numbering (not a true continuum: real-world
  numbering includes things like "7.3" for a book that sits between two others in a series, or
  non-numeric conventions entirely), and a string leaves room to fix that representation later
  without another type migration.
- `publisher`/`series` are `None` when the book has no linked publisher/series — Calibre allows
  both to be unset.
- Deliberately out of scope for now: ISBN (Calibre has both a legacy `books.isbn` column and a
  generic `identifiers` table; which one to use is deferred to whenever ISBN is actually
  needed).
- A missing id is not an error at the gateway level — `get_book_details` always succeeds if
  the library itself is valid; ids that don't exist land in `missing_ids` instead of raising.

## Gateway

`book0_core/gateway.py`'s `LibraryGateway` Protocol grows:

```python
def get_book_details(self, ids: list[str]) -> BookDetailsResult: ...
```

- **`SqliteLibraryGateway.get_book_details(ids)`** — same existence/schema checks
  (`LibraryNotFoundError`, `NotACalibreLibraryError`) as every other method. An empty `ids`
  list is valid; the implementation must not special-case an early return for it (e.g. `if not
  ids: return BookDetailsResult((), ())` before ever touching the database) — `ids` is
  expected to eventually sit alongside other, not-yet-designed parameters (a future
  "suggest a book" mode is one candidate raised during design), and an early return keyed only
  on `ids` being empty would need to be unwound once those parameters exist. For now the
  method's only parameter stays `ids: list[str]`; this is a forward note about implementation
  shape, not a signature change today. `WHERE id IN (...)` naturally returns zero rows for an
  empty `ids` list regardless, so this has no behavioral effect yet. The query joins `books`
  against `books_authors_link`/`authors` and `books_tags_link`/`tags` (both many-to-many,
  aggregated per book — same `GROUP_CONCAT` pattern `list_books` already uses for authors),
  and against `books_publishers_link`/`publishers` and `books_series_link`/`series` (both
  treated as at-most-one per book, matching the existing `list_publishers`/Publishers-feature
  convention, even though Calibre's schema technically allows more). `series_index` comes
  directly off the `books` row, not a link table. Exact SQL (subquery shape, `GROUP_CONCAT`
  vs. correlated subqueries) is a plan-level decision, not pinned down here.
  - **No ordering is guaranteed anywhere** — not in the SQL, not by the gateway reassembling
    results, not in presentation. Earlier drafts of this design required `books` to come back
    in the order `ids` was requested; that requirement is deliberately dropped as premature
    (YAGNI) — nothing today needs it, and enforcing an order (in SQL via `ORDER BY`, or by
    reordering in Python) is its own decision to make later, once something actually depends
    on a specific order. `books` and `missing_ids` come back in whatever order the
    implementation naturally produces, which may change between calls or versions of the
    query. Tests must account for this themselves (compare as a set, or sort before
    comparing) rather than asserting positionally.
  - `missing_ids` is every requested id with no matching row — `tuple[str, ...]`, matching
    every other collection type in this codebase (`Book.authors`, `BookDetails.tags`, etc. are
    all tuples too), with no ordering guarantee (see above).

- **`HttpLibraryGateway.get_book_details(ids)`** — `POST /libraries/{tag}/books/detail` with
  JSON body `{"ids": [...]}`, same 404/500 error reconstruction as every other method.

## API

`book0_api/schemas.py` gains schemas mirroring the domain models 1:1 (`SeriesOut`,
`SeriesItemOut`, `BookDetailsOut`), each with a `from_*` classmethod, same pattern as
`AuthorOut`/`PublisherOut`. The response body for a successful call is
`{"books": [...], "missing_ids": [...]}` — a single JSON object, not a bare list (unlike the
existing three routes), since there are two things to return together.

`book0_api/main.py` gains `POST /libraries/{tag}/books/detail`, taking a JSON body
`{"ids": [...]}` (a `BookIdsIn` Pydantic model with `ids: list[str]`). `POST` rather than `GET`
because this is the first route that needs a request body — none of the existing three routes
take one. Error mapping is the same shape as the other three routes (`LibraryNotFoundError` →
404, `NotACalibreLibraryError` → 500), with one addition: an **unconfigured tag** returns
`{"books": [], "missing_ids": [...all requested ids]}` rather than a bare `[]` — this is the
direct consequence of the existing "unconfigured tag behaves like an empty library" convention
(an empty library has no books, so every requested id is, definitionally, missing), not a new
special case.

## Presentation

`book0_presentation/tables.py` gains `render_book_details_table(books: list[BookDetails]) ->
str` — same shape as every other `render_*_table` function: it formats whatever sequence of
`BookDetails` it's handed, in the order given, with no knowledge of `BookDetailsResult`,
`missing_ids`, requested ids, or the Gateway. Reordering to match the originally-requested
`--ids` order, and anything to do with `missing_ids`, is the caller's (CLI's) responsibility —
see CLI UX below. This keeps the presentation layer exactly as "dumb" as
`render_book_table`/`render_author_table`/`render_publisher_table` already are.

- If `books` is empty: `"No book details found."` (matching the existing empty-result
  convention).
- Otherwise: an aligned table (same `_align_rows` helper) with one row per book — columns
  covering id, title, authors, publisher, series (name + index), tags, pub date.
- Authors and tags are joined with `" & "` per the cell (not `", "` like the existing books
  table), to leave room for a comma to mean something else if a future column needs it (e.g.
  Calibre-style "Lastname, Firstname" author formatting, which uses a comma internally). This
  separator convention is explicitly expected to be revisited later, including possibly
  choosing a different separator per field (authors vs. tags) — not settled permanently here.

Exact column order/widths are a plan-level decision.

**Amendment (post-implementation cleanup):** `render_book_details_table` itself is unchanged
— still just `(books: list[BookDetails]) -> str`, still ignorant of `BookDetailsResult`,
`missing_ids`, and requested ids. But the reordering and missing-ids-message logic described
under "CLI UX" below turned out to be identical across both CLIs, so rather than leave it
duplicated it was extracted into two small functions that *do* live in
`book0_presentation/tables.py` and *do* know about `BookDetailsResult`/ids:
`order_book_details_by_ids(result: BookDetailsResult, ids: list[str]) -> list[BookDetails]`
and `format_missing_ids_message(missing_ids: tuple[str, ...]) -> str | None`. Both CLIs' `run()`
call these instead of inlining the logic themselves. This is a deliberate, requested exception
to this section's original "no knowledge of `BookDetailsResult`" rule for
`render_book_details_table` specifically — the rule still holds for the render function itself,
it just no longer describes every function in the module.

## CLI UX

Both `book0` and `book0-remote` gain a fourth subcommand, `books-detail`:

- `book0 books-detail --ids 1,2,3 [--tag TAG]`
- `book0-remote books-detail --ids 1,2,3 --server URL --tag TAG`

`--ids` takes a comma-separated list, split into `list[str]` with **no numeric validation or
casting** — ids are opaque strings at every layer above the SQLite query, so the CLI passes
whatever was typed straight through; a non-numeric or unknown id simply won't match anything
and comes back in `missing_ids`, it is never a CLI usage error. Omitting `--ids` entirely (no
value at all) *is* a usage error — this is `argparse`'s ordinary required-argument behavior,
not custom validation. An empty resolved id list (e.g. `--ids ""`) is valid at the
gateway/protocol level and returns an empty result.

Both CLIs' `run()` own two things the Gateway and presentation layer deliberately don't:

- **Ordering for display.** After calling `get_book_details(ids)`, `run()` reorders
  `result.books` to match the order `--ids` was given (plain Python — e.g. build a lookup by
  `id` and walk the parsed `--ids` list) before calling `render_book_details_table` with that
  ordered sequence. This is what gives the user a deterministic, request-order display without
  requiring the Gateway or presentation layer to guarantee anything.
- **Reporting missing ids.** After printing the table, if `result.missing_ids` is non-empty,
  `run()` prints its own line about them directly (e.g. `Missing ids: 4, 99`) — this is plain
  CLI-level string formatting, not a presentation-layer function, and not something
  `render_book_details_table` knows about.

The CLI subcommand name (`books-detail`) mapping to the API route's path segment
(`/books/detail`) — dash becomes slash — is noted as a naming convention that may recur for
future subcommands, not something enforced by shared code today.

## Error handling

- Missing/unknown ids: not an error, reported via `missing_ids` (see Domain model and API
  above).
- Missing library file, non-Calibre file: same `LibraryNotFoundError`/`NotACalibreLibraryError`
  as every other method, mapped identically by `book0_api` and reconstructed identically by
  `HttpLibraryGateway`.
- Unconfigured tag: `book0_api`/`book0-remote` treat it as an empty library (see API section);
  `book0`'s `--tag` still hard-errors on an unknown tag, unchanged, matching existing
  Books/Authors/Publishers behavior.

## Testing

- `tests/conftest.py`: extend `calibre_metadata_db` with `series`/`books_series_link` tables, a
  `series_index` column on the existing `books` table (not present in the fixture's schema
  today), and `books_tags_link`/`tags` tables — none of these exist in the fixture yet. Add
  fixture data covering: a book with a publisher, series, and tags; a book with none of them;
  a book with only some.
- Unit: `Series`, `SeriesItem`, `BookDetails`, `BookDetailsResult`, the new API schemas'
  `from_*` classmethods, `render_book_details_table` (empty list, one book, several books,
  rendered in whatever order the list is given — no reordering or missing-ids logic to test
  here, since the function doesn't have either).
- Integration: `SqliteLibraryGateway.get_book_details` (nominal with all fields populated, a
  book missing publisher/series/tags, missing ids, empty `ids` list, missing file, non-Calibre
  file), `HttpLibraryGateway.get_book_details` (same cases via the real route). Every test
  comparing `books`/`missing_ids` against expected data does so order-independently (set
  comparison or sorting both sides before comparing) — no test may rely on either collection's
  return order at the Gateway level.
- Integration, both CLIs' `run()` for `books-detail`: the `--ids` comma-parsing, a non-numeric
  id landing in `missing_ids`, the missing-`--ids`-value usage error, **and** two cases specific
  to the CLI's own responsibilities — requesting ids out of title-sort order and confirming the
  printed table follows the requested order instead, and requesting a mix of known/unknown ids
  and confirming the "Missing ids: ..." line reports the unknown ones.
- E2E: the new route (nominal, unconfigured tag, both error mappings, ids partially found).

## Out of scope

- ISBN (deferred — legacy column vs. `identifiers` table not yet decided).
- Any change to `Book`/`BookOut` (no `publisher`/`series`/`tags` field added there — this stays
  a separate access pattern, not a merge into the existing summary).
- Id-scoping-by-library-tag (raised during design, deliberately deferred).
- A shared universe of "series inside series" (Calibre can't model this either) — not handled.
- Series/Tags/Language as their own standalone listings (separate future features).
