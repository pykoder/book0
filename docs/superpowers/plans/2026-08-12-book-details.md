# Book Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new access pattern — `get_book_details(ids)` — that fetches rich, joined
details (publisher, series + position in it, authors, tags) for an explicit list of book ids,
alongside the existing flat `list_books` summary, on both `book0` and `book0-remote`.

**Architecture:** `book0_core.models` gains `Series`, `SeriesItem`, `BookDetails`,
`BookDetailsResult`. `LibraryGateway` (the same Protocol `list_books`/`list_authors`/
`list_publishers` already live on) grows a fourth method, `get_book_details(ids: list[str]) ->
BookDetailsResult`. `SqliteLibraryGateway` implements it with one query using correlated
subqueries for the many-to-many joins (authors, tags) and `LEFT JOIN`s for the at-most-one
joins (publisher, series) — same "at most one" convention already established for
`list_publishers`. `HttpLibraryGateway` implements it as `POST /libraries/{tag}/books/detail`
with a JSON body, the first route in this project needing a request body.
`book0_presentation.tables` gains `render_book_details_table(books: list[BookDetails])`,
shaped exactly like the other three `render_*_table` functions — it does not know about
ordering or missing ids. Both CLIs gain a `books-detail` subcommand, which owns reordering the
result to match the requested `--ids` order and reporting missing ids — responsibilities the
Gateway and presentation layer deliberately don't have.

**Tech Stack:** Python 3.12, stdlib `sqlite3`/`argparse`, FastAPI + Pydantic, `httpx`,
`pytest`, `uv`.

**Depends on:** the opaque-string-ids retrofit
(`docs/superpowers/plans/2026-08-12-opaque-string-ids.md`) — already landed and merged. Every
id-typed field in this plan is `str` from the start.

## Global Constraints

- Every command goes through `uv run <tool>` — never a bare `python`/`pytest`/`ruff`/`mypy`.
- `book0_core` never depends on `book0_cli`, `book0_cli_remote`, `book0_api`, or `argparse`.
- `book0_api`'s routes stay plain `def` (never `async def`).
- `book0_api` never returns a raw `sqlite3.OperationalError` or unmapped 500.
- No change to the SQL text of `_LIST_BOOKS_QUERY`/`_LIST_AUTHORS_QUERY`/
  `_LIST_PUBLISHERS_QUERY` — this plan only adds a new query.
- `get_book_details` must not special-case an early return for an empty `ids` list (a forward
  note for future non-id parameters) — `WHERE id IN (...)` with zero placeholders is valid
  SQLite and naturally returns zero rows.
- **No ordering is guaranteed by the Gateway or the SQL** — `books` and `missing_ids` come
  back in whatever order the query/Python naturally produces. Every test comparing them must
  do so order-independently (as a set, or sorted before comparing). Reordering for display,
  and reporting missing ids, are the CLI's job, not the Gateway's or the presentation layer's.
- `render_book_details_table` takes only `books: list[BookDetails]` — no `ids`, no
  `BookDetailsResult`, no knowledge of missing ids. Same shape as `render_book_table`/
  `render_author_table`/`render_publisher_table`.
- **Each task's commit touches only the files that task's own section below lists.** If
  running the full suite reveals a failure outside a task's declared files, report it — do not
  fix it inside that task's commit. (This bit the opaque-string-ids retrofit once already: an
  implementer bundled a different task's fix into its own commit because the full suite
  surfaced it; it had to be split back out via `git reset --soft` before review could proceed
  cleanly. Don't repeat it.)
- Every new function/class ships with a test in the same commit.
- Ship no config option, flag, or abstraction the spec did not ask for: no ISBN, no
  `publisher`/`series`/`tags` field on `Book`/`BookOut`, no sort option.
- Design doc: `docs/superpowers/specs/2026-08-12-book-details-design.md`.

---

### Task 1: Domain model — `Series`, `SeriesItem`, `BookDetails`, `BookDetailsResult`

**Files:**
- Modify: `src/book0_core/models.py`
- Modify: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `Series(id: str, name: str)`, `SeriesItem(series: Series, index: str | None)`,
  `BookDetails(id: str, title: str, pubdate: str | None, authors: tuple[str, ...], tags:
  tuple[str, ...], publisher: Publisher | None, series: SeriesItem | None)`,
  `BookDetailsResult(books: tuple[BookDetails, ...], missing_ids: tuple[str, ...])` — every
  later task in this plan depends on these four types.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_models.py`, changing the import line:

```python
from book0_core.models import Author, Book, BookDetails, BookDetailsResult, Publisher, Series, SeriesItem
```

```python
def test_series_holds_id_and_name():
    series = Series(id="1", name="Dune Chronicles")

    assert series.id == "1"
    assert series.name == "Dune Chronicles"


def test_series_is_frozen():
    series = Series(id="1", name="Dune Chronicles")

    with pytest.raises(AttributeError):
        series.name = "Other"


def test_series_item_holds_series_and_index():
    series_item = SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0")

    assert series_item.series == Series(id="1", name="Dune Chronicles")
    assert series_item.index == "1.0"


def test_series_item_accepts_none_index():
    series_item = SeriesItem(series=Series(id="1", name="Dune Chronicles"), index=None)

    assert series_item.index is None


def test_series_item_is_frozen():
    series_item = SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0")

    with pytest.raises(AttributeError):
        series_item.index = "2.0"


def test_book_details_holds_all_fields():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate="1965-08-01",
        authors=("Frank Herbert",),
        tags=("sci-fi", "classic"),
        publisher=Publisher(id="1", name="Ace Books"),
        series=SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0"),
    )

    assert book_details.id == "1"
    assert book_details.title == "Dune"
    assert book_details.pubdate == "1965-08-01"
    assert book_details.authors == ("Frank Herbert",)
    assert book_details.tags == ("sci-fi", "classic")
    assert book_details.publisher == Publisher(id="1", name="Ace Books")
    assert book_details.series == SeriesItem(
        series=Series(id="1", name="Dune Chronicles"), index="1.0"
    )


def test_book_details_accepts_none_publisher_and_series():
    book_details = BookDetails(
        id="2",
        title="The Hobbit",
        pubdate=None,
        authors=("J.R.R. Tolkien",),
        tags=(),
        publisher=None,
        series=None,
    )

    assert book_details.publisher is None
    assert book_details.series is None


def test_book_details_is_frozen():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )

    with pytest.raises(AttributeError):
        book_details.title = "Other"


def test_book_details_result_holds_books_and_missing_ids():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )
    result = BookDetailsResult(books=(book_details,), missing_ids=("99",))

    assert result.books == (book_details,)
    assert result.missing_ids == ("99",)


def test_book_details_result_is_frozen():
    result = BookDetailsResult(books=(), missing_ids=())

    with pytest.raises(AttributeError):
        result.missing_ids = ("1",)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Series'`

- [ ] **Step 3: Implement the new domain models**

Append to `src/book0_core/models.py`, after the existing `Publisher` class:

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: PASS (17 tests: 7 existing + 10 new)

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/models.py tests/unit/test_models.py
git commit -m "feat: add Series, SeriesItem, BookDetails, BookDetailsResult domain models"
```

---

### Task 2: `LibraryGateway.get_book_details` + `SqliteLibraryGateway.get_book_details`

**Files:**
- Modify: `src/book0_core/gateway.py`
- Modify: `src/book0_core/sqlite_gateway.py`
- Modify: `tests/conftest.py`
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: `Series`, `SeriesItem`, `BookDetails`, `BookDetailsResult` from Task 1.
- Produces: `LibraryGateway.get_book_details(ids: list[str]) -> BookDetailsResult` (Protocol
  method every implementation must have); `SqliteLibraryGateway.get_book_details(ids: list[str])
  -> BookDetailsResult`; `tests.conftest.DUNE_DETAILS`/`HOBBIT_DETAILS`/`GOOD_OMENS_DETAILS:
  BookDetails` (fixture data every later test task imports).

- [ ] **Step 1: Extend the shared fixture**

In `tests/conftest.py`, change the import line and add the three named `BookDetails` fixtures
after `CALIBRE_LIBRARY_PUBLISHERS`:

```python
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    Publisher,
    Series,
    SeriesItem,
)
```

```python
# BookDetails for the three books in the fixture DB, covering: a book with a
# publisher, series, and tags (Dune); a book with none of them (The Hobbit);
# a book with only some (Good Omens - publisher and tags, no series).
DUNE_DETAILS = BookDetails(
    id="1",
    title="Dune",
    pubdate="1965-08-01",
    authors=("Frank Herbert",),
    tags=("sci-fi", "classic"),
    publisher=Publisher(id="1", name="Ace Books"),
    series=SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0"),
)

HOBBIT_DETAILS = BookDetails(
    id="2",
    title="The Hobbit",
    pubdate=None,
    authors=("J.R.R. Tolkien",),
    tags=(),
    publisher=None,
    series=None,
)

GOOD_OMENS_DETAILS = BookDetails(
    id="3",
    title="Good Omens",
    pubdate="1990-05-01",
    authors=("Neil Gaiman", "Terry Pratchett"),
    tags=("fantasy", "humor"),
    publisher=Publisher(id="2", name="Gollancz"),
    series=None,
)
```

Change the `books` table's schema (add `series_index`), and add `series`/`books_series_link`/
`tags`/`books_tags_link` tables, in the existing `executescript` call:

```sql
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    pubdate TEXT,
    series_index REAL
);
CREATE TABLE authors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE books_authors_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    author INTEGER NOT NULL
);
CREATE TABLE publishers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE books_publishers_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    publisher INTEGER NOT NULL
);
CREATE TABLE series (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE books_series_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    series INTEGER NOT NULL
);
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE books_tags_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    tag INTEGER NOT NULL
);
```

Change the `books` insert to include `series_index` (Dune is book 1 in its series; The Hobbit
and Good Omens have no series, so `series_index` is `NULL` for both):

```python
connection.executemany(
    "INSERT INTO books (id, title, pubdate, series_index) VALUES (?, ?, ?, ?)",
    [
        (1, "Dune", "1965-08-01", 1.0),
        (2, "The Hobbit", None, None),
        (3, "Good Omens", "1990-05-01", None),
    ],
)
```

Add, after the existing `books_publishers_link` insert:

```python
connection.executemany(
    "INSERT INTO series (id, name) VALUES (?, ?)",
    [(1, "Dune Chronicles")],
)
connection.executemany(
    "INSERT INTO books_series_link (book, series) VALUES (?, ?)",
    [(1, 1)],
)
connection.executemany(
    "INSERT INTO tags (id, name) VALUES (?, ?)",
    [
        (1, "sci-fi"),
        (2, "classic"),
        (3, "fantasy"),
        (4, "humor"),
    ],
)
connection.executemany(
    "INSERT INTO books_tags_link (book, tag) VALUES (?, ?)",
    [(1, 1), (1, 2), (3, 3), (3, 4)],
)
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/integration/test_sqlite_gateway.py`, adding the new fixture names to the
existing `from tests.conftest import (...)` line:

```python
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    DUNE_DETAILS,
    GOOD_OMENS_DETAILS,
    HOBBIT_DETAILS,
)
```

```python
def test_get_book_details_returns_details_for_a_book_with_everything(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1"])

    assert result.books == (DUNE_DETAILS,)
    assert result.missing_ids == ()


def test_get_book_details_returns_details_for_a_book_with_nothing_linked(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["2"])

    assert result.books == (HOBBIT_DETAILS,)
    assert result.missing_ids == ()


def test_get_book_details_returns_details_for_a_book_with_only_some_fields(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["3"])

    assert result.books == (GOOD_OMENS_DETAILS,)
    assert result.missing_ids == ()


def test_get_book_details_returns_all_requested_books_regardless_of_order(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["3", "1", "2"])

    assert set(result.books) == {DUNE_DETAILS, HOBBIT_DETAILS, GOOD_OMENS_DETAILS}
    assert result.missing_ids == ()


def test_get_book_details_reports_unknown_ids_as_missing(calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details(["1", "999", "abc"])

    assert result.books == (DUNE_DETAILS,)
    assert set(result.missing_ids) == {"999", "abc"}


def test_get_book_details_returns_empty_result_for_empty_ids_list(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    result = gateway.get_book_details([])

    assert result.books == ()
    assert result.missing_ids == ()


def test_get_book_details_opens_the_database_read_only(
    calibre_metadata_db: Path, monkeypatch: pytest.MonkeyPatch
):
    real_connect = sqlite3.connect
    captured_calls: list[tuple[str, bool]] = []

    def spying_connect(
        database: str, *args: object, **kwargs: object
    ) -> sqlite3.Connection:
        captured_calls.append((str(database), bool(kwargs.get("uri", False))))
        return real_connect(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlite3, "connect", spying_connect)
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    gateway.get_book_details(["1"])

    assert captured_calls == [(f"file:{calibre_metadata_db}?mode=ro", True)]


def test_missing_file_raises_library_not_found_error_for_book_details(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.get_book_details(["1"])


def test_non_calibre_sqlite_file_raises_not_a_calibre_library_error_for_book_details(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    gateway = SqliteLibraryGateway(db_path)

    with pytest.raises(NotACalibreLibraryError):
        gateway.get_book_details(["1"])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: FAIL with `AttributeError: 'SqliteLibraryGateway' object has no attribute
'get_book_details'`

- [ ] **Step 4: Add the Protocol method and the SQLite implementation**

`src/book0_core/gateway.py` becomes:

```python
from typing import Protocol

from book0_core.models import Author, Book, BookDetailsResult, Publisher


class LibraryGateway(Protocol):
    def list_books(self) -> list[Book]: ...
    def list_authors(self) -> list[Author]: ...
    def list_publishers(self) -> list[Publisher]: ...
    def get_book_details(self, ids: list[str]) -> BookDetailsResult: ...
```

In `src/book0_core/sqlite_gateway.py`, change the model import and add the query constant
after `_LIST_PUBLISHERS_QUERY`:

```python
from book0_core.models import Author, Book, BookDetails, BookDetailsResult, Publisher, Series, SeriesItem
```

```python
_GET_BOOK_DETAILS_QUERY_TEMPLATE = """
    SELECT
        books.id,
        books.title,
        books.pubdate,
        books.series_index,
        (
            SELECT GROUP_CONCAT(authors.name, ', ')
            FROM books_authors_link
            JOIN authors ON authors.id = books_authors_link.author
            WHERE books_authors_link.book = books.id
        ) AS authors,
        (
            SELECT GROUP_CONCAT(tags.name, ', ')
            FROM books_tags_link
            JOIN tags ON tags.id = books_tags_link.tag
            WHERE books_tags_link.book = books.id
        ) AS tags,
        publishers.id,
        publishers.name,
        series.id,
        series.name
    FROM books
    LEFT JOIN books_publishers_link ON books_publishers_link.book = books.id
    LEFT JOIN publishers ON publishers.id = books_publishers_link.publisher
    LEFT JOIN books_series_link ON books_series_link.book = books.id
    LEFT JOIN series ON series.id = books_series_link.series
    WHERE books.id IN ({placeholders})
"""
```

(Authors and tags are aggregated via correlated subqueries, not a direct `LEFT JOIN`, because
joining two many-to-many link tables into the same query would fan out rows — a book with 2
authors and 3 tags would produce 6 joined rows before any `GROUP_CONCAT`. A scalar subquery per
book avoids that. Publisher and series stay plain `LEFT JOIN`s because this project already
treats them as at-most-one-per-book, same as `list_publishers`.)

Add the method to `SqliteLibraryGateway`, after `list_publishers`:

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

(`books.id IN (?, ?, ...)` bound with `str` parameters against an `INTEGER`-affinity column
relies on SQLite's own type-affinity coercion: a numeric-looking `str` like `"1"` is converted
to `1` for the comparison and matches; a non-numeric `str` like `"abc"` cannot be converted and
is compared as text against an integer column, which never matches — so a non-numeric id
naturally lands in `missing_ids` with no special-casing needed in Python. An empty `ids` list
produces `WHERE books.id IN ()`, which is valid SQLite and always false, matching this plan's
"no early return" constraint.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py tests/unit/test_models.py -v`
Expected: PASS (42 tests: 17 from Task 1 + 25 in `test_sqlite_gateway.py` (16 existing + 9 new))

- [ ] **Step 6: Commit**

```bash
git add src/book0_core/gateway.py src/book0_core/sqlite_gateway.py tests/conftest.py \
        tests/integration/test_sqlite_gateway.py
git commit -m "feat: add get_book_details to LibraryGateway and SqliteLibraryGateway"
```

---

### Task 3: `book0_api` schemas for book details

**Files:**
- Modify: `src/book0_api/schemas.py`
- Modify: `tests/unit/test_book0_api_schemas.py`

**Interfaces:**
- Consumes: `Series`, `SeriesItem`, `BookDetails`, `BookDetailsResult` from Task 1, `Publisher`
  from before this plan.
- Produces: `book0_api.schemas.SeriesOut`, `SeriesItemOut`, `BookDetailsOut`,
  `BookDetailsResultOut` (each with a `from_*` classmethod, same pattern as `AuthorOut`), and
  `BookIdsIn(ids: list[str])` — the request body model. Used by Task 4's route.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_book0_api_schemas.py`, changing the import lines:

```python
from book0_api.schemas import (
    AuthorOut,
    BookDetailsOut,
    BookDetailsResultOut,
    BookOut,
    PublisherOut,
    SeriesItemOut,
    SeriesOut,
)
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    Publisher,
    Series,
    SeriesItem,
)
```

```python
def test_from_series_converts_series_to_series_out():
    series = Series(id="1", name="Dune Chronicles")

    series_out = SeriesOut.from_series(series)

    assert series_out == SeriesOut(id="1", name="Dune Chronicles")


def test_from_series_item_converts_series_item_to_series_item_out():
    series_item = SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0")

    series_item_out = SeriesItemOut.from_series_item(series_item)

    assert series_item_out == SeriesItemOut(
        series=SeriesOut(id="1", name="Dune Chronicles"), index="1.0"
    )


def test_from_book_details_converts_book_details_with_everything_populated():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate="1965-08-01",
        authors=("Frank Herbert",),
        tags=("sci-fi", "classic"),
        publisher=Publisher(id="1", name="Ace Books"),
        series=SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0"),
    )

    book_details_out = BookDetailsOut.from_book_details(book_details)

    assert book_details_out == BookDetailsOut(
        id="1",
        title="Dune",
        pubdate="1965-08-01",
        authors=["Frank Herbert"],
        tags=["sci-fi", "classic"],
        publisher=PublisherOut(id="1", name="Ace Books"),
        series=SeriesItemOut(
            series=SeriesOut(id="1", name="Dune Chronicles"), index="1.0"
        ),
    )


def test_from_book_details_converts_book_details_with_no_publisher_or_series():
    book_details = BookDetails(
        id="2",
        title="The Hobbit",
        pubdate=None,
        authors=("J.R.R. Tolkien",),
        tags=(),
        publisher=None,
        series=None,
    )

    book_details_out = BookDetailsOut.from_book_details(book_details)

    assert book_details_out.publisher is None
    assert book_details_out.series is None
    assert book_details_out.tags == []


def test_from_book_details_result_converts_books_and_missing_ids():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )
    result = BookDetailsResult(books=(book_details,), missing_ids=("99",))

    result_out = BookDetailsResultOut.from_book_details_result(result)

    assert result_out == BookDetailsResultOut(
        books=[BookDetailsOut.from_book_details(book_details)],
        missing_ids=["99"],
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'SeriesOut'`

- [ ] **Step 3: Implement the schemas**

`src/book0_api/schemas.py` becomes:

```python
from pydantic import BaseModel

from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    Publisher,
    Series,
    SeriesItem,
)


class AuthorOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_author(cls, author: Author) -> "AuthorOut":
        return cls(id=author.id, name=author.name)


class PublisherOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_publisher(cls, publisher: Publisher) -> "PublisherOut":
        return cls(id=publisher.id, name=publisher.name)


class SeriesOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_series(cls, series: Series) -> "SeriesOut":
        return cls(id=series.id, name=series.name)


class SeriesItemOut(BaseModel):
    series: SeriesOut
    index: str | None

    @classmethod
    def from_series_item(cls, series_item: SeriesItem) -> "SeriesItemOut":
        return cls(
            series=SeriesOut.from_series(series_item.series),
            index=series_item.index,
        )


class BookOut(BaseModel):
    id: str
    title: str
    authors: list[str]
    pubdate: str | None

    @classmethod
    def from_book(cls, book: Book) -> "BookOut":
        return cls(
            id=book.id,
            title=book.title,
            authors=list(book.authors),
            pubdate=book.pubdate,
        )


class BookDetailsOut(BaseModel):
    id: str
    title: str
    pubdate: str | None
    authors: list[str]
    tags: list[str]
    publisher: PublisherOut | None
    series: SeriesItemOut | None

    @classmethod
    def from_book_details(cls, book_details: BookDetails) -> "BookDetailsOut":
        return cls(
            id=book_details.id,
            title=book_details.title,
            pubdate=book_details.pubdate,
            authors=list(book_details.authors),
            tags=list(book_details.tags),
            publisher=(
                PublisherOut.from_publisher(book_details.publisher)
                if book_details.publisher is not None
                else None
            ),
            series=(
                SeriesItemOut.from_series_item(book_details.series)
                if book_details.series is not None
                else None
            ),
        )


class BookDetailsResultOut(BaseModel):
    books: list[BookDetailsOut]
    missing_ids: list[str]

    @classmethod
    def from_book_details_result(
        cls, result: BookDetailsResult
    ) -> "BookDetailsResultOut":
        return cls(
            books=[BookDetailsOut.from_book_details(book) for book in result.books],
            missing_ids=list(result.missing_ids),
        )


class BookIdsIn(BaseModel):
    ids: list[str]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: PASS (9 tests: 4 existing + 5 new)

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/schemas.py tests/unit/test_book0_api_schemas.py
git commit -m "feat: add SeriesOut, SeriesItemOut, BookDetailsOut, BookDetailsResultOut, BookIdsIn schemas"
```

---

### Task 4: `POST /libraries/{tag}/books/detail` route

**Files:**
- Modify: `src/book0_api/main.py`
- Test: `tests/e2e/test_book0_api_main.py`

**Interfaces:**
- Consumes: `BookIdsIn`, `BookDetailsResultOut` from Task 3;
  `SqliteLibraryGateway.get_book_details` from Task 2.
- Produces: `POST /libraries/{tag}/books/detail` route on the app returned by `create_app`,
  used by Task 5's `HttpLibraryGateway.get_book_details`.

- [ ] **Step 1: Write the failing tests**

Add the new fixtures to the existing import line in `tests/e2e/test_book0_api_main.py`:

```python
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    DUNE_DETAILS,
)
```

Append:

```python
def test_get_book_details_returns_expected_details_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/fiction/books/detail", json={"ids": ["1"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["missing_ids"] == []
    assert len(body["books"]) == 1
    assert body["books"][0] == {
        "id": "1",
        "title": "Dune",
        "pubdate": "1965-08-01",
        "authors": ["Frank Herbert"],
        "tags": ["sci-fi", "classic"],
        "publisher": {"id": "1", "name": "Ace Books"},
        "series": {
            "series": {"id": "1", "name": "Dune Chronicles"},
            "index": "1.0",
        },
    }
    assert DUNE_DETAILS.title == "Dune"  # sanity check the fixture agrees


def test_get_book_details_reports_missing_ids_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/fiction/books/detail", json={"ids": ["1", "999"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["missing_ids"] == ["999"]
    assert len(body["books"]) == 1


def test_get_book_details_returns_all_requested_ids_as_missing_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.post(
        "/libraries/does-not-exist/books/detail", json={"ids": ["1", "2"]}
    )

    assert response.status_code == 200
    assert response.json() == {"books": [], "missing_ids": ["1", "2"]}


def test_get_book_details_returns_404_when_configured_path_is_missing(
    tmp_path: Path,
):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.post(
        "/libraries/fiction/books/detail", json={"ids": ["1"]}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_get_book_details_returns_500_when_configured_path_is_not_a_calibre_library(
    tmp_path: Path,
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    app = create_app({"fiction": db_path})
    client = TestClient(app)

    response = client.post(
        "/libraries/fiction/books/detail", json={"ids": ["1"]}
    )

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: FAIL with 404 "Not Found" (route doesn't exist) on the new tests

- [ ] **Step 3: Implement the route**

In `src/book0_api/main.py`, change the schema import and add the route after `list_publishers`:

```python
from book0_api.schemas import (
    AuthorOut,
    BookDetailsResultOut,
    BookIdsIn,
    BookOut,
    PublisherOut,
)
```

```python
    @app.post("/libraries/{tag}/books/detail", response_model=None)
    def get_book_details(
        tag: str, body: BookIdsIn
    ) -> BookDetailsResultOut | JSONResponse:
        db_path = libraries.get(tag)
        if db_path is None:
            return BookDetailsResultOut(books=[], missing_ids=body.ids)

        gateway = SqliteLibraryGateway(db_path)
        try:
            result = gateway.get_book_details(body.ids)
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

        return BookDetailsResultOut.from_book_details_result(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/main.py tests/e2e/test_book0_api_main.py
git commit -m "feat: add POST /libraries/{tag}/books/detail route"
```

---

### Task 5: `HttpLibraryGateway.get_book_details`

**Files:**
- Modify: `src/book0_cli_remote/http_gateway.py`
- Test: `tests/integration/test_http_gateway.py`

**Interfaces:**
- Consumes: `Series`, `SeriesItem`, `BookDetails`, `BookDetailsResult` from Task 1, the route
  from Task 4.
- Produces: `HttpLibraryGateway.get_book_details(ids: list[str]) -> BookDetailsResult`, used by
  Task 8.

- [ ] **Step 1: Write the failing tests**

Add the new fixtures to the existing import line in `tests/integration/test_http_gateway.py`:

```python
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    DUNE_DETAILS,
    GOOD_OMENS_DETAILS,
    HOBBIT_DETAILS,
)
```

Append:

```python
def test_get_book_details_returns_expected_details_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.get_book_details(["3", "1", "2"])

    assert set(result.books) == {DUNE_DETAILS, HOBBIT_DETAILS, GOOD_OMENS_DETAILS}
    assert result.missing_ids == ()


def test_get_book_details_reports_missing_ids_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.get_book_details(["1", "999"])

    assert result.books == (DUNE_DETAILS,)
    assert result.missing_ids == ("999",)


def test_get_book_details_treats_unknown_tag_as_all_missing(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    result = gateway.get_book_details(["1", "2"])

    assert result.books == ()
    assert set(result.missing_ids) == {"1", "2"}


def test_get_book_details_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.get_book_details(["1"])


def test_get_book_details_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.get_book_details(["1"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: FAIL with `AttributeError: 'HttpLibraryGateway' object has no attribute
'get_book_details'`

- [ ] **Step 3: Implement `get_book_details`**

In `src/book0_cli_remote/http_gateway.py`, change the model import and add a module-level
helper plus the method after `list_publishers`:

```python
from book0_core.models import Author, Book, BookDetails, BookDetailsResult, Publisher, Series, SeriesItem
```

```python
def _book_details_from_json(row: dict[str, object]) -> BookDetails:
    publisher_row = row["publisher"]
    publisher = (
        Publisher(id=publisher_row["id"], name=publisher_row["name"])  # type: ignore[index]
        if publisher_row is not None
        else None
    )
    series_row = row["series"]
    series = (
        SeriesItem(
            series=Series(
                id=series_row["series"]["id"],  # type: ignore[index]
                name=series_row["series"]["name"],  # type: ignore[index]
            ),
            index=series_row["index"],  # type: ignore[index]
        )
        if series_row is not None
        else None
    )
    return BookDetails(
        id=row["id"],  # type: ignore[arg-type]
        title=row["title"],  # type: ignore[arg-type]
        pubdate=row["pubdate"],  # type: ignore[arg-type]
        authors=tuple(row["authors"]),  # type: ignore[arg-type]
        tags=tuple(row["tags"]),  # type: ignore[arg-type]
        publisher=publisher,
        series=series,
    )
```

```python
    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        response = self._client.post(
            f"/libraries/{self._tag}/books/detail", json={"ids": ids}
        )

        if response.status_code in (404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        body = response.json()
        return BookDetailsResult(
            books=tuple(_book_details_from_json(row) for row in body["books"]),
            missing_ids=tuple(body["missing_ids"]),
        )
```

(The `# type: ignore[index]`/`# type: ignore[arg-type]` comments mirror this file's existing
style of building typed domain objects from an untyped `response.json()` dict — the same
pattern `list_books`/`list_authors`/`list_publishers` already use implicitly by relying on
`Any` from `response.json()`; `_book_details_from_json` just has enough nested structure that
mypy's inference needs the explicit nudge in a few spots.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/http_gateway.py tests/integration/test_http_gateway.py
git commit -m "feat: add get_book_details to HttpLibraryGateway"
```

---

### Task 6: `render_book_details_table`

**Files:**
- Modify: `src/book0_presentation/tables.py`
- Test: `tests/unit/test_tables.py`

**Interfaces:**
- Consumes: `BookDetails` from Task 1.
- Produces: `render_book_details_table(books: list[BookDetails]) -> str`, used by Tasks 7-8.
  Same shape as `render_book_table`/`render_author_table`/`render_publisher_table` — no `ids`
  parameter, no knowledge of missing ids.

- [ ] **Step 1: Write the failing tests**

Change the import lines in `tests/unit/test_tables.py` and append:

```python
from book0_core.models import Author, Book, BookDetails, Publisher, Series, SeriesItem
from book0_presentation.tables import (
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)
```

```python
def test_render_book_details_table_aligns_columns_with_headers():
    books = [
        BookDetails(
            id="1",
            title="Dune",
            pubdate="1965-08-01",
            authors=("Frank Herbert",),
            tags=("sci-fi", "classic"),
            publisher=Publisher(id="1", name="Ace Books"),
            series=SeriesItem(
                series=Series(id="1", name="Dune Chronicles"), index="1.0"
            ),
        ),
        BookDetails(
            id="2",
            title="The Hobbit",
            pubdate=None,
            authors=("J.R.R. Tolkien",),
            tags=(),
            publisher=None,
            series=None,
        ),
    ]

    output = render_book_details_table(books)
    # Compare with runs of whitespace collapsed to a single space, so this
    # test checks column content/order, not exact padding widths (which
    # _align_rows already has dedicated coverage for via the other
    # render_*_table tests).
    lines = [" ".join(line.split()) for line in output.splitlines()]

    assert lines[0] == "ID Title Authors Publisher Series Series Index Tags Pub Date"
    assert lines[1] == (
        "1 Dune Frank Herbert Ace Books Dune Chronicles 1.0 "
        "sci-fi & classic 1965-08-01"
    )
    assert lines[2] == "2 The Hobbit J.R.R. Tolkien"


def test_render_book_details_table_joins_multiple_authors_and_tags_with_ampersand():
    books = [
        BookDetails(
            id="3",
            title="Good Omens",
            pubdate="1990-05-01",
            authors=("Neil Gaiman", "Terry Pratchett"),
            tags=("fantasy", "humor"),
            publisher=Publisher(id="2", name="Gollancz"),
            series=None,
        ),
    ]

    output = render_book_details_table(books)

    assert "Neil Gaiman & Terry Pratchett" in output
    assert "fantasy & humor" in output


def test_render_book_details_table_reports_empty_list():
    assert render_book_details_table([]) == "No book details found."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_book_details_table'`

- [ ] **Step 3: Implement `render_book_details_table`**

In `src/book0_presentation/tables.py`, change the model import, add a headers constant and a
list-separator constant, and add the function after `render_publisher_table`:

```python
from book0_core.models import Author, Book, BookDetails, Publisher
```

```python
_BOOK_DETAILS_HEADERS = (
    "ID",
    "Title",
    "Authors",
    "Publisher",
    "Series",
    "Series Index",
    "Tags",
    "Pub Date",
)
_LIST_SEPARATOR = " & "
```

```python
def render_book_details_table(books: list[BookDetails]) -> str:
    if not books:
        return "No book details found."

    rows: list[tuple[str, ...]] = [
        (
            book.id,
            book.title,
            _LIST_SEPARATOR.join(book.authors),
            book.publisher.name if book.publisher is not None else "",
            book.series.series.name if book.series is not None else "",
            book.series.index or "" if book.series is not None else "",
            _LIST_SEPARATOR.join(book.tags),
            _format_pubdate(book.pubdate),
        )
        for book in books
    ]
    return _align_rows(_BOOK_DETAILS_HEADERS, rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: PASS (11 tests: 8 existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/book0_presentation/tables.py tests/unit/test_tables.py
git commit -m "feat: add render_book_details_table"
```

---

### Task 7: `books-detail` subcommand on `book0`

**Files:**
- Modify: `src/book0_cli/main.py`
- Test: `tests/integration/test_cli_main.py`

**Interfaces:**
- Consumes: `render_book_details_table` from Task 6,
  `SqliteLibraryGateway.get_book_details` from Task 2.
- Produces: `book0 books-detail --ids ID,ID,... [--tag TAG]` CLI behavior. Owns reordering
  `result.books` to match the requested `--ids` order, and reporting `result.missing_ids` —
  neither the Gateway nor `render_book_details_table` does either.

- [ ] **Step 1: Write the failing tests**

Add `DUNE_DETAILS`/`GOOD_OMENS_DETAILS`/`HOBBIT_DETAILS` to the existing import line, and
`render_book_details_table` to the renderer import, in `tests/integration/test_cli_main.py`:

```python
from book0_presentation.tables import (
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    DUNE_DETAILS,
    GOOD_OMENS_DETAILS,
    HOBBIT_DETAILS,
)
```

Append:

```python
def test_run_prints_book_details_in_the_requested_id_order(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["books-detail", "--ids", "3,1", "--tag", "fiction"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_book_details_table([GOOD_OMENS_DETAILS, DUNE_DETAILS]) + "\n"
    )


def test_run_reports_missing_ids_for_book_details(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["books-detail", "--ids", "1,999", "--tag", "fiction"])

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert captured == render_book_details_table([DUNE_DETAILS]) + "\nMissing ids: 999\n"


def test_run_prints_no_book_details_found_when_all_ids_are_unknown(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["books-detail", "--ids", "999", "--tag", "fiction"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out == "No book details found.\nMissing ids: 999\n"
    )


def test_run_treats_empty_ids_as_an_empty_request(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["books-detail", "--ids", "", "--tag", "fiction"])

    assert exit_code == 0
    assert capsys.readouterr().out == "No book details found.\n"


def test_run_reports_usage_error_when_ids_is_omitted_entirely(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["books-detail"])

    assert exc_info.value.code == 2


def test_run_help_mentions_the_books_detail_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "books-detail" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: FAIL — `run(["books-detail", ...])` exits 2 (argparse: invalid choice), and
`"books-detail"` is absent from `--help` output

- [ ] **Step 3: Implement the `books-detail` subcommand**

In `src/book0_cli/main.py`:

```python
from book0_presentation.tables import (
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)

_SUBCOMMANDS = ("books", "authors", "publishers", "books-detail")
```

```python
    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--tag", help=_TAG_HELP)

    books_detail_parser = subparsers.add_parser("books-detail")
    books_detail_parser.add_argument(
        "--ids", required=True, help="comma-separated list of book ids"
    )
    books_detail_parser.add_argument("--tag", help=_TAG_HELP)

    return parser
```

```python
    try:
        if args.command == "authors":
            print(render_author_table(gateway.list_authors()))
        elif args.command == "publishers":
            print(render_publisher_table(gateway.list_publishers()))
        elif args.command == "books-detail":
            ids = args.ids.split(",") if args.ids else []
            result = gateway.get_book_details(ids)
            books_by_id = {book.id: book for book in result.books}
            ordered_books = [
                books_by_id[requested_id]
                for requested_id in ids
                if requested_id in books_by_id
            ]
            print(render_book_details_table(ordered_books))
            if result.missing_ids:
                print(f"Missing ids: {', '.join(result.missing_ids)}")
        else:
            print(render_book_table(gateway.list_books()))
    except (LibraryNotFoundError, NotACalibreLibraryError) as error:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli/main.py tests/integration/test_cli_main.py
git commit -m "feat: add books-detail subcommand to book0"
```

---

### Task 8: `books-detail` subcommand on `book0-remote`

**Files:**
- Modify: `src/book0_cli_remote/main.py`
- Test: `tests/integration/test_cli_remote_main.py`

**Interfaces:**
- Consumes: `render_book_details_table` from Task 6, `HttpLibraryGateway.get_book_details` from
  Task 5.
- Produces: `book0-remote books-detail --ids ID,ID,... --server URL --tag TAG` CLI behavior,
  same reordering/missing-ids-reporting responsibility as Task 7.

- [ ] **Step 1: Write the failing tests**

Add the new fixtures and renderer to the existing import lines in
`tests/integration/test_cli_remote_main.py`:

```python
from book0_presentation.tables import (
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    DUNE_DETAILS,
    GOOD_OMENS_DETAILS,
)
```

Append:

```python
def test_run_prints_book_details_in_the_requested_id_order(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "3,1",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_book_details_table([GOOD_OMENS_DETAILS, DUNE_DETAILS]) + "\n"
    )


def test_run_reports_missing_ids_for_book_details(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1,999",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert captured == render_book_details_table([DUNE_DETAILS]) + "\nMissing ids: 999\n"


def test_run_reports_all_ids_missing_for_an_unconfigured_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1,2",
            "--server",
            "unused",
            "--tag",
            "does-not-exist",
        ],
        client=client,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert captured == "No book details found.\nMissing ids: 1, 2\n"


def test_run_reports_usage_error_when_ids_is_omitted_entirely(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["books-detail", "--server", "unused", "--tag", "fiction"])

    assert exc_info.value.code == 2


def test_run_help_mentions_the_books_detail_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "books-detail" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: FAIL — `run(["books-detail", ...])` exits 2 (argparse: invalid choice), and
`"books-detail"` is absent from `--help` output

- [ ] **Step 3: Implement the `books-detail` subcommand**

In `src/book0_cli_remote/main.py`:

```python
from book0_presentation.tables import (
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)

_SUBCOMMANDS = ("books", "authors", "publishers", "books-detail")
```

```python
    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--server", required=True)
    publishers_parser.add_argument("--tag", required=True)

    books_detail_parser = subparsers.add_parser("books-detail")
    books_detail_parser.add_argument(
        "--ids", required=True, help="comma-separated list of book ids"
    )
    books_detail_parser.add_argument("--server", required=True)
    books_detail_parser.add_argument("--tag", required=True)

    return parser
```

```python
            if args.command == "authors":
                print(render_author_table(gateway.list_authors()))
            elif args.command == "publishers":
                print(render_publisher_table(gateway.list_publishers()))
            elif args.command == "books-detail":
                ids = args.ids.split(",") if args.ids else []
                result = gateway.get_book_details(ids)
                books_by_id = {book.id: book for book in result.books}
                ordered_books = [
                    books_by_id[requested_id]
                    for requested_id in ids
                    if requested_id in books_by_id
                ]
                print(render_book_details_table(ordered_books))
                if result.missing_ids:
                    print(f"Missing ids: {', '.join(result.missing_ids)}")
            else:
                print(render_book_table(gateway.list_books()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/main.py tests/integration/test_cli_remote_main.py
git commit -m "feat: add books-detail subcommand to book0-remote"
```

---

### Task 9: Update `architecture.md` and `README.md`

**Files:**
- Modify: `.claude/rules/architecture.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by another task — this is the last task.

- [ ] **Step 1: Update `.claude/rules/architecture.md`**

Apply these exact replacements:

```
-│   ├── models.py               # Book: frozen dataclass (id, title, authors, pubdate);
-│                                  # Author: frozen dataclass (id, name); Publisher: frozen
-│                                  # dataclass (id, name)
+│   ├── models.py               # Book: frozen dataclass (id, title, authors, pubdate);
+│                                  # Author/Publisher/Series: frozen dataclass (id, name);
+│                                  # SeriesItem (series, index); BookDetails (id, title,
+│                                  # pubdate, authors, tags, publisher, series);
+│                                  # BookDetailsResult (books, missing_ids)
```

```
-│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book],
-│                                    # list_authors() -> list[Author],
-│                                    # list_publishers() -> list[Publisher]
+│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book],
+│                                    # list_authors() -> list[Author],
+│                                    # list_publishers() -> list[Publisher],
+│                                    # get_book_details(ids) -> BookDetailsResult
```

```
-│   └── tables.py                  # render_book_table(list[Book]) -> str, render_author_table(list[Author]) -> str,
-│                                    # render_publisher_table(list[Publisher]) -> str, aligned plain-text tables
+│   └── tables.py                  # render_book_table(list[Book]) -> str, render_author_table(list[Author]) -> str,
+│                                    # render_publisher_table(list[Publisher]) -> str,
+│                                    # render_book_details_table(list[BookDetails]) -> str,
+│                                    # aligned plain-text tables
```

```
-├── book0_cli/
-│   ├── config.py                  # default_library_path(), xdg_config_path(), find_config_file()
-│   └── main.py                    # `book0` entry point: `books`/`authors`/`publishers`
-│                                    # subcommands (books is the default), --tag TAG (optional)
-│                                    # -> SqliteLibraryGateway
+├── book0_cli/
+│   ├── config.py                  # default_library_path(), xdg_config_path(), find_config_file()
+│   └── main.py                    # `book0` entry point: `books`/`authors`/`publishers`/
+│                                    # `books-detail` subcommands (books is the default), --tag
+│                                    # TAG (optional), --ids (books-detail only, required)
+│                                    # -> SqliteLibraryGateway
```

```
-│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate;
-│                                    # AuthorOut: id, name; PublisherOut: id, name
+│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate;
+│                                    # AuthorOut/PublisherOut/SeriesOut: id, name;
+│                                    # SeriesItemOut: series, index; BookDetailsOut: id, title,
+│                                    # pubdate, authors, tags, publisher, series;
+│                                    # BookDetailsResultOut: books, missing_ids; BookIdsIn: ids
```

```
-└── book0_cli_remote/
-    ├── main.py                    # `book0-remote` entry point: `books`/`authors`/`publishers`
-    │                                subcommands (books is the default), --server URL --tag TAG
-    │                                -> HttpLibraryGateway
+└── book0_cli_remote/
+    ├── main.py                    # `book0-remote` entry point: `books`/`authors`/`publishers`/
+    │                                `books-detail` subcommands (books is the default),
+    │                                --server URL --tag TAG (both required), --ids
+    │                                (books-detail only, required) -> HttpLibraryGateway
```

```
-`tests/conftest.py` holds the shared Calibre-shaped SQLite fixture (`calibre_metadata_db`) and
-its expected `Book` list (`CALIBRE_LIBRARY_BOOKS`), `Author` list (`CALIBRE_LIBRARY_AUTHORS`),
-and `Publisher` list (`CALIBRE_LIBRARY_PUBLISHERS`) - `book0_core`, `book0_api`, and both
-CLIs' tests all build on it rather than each defining their own fixture DB.
+`tests/conftest.py` holds the shared Calibre-shaped SQLite fixture (`calibre_metadata_db`) and
+its expected `Book` list (`CALIBRE_LIBRARY_BOOKS`), `Author` list (`CALIBRE_LIBRARY_AUTHORS`),
+`Publisher` list (`CALIBRE_LIBRARY_PUBLISHERS`), and three named `BookDetails` fixtures
+(`DUNE_DETAILS`, `HOBBIT_DETAILS`, `GOOD_OMENS_DETAILS`) - `book0_core`, `book0_api`, and both
+CLIs' tests all build on it rather than each defining their own fixture DB.
```

```
-- `book0_presentation` depends only on `book0_core` (needs `Book`/`Author`/`Publisher` for
-  `render_book_table`'s/`render_author_table`'s/`render_publisher_table`'s signatures). No
-  CLI, no web framework.
+- `book0_presentation` depends only on `book0_core` (needs `Book`/`Author`/`Publisher`/
+  `BookDetails` for `render_book_table`'s/`render_author_table`'s/`render_publisher_table`'s/
+  `render_book_details_table`'s signatures). No CLI, no web framework.
```

- [ ] **Step 2: Update `README.md`**

Apply these exact replacements:

```
-Lists the books, authors, or publishers in a [Calibre](https://calibre-ebook.com/) library. Two ways to run it:
+Lists the books, authors, or publishers in a [Calibre](https://calibre-ebook.com/) library,
+and fetches richer joined details (publisher, series, tags) for a specific set of book ids.
+Two ways to run it:
```

```
-Calibre's own default library. Choose `books`, `authors`, or `publishers` - `books` is the
-default:
+Calibre's own default library. Choose `books`, `authors`, `publishers`, or `books-detail` -
+`books` is the default:

 ```sh
 uv run book0 books --tag <tag>      # or just `uv run book0 --tag <tag>` - `books` is the default
 uv run book0 authors --tag <tag>
 uv run book0 publishers --tag <tag>
+uv run book0 books-detail --ids 1,2,3 --tag <tag>
 # or, with no --tag:
 uv run book0                        # reads Calibre's default library (books)
 ```
```

Immediately after the existing publishers sample block, add:

```
+```
+ID  Title  Authors        Publisher  Series           Series Index  Tags              Pub Date
+1   Dune   Frank Herbert  Ace Books  Dune Chronicles  1.0           sci-fi & classic  1965-08-01
+```
+
+`books-detail` never errors on an unknown id - it prints a `Missing ids: ...` line after the
+table (or on its own, if none of the requested ids were found) instead.
+
```

```
 uv run book0-remote books --server http://127.0.0.1:8000 --tag fiction
 # or just `uv run book0-remote --server ... --tag fiction` - `books` is the default
 uv run book0-remote authors --server http://127.0.0.1:8000 --tag fiction
 uv run book0-remote publishers --server http://127.0.0.1:8000 --tag fiction
+uv run book0-remote books-detail --ids 1,2,3 --server http://127.0.0.1:8000 --tag fiction
```

- [ ] **Step 3: Verify the full suite, lint, and type-check still pass**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all pass, no new warnings

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/architecture.md README.md
git commit -m "docs: document books-detail subcommand and get_book_details in architecture.md and README"
```

---

## Out of scope (see design doc)

- ISBN (legacy `books.isbn` column vs. `identifiers` table not yet decided).
- Any change to `Book`/`BookOut` (no `publisher`/`series`/`tags` field added there).
- Id-scoping-by-library-tag.
- A shared universe of "series inside series."
- Series/Tags/Language as their own standalone listings — separate future features.
