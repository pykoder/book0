# Book Id Normalization/Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two related `get_book_details` bugs — SQLite's numeric affinity silently
aliasing malformed ids (`"01"`, `" 1"`, `"1.0"`, `"+1"`, `"1e0"`) to a real book's id, and
duplicate requested ids producing duplicate rendered rows — entirely inside the two places
that actually own each problem.

**Architecture:** `book0_presentation/tables.py::order_book_details_by_ids` dedupes as it
builds its output list (backend-agnostic fix). `book0_core/sqlite_gateway.py` gains a
private, SQLite-specific `SqliteLibraryGateway._partition_ids` static method that dedupes
(first-seen order, empty segments dropped) and splits requested ids into `(deduped_ids,
valid_ids)` using this backend's id format (`^[1-9]\d*$`); `get_book_details` uses
`valid_ids` for its SQL query and `deduped_ids` to compute `missing_ids`, folding both
invalid-format and valid-but-not-found ids into one tuple in original first-seen order. No
new shared module, no `LibraryGateway` Protocol change, no `book0_api`/`book0_cli_remote`
changes.

**Tech Stack:** Python 3.12, stdlib `sqlite3`/`re`, `pytest`, `uv`.

## Global Constraints

- Every command goes through `uv run <tool>` — never a bare `python`/`pytest`/`ruff`/`mypy`.
- `WHERE id IN ()` (an empty `IN` clause) is valid SQL and simply matches no rows — verified
  directly against SQLite. No special-casing for an empty `valid_ids` is needed anywhere in
  this plan.
- `_partition_ids` is SQLite-specific (its validity regex assumes Calibre's integer
  autoincrement id scheme) and lives as a private static method on `SqliteLibraryGateway`
  itself, not as a shared `book0_core` utility — a future non-SQLite `LibraryGateway`
  implementation would define its own partitioning against its own id scheme.
- Each task's commit touches only the files that task's own section below lists.
- Every new function/class ships with a test in the same commit. `SqliteLibraryGateway`'s
  existing private helpers (`_normalize_pubdate`, `_check_is_calibre_library`) are never
  unit-tested directly — only indirectly through `get_book_details`'s integration tests
  against a real temp SQLite file. `_partition_ids` follows the same established pattern:
  no new unit test file for it, covered indirectly through `get_book_details`'s integration
  tests.
- Design doc: `docs/superpowers/specs/2026-08-14-book-id-normalization-design.md`.

---

### Task 1: Fix duplicate rendered rows in `order_book_details_by_ids`

**Files:**
- Modify: `src/book0_presentation/tables.py:96-102`
- Test: `tests/unit/test_tables.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `order_book_details_by_ids(result: BookDetailsResult, ids: list[str]) ->
  list[BookDetails]` — signature unchanged, now dedupes its own traversal. No caller changes
  anywhere in the codebase.

- [ ] **Step 1: Write the failing test**

Add this test to `tests/unit/test_tables.py`, right after
`test_order_book_details_by_ids_skips_ids_not_in_the_result` (matches that test's exact
`BookDetails` construction style):

```python
def test_order_book_details_by_ids_skips_duplicate_requested_ids():
    dune = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )
    result = BookDetailsResult(books=(dune,), missing_ids=())

    ordered = order_book_details_by_ids(result, ["1", "1"])

    assert ordered == [dune]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_tables.py::test_order_book_details_by_ids_skips_duplicate_requested_ids -v`
Expected: FAIL — `assert [dune, dune] == [dune]` (the current implementation appends the same
book once per requested id, including duplicates).

- [ ] **Step 3: Implement the dedup fix**

In `src/book0_presentation/tables.py`, replace the current `order_book_details_by_ids`
(lines 96-102):

```python
def order_book_details_by_ids(
    result: BookDetailsResult, ids: list[str]
) -> list[BookDetails]:
    books_by_id = {book.id: book for book in result.books}
    return [
        books_by_id[requested_id] for requested_id in ids if requested_id in books_by_id
    ]
```

with:

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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: PASS (all tests in the file, including the two pre-existing
`order_book_details_by_ids` tests and the new one — 3 total for this function)

- [ ] **Step 5: Commit**

```bash
git add src/book0_presentation/tables.py tests/unit/test_tables.py
git commit -m "fix: dedupe order_book_details_by_ids so a repeated requested id renders once"
```

---

### Task 2: Fix numeric-affinity aliasing in `SqliteLibraryGateway.get_book_details`

**Files:**
- Modify: `src/book0_core/sqlite_gateway.py`
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `SqliteLibraryGateway._partition_ids(raw_ids: list[str]) -> tuple[list[str],
  list[str]]` (private static method, no external caller — internal to `get_book_details`).
  `get_book_details`'s public signature (`ids: list[str] -> BookDetailsResult`) is unchanged.

- [ ] **Step 1: Write the failing tests**

Add these two tests to `tests/integration/test_sqlite_gateway.py`, right after
`test_get_book_details_reports_unknown_ids_as_missing` (matches that test's exact style —
plain `assert result.books == (...)` / `assert result.missing_ids == (...)`, no mocking):

```python
def test_get_book_details_treats_numeric_affinity_aliases_as_distinct_missing_ids(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["01", " 1", "1.0", "+1", "1e0"])

    assert result.books == ()
    assert result.missing_ids == ("01", " 1", "1.0", "+1", "1e0")


def test_get_book_details_handles_duplicates_invalid_and_unknown_ids_together(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "01", "999", "1"])

    assert result.books == (DUNE_DETAILS,)
    assert result.missing_ids == ("01", "999")


def test_get_book_details_returns_all_ids_as_missing_when_none_are_valid(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["abc", "def"])

    assert result.books == ()
    assert result.missing_ids == ("abc", "def")


def test_get_book_details_silently_drops_empty_id_segments(calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "", "2"])

    assert set(result.books) == {DUNE_DETAILS, HOBBIT_DETAILS}
    assert result.missing_ids == ()
```

(`test_get_book_details_treats_numeric_affinity_aliases_as_distinct_missing_ids` verifies the
core bug directly: today, all five of `"01"`, `" 1"`, `"1.0"`, `"+1"`, `"1e0"` alias to id
`"1"` via SQLite's numeric affinity — confirmed empirically against a real
`INTEGER PRIMARY KEY` column — so the *current* code returns `books == (DUNE_DETAILS,)`,
`missing_ids == ()` for this call; after the fix, none of these strings match the validity
regex, so none reach the SQL query at all, and all five land in `missing_ids` in original
order. `test_get_book_details_handles_duplicates_invalid_and_unknown_ids_together` verifies
the three cases compose correctly in one call: the duplicate `"1"` is deduped to a single
match, `"01"` never reaches the DB and is reported as missing rather than aliasing to `"1"`,
and `"999"` is missing for the ordinary reason (well-formed but nonexistent) — all three
missing/duplicate mechanisms exercised together, in one request, matching first-seen request
order in the output. `test_get_book_details_returns_all_ids_as_missing_when_none_are_valid`
exercises the fully-empty-`valid_ids` path end to end (no special-casing needed, but also
never directly exercised by the other tests, which all include at least one valid id).
`test_get_book_details_silently_drops_empty_id_segments` exercises `_partition_ids`'s
`raw_id == ""` branch, which none of the other new or existing tests reach — this test uses
`set(result.books) ==` rather than tuple equality, matching the established convention in
`test_get_book_details_returns_all_requested_books_regardless_of_order` for asserting on
`get_book_details`'s row order, which is not guaranteed to match request order — only
`order_book_details_by_ids`, at the presentation layer, does that. This test is *also*
expected to fail before the fix — confirmed empirically: today's code passes `""` straight
into the SQL query alongside `"1"`/`"2"`, it matches no row, and
`missing_ids = tuple(id_ for id_ in ids if id_ not in found_ids)` then includes the literal
empty string, giving `missing_ids == ("",)` rather than `()` — a second, smaller symptom of
the same "nothing filters the raw ids before they reach missing_ids" root cause the numeric-
affinity bug has.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py::test_get_book_details_treats_numeric_affinity_aliases_as_distinct_missing_ids tests/integration/test_sqlite_gateway.py::test_get_book_details_handles_duplicates_invalid_and_unknown_ids_together tests/integration/test_sqlite_gateway.py::test_get_book_details_silently_drops_empty_id_segments -v`
Expected: FAIL on all three — the first two return `books == (DUNE_DETAILS,)` with a smaller
`missing_ids` than expected (SQLite's numeric affinity matches these malformed ids to
`"1"`); the third returns `missing_ids == ("",)` instead of `()` (the empty segment isn't
filtered out today). `test_get_book_details_returns_all_ids_as_missing_when_none_are_valid`
is expected to PASS even against the current code — neither `"abc"` nor `"def"` coerces to
any row via numeric affinity, so this one exists to lock in behavior the fix must preserve,
not to demonstrate a bug.

- [ ] **Step 3: Implement `_partition_ids` and update `get_book_details`**

In `src/book0_core/sqlite_gateway.py`, add `import re` to the top-of-file imports (alongside
the existing `import sqlite3` / `from pathlib import Path`), and add a new module-level
constant right after the existing `_UNDEFINED_PUBDATE_PREFIX` constant:

```python
_VALID_ID_PATTERN = re.compile(r"^[1-9]\d*$")
```

Add this new private static method to the `SqliteLibraryGateway` class, placed right after
`get_book_details` and before `_normalize_pubdate`:

```python
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
```

Replace `get_book_details`'s current body:

```python
    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        if not self._db_path.exists():
            raise LibraryNotFoundError(f"Calibre library not found: {self._db_path}")

        connection = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            self._check_is_calibre_library(connection)
            placeholders = ", ".join("?" for _ in ids)
            query = _GET_BOOK_DETAILS_QUERY_TEMPLATE.format(placeholders=placeholders)
            rows = connection.execute(query, ids).fetchall()
        finally:
            connection.close()

        books = []
        found_ids: set[str] = set()
        for row in rows:
            book_id = str(row[0])
            found_ids.add(book_id)
            books.append(
                BookDetails(
                    id=book_id,
                    title=row[1],
                    pubdate=self._normalize_pubdate(row[2]),
                    authors=tuple(row[4].split(", ")) if row[4] else (),
                    tags=tuple(row[5].split(", ")) if row[5] else (),
                    publisher=(
                        Publisher(id=str(row[6]), name=row[7])
                        if row[6] is not None
                        else None
                    ),
                    series=(
                        SeriesItem(
                            series=Series(id=str(row[8]), name=row[9]),
                            index=str(row[3]) if row[3] is not None else None,
                        )
                        if row[8] is not None
                        else None
                    ),
                )
            )

        missing_ids = tuple(id_ for id_ in ids if id_ not in found_ids)
        return BookDetailsResult(books=tuple(books), missing_ids=missing_ids)
```

with:

```python
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
            book_id = str(row[0])
            found_ids.add(book_id)
            books.append(
                BookDetails(
                    id=book_id,
                    title=row[1],
                    pubdate=self._normalize_pubdate(row[2]),
                    authors=tuple(row[4].split(", ")) if row[4] else (),
                    tags=tuple(row[5].split(", ")) if row[5] else (),
                    publisher=(
                        Publisher(id=str(row[6]), name=row[7])
                        if row[6] is not None
                        else None
                    ),
                    series=(
                        SeriesItem(
                            series=Series(id=str(row[8]), name=row[9]),
                            index=str(row[3]) if row[3] is not None else None,
                        )
                        if row[8] is not None
                        else None
                    ),
                )
            )

        missing_ids = tuple(id_ for id_ in deduped_ids if id_ not in found_ids)
        return BookDetailsResult(books=tuple(books), missing_ids=missing_ids)
```

(Only the query's parameter list — `valid_ids` instead of `ids` — and the final
`missing_ids` computation — `deduped_ids` instead of `ids` — actually change; the
row-building loop itself is untouched. No special-casing for an empty `valid_ids`: `WHERE
id IN ()` is valid SQL and simply matches no rows, so the query runs the exact same code
path regardless of how many valid ids there are.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: PASS — every test in the file, including the four new ones and all pre-existing
`get_book_details` tests (in particular
`test_get_book_details_returns_all_requested_books_regardless_of_order`,
`test_get_book_details_reports_unknown_ids_as_missing`, and
`test_get_book_details_returns_empty_result_for_empty_ids_list`, none of which change
behavior).

- [ ] **Step 5: Run the full suite, lint, format, and type-check**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all pass, no new warnings.

- [ ] **Step 6: Commit**

```bash
git add src/book0_core/sqlite_gateway.py tests/integration/test_sqlite_gateway.py
git commit -m "fix: stop SQLite numeric affinity from aliasing malformed book ids to real ones"
```

---

## Out of scope (see design doc)

- `books-detail` response projection + pagination (undesigned — tracked in
  `docs/superpowers/TODO.md`).
- Far-future multi-library `(tag, id)` identity (undesigned — tracked in
  `docs/superpowers/TODO.md`).
- `LibraryGateway` Protocol conformance never statically checked (unrelated pre-existing gap
  — tracked in `docs/superpowers/TODO.md`).
