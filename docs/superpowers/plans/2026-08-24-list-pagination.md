# List Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add paginated `list_books`/`list_authors`/`list_publishers` variants across
`book0_core`, `book0_config`, `book0_api`, `book0_cli_remote`, and both CLIs, so a large
Calibre library can be listed a bounded page at a time instead of dumped whole.

**Architecture:** `LibraryGateway` grows three new methods
(`list_books_page`/`list_authors_page`/`list_publishers_page`) plus `close_pagination`,
alongside the four existing untouched methods. `SqliteLibraryGateway` gets a lazy persistent
connection and a small table of generator-backed pagination sessions keyed by an advisory
`handle`. `HttpLibraryGateway`'s paginated methods are stateless (fresh HTTP call every time,
handle never sent); its *existing* unpaginated methods gain transparent multi-page auto-fetch
so they keep returning the complete list even when a `book0_api` server forces pagination via
`default-page-size`. `book0_api` resolves an effective page size from the request and a
server-side ceiling, returning either today's plain array or a new paginated JSON object
depending on that resolution. Both CLIs gain `--page`/`--page-size` flags with a
flag-then-config resolution, rendering a page-footer line after the table.

**Tech Stack:** Python 3.12, stdlib `sqlite3`/`tomllib`/`uuid`/`time`, FastAPI/Pydantic, httpx,
pytest, managed with `uv`.

**Spec:** `docs/superpowers/specs/2026-08-20-list-pagination-design.md`

## Global Constraints

- `book0_core` never opens a Calibre library for write; connections stay `mode=ro`.
- `book0_api` routes stay plain `def` — no blocking I/O inside `async def`.
- `book0_api` never imports `book0_cli`, `book0_cli_remote`, or `book0_presentation`.
- `book0_cli_remote` never imports `book0_api` or `book0_config`.
- `book0_cli` and `book0_cli_remote` never share a run-loop function — mirror logic in each
  `main.py` separately rather than factoring a shared helper between them.
- No new `book0_core.errors` class for this feature — every edge case (stale handle, `page`/
  `page_size` ≤ 0, unknown tag) degrades gracefully rather than raising.
- Every command goes through `uv run` (`uv run pytest`, `uv run ruff check .`,
  `uv run ruff format .`, `uv run mypy src`) — never a bare binary.
- Type-hint every function signature; no bare `Any`; no mutable default arguments.
- Never disable, comment out, or weaken an existing test to make it pass — update it to match
  the new spec, with a clear reason, if its assertions become stale.
- `get_book_details`/`books-detail` itself is unchanged by this plan (no `--page` on that
  subcommand, no field/route touched by any task below).

**Resolved design gap (confirmed with the user before this plan was written):** the design
doc leaves unspecified what `HttpLibraryGateway.list_books()`/`list_authors()`/
`list_publishers()` — the pre-existing, *unpaginated* methods — do when talking to a
`book0_api` server that forces pagination via `default-page-size`. Both send the same wire
request (no `page`/`page_size` params), so the server cannot tell them apart; a forcing server
returns a paginated JSON object instead of a plain array. Resolution: these methods detect a
paginated-shaped response and transparently walk every remaining page via follow-up requests,
concatenating the results — `list_books()` keeps returning the *complete* list either way, at
the cost of extra round-trips against a forcing server. See Task 10.

---

## Task 1: `book0_core` — `Paged*Result` dataclasses + `LibraryGateway` Protocol methods

**Files:**
- Modify: `src/book0_core/models.py`
- Modify: `src/book0_core/gateway.py`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PagedBooksResult(items: tuple[Book, ...], page: int, page_size: int,
  total_pages: int | None, has_more_than_shown: bool, handle: str | None)`, and
  `PagedAuthorsResult`/`PagedPublishersResult` with the same shape swapping `Book` for
  `Author`/`Publisher`. `LibraryGateway.list_books_page(page: int, page_size: int, handle:
  str | None = None) -> PagedBooksResult` and its `list_authors_page`/`list_publishers_page`/
  `close_pagination(handle: str) -> None` counterparts — every later task's concrete gateway
  method must match these signatures exactly.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_models.py`, after the last `test_book_details_result_*` test:

```python
def test_paged_books_result_holds_items_and_page_metadata():
    result = PagedBooksResult(
        items=(Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate=None),),
        page=1,
        page_size=20,
        total_pages=3,
        has_more_than_shown=False,
        handle="abc123",
    )

    assert result.page == 1
    assert result.page_size == 20
    assert result.total_pages == 3
    assert result.has_more_than_shown is False
    assert result.handle == "abc123"


def test_paged_books_result_accepts_none_total_pages_and_none_handle():
    result = PagedBooksResult(
        items=(),
        page=5,
        page_size=20,
        total_pages=None,
        has_more_than_shown=True,
        handle=None,
    )

    assert result.total_pages is None
    assert result.handle is None


def test_paged_books_result_is_frozen():
    result = PagedBooksResult(
        items=(),
        page=1,
        page_size=20,
        total_pages=0,
        has_more_than_shown=False,
        handle=None,
    )

    with pytest.raises(AttributeError):
        result.page = 2


def test_paged_authors_result_holds_items_and_page_metadata():
    result = PagedAuthorsResult(
        items=(Author(id="1", name="Frank Herbert"),),
        page=1,
        page_size=20,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    assert result.items == (Author(id="1", name="Frank Herbert"),)
    assert result.total_pages == 1


def test_paged_publishers_result_holds_items_and_page_metadata():
    result = PagedPublishersResult(
        items=(Publisher(id="1", name="Ace Books"),),
        page=1,
        page_size=20,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    assert result.items == (Publisher(id="1", name="Ace Books"),)
    assert result.total_pages == 1
```

Update the file's top import to add the three new names:

```python
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
    Series,
    SeriesItem,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'PagedBooksResult'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/book0_core/models.py`, after `BookDetailsResult`:

```python
@dataclass(frozen=True)
class PagedBooksResult:
    items: tuple[Book, ...]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool
    handle: str | None


@dataclass(frozen=True)
class PagedAuthorsResult:
    items: tuple[Author, ...]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool
    handle: str | None


@dataclass(frozen=True)
class PagedPublishersResult:
    items: tuple[Publisher, ...]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool
    handle: str | None
```

Replace `src/book0_core/gateway.py` in full:

```python
from typing import Protocol

from book0_core.models import (
    Author,
    Book,
    BookDetailsResult,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
)


class LibraryGateway(Protocol):
    def list_books(self) -> list[Book]: ...
    def list_authors(self) -> list[Author]: ...
    def list_publishers(self) -> list[Publisher]: ...
    def get_book_details(self, ids: list[str]) -> BookDetailsResult: ...
    def list_books_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult: ...
    def list_authors_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult: ...
    def list_publishers_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult: ...
    def close_pagination(self, handle: str) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: PASS (all tests, including the three new ones).

Also run: `uv run mypy src`
Expected: no new errors (existing implementations don't satisfy the widened Protocol yet —
that's fine, nothing is annotated `: LibraryGateway` at a construction site yet, per the
project's known, tracked gap in `docs/superpowers/TODO.md`).

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/models.py src/book0_core/gateway.py tests/unit/test_models.py
git commit -m "feat: add Paged*Result models and LibraryGateway pagination methods"
```

---

## Task 2: `SqliteLibraryGateway` — lazy persistent connection

**Files:**
- Modify: `src/book0_core/sqlite_gateway.py`
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: nothing new (internal refactor only).
- Produces: `SqliteLibraryGateway._connect(self) -> sqlite3.Connection` — Task 3 relies on
  this existing and being reusable across calls without closing.

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_sqlite_gateway.py`, after
`test_sqlite_gateway_satisfies_the_library_gateway_protocol`:

```python
def test_gateway_reuses_the_same_connection_across_multiple_method_calls(
    calibre_metadata_db: Path, monkeypatch: pytest.MonkeyPatch
):
    real_connect = sqlite3.connect
    captured_calls: list[str] = []

    def spying_connect(
        database: str, *args: object, **kwargs: object
    ) -> sqlite3.Connection:
        captured_calls.append(str(database))
        return real_connect(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlite3, "connect", spying_connect)
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    gateway.list_books()
    gateway.list_authors()
    gateway.list_publishers()

    assert captured_calls == [f"file:{calibre_metadata_db}?mode=ro"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py::test_gateway_reuses_the_same_connection_across_multiple_method_calls -v`
Expected: FAIL — `captured_calls` has 3 entries today (one per method call), not 1.

- [ ] **Step 3: Write minimal implementation**

In `src/book0_core/sqlite_gateway.py`, replace `__init__` and each of the four existing
methods:

```python
class SqliteLibraryGateway:
    def __init__(self, library_path: Path) -> None:
        self._db_path = (
            library_path / "metadata.db" if library_path.is_dir() else library_path
        )
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            if not self._db_path.exists():
                raise LibraryNotFoundError(
                    f"Calibre library not found: {self._db_path}"
                )
            connection = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            self._check_is_calibre_library(connection)
            self._connection = connection
        return self._connection

    def list_books(self) -> list[Book]:
        connection = self._connect()
        rows = connection.execute(_LIST_BOOKS_QUERY).fetchall()

        return [
            Book(
                id=str(row[0]),
                title=row[1],
                authors=tuple(row[2].split(", ")) if row[2] else (),
                pubdate=self._normalize_pubdate(row[3]),
            )
            for row in rows
        ]

    def list_authors(self) -> list[Author]:
        connection = self._connect()
        rows = connection.execute(_LIST_AUTHORS_QUERY).fetchall()

        return [Author(id=str(row[0]), name=row[1]) for row in rows]

    def list_publishers(self) -> list[Publisher]:
        connection = self._connect()
        rows = connection.execute(_LIST_PUBLISHERS_QUERY).fetchall()

        return [Publisher(id=str(row[0]), name=row[1]) for row in rows]

    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        deduped_ids, valid_ids = self._partition_ids(ids)

        connection = self._connect()
        placeholders = ", ".join("?" for _ in valid_ids)
        query = _GET_BOOK_DETAILS_QUERY_TEMPLATE.format(placeholders=placeholders)
        rows = connection.execute(query, valid_ids).fetchall()

        books = []
        found_ids: set[str] = set()
        library_root = self._db_path.parent
        for row in rows:
            book_id = str(row[0])
            found_ids.add(book_id)
            cover_path = self._compute_cover_path(library_root, row[10], row[11])
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
                    cover_path=cover_path,
                )
            )

        missing_ids = tuple(id_ for id_ in deduped_ids if id_ not in found_ids)
        return BookDetailsResult(books=tuple(books), missing_ids=missing_ids)
```

(Everything else in the file — `_compute_cover_path`, `_partition_ids`, `_normalize_pubdate`,
`_check_is_calibre_library`, the module-level query constants — stays unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: PASS (all tests, including the new one — the existing "opens read only" tests each
call only one method per gateway instance, so they still see exactly one `connect` call each;
the missing-file and non-calibre-file tests still raise on the first call, unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/sqlite_gateway.py tests/integration/test_sqlite_gateway.py
git commit -m "refactor: make SqliteLibraryGateway's connection lazy and persistent"
```

---

## Task 3: `SqliteLibraryGateway.list_books_page` + pagination session infrastructure

**Files:**
- Modify: `src/book0_core/sqlite_gateway.py`
- Modify: `tests/conftest.py` (new fixture)
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: `SqliteLibraryGateway._connect()` from Task 2.
- Produces: `SqliteLibraryGateway.list_books_page(page, page_size, handle=None) ->
  PagedBooksResult`, `close_pagination(handle: str) -> None`, and the shared internals
  `_fetch_page`, `_bounded_total_pages`, `_prune_expired_sessions`, `_now`, `_PaginationSession`
  — Tasks 4 and 5 call `_fetch_page`/`_bounded_total_pages` unchanged for authors/publishers.

- [ ] **Step 1: Add the larger fixture**

Add to `tests/conftest.py`, after the `expected_book_details` fixture:

```python
@pytest.fixture
def many_books_db(tmp_path: Path) -> Path:
    """7 books/authors/publishers, deliberately unlinked to each other - only counts
    and title/name ordering matter for exercising pagination beyond a single page."""
    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                pubdate TEXT,
                series_index REAL,
                path TEXT,
                has_cover INTEGER
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
            """
        )
        connection.executemany(
            "INSERT INTO books (id, title) VALUES (?, ?)",
            [(i, f"Book {i}") for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO authors (id, name) VALUES (?, ?)",
            [(i, f"Author {i}") for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO publishers (id, name) VALUES (?, ?)",
            [(i, f"Publisher {i}") for i in range(1, 8)],
        )
        connection.commit()
    finally:
        connection.close()
    return db_path
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/integration/test_sqlite_gateway.py`:

```python
def test_list_books_page_returns_the_requested_page_in_title_order(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(1, 2)

    assert [book.title for book in result.items] == ["Book 1", "Book 2"]
    assert result.page == 1
    assert result.page_size == 2


def test_list_books_page_cold_jump_to_a_later_page_returns_correct_rows(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(3, 2)

    assert [book.title for book in result.items] == ["Book 5", "Book 6"]


def test_list_books_page_last_page_has_fewer_items_and_no_handle(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(4, 2)

    assert [book.title for book in result.items] == ["Book 7"]
    assert result.handle is None


def test_list_books_page_reports_exact_total_pages_under_the_cap(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(1, 2)

    assert result.total_pages == 4
    assert result.has_more_than_shown is False


def test_list_books_page_reports_many_when_count_exceeds_the_cap(
    many_books_db: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(sqlite_gateway, "_PAGE_COUNT_CAP", 2)
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(1, 2)

    assert result.total_pages is None
    assert result.has_more_than_shown is True


def test_list_books_page_reports_zero_total_pages_for_an_empty_library(
    calibre_metadata_db: Path,
):
    db_path = calibre_metadata_db.parent / "empty" / "metadata.db"
    db_path.parent.mkdir()
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                pubdate TEXT, series_index REAL, path TEXT, has_cover INTEGER);
            CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL, author INTEGER NOT NULL);
            """
        )
        connection.commit()
    finally:
        connection.close()
    gateway = SqliteLibraryGateway(db_path)

    result = gateway.list_books_page(1, 2)

    assert result.items == ()
    assert result.total_pages == 0
    assert result.handle is None


def test_list_books_page_reuses_the_session_for_the_immediate_next_page(
    many_books_db: Path,
):
    # sqlite3.Connection is a C-extension type - its methods can't be monkeypatched
    # directly (monkeypatch.setattr(sqlite3.Connection, "execute", ...) raises
    # TypeError: cannot set 'execute' attribute of immutable type). Use the
    # connection's own set_trace_callback instead: it receives the SQL text of
    # every statement actually executed on it, which is exactly what "no new
    # OFFSET query for the reused page" needs to observe.
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    traced_sql: list[str] = []
    gateway._connect().set_trace_callback(traced_sql.append)
    second = gateway.list_books_page(2, 2, handle=first.handle)

    assert [book.title for book in second.items] == ["Book 3", "Book 4"]
    assert not any("OFFSET" in sql for sql in traced_sql)


def test_list_books_page_falls_back_to_a_fresh_fetch_outside_the_reusable_range(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    # Requesting page 1 again (not the session's next page, 2) must not reuse it.
    repeated = gateway.list_books_page(1, 2, handle=first.handle)

    assert [book.title for book in repeated.items] == ["Book 1", "Book 2"]


def test_list_books_page_closes_the_superseded_session_on_a_same_stream_fallback(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    assert first.handle in gateway._sessions
    gateway.list_books_page(1, 2, handle=first.handle)  # repeats page 1, not next

    assert first.handle not in gateway._sessions


def test_list_books_page_falls_back_when_handle_is_unknown(many_books_db: Path):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_books_page(2, 2, handle="not-a-real-handle")

    assert [book.title for book in result.items] == ["Book 3", "Book 4"]


def test_list_books_page_falls_back_when_page_size_does_not_match_the_session(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    result = gateway.list_books_page(2, 3, handle=first.handle)

    assert [book.title for book in result.items] == ["Book 4", "Book 5", "Book 6"]


# (The "handle belongs to a different resource" fallback case needs a second real
# resource type to be meaningful - list_authors_page doesn't exist until Task 4, so
# that test lives there instead, once both methods exist to cross-check against
# each other.)


def test_close_pagination_releases_the_session(many_books_db: Path):
    gateway = SqliteLibraryGateway(many_books_db)
    first = gateway.list_books_page(1, 2)
    assert first.handle is not None

    gateway.close_pagination(first.handle)
    second = gateway.list_books_page(2, 2, handle=first.handle)

    # A fresh fetch for page 2 gets its own new handle, distinct from the closed one.
    assert second.handle != first.handle
    assert [book.title for book in second.items] == ["Book 3", "Book 4"]


def test_close_pagination_is_silent_and_idempotent_for_an_unknown_handle(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    gateway.close_pagination("never-issued")
    gateway.close_pagination("never-issued")  # idempotent, no exception


def test_list_books_page_expires_a_session_after_the_timeout(
    many_books_db: Path, monkeypatch: pytest.MonkeyPatch
):
    fake_now = [1000.0]
    monkeypatch.setattr(SqliteLibraryGateway, "_now", lambda self: fake_now[0])
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_books_page(1, 2)
    fake_now[0] += 61
    result = gateway.list_books_page(2, 2, handle=first.handle)

    assert [book.title for book in result.items] == ["Book 3", "Book 4"]
```

Add `from book0_core import sqlite_gateway` to the file's imports (needed for the
`_PAGE_COUNT_CAP` monkeypatch above), alongside the existing
`from book0_core.sqlite_gateway import SqliteLibraryGateway`.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -k list_books_page -v`
Expected: FAIL — `AttributeError: 'SqliteLibraryGateway' object has no attribute
'list_books_page'`.

- [ ] **Step 4: Write minimal implementation**

Add these imports to the top of `src/book0_core/sqlite_gateway.py`:

```python
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
```

Add these module-level constants after `_VALID_ID_PATTERN`:

```python
_SESSION_TIMEOUT_SECONDS = 60
_PAGE_COUNT_CAP = 100  # in pages; the row cap is _PAGE_COUNT_CAP * page_size

_LIST_BOOKS_QUERY_FROM_OFFSET = _LIST_BOOKS_QUERY + "\n    LIMIT -1 OFFSET ?"
_LIST_BOOKS_COUNT_QUERY = "SELECT books.id FROM books"


@dataclass
class _PaginationSession:
    resource: str
    page_size: int
    next_page: int
    cursor: sqlite3.Cursor
    last_access: float
```

Add `self._sessions: dict[str, _PaginationSession] = {}` to `__init__`, right after
`self._connection: sqlite3.Connection | None = None`.

Add these methods to `SqliteLibraryGateway` (anywhere after `_connect`, e.g. right after
`get_book_details`):

```python
def list_books_page(
    self, page: int, page_size: int, handle: str | None = None
) -> PagedBooksResult:
    connection = self._connect()
    rows, result_handle = self._fetch_page(
        connection, "books", page, page_size, handle, _LIST_BOOKS_QUERY_FROM_OFFSET
    )
    total_pages, has_more = self._bounded_total_pages(
        connection, _LIST_BOOKS_COUNT_QUERY, page_size
    )
    books = tuple(
        Book(
            id=str(row[0]),
            title=row[1],
            authors=tuple(row[2].split(", ")) if row[2] else (),
            pubdate=self._normalize_pubdate(row[3]),
        )
        for row in rows
    )
    return PagedBooksResult(
        items=books,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_more_than_shown=has_more,
        handle=result_handle,
    )


def close_pagination(self, handle: str) -> None:
    session = self._sessions.pop(handle, None)
    if session is not None:
        session.cursor.close()


def _now(self) -> float:
    return time.monotonic()


def _prune_expired_sessions(self) -> None:
    now = self._now()
    expired = [
        handle
        for handle, session in self._sessions.items()
        if now - session.last_access > _SESSION_TIMEOUT_SECONDS
    ]
    for handle in expired:
        self._sessions.pop(handle).cursor.close()


def _fetch_page(
    self,
    connection: sqlite3.Connection,
    resource: str,
    page: int,
    page_size: int,
    handle: str | None,
    query_from_offset: str,
) -> tuple[list[tuple[object, ...]], str | None]:
    self._prune_expired_sessions()

    session = self._sessions.get(handle) if handle is not None else None
    reusable = (
        session is not None
        and session.resource == resource
        and session.page_size == page_size
        and session.next_page == page
    )
    if reusable and session is not None and handle is not None:
        rows = session.cursor.fetchmany(page_size)
        session.next_page += 1
        session.last_access = self._now()
        result_handle: str | None = handle
    else:
        # A known handle for the *same* resource/page_size that just isn't the
        # session's next page (a repeat, a backward jump) is superseded, not
        # merely unrelated - close it now rather than waiting out the timeout.
        # A handle that mismatches on resource or page_size might still be a
        # different, still-wanted session under its own handle - leave it for
        # the timeout instead of closing it as a side effect of this call.
        if (
            session is not None
            and handle is not None
            and session.resource == resource
            and session.page_size == page_size
        ):
            self._sessions.pop(handle, None)
            session.cursor.close()

        offset = (page - 1) * page_size
        cursor = connection.execute(query_from_offset, (offset,))
        rows = cursor.fetchmany(page_size)
        session = _PaginationSession(
            resource=resource,
            page_size=page_size,
            next_page=page + 1,
            cursor=cursor,
            last_access=self._now(),
        )
        result_handle = str(uuid.uuid4())
        self._sessions[result_handle] = session

    if len(rows) < page_size:
        self._sessions.pop(result_handle, None)
        session.cursor.close()
        result_handle = None

    return rows, result_handle


def _bounded_total_pages(
    self, connection: sqlite3.Connection, count_query: str, page_size: int
) -> tuple[int | None, bool]:
    row_cap = _PAGE_COUNT_CAP * page_size + 1
    count = connection.execute(
        f"SELECT COUNT(*) FROM ({count_query} LIMIT ?)", (row_cap,)
    ).fetchone()[0]
    if count > _PAGE_COUNT_CAP * page_size:
        return None, True
    total_pages = -(-count // page_size) if count else 0
    return total_pages, False
```

Add `PagedBooksResult` to the `book0_core.models` import at the top of the file (the import
already lists `Author, Book, BookDetails, BookDetailsResult, Publisher, Series, SeriesItem`;
add `PagedAuthorsResult, PagedBooksResult, PagedPublishersResult` — the latter two are unused
until Tasks 4/5 but importing all three together now avoids a second import-line edit per
task).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: PASS (all tests, including every new one above and every pre-existing one).

Also run: `uv run ruff check .` and `uv run mypy src` — fix any new report (the unused
`PagedAuthorsResult`/`PagedPublishersResult` import will be flagged by ruff until Tasks 4/5
use them; if so, only import `PagedBooksResult` here and add the other two in their own
tasks instead).

- [ ] **Step 6: Commit**

```bash
git add src/book0_core/sqlite_gateway.py tests/conftest.py tests/integration/test_sqlite_gateway.py
git commit -m "feat: add SqliteLibraryGateway.list_books_page with session-based handle reuse"
```

---

## Task 4: `SqliteLibraryGateway.list_authors_page`

**Files:**
- Modify: `src/book0_core/sqlite_gateway.py`
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: `_fetch_page`, `_bounded_total_pages` from Task 3.
- Produces: `SqliteLibraryGateway.list_authors_page(page, page_size, handle=None) ->
  PagedAuthorsResult`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_sqlite_gateway.py`:

```python
def test_list_authors_page_returns_the_requested_page_in_name_order(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_authors_page(1, 2)

    assert [author.name for author in result.items] == ["Author 1", "Author 2"]
    assert result.total_pages == 4


def test_list_authors_page_reuses_the_session_for_the_immediate_next_page(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_authors_page(1, 2)
    second = gateway.list_authors_page(2, 2, handle=first.handle)

    assert [author.name for author in second.items] == ["Author 3", "Author 4"]


def test_list_authors_page_last_page_has_no_handle(many_books_db: Path):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_authors_page(4, 2)

    assert [author.name for author in result.items] == ["Author 7"]
    assert result.handle is None


def test_list_books_page_falls_back_when_handle_belongs_to_a_different_resource(
    many_books_db: Path,
):
    # Moved here from Task 3: this fallback case needs two real resource types to
    # be meaningful, and list_authors_page didn't exist yet in Task 3.
    gateway = SqliteLibraryGateway(many_books_db)

    authors_first = gateway.list_authors_page(1, 2)
    result = gateway.list_books_page(2, 2, handle=authors_first.handle)

    assert [book.title for book in result.items] == ["Book 3", "Book 4"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -k list_authors_page -v`
Expected: FAIL — `AttributeError: 'SqliteLibraryGateway' object has no attribute
'list_authors_page'`.

- [ ] **Step 3: Write minimal implementation**

Add to the module-level constants block (next to `_LIST_BOOKS_QUERY_FROM_OFFSET`):

```python
_LIST_AUTHORS_QUERY_FROM_OFFSET = _LIST_AUTHORS_QUERY + " LIMIT -1 OFFSET ?"
_LIST_AUTHORS_COUNT_QUERY = "SELECT id FROM authors"
```

Add this method to `SqliteLibraryGateway`, right after `list_books_page`:

```python
    def list_authors_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult:
        connection = self._connect()
        rows, result_handle = self._fetch_page(
            connection,
            "authors",
            page,
            page_size,
            handle,
            _LIST_AUTHORS_QUERY_FROM_OFFSET,
        )
        total_pages, has_more = self._bounded_total_pages(
            connection, _LIST_AUTHORS_COUNT_QUERY, page_size
        )
        authors = tuple(Author(id=str(row[0]), name=row[1]) for row in rows)
        return PagedAuthorsResult(
            items=authors,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )
```

If Task 3 imported only `PagedBooksResult`, add `PagedAuthorsResult` to the
`book0_core.models` import now.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/sqlite_gateway.py tests/integration/test_sqlite_gateway.py
git commit -m "feat: add SqliteLibraryGateway.list_authors_page"
```

---

## Task 5: `SqliteLibraryGateway.list_publishers_page`

**Files:**
- Modify: `src/book0_core/sqlite_gateway.py`
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: `_fetch_page`, `_bounded_total_pages` from Task 3.
- Produces: `SqliteLibraryGateway.list_publishers_page(page, page_size, handle=None) ->
  PagedPublishersResult`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_sqlite_gateway.py`:

```python
def test_list_publishers_page_returns_the_requested_page_in_name_order(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_publishers_page(1, 2)

    assert [publisher.name for publisher in result.items] == [
        "Publisher 1",
        "Publisher 2",
    ]
    assert result.total_pages == 4


def test_list_publishers_page_reuses_the_session_for_the_immediate_next_page(
    many_books_db: Path,
):
    gateway = SqliteLibraryGateway(many_books_db)

    first = gateway.list_publishers_page(1, 2)
    second = gateway.list_publishers_page(2, 2, handle=first.handle)

    assert [publisher.name for publisher in second.items] == [
        "Publisher 3",
        "Publisher 4",
    ]


def test_list_publishers_page_last_page_has_no_handle(many_books_db: Path):
    gateway = SqliteLibraryGateway(many_books_db)

    result = gateway.list_publishers_page(4, 2)

    assert [publisher.name for publisher in result.items] == ["Publisher 7"]
    assert result.handle is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -k list_publishers_page -v`
Expected: FAIL — `AttributeError: 'SqliteLibraryGateway' object has no attribute
'list_publishers_page'`.

- [ ] **Step 3: Write minimal implementation**

Add to the module-level constants block:

```python
_LIST_PUBLISHERS_QUERY_FROM_OFFSET = _LIST_PUBLISHERS_QUERY + " LIMIT -1 OFFSET ?"
_LIST_PUBLISHERS_COUNT_QUERY = "SELECT id FROM publishers"
```

Add this method to `SqliteLibraryGateway`, right after `list_authors_page`:

```python
    def list_publishers_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult:
        connection = self._connect()
        rows, result_handle = self._fetch_page(
            connection,
            "publishers",
            page,
            page_size,
            handle,
            _LIST_PUBLISHERS_QUERY_FROM_OFFSET,
        )
        total_pages, has_more = self._bounded_total_pages(
            connection, _LIST_PUBLISHERS_COUNT_QUERY, page_size
        )
        publishers = tuple(Publisher(id=str(row[0]), name=row[1]) for row in rows)
        return PagedPublishersResult(
            items=publishers,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=result_handle,
        )
```

If not already imported, add `PagedPublishersResult` to the `book0_core.models` import.

Also add a Protocol-conformance sanity check to
`test_sqlite_gateway_satisfies_the_library_gateway_protocol` in
`tests/integration/test_sqlite_gateway.py` — replace its body:

```python
def test_sqlite_gateway_satisfies_the_library_gateway_protocol(
    calibre_metadata_db: Path,
):
    gateway: LibraryGateway = SqliteLibraryGateway(calibre_metadata_db)

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS
    paged = gateway.list_books_page(1, 10)
    assert paged.page == 1
    gateway.close_pagination("unused-handle")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: PASS.

Run: `uv run mypy src`
Expected: no new errors — `SqliteLibraryGateway` now structurally satisfies the full
`LibraryGateway` Protocol.

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/sqlite_gateway.py tests/integration/test_sqlite_gateway.py
git commit -m "feat: add SqliteLibraryGateway.list_publishers_page"
```

---

## Task 6: `book0_config` — `default-page-size`

**Files:**
- Modify: `src/book0_config/config.py`
- Modify: `book0-libraries.toml`
- Test: `tests/unit/test_book0_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `LibraryConfig.default_page_size: int | None = None`, read by
  `load_libraries` from an optional top-level `default-page-size` TOML key — Task 9
  (`book0_api/asgi.py`) and Task 12 (`book0_cli`) read this field.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_book0_config.py`:

```python
def test_load_libraries_reads_default_page_size_when_present(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        "default-page-size = 25\n\n"
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\n'
    )

    config = load_libraries(config_path)

    assert config.default_page_size == 25


def test_load_libraries_default_page_size_is_none_when_absent(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text('[libraries]\nfiction = "/path/to/fiction/metadata.db"\n')

    config = load_libraries(config_path)

    assert config.default_page_size is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_config.py -v`
Expected: FAIL — `AttributeError: 'LibraryConfig' object has no attribute
'default_page_size'`.

- [ ] **Step 3: Write minimal implementation**

Replace `src/book0_config/config.py` in full:

```python
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


@dataclass(frozen=True)
class LibraryConfig:
    libraries: dict[str, Path]
    default_tag: str | None
    default_page_size: int | None = None


def _expand_env_vars(value: str) -> str:
    return _ENV_VAR_PATTERN.sub(lambda match: os.environ[match.group(1)], value)


def load_libraries(config_path: Path) -> LibraryConfig:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    libraries = {
        tag: Path(_expand_env_vars(path)) for tag, path in data["libraries"].items()
    }
    return LibraryConfig(
        libraries=libraries,
        default_tag=data.get("default-library"),
        default_page_size=data.get("default-page-size"),
    )
```

Add a documentation comment to `book0-libraries.toml`, right after the existing
`default-library` comment block at the end of the file:

```toml

# Optional: cap every response's page size at this value, and force pagination even when a
# client sends no page_size param at all (a client requesting a smaller page_size still gets
# its own smaller size - this is a ceiling, not a fixed size). Protects the server from an
# unbounded query when unset, no cap is imposed and an omitted page_size stays unpaginated,
# exactly like today.
# default-page-size = 100
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_config.py -v`
Expected: PASS (all tests, including the pre-existing ones that construct `LibraryConfig(...)`
without a third argument — the new field's `= None` default keeps those equality checks
correct).

- [ ] **Step 5: Commit**

```bash
git add src/book0_config/config.py book0-libraries.toml tests/unit/test_book0_config.py
git commit -m "feat: add default-page-size to book0_config's LibraryConfig"
```

---

## Task 7: `book0_cli_remote/config.py` — client-side `default-page-size`

**Files:**
- Modify: `src/book0_cli_remote/config.py`
- Test: `tests/unit/test_cli_remote_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `load_default_page_size(config_path: Path) -> int | None` — Task 13
  (`book0_cli_remote/main.py`) calls this.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_cli_remote_config.py`:

```python
def test_load_default_page_size_returns_the_configured_value(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text('server = "http://127.0.0.1:8000"\ndefault-page-size = 25\n')

    assert load_default_page_size(config_path) == 25


def test_load_default_page_size_returns_none_when_key_is_absent(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text('server = "http://127.0.0.1:8000"\n')

    assert load_default_page_size(config_path) is None


def test_load_default_page_size_raises_toml_decode_error_for_invalid_toml(
    tmp_path: Path,
):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text("not valid toml === \n")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_default_page_size(config_path)
```

Add `load_default_page_size` to the file's import from `book0_cli_remote.config`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_remote_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_default_page_size'`.

- [ ] **Step 3: Write minimal implementation**

Update the module docstring at the top of `src/book0_cli_remote/config.py`:

```python
"""Client-side config discovery/loading for `book0-remote`'s `--server` fallback.

Reads `.book0-client.toml`, a personal/local file (gitignored, not committed) holding a
`server = "http://host:port"` key (required), an optional `cover-cache-dir = "/path"` key
(falls back to an XDG cache directory when absent), and an optional
`default-page-size = N` key (used only when `--page-size` is omitted) - the schema may grow
further, but no other key is designed yet.
"""
```

Add this function at the end of the file:

```python
def load_default_page_size(config_path: Path) -> int | None:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return data.get("default-page-size")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_remote_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/config.py tests/unit/test_cli_remote_config.py
git commit -m "feat: add load_default_page_size to book0_cli_remote's client config"
```

---

## Task 8: `book0_api/schemas.py` — `Paged*Out` wire schemas

**Files:**
- Modify: `src/book0_api/schemas.py`
- Test: `tests/unit/test_book0_api_schemas.py`

**Interfaces:**
- Consumes: `PagedBooksResult`/`PagedAuthorsResult`/`PagedPublishersResult` from Task 1.
- Produces: `PagedBooksOut.from_paged_result(PagedBooksResult) -> PagedBooksOut` and the
  `PagedAuthorsOut`/`PagedPublishersOut` equivalents — Task 9 (`book0_api/main.py`) returns
  these from the list routes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_book0_api_schemas.py`:

```python
def test_from_paged_result_converts_books_and_page_metadata():
    book = Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01")
    result = PagedBooksResult(
        items=(book,),
        page=2,
        page_size=10,
        total_pages=5,
        has_more_than_shown=False,
        handle="abc123",
    )

    paged_out = PagedBooksOut.from_paged_result(result)

    assert paged_out == PagedBooksOut(
        items=[BookOut.from_book(book)],
        page=2,
        page_size=10,
        total_pages=5,
        has_more_than_shown=False,
    )


def test_from_paged_result_keeps_none_total_pages():
    result = PagedBooksResult(
        items=(),
        page=1,
        page_size=10,
        total_pages=None,
        has_more_than_shown=True,
        handle=None,
    )

    paged_out = PagedBooksOut.from_paged_result(result)

    assert paged_out.total_pages is None
    assert paged_out.has_more_than_shown is True


def test_paged_authors_out_from_paged_result_converts_authors():
    author = Author(id="1", name="Frank Herbert")
    result = PagedAuthorsResult(
        items=(author,),
        page=1,
        page_size=10,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    paged_out = PagedAuthorsOut.from_paged_result(result)

    assert paged_out == PagedAuthorsOut(
        items=[AuthorOut.from_author(author)],
        page=1,
        page_size=10,
        total_pages=1,
        has_more_than_shown=False,
    )


def test_paged_publishers_out_from_paged_result_converts_publishers():
    publisher = Publisher(id="1", name="Ace Books")
    result = PagedPublishersResult(
        items=(publisher,),
        page=1,
        page_size=10,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    paged_out = PagedPublishersOut.from_paged_result(result)

    assert paged_out == PagedPublishersOut(
        items=[PublisherOut.from_publisher(publisher)],
        page=1,
        page_size=10,
        total_pages=1,
        has_more_than_shown=False,
    )
```

Update the file's two import blocks:

```python
from book0_api.schemas import (
    AuthorOut,
    BookDetailsOut,
    BookDetailsResultOut,
    BookOut,
    PagedAuthorsOut,
    PagedBooksOut,
    PagedPublishersOut,
    PublisherOut,
    SeriesItemOut,
    SeriesOut,
)
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
    Series,
    SeriesItem,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'PagedBooksOut'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/book0_api/schemas.py`, after `BookOut`:

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


class PagedAuthorsOut(BaseModel):
    items: list[AuthorOut]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool

    @classmethod
    def from_paged_result(cls, result: PagedAuthorsResult) -> "PagedAuthorsOut":
        return cls(
            items=[AuthorOut.from_author(author) for author in result.items],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
            has_more_than_shown=result.has_more_than_shown,
        )


class PagedPublishersOut(BaseModel):
    items: list[PublisherOut]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool

    @classmethod
    def from_paged_result(cls, result: PagedPublishersResult) -> "PagedPublishersOut":
        return cls(
            items=[
                PublisherOut.from_publisher(publisher) for publisher in result.items
            ],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
            has_more_than_shown=result.has_more_than_shown,
        )
```

Update the `book0_core.models` import at the top of `src/book0_api/schemas.py` to add
`PagedAuthorsResult, PagedBooksResult, PagedPublishersResult`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/schemas.py tests/unit/test_book0_api_schemas.py
git commit -m "feat: add Paged*Out wire schemas to book0_api"
```

---

## Task 9: `book0_api` — `page`/`page_size` query params + server-side resolution

**Files:**
- Modify: `src/book0_api/main.py`
- Modify: `src/book0_api/asgi.py`
- Test: `tests/e2e/test_book0_api_main.py`
- Test: `tests/e2e/test_book0_api_asgi.py`

**Interfaces:**
- Consumes: `PagedBooksOut`/`PagedAuthorsOut`/`PagedPublishersOut` from Task 8;
  `SqliteLibraryGateway.list_books_page`/etc. from Tasks 3-5; `LibraryConfig.default_page_size`
  from Task 6.
- Produces: `create_app(libraries, default_tag=None, default_page_size=None) -> FastAPI` — a
  new third parameter, and `GET /libraries/{books,authors,publishers}` now accept `page`/
  `page_size` query params. Task 10 (`HttpLibraryGateway`) is the consumer of this wire
  contract.

- [ ] **Step 1: Write the failing tests**

Add to `tests/e2e/test_book0_api_main.py`, using a `many_books_db` fixture for the
multi-page cases (add `many_books_db: Path` fixture parameters as needed):

```python
def test_list_books_returns_a_paginated_response_when_page_size_is_given(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page": 1, "page_size": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["items"]] == ["Book 1", "Book 2"]
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total_pages"] == 4
    assert body["has_more_than_shown"] is False


def test_list_books_omitting_page_and_page_size_stays_unpaginated_with_no_server_default(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 7


def test_list_books_server_default_page_size_forces_pagination(many_books_db: Path):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert [item["title"] for item in body["items"]] == ["Book 1", "Book 2"]


def test_list_books_server_default_page_size_caps_a_larger_client_request(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page_size": 100}
    )

    assert response.status_code == 200
    assert response.json()["page_size"] == 2


def test_list_books_client_page_size_smaller_than_server_default_is_honored(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=5)
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction", "page_size": 2})

    assert response.status_code == 200
    assert response.json()["page_size"] == 2


def test_list_books_non_positive_page_is_normalized_to_one(many_books_db: Path):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page": 0, "page_size": 2}
    )

    assert response.status_code == 200
    assert response.json()["page"] == 1


def test_list_books_non_positive_page_size_is_normalized_to_unpaginated(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction", "page_size": 0})

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_books_non_numeric_page_returns_422(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction", "page": "abc"})

    assert response.status_code == 422


def test_list_books_returns_400_for_an_unknown_tag_even_when_page_size_is_given(
    many_books_db: Path,
):
    # Unknown-tag handling (TagRequiredError -> 400) happens in _resolve_db_path,
    # before pagination resolution runs at all - this test just confirms the two
    # features don't interact / pagination params don't bypass tag validation.
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books",
        params={"tag": "does-not-exist", "page": 1, "page_size": 2},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_list_authors_returns_a_paginated_response_when_page_size_is_given(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/authors", params={"tag": "fiction", "page": 1, "page_size": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Author 1", "Author 2"]


def test_list_publishers_returns_a_paginated_response_when_page_size_is_given(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/publishers", params={"tag": "fiction", "page": 1, "page_size": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Publisher 1", "Publisher 2"]
```

Add to `tests/e2e/test_book0_api_asgi.py`:

```python
def test_asgi_app_forces_pagination_from_config_files_default_page_size(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_path = tmp_path / "book0-libraries.toml"
    config_path.write_text(
        f'default-library = "fiction"\n'
        f"default-page-size = 2\n\n"
        f'[libraries]\nfiction = "{many_books_db}"\n'
    )
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_path))

    from book0_api import asgi

    importlib.reload(asgi)

    client = TestClient(asgi.app)
    response = client.get("/libraries/books")

    assert response.status_code == 200
    assert response.json()["page_size"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/e2e/test_book0_api_main.py tests/e2e/test_book0_api_asgi.py -v`
Expected: FAIL — `TypeError: create_app() got an unexpected keyword argument
'default_page_size'`.

- [ ] **Step 3: Write minimal implementation**

In `src/book0_api/main.py`, update the imports (note: `_resolve_db_path` in the current code
already raises `TagRequiredError` for *both* an unresolvable tag and an unknown/unconfigured
one — it returns a plain `Path`, never `Path | None` — so no `PagedBooksResult`/etc. import is
needed here; the empty-paged-result construction a stale version of this plan used for an
"unknown tag" branch does not apply):

```python
from book0_api.schemas import (
    AuthorOut,
    BookDetailsResultOut,
    BookIdsIn,
    BookOut,
    PagedAuthorsOut,
    PagedBooksOut,
    PagedPublishersOut,
    PublisherOut,
)
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.sqlite_gateway import SqliteLibraryGateway
```

Add these two module-level helpers, right after `_cover_not_found`:

```python
def _resolve_effective_page(page: int | None) -> int:
    return page if page is not None and page > 0 else 1


def _resolve_effective_page_size(
    requested_page_size: int | None, server_default: int | None
) -> int | None:
    normalized_request = (
        requested_page_size
        if requested_page_size is not None and requested_page_size > 0
        else None
    )
    if server_default is not None:
        return (
            min(normalized_request, server_default)
            if normalized_request is not None
            else server_default
        )
    return normalized_request
```

Change `create_app`'s signature:

```python
def create_app(
    libraries: dict[str, Path],
    default_tag: str | None = None,
    default_page_size: int | None = None,
) -> FastAPI:
```

Replace the `list_books`, `list_authors`, and `list_publishers` route functions (the
`get_book_details` and `get_book_cover` routes stay untouched). `_resolve_db_path` always
either returns a usable `Path` or raises `TagRequiredError` (an unknown tag raises too, same
as an unresolvable one) — no `db_path is None` branch is needed or reachable:

```python
@app.get("/libraries/books", response_model=None)
def list_books(
    tag: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[BookOut] | PagedBooksOut | JSONResponse:
    try:
        db_path = _resolve_db_path(tag)
    except TagRequiredError as error:
        return JSONResponse(
            status_code=400,
            content={"error": "TagRequiredError", "detail": str(error)},
        )

    effective_page_size = _resolve_effective_page_size(page_size, default_page_size)

    gateway = SqliteLibraryGateway(db_path)
    try:
        if effective_page_size is None:
            books = gateway.list_books()
        else:
            paged_result = gateway.list_books_page(
                _resolve_effective_page(page), effective_page_size
            )
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

    if effective_page_size is None:
        return [BookOut.from_book(book) for book in books]
    return PagedBooksOut.from_paged_result(paged_result)


@app.get("/libraries/authors", response_model=None)
def list_authors(
    tag: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[AuthorOut] | PagedAuthorsOut | JSONResponse:
    try:
        db_path = _resolve_db_path(tag)
    except TagRequiredError as error:
        return JSONResponse(
            status_code=400,
            content={"error": "TagRequiredError", "detail": str(error)},
        )

    effective_page_size = _resolve_effective_page_size(page_size, default_page_size)

    gateway = SqliteLibraryGateway(db_path)
    try:
        if effective_page_size is None:
            authors = gateway.list_authors()
        else:
            paged_result = gateway.list_authors_page(
                _resolve_effective_page(page), effective_page_size
            )
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

    if effective_page_size is None:
        return [AuthorOut.from_author(author) for author in authors]
    return PagedAuthorsOut.from_paged_result(paged_result)


@app.get("/libraries/publishers", response_model=None)
def list_publishers(
    tag: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[PublisherOut] | PagedPublishersOut | JSONResponse:
    try:
        db_path = _resolve_db_path(tag)
    except TagRequiredError as error:
        return JSONResponse(
            status_code=400,
            content={"error": "TagRequiredError", "detail": str(error)},
        )

    effective_page_size = _resolve_effective_page_size(page_size, default_page_size)

    gateway = SqliteLibraryGateway(db_path)
    try:
        if effective_page_size is None:
            publishers = gateway.list_publishers()
        else:
            paged_result = gateway.list_publishers_page(
                _resolve_effective_page(page), effective_page_size
            )
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

    if effective_page_size is None:
        return [PublisherOut.from_publisher(publisher) for publisher in publishers]
    return PagedPublishersOut.from_paged_result(paged_result)
```

Update `src/book0_api/asgi.py`:

```python
import os
from pathlib import Path

from book0_api.cli import CONFIG_ENV_VAR
from book0_api.main import create_app
from book0_config.config import load_libraries

config = load_libraries(Path(os.environ[CONFIG_ENV_VAR]))
app = create_app(config.libraries, config.default_tag, config.default_page_size)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/e2e -v`
Expected: PASS (all tests, including every pre-existing `list_books`/`list_authors`/
`list_publishers` test — none of them pass `page`/`page_size`, and no server default is
configured in any of them, so `effective_page_size` resolves to `None` and behavior is
byte-for-byte identical to before).

Also run: `uv run mypy src` and `uv run ruff check .` — fix any new report.

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/main.py src/book0_api/asgi.py tests/e2e/test_book0_api_main.py tests/e2e/test_book0_api_asgi.py
git commit -m "feat: add page/page_size query params and server-side default-page-size to book0_api"
```

---

## Task 10: `HttpLibraryGateway` — paginated methods + transparent multi-page auto-fetch

**Files:**
- Modify: `src/book0_cli_remote/http_gateway.py`
- Test: `tests/integration/test_http_gateway.py`

**Interfaces:**
- Consumes: `PagedBooksOut`/etc. wire shape from Task 9.
- Produces: `HttpLibraryGateway.list_books_page(page, page_size, handle=None) ->
  PagedBooksResult` (and `list_authors_page`/`list_publishers_page`/`close_pagination`), plus
  a transparently-multi-page `list_books()`/`list_authors()`/`list_publishers()` — Task 13
  (`book0_cli_remote/main.py`) calls the paginated methods; the plain methods are unchanged
  from every existing caller's point of view.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_http_gateway.py`:

```python
def test_list_books_page_returns_the_requested_page(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.list_books_page(1, 2)

    assert [book.title for book in result.items] == ["Book 1", "Book 2"]
    assert result.page == 1
    assert result.page_size == 2
    assert result.total_pages == 4


def test_list_books_page_never_sends_the_handle_over_the_wire(
    many_books_db: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client_for({"fiction": many_books_db})
    captured_params: list[dict[str, str]] = []
    real_get = client.get

    def spying_get(url: str, **kwargs: object) -> httpx.Response:
        captured_params.append(dict(kwargs.get("params", {})))  # type: ignore[arg-type]
        return real_get(url, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(client, "get", spying_get)
    gateway = HttpLibraryGateway(client, "fiction")

    gateway.list_books_page(2, 2, handle="some-handle-from-a-previous-call")

    assert all("handle" not in params for params in captured_params)


def test_close_pagination_is_a_no_op(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    gateway.close_pagination("any-handle")  # no exception


def test_list_authors_page_returns_the_requested_page(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.list_authors_page(1, 2)

    assert [author.name for author in result.items] == ["Author 1", "Author 2"]


def test_list_publishers_page_returns_the_requested_page(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.list_publishers_page(1, 2)

    assert [publisher.name for publisher in result.items] == [
        "Publisher 1",
        "Publisher 2",
    ]


def test_list_books_transparently_fetches_every_page_when_server_forces_pagination(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)
    gateway = HttpLibraryGateway(client, "fiction")

    books = gateway.list_books()

    assert [book.title for book in books] == [f"Book {i}" for i in range(1, 8)]


def test_list_authors_transparently_fetches_every_page_when_server_forces_pagination(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)
    gateway = HttpLibraryGateway(client, "fiction")

    authors = gateway.list_authors()

    assert [author.name for author in authors] == [f"Author {i}" for i in range(1, 8)]


def test_list_books_returns_plain_list_unchanged_when_server_does_not_force_pagination(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS
```

Update the file's imports: add `from book0_core.models import (..., PagedAuthorsResult,
PagedBooksResult, PagedPublishersResult)` alongside the existing model imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_http_gateway.py -k "page or transparently" -v`
Expected: FAIL — `AttributeError: 'HttpLibraryGateway' object has no attribute
'list_books_page'`.

- [ ] **Step 3: Write minimal implementation**

Replace `src/book0_cli_remote/http_gateway.py` in full:

```python
from pathlib import Path
from typing import Literal

import httpx

from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
    Series,
    SeriesItem,
)

_ERROR_TYPES = {
    "LibraryNotFoundError": LibraryNotFoundError,
    "NotACalibreLibraryError": NotACalibreLibraryError,
    "TagRequiredError": TagRequiredError,
}


class HttpLibraryGateway:
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

    def _params(self) -> dict[str, str]:
        return {"tag": self._tag} if self._tag is not None else {}

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

    def list_books(self) -> list[Book]:
        response = self._client.get("/libraries/books", params=self._params())
        self._raise_for_error(response)

        body = response.json()
        if isinstance(body, dict):
            return self._collect_all_book_pages(body)
        return [self._book_from_json(row) for row in body]

    def _collect_all_book_pages(self, first_page: dict[str, object]) -> list[Book]:
        page_size = first_page["page_size"]
        page = first_page["page"]
        items = first_page["items"]  # type: ignore[assignment]
        books = [self._book_from_json(row) for row in items]  # type: ignore[union-attr]
        while len(items) == page_size:  # type: ignore[arg-type]
            page += 1  # type: ignore[operator]
            response = self._client.get(
                "/libraries/books",
                params={
                    **self._params(),
                    "page": str(page),
                    "page_size": str(page_size),
                },
            )
            self._raise_for_error(response)
            next_page = response.json()
            items = next_page["items"]
            books.extend(self._book_from_json(row) for row in items)
        return books

    def list_authors(self) -> list[Author]:
        response = self._client.get("/libraries/authors", params=self._params())
        self._raise_for_error(response)

        body = response.json()
        if isinstance(body, dict):
            return self._collect_all_author_pages(body)
        return [self._author_from_json(row) for row in body]

    def _collect_all_author_pages(self, first_page: dict[str, object]) -> list[Author]:
        page_size = first_page["page_size"]
        page = first_page["page"]
        items = first_page["items"]  # type: ignore[assignment]
        authors = [self._author_from_json(row) for row in items]  # type: ignore[union-attr]
        while len(items) == page_size:  # type: ignore[arg-type]
            page += 1  # type: ignore[operator]
            response = self._client.get(
                "/libraries/authors",
                params={
                    **self._params(),
                    "page": str(page),
                    "page_size": str(page_size),
                },
            )
            self._raise_for_error(response)
            next_page = response.json()
            items = next_page["items"]
            authors.extend(self._author_from_json(row) for row in items)
        return authors

    def list_publishers(self) -> list[Publisher]:
        response = self._client.get("/libraries/publishers", params=self._params())
        self._raise_for_error(response)

        body = response.json()
        if isinstance(body, dict):
            return self._collect_all_publisher_pages(body)
        return [self._publisher_from_json(row) for row in body]

    def _collect_all_publisher_pages(
        self, first_page: dict[str, object]
    ) -> list[Publisher]:
        page_size = first_page["page_size"]
        page = first_page["page"]
        items = first_page["items"]  # type: ignore[assignment]
        publishers = [self._publisher_from_json(row) for row in items]  # type: ignore[union-attr]
        while len(items) == page_size:  # type: ignore[arg-type]
            page += 1  # type: ignore[operator]
            response = self._client.get(
                "/libraries/publishers",
                params={
                    **self._params(),
                    "page": str(page),
                    "page_size": str(page_size),
                },
            )
            self._raise_for_error(response)
            next_page = response.json()
            items = next_page["items"]
            publishers.extend(self._publisher_from_json(row) for row in items)
        return publishers

    def list_books_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult:
        response = self._client.get(
            "/libraries/books",
            params={**self._params(), "page": str(page), "page_size": str(page_size)},
        )
        self._raise_for_error(response)
        body = response.json()
        return PagedBooksResult(
            items=tuple(self._book_from_json(row) for row in body["items"]),
            page=body["page"],
            page_size=body["page_size"],
            total_pages=body["total_pages"],
            has_more_than_shown=body["has_more_than_shown"],
            handle=None,
        )

    def list_authors_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult:
        response = self._client.get(
            "/libraries/authors",
            params={**self._params(), "page": str(page), "page_size": str(page_size)},
        )
        self._raise_for_error(response)
        body = response.json()
        return PagedAuthorsResult(
            items=tuple(self._author_from_json(row) for row in body["items"]),
            page=body["page"],
            page_size=body["page_size"],
            total_pages=body["total_pages"],
            has_more_than_shown=body["has_more_than_shown"],
            handle=None,
        )

    def list_publishers_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult:
        response = self._client.get(
            "/libraries/publishers",
            params={**self._params(), "page": str(page), "page_size": str(page_size)},
        )
        self._raise_for_error(response)
        body = response.json()
        return PagedPublishersResult(
            items=tuple(self._publisher_from_json(row) for row in body["items"]),
            page=body["page"],
            page_size=body["page_size"],
            total_pages=body["total_pages"],
            has_more_than_shown=body["has_more_than_shown"],
            handle=None,
        )

    def close_pagination(self, handle: str) -> None:
        pass

    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        response = self._client.post(
            "/libraries/books/detail", params=self._params(), json={"ids": ids}
        )
        self._raise_for_error(response)

        body = response.json()
        return BookDetailsResult(
            books=tuple(self._book_details_from_json(row) for row in body["books"]),
            missing_ids=tuple(body["missing_ids"]),
        )

    @staticmethod
    def _book_from_json(row: dict[str, object]) -> Book:
        return Book(
            id=row["id"],  # type: ignore[arg-type]
            title=row["title"],  # type: ignore[arg-type]
            authors=tuple(row["authors"]),  # type: ignore[arg-type]
            pubdate=row["pubdate"],  # type: ignore[arg-type]
        )

    @staticmethod
    def _author_from_json(row: dict[str, object]) -> Author:
        return Author(id=row["id"], name=row["name"])  # type: ignore[arg-type]

    @staticmethod
    def _publisher_from_json(row: dict[str, object]) -> Publisher:
        return Publisher(id=row["id"], name=row["name"])  # type: ignore[arg-type]

    def _book_details_from_json(self, row: dict[str, object]) -> BookDetails:
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
            cover_path=self._resolve_cover(row["id"], row["has_cover"]),  # type: ignore[arg-type]
        )

    def _resolve_cover(
        self, book_id: str, has_cover: bool
    ) -> str | None | Literal[False]:
        if not has_cover:
            return None
        if self._cache_dir is None:
            return False
        if Path(book_id).name != book_id:
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

Add `from book0_api.main import create_app` and `from fastapi.testclient import TestClient`
to `tests/integration/test_http_gateway.py`'s imports if not already present (they already
are, per the existing `_client_for` helper).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: PASS (all tests, including every pre-existing `get_book_details`/`list_*` test —
`_raise_for_error` behaves identically to the inline checks it replaces).

Also run: `uv run mypy src` and `uv run ruff check .` — the `# type: ignore` comments mirror
the pattern the file already uses for untyped `response.json()` dict access; fix any new
report that isn't already covered by one of them.

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/http_gateway.py tests/integration/test_http_gateway.py
git commit -m "feat: add HttpLibraryGateway pagination methods and transparent multi-page fetch"
```

---

## Task 11: `book0_presentation/tables.py` — page-footer helper

**Files:**
- Modify: `src/book0_presentation/tables.py`
- Test: `tests/unit/test_tables.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `format_page_footer(page: int, total_pages: int | None) -> str` — Tasks 12 and 13
  call this after rendering a page's table.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_tables.py`:

```python
def test_format_page_footer_shows_exact_total_pages():
    assert format_page_footer(3, 12) == "Page 3 of 12"


def test_format_page_footer_shows_many_when_total_pages_is_none():
    assert format_page_footer(3, None) == "Page 3 of many"


def test_format_page_footer_shows_zero_total_pages_for_an_empty_result():
    assert format_page_footer(1, 0) == "Page 1 of 0"
```

Add `format_page_footer` to the file's import from `book0_presentation.tables`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: FAIL — `ImportError: cannot import name 'format_page_footer'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/book0_presentation/tables.py`, at the end of the file:

```python
def format_page_footer(page: int, total_pages: int | None) -> str:
    total = str(total_pages) if total_pages is not None else "many"
    return f"Page {page} of {total}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/book0_presentation/tables.py tests/unit/test_tables.py
git commit -m "feat: add format_page_footer to book0_presentation"
```

---

## Task 12: `book0` (direct CLI) — `--page`/`--page-size`

**Files:**
- Modify: `src/book0_cli/main.py`
- Test: `tests/integration/test_cli_main.py`

**Interfaces:**
- Consumes: `SqliteLibraryGateway.list_books_page`/etc. from Tasks 3-5;
  `LibraryConfig.default_page_size` from Task 6; `format_page_footer` from Task 11.
- Produces: `book0 books/authors/publishers --page N --page-size M`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_cli_main.py` (reusing the `_write_config` helper already in
the file):

```python
def test_run_paginates_books_when_page_size_flag_is_given(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", many_books_db)

    exit_code = run(["--tag", "fiction", "--page-size", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Book 1" in captured.out
    assert "Book 3" not in captured.out
    assert captured.out.strip().endswith("Page 1 of 4")


def test_run_paginates_books_to_the_requested_page(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", many_books_db)

    exit_code = run(["--tag", "fiction", "--page", "2", "--page-size", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Book 3" in captured.out
    assert "Book 5" not in captured.out
    assert captured.out.strip().endswith("Page 2 of 4")


def test_run_uses_config_default_page_size_when_flag_is_omitted(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-page-size = 2\n\n[libraries]\nfiction = "{many_books_db}"\n'
    )

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip().endswith("Page 1 of 4")


def test_run_page_size_flag_overrides_config_default(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-page-size = 2\n\n[libraries]\nfiction = "{many_books_db}"\n'
    )

    exit_code = run(["--tag", "fiction", "--page-size", "5"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip().endswith("Page 1 of 2")


def test_run_does_not_paginate_when_no_page_size_resolves(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["--tag", "fiction", "--page", "2"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_normalizes_non_positive_page_size_to_unpaginated(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["--tag", "fiction", "--page-size", "0"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_normalizes_non_positive_page_to_one(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", many_books_db)

    exit_code = run(["--tag", "fiction", "--page", "-1", "--page-size", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Book 1" in captured.out
    assert captured.out.strip().endswith("Page 1 of 4")


def test_run_paginates_authors(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", many_books_db)

    exit_code = run(["authors", "--tag", "fiction", "--page-size", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Author 1" in captured.out
    assert captured.out.strip().endswith("Page 1 of 4")


def test_run_paginates_publishers(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", many_books_db)

    exit_code = run(["publishers", "--tag", "fiction", "--page-size", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Publisher 1" in captured.out
    assert captured.out.strip().endswith("Page 1 of 4")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_main.py -k page -v`
Expected: FAIL — `error: unrecognized arguments: --page-size 2` (argparse rejects the
unknown flag).

- [ ] **Step 3: Write minimal implementation**

In `src/book0_cli/main.py`, update the import from `book0_presentation.tables` to add
`format_page_footer`.

In `_build_parser`, add to each of the `books_parser`, `authors_parser`, and
`publishers_parser` blocks (not `books_detail_parser`):

```python
    books_parser.add_argument("--page", type=int, default=None)
    books_parser.add_argument("--page-size", type=int, default=None)
```

(same two lines, with `authors_parser`/`publishers_parser` in place of `books_parser`, right
after each parser's existing `--tag` argument).

Add these two module-level helpers, right after `_TAG_HELP`:

```python
def _resolve_page_size(
    cli_page_size: int | None, config_page_size: int | None
) -> int | None:
    candidate = cli_page_size if cli_page_size is not None else config_page_size
    return candidate if candidate is not None and candidate > 0 else None


def _resolve_page(cli_page: int | None) -> int:
    return cli_page if cli_page is not None and cli_page > 0 else 1
```

Replace the dispatch block inside `run` (from `if args.command == "authors":` through
`print(render_book_table(gateway.list_books()))`):

```python
if args.command == "books-detail":
    ids = [segment.strip() for segment in args.ids.split(",")] if args.ids else []
    result = gateway.get_book_details(ids)
    ordered_books = order_book_details_by_ids(result, ids)
    print(render_book_details_table(ordered_books))
    missing_ids_message = format_missing_ids_message(result.missing_ids)
    if missing_ids_message is not None:
        print(missing_ids_message)
else:
    page_size = _resolve_page_size(args.page_size, config.default_page_size)
    page = _resolve_page(args.page)

    if args.command == "authors":
        if page_size is None:
            print(render_author_table(gateway.list_authors()))
        else:
            paged = gateway.list_authors_page(page, page_size)
            print(render_author_table(list(paged.items)))
            print(format_page_footer(paged.page, paged.total_pages))
    elif args.command == "publishers":
        if page_size is None:
            print(render_publisher_table(gateway.list_publishers()))
        else:
            paged = gateway.list_publishers_page(page, page_size)
            print(render_publisher_table(list(paged.items)))
            print(format_page_footer(paged.page, paged.total_pages))
    else:
        if page_size is None:
            print(render_book_table(gateway.list_books()))
        else:
            paged = gateway.list_books_page(page, page_size)
            print(render_book_table(list(paged.items)))
            print(format_page_footer(paged.page, paged.total_pages))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: PASS (all tests, including every pre-existing one — `args.page`/`args.page_size`
default to `None` when the flags are omitted, `_resolve_page_size` returns `None` in that
case with no config default set, and the `else` branch's plain-list calls are unchanged from
before).

Also run: `uv run ruff check .` and `uv run mypy src`.

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli/main.py tests/integration/test_cli_main.py
git commit -m "feat: add --page/--page-size to book0"
```

---

## Task 13: `book0-remote` — `--page`/`--page-size`

**Files:**
- Modify: `src/book0_cli_remote/main.py`
- Test: `tests/integration/test_cli_remote_main.py`

**Interfaces:**
- Consumes: `HttpLibraryGateway.list_books_page`/etc. from Task 10;
  `load_default_page_size` from Task 7; `format_page_footer` from Task 11.
- Produces: `book0-remote books/authors/publishers --page N --page-size M`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_cli_remote_main.py` (the file already has a `_client_for`-style
helper or constructs `TestClient(create_app(...))` inline per its existing tests — follow
whichever pattern the file already uses at the point of insertion):

```python
def test_run_paginates_books_when_page_size_flag_is_given(
    many_books_db: Path, capsys: pytest.CaptureFixture[str]
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    exit_code = run(["--tag", "fiction", "--page-size", "2"], client=client)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Book 1" in captured.out
    assert "Book 3" not in captured.out
    assert captured.out.strip().endswith("Page 1 of 4")


def test_run_paginates_books_to_the_requested_page(
    many_books_db: Path, capsys: pytest.CaptureFixture[str]
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    exit_code = run(
        ["--tag", "fiction", "--page", "2", "--page-size", "2"], client=client
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Book 3" in captured.out
    assert captured.out.strip().endswith("Page 2 of 4")


def test_run_uses_client_config_default_page_size_when_flag_is_omitted(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text(
        'server = "http://testserver"\ndefault-page-size = 2\n'
    )
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    exit_code = run(["--tag", "fiction"], client=client)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip().endswith("Page 1 of 4")


def test_run_page_size_flag_overrides_client_config_default(
    many_books_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text(
        'server = "http://testserver"\ndefault-page-size = 2\n'
    )
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    exit_code = run(["--tag", "fiction", "--page-size", "5"], client=client)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip().endswith("Page 1 of 2")


def test_run_does_not_paginate_when_no_page_size_resolves(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    exit_code = run(["--tag", "fiction"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_paginates_authors(many_books_db: Path, capsys: pytest.CaptureFixture[str]):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    exit_code = run(["authors", "--tag", "fiction", "--page-size", "2"], client=client)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Author 1" in captured.out
    assert captured.out.strip().endswith("Page 1 of 4")


def test_run_paginates_publishers(
    many_books_db: Path, capsys: pytest.CaptureFixture[str]
):
    app = create_app({"fiction": many_books_db})
    client = TestClient(app)

    exit_code = run(
        ["publishers", "--tag", "fiction", "--page-size", "2"], client=client
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Publisher 1" in captured.out
    assert captured.out.strip().endswith("Page 1 of 4")
```

Add `from book0_api.main import create_app` and `from fastapi.testclient import TestClient`
to the file's imports if not already present, and `format_page_footer` is not needed directly
in the test file (assertions use plain string matching on `captured.out`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -k page -v`
Expected: FAIL — `error: unrecognized arguments: --page-size 2`.

- [ ] **Step 3: Write minimal implementation**

In `src/book0_cli_remote/main.py`, update the imports:

```python
from book0_cli_remote.config import (
    LOCAL_CONFIG_FILENAME,
    find_config_file,
    load_cover_cache_dir,
    load_default_page_size,
    load_server,
    xdg_cache_path,
    xdg_config_path,
)
from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_presentation.tables import (
    format_missing_ids_message,
    format_page_footer,
    order_book_details_by_ids,
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)
```

In `_build_parser`, add to each of `books_parser`, `authors_parser`, and
`publishers_parser` (not `books_detail_parser`), right after each parser's existing `--tag`
argument:

```python
    books_parser.add_argument("--page", type=int, default=None)
    books_parser.add_argument("--page-size", type=int, default=None)
```

(mirrored for `authors_parser`/`publishers_parser`).

Add these two module-level helpers, right after `_SERVER_HELP`:

```python
def _resolve_page_size(
    cli_page_size: int | None, config_page_size: int | None
) -> int | None:
    candidate = cli_page_size if cli_page_size is not None else config_page_size
    return candidate if candidate is not None and candidate > 0 else None


def _resolve_page(cli_page: int | None) -> int:
    return cli_page if cli_page is not None and cli_page > 0 else 1
```

Inside `run`, right after the `gateway = HttpLibraryGateway(...)` construction and its
following `try:`, replace the dispatch block (from `if args.command == "authors":` through
`print(render_book_table(gateway.list_books()))`):

```python
if args.command == "books-detail":
    ids = [segment.strip() for segment in args.ids.split(",")] if args.ids else []
    result = gateway.get_book_details(ids)
    ordered_books = order_book_details_by_ids(result, ids)
    print(render_book_details_table(ordered_books))
    missing_ids_message = format_missing_ids_message(result.missing_ids)
    if missing_ids_message is not None:
        print(missing_ids_message)
else:
    config_page_size = None
    page_size_config_path = find_config_file()
    if page_size_config_path is not None:
        try:
            config_page_size = load_default_page_size(page_size_config_path)
        except tomllib.TOMLDecodeError as error:
            print(
                f"Invalid book0-remote client config file "
                f"{page_size_config_path}: {error}",
                file=sys.stderr,
            )
            return 1
    page_size = _resolve_page_size(args.page_size, config_page_size)
    page = _resolve_page(args.page)

    if args.command == "authors":
        if page_size is None:
            print(render_author_table(gateway.list_authors()))
        else:
            paged = gateway.list_authors_page(page, page_size)
            print(render_author_table(list(paged.items)))
            print(format_page_footer(paged.page, paged.total_pages))
    elif args.command == "publishers":
        if page_size is None:
            print(render_publisher_table(gateway.list_publishers()))
        else:
            paged = gateway.list_publishers_page(page, page_size)
            print(render_publisher_table(list(paged.items)))
            print(format_page_footer(paged.page, paged.total_pages))
    else:
        if page_size is None:
            print(render_book_table(gateway.list_books()))
        else:
            paged = gateway.list_books_page(page, page_size)
            print(render_book_table(list(paged.items)))
            print(format_page_footer(paged.page, paged.total_pages))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: PASS (all tests, including every pre-existing one — the `return 1` inside the
`try` block's new page-size-config-loading branch is reachable inside the same `finally:
client.close()` as every other early return in this function, matching the existing pattern
used for `books-detail`'s cover-cache-dir loading a few lines above).

Also run: `uv run ruff check .` and `uv run mypy src`.

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/main.py tests/integration/test_cli_remote_main.py
git commit -m "feat: add --page/--page-size to book0-remote"
```

---

## Task 14: `README.md` — document `--page`/`--page-size`/`default-page-size`

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by later tasks — this is the plan's final task.

- [ ] **Step 1: Update the `book0` section**

In the `## \`book0\` - direct CLI` section of `README.md`, right after the existing usage
example block (the one showing `uv run book0 books --tag <tag>` etc.), add:

```markdown
Add `--page-size <N>` to page a `books`/`authors`/`publishers` listing instead of dumping the
whole library (`books-detail` is unrelated and has no `--page`) - `--page <N>` picks which
page (default `1`); a page footer (`Page 1 of 4`, or `Page 1 of many` past a bounded count) is
printed after the table:

```sh
uv run book0 books --tag <tag> --page-size 50
uv run book0 books --tag <tag> --page 2 --page-size 50
```

`--page-size` also has a config-file fallback: set `default-page-size = 50` in `.book0.toml`
to paginate every listing by default without passing the flag each time; `--page-size`
overrides it when given, and a `--page-size 0`/negative value (or a value with no source at
all) means "not paginated", matching today's full-listing behavior.
```

- [ ] **Step 2: Update the `book0-remote` section**

In the `## \`book0-remote\` + \`book0_api\` - HTTP-backed CLI` section, right after the
existing `### 2. Run the CLI against it` usage example block, add:

```markdown
`--page`/`--page-size` work the same way as `book0`'s, with `.book0-client.toml`'s
`default-page-size` as the config-file fallback instead of `.book0.toml`'s. A server operator
can additionally set `default-page-size` in `book0-libraries.toml` as a hard ceiling - it caps
any client-requested `--page-size` down to that value, and forces pagination even when a
client sends none at all; `book0-remote` handles a forced response transparently, so
`books`/`authors`/`publishers` without `--page-size` still show the complete listing (just via
more requests under the hood) unless you pass `--page-size` yourself to see one page at a
time.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document --page, --page-size, and default-page-size"
```

---

## Final verification

- [ ] Run the whole suite: `uv run pytest`
- [ ] `uv run ruff check .` and `uv run ruff format --check .`
- [ ] `uv run mypy src`
- [ ] Re-read `docs/superpowers/specs/2026-08-20-list-pagination-design.md` end to end and
      confirm every section has a corresponding task above (models/Protocol → Task 1;
      `SqliteLibraryGateway` persistent connection/sessions → Tasks 2-3; `list_authors_page`/
      `list_publishers_page` → Tasks 4-5; `book0_config`/client config → Tasks 6-7; wire
      schemas → Task 8; `book0_api` resolution → Task 9; `HttpLibraryGateway` → Task 10;
      rendering → Task 11; both CLIs → Tasks 12-13; error-handling table → covered across
      Tasks 9, 12, 13's normalization tests).
- [ ] Remove the now-resolved TODO item ("`books-detail` response projection + pagination")
      from `docs/superpowers/TODO.md` if it is still present when this plan lands — it should
      have been superseded already by the design doc's Purpose section, but confirm.
