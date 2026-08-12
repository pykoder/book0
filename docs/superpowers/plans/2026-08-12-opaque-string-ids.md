# Opaque String Ids Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `Book.id`, `Author.id`, and `Publisher.id` from `int` to `str` across the
whole codebase, so `book0_core` stops leaking Calibre's `INTEGER PRIMARY KEY` as an
implementation detail into the domain model.

**Architecture:** `SqliteLibraryGateway` keeps its SQL untouched and wraps each row's id as
`str(row[0])` when building a `Book`/`Author`/`Publisher`. `book0_api`'s schemas
(`BookOut`/`AuthorOut`/`PublisherOut`) change their `id` field to `str`, which changes the
JSON wire shape from a number to a string — an accepted breaking change, since
`book0-remote` is the only consumer and gets updated in the same pass.
`HttpLibraryGateway` needs **no code change**: it already builds domain objects straight from
parsed JSON with no cast (`Book(id=row["id"], ...)`), so a JSON string flows through exactly
like a JSON number did. `book0_presentation/tables.py`'s `str(book.id)`-style casts become
redundant once `id` is already a `str` and are simplified to `book.id` directly.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, FastAPI + Pydantic, `httpx`, `pytest`, `uv`.

## Global Constraints

- Every command goes through `uv run <tool>` — never a bare `python`/`pytest`/`ruff`/`mypy`.
- This is a pure type/representation change — no new behavior, no new fields, no SQL changes,
  no change to `book0_config`, tag resolution, or either CLI's `--tag` handling.
- No zero-padding or other formatting when stringifying an id — plain `str(row[0])`.
- Every existing test must still pass, with only its id literals adjusted from int to the
  equivalent string. No test is deleted or skipped.
- Design doc: `docs/superpowers/specs/2026-08-12-opaque-string-ids-design.md`.

---

### Task 1: `Book`/`Author`/`Publisher.id` become `str`

**Files:**
- Modify: `src/book0_core/models.py`
- Modify: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `Book.id: str`, `Author.id: str`, `Publisher.id: str` — every later task in this
  plan and every existing caller depends on this new type.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_models.py` becomes:

```python
import pytest

from book0_core.models import Author, Book, Publisher


def test_book_holds_id_title_authors_and_pubdate():
    book = Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01")

    assert book.id == "1"
    assert book.title == "Dune"
    assert book.authors == ("Frank Herbert",)
    assert book.pubdate == "1965-08-01"


def test_book_accepts_none_pubdate():
    book = Book(id="2", title="Unknown", authors=("Someone",), pubdate=None)

    assert book.pubdate is None


def test_book_is_frozen():
    book = Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate=None)

    with pytest.raises(AttributeError):
        book.title = "Other"


def test_author_holds_id_and_name():
    author = Author(id="1", name="Frank Herbert")

    assert author.id == "1"
    assert author.name == "Frank Herbert"


def test_author_is_frozen():
    author = Author(id="1", name="Frank Herbert")

    with pytest.raises(AttributeError):
        author.name = "Other"


def test_publisher_holds_id_and_name():
    publisher = Publisher(id="1", name="Ace Books")

    assert publisher.id == "1"
    assert publisher.name == "Ace Books"


def test_publisher_is_frozen():
    publisher = Publisher(id="1", name="Ace Books")

    with pytest.raises(AttributeError):
        publisher.name = "Other"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: FAIL — `assert book.id == "1"` fails because `book.id` is still `1` (int)

- [ ] **Step 3: Change the domain model**

`src/book0_core/models.py` becomes:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    id: str
    title: str
    authors: tuple[str, ...]
    pubdate: str | None


@dataclass(frozen=True)
class Author:
    id: str
    name: str


@dataclass(frozen=True)
class Publisher:
    id: str
    name: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/models.py tests/unit/test_models.py
git commit -m "refactor: change Book/Author/Publisher.id from int to str"
```

---

### Task 2: `SqliteLibraryGateway` stringifies ids, fixture data updates

**Files:**
- Modify: `src/book0_core/sqlite_gateway.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `Book`/`Author`/`Publisher` with `id: str` from Task 1.
- Produces: `SqliteLibraryGateway.list_books/list_authors/list_publishers` returning `id: str`
  objects; `tests.conftest.CALIBRE_LIBRARY_BOOKS/AUTHORS/PUBLISHERS` with string id literals,
  which `tests/integration/test_sqlite_gateway.py` already imports and compares against
  verbatim — no change needed to that test file itself, since it never hardcodes an id
  literal, only compares against these fixtures.

- [ ] **Step 1: Update the fixture data**

In `tests/conftest.py`, change every `id=N` literal in `CALIBRE_LIBRARY_BOOKS`,
`CALIBRE_LIBRARY_AUTHORS`, and `CALIBRE_LIBRARY_PUBLISHERS` to the equivalent string. The
`CREATE TABLE`/`INSERT` statements building `calibre_metadata_db` are untouched — Calibre's
columns stay `INTEGER`, only the Python-side fixture constants change:

```python
CALIBRE_LIBRARY_BOOKS = [
    Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01"),
    Book(
        id="3",
        title="Good Omens",
        authors=("Neil Gaiman", "Terry Pratchett"),
        pubdate="1990-05-01",
    ),
    Book(id="2", title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None),
]

# Authors as inserted into the fixture DB, already in the order list_authors()
# is expected to return them (sorted by name).
CALIBRE_LIBRARY_AUTHORS = [
    Author(id="1", name="Frank Herbert"),
    Author(id="2", name="J.R.R. Tolkien"),
    Author(id="3", name="Neil Gaiman"),
    Author(id="4", name="Terry Pratchett"),
]

# Publishers as inserted into the fixture DB, already in the order
# list_publishers() is expected to return them (sorted by name). The Hobbit
# (book id 2) is deliberately left unlinked - Calibre allows a book with no
# publisher set.
CALIBRE_LIBRARY_PUBLISHERS = [
    Publisher(id="1", name="Ace Books"),
    Publisher(id="2", name="Gollancz"),
]
```

(Keep the existing comments above `CALIBRE_LIBRARY_BOOKS` unchanged — only the constants
shown above have literal edits.)

- [ ] **Step 2: Run the integration suite to verify it fails**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: FAIL — e.g. `test_list_books_returns_books_sorted_by_title_with_authors_and_pubdate`
fails because `SqliteLibraryGateway.list_books()` still returns `id=1` (int) while the fixture
now expects `id="1"` (str)

- [ ] **Step 3: Stringify ids in `SqliteLibraryGateway`**

In `src/book0_core/sqlite_gateway.py`, change the three id-producing lines (SQL text is
unchanged):

```python
        return [
            Book(
                id=str(row[0]),
                title=row[1],
                authors=tuple(row[2].split(", ")) if row[2] else (),
                pubdate=self._normalize_pubdate(row[3]),
            )
            for row in rows
        ]
```

```python
        return [Author(id=str(row[0]), name=row[1]) for row in rows]
```

```python
        return [Publisher(id=str(row[0]), name=row[1]) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py tests/unit/test_models.py -v`
Expected: PASS (23 tests: 7 from Task 1 + 16 in `test_sqlite_gateway.py`)

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/sqlite_gateway.py tests/conftest.py
git commit -m "refactor: stringify ids in SqliteLibraryGateway, update fixture data"
```

---

### Task 3: `book0_api` schemas change `id` to `str`

**Files:**
- Modify: `src/book0_api/schemas.py`
- Modify: `tests/unit/test_book0_api_schemas.py`

**Interfaces:**
- Consumes: `Book`/`Author`/`Publisher` with `id: str` from Task 1.
- Produces: `BookOut`/`AuthorOut`/`PublisherOut` with `id: str` — the new JSON wire shape
  (`"id": "1"` instead of `"id": 1"`) that `tests/e2e/test_book0_api_main.py` and
  `tests/integration/test_http_gateway.py` already expect without any change to those files,
  since both build their expected JSON from `book.id`/`author.id`/`publisher.id` dynamically
  rather than hardcoding a literal.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_book0_api_schemas.py` becomes:

```python
from book0_api.schemas import AuthorOut, BookOut, PublisherOut
from book0_core.models import Author, Book, Publisher


def test_from_book_converts_authors_tuple_to_list():
    book = Book(
        id="3",
        title="Good Omens",
        authors=("Neil Gaiman", "Terry Pratchett"),
        pubdate="1990-05-01",
    )

    book_out = BookOut.from_book(book)

    assert book_out == BookOut(
        id="3",
        title="Good Omens",
        authors=["Neil Gaiman", "Terry Pratchett"],
        pubdate="1990-05-01",
    )


def test_from_book_keeps_none_pubdate():
    book = Book(id="2", title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None)

    book_out = BookOut.from_book(book)

    assert book_out.pubdate is None


def test_from_author_converts_author_to_author_out():
    author = Author(id="3", name="Neil Gaiman")

    author_out = AuthorOut.from_author(author)

    assert author_out == AuthorOut(id="3", name="Neil Gaiman")


def test_from_publisher_converts_publisher_to_publisher_out():
    publisher = Publisher(id="1", name="Ace Books")

    publisher_out = PublisherOut.from_publisher(publisher)

    assert publisher_out == PublisherOut(id="1", name="Ace Books")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: FAIL — Pydantic coerces `id="3"` against a still-`int` field, or the equality
comparison fails depending on Pydantic's coercion; either way the test fails against the
current `int` schema

- [ ] **Step 3: Change the schemas**

`src/book0_api/schemas.py` becomes:

```python
from pydantic import BaseModel

from book0_core.models import Author, Book, Publisher


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/schemas.py tests/unit/test_book0_api_schemas.py
git commit -m "refactor: change BookOut/AuthorOut/PublisherOut.id from int to str"
```

---

### Task 4: Presentation layer drops the now-redundant `str()` cast

**Files:**
- Modify: `src/book0_presentation/tables.py`
- Modify: `tests/unit/test_tables.py`

**Interfaces:**
- Consumes: `Book`/`Author`/`Publisher` with `id: str` from Task 1.
- Produces: `render_book_table`/`render_author_table`/`render_publisher_table` unchanged in
  output shape (still render the id as plain text) but reading `.id` directly instead of
  `str(.id)`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_tables.py` becomes:

```python
from book0_core.models import Author, Book, Publisher
from book0_presentation.tables import (
    render_author_table,
    render_book_table,
    render_publisher_table,
)


def test_render_book_table_aligns_columns_with_headers():
    books = [
        Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01"),
        Book(
            id="3",
            title="Good Omens",
            authors=("Neil Gaiman", "Terry Pratchett"),
            pubdate="1990-05-01",
        ),
        Book(id="2", title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None),
    ]

    output = render_book_table(books)

    assert output == (
        "ID  Title       Author(s)                     Pub Date\n"
        "1   Dune        Frank Herbert                 1965-08-01\n"
        "3   Good Omens  Neil Gaiman, Terry Pratchett  1990-05-01\n"
        "2   The Hobbit  J.R.R. Tolkien"
    )


def test_render_book_table_reports_empty_library():
    assert render_book_table([]) == "No books found."


def test_render_book_table_shows_date_only_when_pubdate_has_a_time_component():
    books = [
        Book(
            id="1",
            title="Dune",
            authors=("Frank Herbert",),
            pubdate="1965-08-01T23:00:00+00:00",
        ),
    ]

    output = render_book_table(books)

    assert output == (
        "ID  Title  Author(s)      Pub Date\n1   Dune   Frank Herbert  1965-08-01"
    )


def test_render_book_table_shows_empty_pubdate_when_none():
    books = [
        Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate=None),
    ]

    output = render_book_table(books)

    assert output == "ID  Title  Author(s)      Pub Date\n1   Dune   Frank Herbert"


def test_render_author_table_aligns_columns_with_headers():
    authors = [
        Author(id="1", name="Frank Herbert"),
        Author(id="3", name="Neil Gaiman"),
        Author(id="2", name="J.R.R. Tolkien"),
    ]

    output = render_author_table(authors)

    assert output == (
        "ID  Name\n1   Frank Herbert\n3   Neil Gaiman\n2   J.R.R. Tolkien"
    )


def test_render_author_table_reports_empty_library():
    assert render_author_table([]) == "No authors found."


def test_render_publisher_table_aligns_columns_with_headers():
    publishers = [
        Publisher(id="1", name="Ace Books"),
        Publisher(id="2", name="Gollancz"),
    ]

    output = render_publisher_table(publishers)

    assert output == "ID  Name\n1   Ace Books\n2   Gollancz"


def test_render_publisher_table_reports_empty_library():
    assert render_publisher_table([]) == "No publishers found."
```

(Every assertion's expected output text is unchanged from before this plan — only the
`Book`/`Author`/`Publisher` construction literals change from int to str. These tests would
in fact already pass without any production-code change, since `str("1") == "1"`; Step 3
below is about removing dead code, not fixing a failure.)

- [ ] **Step 2: Run tests to verify they still pass as-is**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: PASS (8 tests) — confirms the id-literal change alone doesn't break rendering,
before the cleanup in Step 3

- [ ] **Step 3: Remove the redundant `str()` casts**

In `src/book0_presentation/tables.py`:

```python
def render_book_table(books: list[Book]) -> str:
    if not books:
        return "No books found."

    rows: list[tuple[str, ...]] = [
        (
            book.id,
            book.title,
            ", ".join(book.authors),
            _format_pubdate(book.pubdate),
        )
        for book in books
    ]
    return _align_rows(_BOOK_HEADERS, rows)


def render_author_table(authors: list[Author]) -> str:
    if not authors:
        return "No authors found."

    rows: list[tuple[str, ...]] = [(author.id, author.name) for author in authors]
    return _align_rows(_AUTHOR_HEADERS, rows)


def render_publisher_table(publishers: list[Publisher]) -> str:
    if not publishers:
        return "No publishers found."

    rows: list[tuple[str, ...]] = [
        (publisher.id, publisher.name) for publisher in publishers
    ]
    return _align_rows(_PUBLISHER_HEADERS, rows)
```

(`_format_pubdate` and `_align_rows` are unchanged — only the three `render_*_table`
functions' row-building lines lose their `str(...)` wrapper around the id.)

- [ ] **Step 4: Run tests to verify they still pass**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_presentation/tables.py tests/unit/test_tables.py
git commit -m "refactor: drop redundant str() cast now that ids are already strings"
```

---

### Task 5: Full-suite verification

**Files:**
- None (verification only — no production or test code changes expected in this task)

**Interfaces:**
- Confirms: `tests/integration/test_http_gateway.py`, `tests/integration/test_cli_main.py`,
  `tests/integration/test_cli_remote_main.py`, and `tests/e2e/test_book0_api_main.py` all pass
  unmodified, as the design doc anticipated (none of them hardcode an id literal — they either
  compare against the `conftest.py` fixtures already updated in Task 2, or don't touch ids at
  all).

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — every test in the suite, including the four files listed above with zero
code changes of their own.

If any test in those four files fails, that means an id-literal assertion was missed by this
plan's review — investigate the specific failure, add a step to fix it, and update this
plan's task list accordingly before proceeding. Do not silently patch it without noting the
gap.

- [ ] **Step 2: Lint, format, and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all clean, no new warnings

- [ ] **Step 3: Confirm the design doc's claims held**

Re-read `docs/superpowers/specs/2026-08-12-opaque-string-ids-design.md`'s "HTTP gateway"
section and confirm `git diff` for this whole plan's range shows zero changes to
`src/book0_cli_remote/http_gateway.py` — the design predicted no code change would be needed
there, and Task 5's green suite is the proof.

No commit for this task unless Step 1 or 2 uncovered something to fix — in that case, fix it
under its own commit before finishing.

---

## Out of scope (see design doc)

- No change to Calibre's SQL schema or query text.
- No change to tag resolution, `book0_config`, or either CLI's `--tag` handling.
- No id-scoping-by-library-tag scheme.
- No special convention distinguishing a "Calibre-internal integer id" from the domain's
  opaque string id.
