# Book id normalization/dedup — design

## Purpose

`get_book_details`'s requested-id handling has two related bugs, both confirmed empirically
during the book-details feature's final review (see `docs/superpowers/TODO.md`):

- SQLite's numeric affinity aliases several string forms to the same row — `"01"`, `" 1"`,
  `"1.0"`, `"+1"`, `"1e0"` all match id `"1"` in a `WHERE id IN (...)` clause — so a malformed
  id can silently match a real book instead of being reported as missing.
- Duplicate requested ids produce duplicate rendered rows — a CLI-level artifact, not a SQL
  one (`IN (1, 1)` doesn't itself duplicate DB rows); the bug is in how the CLI rebuilds its
  output list from the raw, possibly-duplicated `--ids` value.

This design fixes both, entirely inside the two places that actually own each problem —
no new shared module, no `LibraryGateway` Protocol change, no `book0_api`/`book0_cli_remote`
changes at all.

A related, larger idea came up during brainstorming — letting a caller control which fields
`books-detail` returns at all (ids only, full detail, a file path, description text) plus
pagination for large libraries — and was deliberately split off rather than folded in here;
see "Out of scope" below and `docs/superpowers/TODO.md`.

## Where each bug is fixed

**Duplicate rendered rows** is backend-agnostic — it doesn't matter what the id format is,
only that the same id string shouldn't produce the same rendered book twice. The fix is local
to presentation:

`book0_presentation/tables.py::order_book_details_by_ids` dedupes as it builds the list,
tracking which ids it has already added:

```python
def order_book_details_by_ids(
    result: BookDetailsResult, ids: list[str]
) -> list[BookDetails]:
    books_by_id = {book.id: book for book in result.books}
    seen: set[str] = set()
    ordered: list[BookDetails] = []
    for requested_id in ids:
        if requested_id in books_by_id and requested_id not in seen:
            seen.add(requested_id)
            ordered.append(books_by_id[requested_id])
    return ordered
```

No caller changes — every existing call site keeps passing whatever `ids` list it already
passes today (raw, comma-split, possibly containing duplicates).

**Numeric-affinity aliasing** is backend-specific: what counts as a syntactically valid id is
a property of the concrete storage backend (SQLite/Calibre's integer autoincrement ids today),
not a universal format a future non-SQLite `LibraryGateway` implementation would necessarily
share (e.g. a UUID- or string-keyed backend). The partitioning logic therefore lives as a
private method on `SqliteLibraryGateway` itself, in `book0_core/sqlite_gateway.py` —
alongside its other backend-specific constants like `_UNDEFINED_PUBDATE_PREFIX` — rather than
as a shared, backend-agnostic `book0_core` utility with one hardcoded regex. A future
non-SQLite gateway would define its own partitioning against its own id scheme; there is no
shared assumption to be wrong for it.

```python
_VALID_ID_PATTERN = re.compile(r"^[1-9]\d*$")


class SqliteLibraryGateway:
    @staticmethod
    def _partition_ids(raw_ids: list[str]) -> tuple[list[str], list[str]]:
        """Dedupe (first-seen order, empty segments dropped); split into
        (deduped_ids, valid_ids) using this backend's id format. deduped_ids
        holds every distinct requested id in original order (valid and
        invalid mixed); valid_ids is the subset safe to place in a SQL
        IN (...) clause, in the same relative order."""
        seen: set[str] = set()
        deduped_ids: list[str] = []
        valid_ids: list[str] = []
        for raw_id in raw_ids:
            if raw_id == "" or raw_id in seen:
                continue
            seen.add(raw_id)
            deduped_ids.append(raw_id)
            if _VALID_ID_PATTERN.match(raw_id):
                valid_ids.append(raw_id)
        return deduped_ids, valid_ids

    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        if not self._db_path.exists():
            raise LibraryNotFoundError(f"Calibre library not found: {self._db_path}")

        deduped_ids, valid_ids = self._partition_ids(ids)

        connection = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            self._check_is_calibre_library(connection)
            placeholders = ", ".join("?" for _ in valid_ids)
            query = _GET_BOOK_DETAILS_QUERY_TEMPLATE.format(placeholders=placeholders)
            rows = connection.execute(query, valid_ids).fetchall()
        finally:
            connection.close()

        books = []
        found_ids: set[str] = set()
        for row in rows:
            # ... unchanged row-building loop ...
            pass

        missing_ids = tuple(id_ for id_ in deduped_ids if id_ not in found_ids)
        return BookDetailsResult(books=tuple(books), missing_ids=missing_ids)
```

`missing_ids = tuple(id_ for id_ in deduped_ids if id_ not in found_ids)` folds both
invalid-format ids and valid-but-not-found ids into one tuple, in original first-seen request
order, with no separate bookkeeping for "which kind of missing" needed.

No special-casing is needed for an empty `valid_ids` (e.g. `--ids` entirely invalid, or
`--ids ""` which already produces `ids = []` today via `args.ids.split(",") if args.ids else
[]`): `WHERE id IN ()` is valid SQL — confirmed directly against SQLite — and simply matches
no rows, so the query executes exactly the same code path regardless of how many valid ids
there are, `0` included.

## Error handling / edge cases

- `--ids "1,1,2"` → book 1 rendered once, not twice.
- `--ids "01, 1, 999"` → `"01"` is its own distinct, never-found id (no longer silently
  aliased to `"1"` by SQLite's numeric affinity); assuming `999` doesn't exist,
  `missing_ids == ("01", "999")`, in original order.
- `--ids "1,,2"` → the empty segment is silently dropped; it never appears in `deduped_ids`,
  `valid_ids`, or the rendered/missing output.
- `--ids "abc,def"` (all invalid) → `books == ()`, `missing_ids == ("abc", "def")`; the query
  still runs with an empty `IN (...)`, which is valid SQL and simply matches nothing.
- An id that is well-formed but simply doesn't exist in the library keeps today's exact
  behavior — it lands in `missing_ids`, same as always.

## Testing

- `tests/unit/test_tables.py`: `order_book_details_by_ids` with a duplicated id in the request
  — asserts the corresponding book appears exactly once, in first-requested position.
- `tests/integration/test_sqlite_gateway.py` (real temp SQLite file, no mocking):
  - a numeric-affinity-aliased id (`"01"`, `" 1"`, `"1.0"`, `"+1"`, or `"1e0"`) is reported as
    missing rather than matching the real book it would have aliased to today;
  - an all-invalid `--ids` request returns an empty `books` tuple and all requested ids in
    `missing_ids`, without error;
  - a single request mixing duplicates, invalid-format ids, and valid-but-unknown ids produces
    correct `books` and `missing_ids` in original first-seen order.
- Existing `tests/integration/test_cli_main.py` / `test_cli_remote_main.py` books-detail tests
  are expected to pass unchanged — behavior for already-valid, non-duplicated, existing ids
  does not change.

## Out of scope

- **`books-detail` response projection + pagination** (undesigned) — raised during
  brainstorming for this fix and deliberately split off rather than folded in: controlling
  which fields `books-detail` returns (ids only, full detail, a file path — possibly
  triggering a download, description/abstract text), plus pagination for libraries with tens
  of thousands of books. Join cost genuinely matters at that scale, and a simple boolean
  "ids only" flag isn't a sufficient design for it — real query-level savings would require
  either forking `BookDetailsResult`'s shape or the `LibraryGateway` Protocol itself. No
  design exists yet. Tracked in `docs/superpowers/TODO.md`.
- **Far-future multi-library `(tag, id)` identity** — raised as motivating context for the
  original TODO item, not as a request to design it now. No design exists yet. Tracked in
  `docs/superpowers/TODO.md`.
- **`LibraryGateway` Protocol conformance never statically checked** — a separate, unrelated
  pre-existing gap. Tracked in `docs/superpowers/TODO.md`.
