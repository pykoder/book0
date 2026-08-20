# List Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add paginated variants of `list_books`/`list_authors`/`list_publishers` (new `*_page` methods on the `LibraryGateway` Protocol, both gateway implementations, `book0_api`'s three list routes, and both CLIs' `books`/`authors`/`publishers` subcommands) so a library with tens of thousands of rows can be listed in bounded chunks instead of dumping everything on every call.

**Architecture:** Three new `LibraryGateway` Protocol methods (`list_books_page`, `list_authors_page`, `list_publishers_page`) plus `close_pagination`, returning three new concrete `Paged*Result` dataclasses. `SqliteLibraryGateway` gets a persistent connection (shared by every method, not just the new ones) and a small table of generator-backed pagination sessions keyed by an advisory handle. `HttpLibraryGateway`/`book0_api` stay stateless — every paginated HTTP call is a fresh bounded query; the server can additionally cap or force an effective page size via a new `default-page-size` config key. Existing unpaginated methods and wire shapes are completely unchanged; pagination is purely additive.

**Tech Stack:** Python 3.12, stdlib `sqlite3`/`argparse`/`tomllib`, FastAPI + Pydantic, `httpx`, `pytest`. No new dependencies.

## Global Constraints

- Every command goes through `uv run <tool>` — never a bare `python`/`pytest`/`ruff`/`mypy`.
- `book0_core` never depends on `book0_cli`, `book0_cli_remote`, `book0_api`, `argparse`, or any web framework.
- All SQL lives in `book0_core/sqlite_gateway.py`; `SqliteLibraryGateway` connects read-only (`mode=ro`) and never opens a Calibre library for write.
- `book0_api`'s routes stay plain `def`, never `async def`.
- Type-hint every function signature (params + return); use `Path` for filesystem paths.
- No new `book0_core.errors` class for this feature — every pagination edge case (bad page/page_size, stale handle) degrades gracefully rather than raising.
- `list_books`/`list_authors`/`list_publishers`/`get_book_details` keep their exact current signatures and return types — zero risk to existing callers/tests.
- Never use a mutable default argument.
- Never ship code without an associated test; never weaken an existing test to make it pass.
- Existing full test suite (`uv run pytest`) must stay green after every task; `uv run ruff check .`, `uv run ruff format .`, `uv run mypy src` must report no new issue.

---

## Task 1: `book0_core.models` — three paged result dataclasses

**Files:**
- Modify: `src/book0_core/models.py`
- Test: `tests/unit/test_models.py` (create if it doesn't already cover `book0_core.models`; check first — if a `tests/unit/test_models.py` already exists, add to it instead of creating a duplicate)

**Interfaces:**
- Produces: `PagedBooksResult(items: tuple[Book, ...], page: int, page_size: int, total_pages: int | None, has_more_than_shown: bool, handle: str | None)`, and `PagedAuthorsResult`/`PagedPublishersResult` with the same field shape swapping `Book` for `Author`/`Publisher`. Consumed by Task 6 (`SqliteLibraryGateway`), Task 7 (`book0_api.schemas`), Task 9 (`HttpLibraryGateway`).

- [ ] **Step 1: Check for an existing models test file**

Run: `ls tests/unit/ | grep -i model`

If a file like `tests/unit/test_models.py` exists, read it first and add the new tests to it following its existing style. If none exists, create `tests/unit/test_models.py`.

- [ ] **Step 2: Write the failing tests**

```python
from book0_core.models import (
    Author,
    Book,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
)


def test_paged_books_result_holds_items_and_page_metadata():
    book = Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01")

    result = PagedBooksResult(
        items=(book,),
        page=1,
        page_size=10,
        total_pages=3,
        has_more_than_shown=False,
        handle="abc123",
    )

    assert result.items == (book,)
    assert result.page == 1
    assert result.page_size == 10
    assert result.total_pages == 3
    assert result.has_more_than_shown is False
    assert result.handle == "abc123"


def test_paged_authors_result_holds_items_and_page_metadata():
    author = Author(id="1", name="Frank Herbert")

    result = PagedAuthorsResult(
        items=(author,),
        page=2,
        page_size=5,
        total_pages=None,
        has_more_than_shown=True,
        handle=None,
    )

    assert result.items == (author,)
    assert result.total_pages is None
    assert result.has_more_than_shown is True
    assert result.handle is None


def test_paged_publishers_result_holds_items_and_page_metadata():
    publisher = Publisher(id="1", name="Ace Books")

    result = PagedPublishersResult(
        items=(publisher,),
        page=1,
        page_size=5,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    assert result.items == (publisher,)
    assert result.total_pages == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'PagedBooksResult'`

- [ ] **Step 4: Add the three dataclasses**

In `src/book0_core/models.py`, append after the existing `BookDetailsResult` dataclass:

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

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_core/models.py tests/unit/test_models.py && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/book0_core/models.py tests/unit/test_models.py
git commit -m "feat: add PagedBooksResult/PagedAuthorsResult/PagedPublishersResult dataclasses"
```

---

## Task 2: `LibraryGateway` Protocol — three new methods

**Files:**
- Modify: `src/book0_core/gateway.py`

**Interfaces:**
- Consumes: `PagedBooksResult`/`PagedAuthorsResult`/`PagedPublishersResult` from Task 1.
- Produces: the `LibraryGateway` Protocol shape that Task 6 (`SqliteLibraryGateway`) and Task 9 (`HttpLibraryGateway`) must both satisfy — `list_books_page(page, page_size, handle=None) -> PagedBooksResult`, `list_authors_page(page, page_size, handle=None) -> PagedAuthorsResult`, `list_publishers_page(page, page_size, handle=None) -> PagedPublishersResult`, `close_pagination(handle) -> None`.

There is no dedicated runtime test for a `Protocol`'s shape (structural typing is checked by `mypy`, not `pytest`) — this task's correctness is verified by Tasks 6 and 9's own tests plus a passing `uv run mypy src` at the end of each of those tasks.

- [ ] **Step 1: Update the Protocol**

Replace the full contents of `src/book0_core/gateway.py`:

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

- [ ] **Step 2: Run the full suite to confirm nothing else references the Protocol in a way that breaks**

Run: `uv run pytest -q`
Expected: PASS (nothing implements `LibraryGateway` as a type-checked variable today — see `docs/superpowers/TODO.md`'s item 3 — so this change is inert until Tasks 6/9 add the methods)

- [ ] **Step 3: Lint and type-check**

Run: `uv run ruff check . && uv run mypy src`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add src/book0_core/gateway.py
git commit -m "feat: add pagination methods to the LibraryGateway Protocol"
```

---

## Task 3: `book0_config` — `default-page-size` config key

**Files:**
- Modify: `src/book0_config/config.py`
- Test: `tests/unit/test_book0_config.py`

**Interfaces:**
- Produces: `LibraryConfig.default_page_size: int | None = None` (new field, defaulted so the existing equality-comparison test that constructs `LibraryConfig(libraries=..., default_tag=...)` with only two kwargs keeps passing unmodified). Consumed by Task 8 (`book0_api`) and Task 11 (`book0_cli`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_book0_config.py`:

```python
def test_load_libraries_returns_none_default_page_size_when_absent(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\n'
    )

    config = load_libraries(config_path)

    assert config.default_page_size is None


def test_load_libraries_reads_default_page_size_when_present(tmp_path: Path):
    config_path = tmp_path / "libraries.toml"
    config_path.write_text(
        'default-page-size = 25\n\n'
        '[libraries]\nfiction = "/path/to/fiction/metadata.db"\n'
    )

    config = load_libraries(config_path)

    assert config.default_page_size == 25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_config.py -v`
Expected: FAIL — `test_load_libraries_reads_default_page_size_when_present` fails on `assert config.default_page_size == 25` (attribute doesn't exist yet); the "absent" test may pass vacuously or error depending on dataclass state, don't rely on it to prove much until Step 4.

- [ ] **Step 3: Add the field**

In `src/book0_config/config.py`, change:

```python
@dataclass(frozen=True)
class LibraryConfig:
    libraries: dict[str, Path]
    default_tag: str | None
```

to:

```python
@dataclass(frozen=True)
class LibraryConfig:
    libraries: dict[str, Path]
    default_tag: str | None
    default_page_size: int | None = None
```

And change `load_libraries`'s return statement from:

```python
    return LibraryConfig(libraries=libraries, default_tag=data.get("default-library"))
```

to:

```python
    return LibraryConfig(
        libraries=libraries,
        default_tag=data.get("default-library"),
        default_page_size=data.get("default-page-size"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_config.py -v`
Expected: PASS, including the pre-existing `test_load_libraries_returns_tag_to_path_mapping_with_no_default_tag` (which constructs `LibraryConfig(libraries=..., default_tag=None)` without a third argument) — confirm it is still green, unmodified.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (231+ tests, no regressions)

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_config/config.py tests/unit/test_book0_config.py && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/book0_config/config.py tests/unit/test_book0_config.py
git commit -m "feat: add default-page-size config key to LibraryConfig"
```

---

## Task 4: `book0_cli_remote/config.py` — client-side `default-page-size` loader

**Files:**
- Modify: `src/book0_cli_remote/config.py`
- Test: `tests/unit/test_cli_remote_config.py`

**Interfaces:**
- Produces: `load_default_page_size(config_path: Path) -> int | None`, mirroring `load_cover_cache_dir`'s exact shape. Consumed by Task 12 (`book0_cli_remote/main.py`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_cli_remote_config.py`, and add `load_default_page_size` to the existing `from book0_cli_remote.config import (...)` block at the top:

```python
def test_load_default_page_size_returns_the_configured_value(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text(
        'server = "http://127.0.0.1:8000"\ndefault-page-size = 25\n'
    )

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

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_remote_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_default_page_size'`

- [ ] **Step 3: Add the function**

In `src/book0_cli_remote/config.py`, append after `load_cover_cache_dir`:

```python
def load_default_page_size(config_path: Path) -> int | None:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    value = data.get("default-page-size")
    return int(value) if value is not None else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_remote_config.py -v`
Expected: PASS

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_cli_remote/config.py tests/unit/test_cli_remote_config.py && uv run mypy src`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/book0_cli_remote/config.py tests/unit/test_cli_remote_config.py
git commit -m "feat: add load_default_page_size to book0_cli_remote config loader"
```

---

## Task 5: Shared test fixture — a library big enough to paginate

**Files:**
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `paginated_calibre_metadata_db(tmp_path: Path) -> Path` pytest fixture — a fresh Calibre-shaped SQLite file with 7 books, 7 authors (one each), and 7 publishers (one each), titled/named `"Book 01"`..`"Book 07"` / `"Author 01"`..`"Author 07"` / `"Publisher 01"`..`"Publisher 07"` so lexical sort order matches numeric order. At `page_size=2` this yields 4 pages (`2, 2, 2, 1`) for every one of the three resources — satisfies the spec's "at least 3 pages at a small page size" requirement. Consumed by Task 6 (`SqliteLibraryGateway` integration tests), Task 9 (`HttpLibraryGateway` integration tests), Task 8 (e2e tests), Tasks 11/12 (CLI integration tests).

- [ ] **Step 1: Add the fixture**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def paginated_calibre_metadata_db(tmp_path: Path) -> Path:
    """A Calibre-shaped library with 7 books/authors/publishers - enough
    rows to exercise more than one page at a small page_size (e.g. 4 pages
    of 2 at page_size=2), unlike the 3-book calibre_metadata_db fixture."""
    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                pubdate TEXT
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
            """
        )
        connection.executemany(
            "INSERT INTO books (id, title, pubdate) VALUES (?, ?, ?)",
            [(i, f"Book {i:02d}", None) for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO authors (id, name) VALUES (?, ?)",
            [(i, f"Author {i:02d}") for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO books_authors_link (book, author) VALUES (?, ?)",
            [(i, i) for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO publishers (id, name) VALUES (?, ?)",
            [(i, f"Publisher {i:02d}") for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO books_publishers_link (book, publisher) VALUES (?, ?)",
            [(i, i) for i in range(1, 8)],
        )
        connection.commit()
    finally:
        connection.close()
    return db_path
```

- [ ] **Step 2: Confirm the fixture loads without errors**

Run: `uv run pytest --fixtures tests/conftest.py 2>&1 | grep -A2 paginated_calibre_metadata_db`
Expected: the fixture is listed with its docstring; no collection errors from `uv run pytest -q` (should still show the same 231 passed as before this task, since nothing consumes the fixture yet)

- [ ] **Step 3: Lint and format**

Run: `uv run ruff check . && uv run ruff format --check tests/conftest.py`
Expected: no errors (note: `tests/conftest.py` has a pre-existing, unrelated formatting issue on lines ~82/97/117 from before this feature — do not let `ruff format` touch those in this commit; run `ruff format --check` only, and if you use `ruff format` on the whole file, review the diff and revert any hunks outside the fixture you just added)

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add paginated_calibre_metadata_db fixture for multi-page coverage"
```

---

## Task 6: `SqliteLibraryGateway` — persistent connection + pagination

This is the largest task. Split into two steps internally (connection refactor, then pagination), but one task/commit pair each since the second depends entirely on the first and neither is independently shippable as "done" — actually, split into two commits for reviewability:

### Task 6a: Persistent connection refactor (no new public behavior)

**Files:**
- Modify: `src/book0_core/sqlite_gateway.py`

**Interfaces:**
- Produces: `SqliteLibraryGateway._connect(self) -> sqlite3.Connection` (private) — opens the connection once per instance and reuses it; existing public methods (`list_books`, `list_authors`, `list_publishers`, `get_book_details`) keep their exact signatures and behavior (verified by the full existing test suite passing unmodified).

- [ ] **Step 1: Confirm the baseline is green**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py tests/integration/test_cli_main.py -v`
Expected: PASS (this is the safety net for the refactor — no test changes in this step)

- [ ] **Step 2: Refactor to a persistent, lazily-opened connection**

In `src/book0_core/sqlite_gateway.py`, add `self._connection: sqlite3.Connection | None = None` to `__init__`:

```python
    def __init__(self, library_path: Path) -> None:
        self._db_path = (
            library_path / "metadata.db" if library_path.is_dir() else library_path
        )
        self._connection: sqlite3.Connection | None = None
```

Add a new private method right after `__init__`:

```python
    def _connect(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise LibraryNotFoundError(f"Calibre library not found: {self._db_path}")
        if self._connection is None:
            self._connection = sqlite3.connect(
                f"file:{self._db_path}?mode=ro", uri=True
            )
            self._check_is_calibre_library(self._connection)
        return self._connection
```

Replace `list_books`:

```python
    def list_books(self) -> list[Book]:
        connection = self._connect()
        rows = connection.execute(_LIST_BOOKS_QUERY).fetchall()
        return [self._row_to_book(row) for row in rows]
```

(This introduces a small new private helper, `_row_to_book`, reused by the paginated method in Task 6b — add it now, right after `list_books`:)

```python
    def _row_to_book(self, row: tuple[object, ...]) -> Book:
        return Book(
            id=str(row[0]),
            title=row[1],  # type: ignore[arg-type]
            authors=tuple(row[2].split(", ")) if row[2] else (),
            pubdate=self._normalize_pubdate(row[3]),  # type: ignore[arg-type]
        )
```

Replace `list_authors`:

```python
    def list_authors(self) -> list[Author]:
        connection = self._connect()
        rows = connection.execute(_LIST_AUTHORS_QUERY).fetchall()
        return [Author(id=str(row[0]), name=row[1]) for row in rows]
```

Replace `list_publishers`:

```python
    def list_publishers(self) -> list[Publisher]:
        connection = self._connect()
        rows = connection.execute(_LIST_PUBLISHERS_QUERY).fetchall()
        return [Publisher(id=str(row[0]), name=row[1]) for row in rows]
```

Replace the top of `get_book_details` (only the connection-acquisition part; the rest of the method body after computing `rows` stays exactly as-is):

```python
    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        deduped_ids, valid_ids = self._partition_ids(ids)

        connection = self._connect()
        placeholders = ", ".join("?" for _ in valid_ids)
        query = _GET_BOOK_DETAILS_QUERY_TEMPLATE.format(placeholders=placeholders)
        rows = connection.execute(query, valid_ids).fetchall()
```

(Delete the old `if not self._db_path.exists(): raise LibraryNotFoundError(...)` guard and the `try/finally: connection.close()` block from all four methods — `_connect()` now owns both the existence check and the connection lifetime.)

- [ ] **Step 3: Run the full existing test suite to confirm zero behavior change**

Run: `uv run pytest -q`
Expected: PASS, same test count as before this task (231 or however many Task 1-5 added, minus zero regressions) — every existing `LibraryNotFoundError`/`NotACalibreLibraryError` test must still pass exactly as before, since `_connect()` re-checks `self._db_path.exists()` on every call even though it only opens the connection once.

- [ ] **Step 4: Add one new regression test proving connection reuse across calls**

Add to `tests/integration/test_sqlite_gateway.py`:

```python
def test_list_books_then_list_authors_reuse_the_same_connection(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    gateway.list_books()
    first_connection = gateway._connection
    gateway.list_authors()
    second_connection = gateway._connection

    assert first_connection is not None
    assert first_connection is second_connection
```

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: PASS

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_core/sqlite_gateway.py tests/integration/test_sqlite_gateway.py && uv run mypy src`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/book0_core/sqlite_gateway.py tests/integration/test_sqlite_gateway.py
git commit -m "refactor: make SqliteLibraryGateway's connection persistent per instance"
```

### Task 6b: Pagination methods + session mechanism

**Files:**
- Modify: `src/book0_core/sqlite_gateway.py`
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: `PagedBooksResult`/`PagedAuthorsResult`/`PagedPublishersResult` (Task 1), `paginated_calibre_metadata_db` fixture (Task 5), `SqliteLibraryGateway._connect()`/`_row_to_book()` (Task 6a).
- Produces: `SqliteLibraryGateway.list_books_page(page, page_size, handle=None) -> PagedBooksResult`, `.list_authors_page(...)`, `.list_publishers_page(...)`, `.close_pagination(handle) -> None`. Consumed directly by Task 11 (`book0_cli`) and Task 8 (`book0_api`).

**Design decisions locked in for this task** (the spec left these to planning):
- Handle range: the simplest option the spec explicitly sanctions — a handle is servable only for **exactly the next page** after the one it was returned from, for the same resource and `page_size`. Anything else (unknown handle, wrong resource, wrong `page_size`, a non-adjacent page) falls back to a fresh, correct, direct fetch.
- `total_pages`/`has_more_than_shown`: a capped `COUNT(*)` query (`SELECT COUNT(*) FROM (SELECT id FROM <table> LIMIT ?)` with `? = max_counted_pages * page_size`); if the returned count hits the cap, `total_pages=None`/`has_more_than_shown=True`, otherwise `total_pages=ceil(count/page_size)`/`has_more_than_shown=False`.
- `max_counted_pages` (real default `100`) and the session clock are constructor-only keyword parameters (`max_counted_pages: int = 100`, `clock: Callable[[], float] = time.monotonic`) — not part of the `LibraryGateway` Protocol, purely for test injection (a small `max_counted_pages` lets a test hit the cap with a handful of rows instead of hundreds; an injectable clock lets a test simulate the 60s timeout without sleeping).
- `close_pagination` is idempotent and silent on an unknown handle.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_sqlite_gateway.py` (add `PagedBooksResult` etc. are not imported directly — tests assert on fields of the returned dataclass instances, so no new import needed beyond what's already imported for `SqliteLibraryGateway`):

```python
def test_list_books_page_returns_the_first_page_directly(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_books_page(1, 2)

    assert [book.title for book in result.items] == ["Book 01", "Book 02"]
    assert result.page == 1
    assert result.page_size == 2
    assert result.total_pages == 4
    assert result.has_more_than_shown is False
    assert result.handle is not None


def test_list_books_page_handle_reuse_pulls_from_the_open_cursor_without_a_new_select(
    paginated_calibre_metadata_db: Path,
):
    # The first page always costs one bounded LIMIT/OFFSET query, and continuing to
    # the very next page costs one more (opening the continuation cursor lazily) - so
    # the *third* page from the same session is where reuse becomes provably free:
    # only reading further from that already-open cursor via fetchmany, no new SELECT.
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    first = gateway.list_books_page(1, 2)
    second = gateway.list_books_page(2, 2, handle=first.handle)

    connection = gateway._connect()
    execute_calls: list[tuple[object, ...]] = []
    original_execute = connection.execute

    def _counting_execute(*args, **kwargs):
        execute_calls.append(args)
        return original_execute(*args, **kwargs)

    connection.execute = _counting_execute  # type: ignore[method-assign]

    third = gateway.list_books_page(3, 2, handle=second.handle)

    assert [book.title for book in third.items] == ["Book 05", "Book 06"]
    # _count_pages always runs its own COUNT query, every call - filter that out and
    # assert no *list*-query SELECT was newly issued for this reused page:
    list_query_calls = [call for call in execute_calls if "COUNT" not in call[0]]
    assert list_query_calls == []


def test_list_books_page_falls_back_correctly_when_handle_is_out_of_range(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    first = gateway.list_books_page(1, 2)

    # Page 4, not page 2 - out of the "exactly next page" range this handle covers.
    result = gateway.list_books_page(4, 2, handle=first.handle)

    assert [book.title for book in result.items] == ["Book 07"]
    assert result.handle is None  # last page, nothing more to serve


def test_list_books_page_falls_back_when_handle_is_from_a_different_page_size(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    first = gateway.list_books_page(1, 2)

    result = gateway.list_books_page(2, 3, handle=first.handle)

    assert [book.title for book in result.items] == ["Book 04", "Book 05", "Book 06"]


def test_list_books_page_falls_back_when_handle_is_unknown(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_books_page(2, 2, handle="not-a-real-handle")

    assert [book.title for book in result.items] == ["Book 03", "Book 04"]


def test_list_books_page_cold_jump_to_a_later_page_returns_correct_rows(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_books_page(3, 2)

    assert [book.title for book in result.items] == ["Book 05", "Book 06"]
    assert result.page == 3


def test_list_books_page_total_pages_is_none_past_the_counted_cap(
    paginated_calibre_metadata_db: Path,
):
    # 7 books, page_size=2, max_counted_pages=2 -> cap = 4 rows, count (7) >= cap.
    gateway = SqliteLibraryGateway(
        paginated_calibre_metadata_db, max_counted_pages=2
    )

    result = gateway.list_books_page(1, 2)

    assert result.total_pages is None
    assert result.has_more_than_shown is True


def test_list_authors_page_returns_the_first_page(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_authors_page(1, 3)

    assert [author.name for author in result.items] == [
        "Author 01",
        "Author 02",
        "Author 03",
    ]
    assert result.total_pages == 3


def test_list_publishers_page_returns_the_first_page(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.list_publishers_page(1, 3)

    assert [publisher.name for publisher in result.items] == [
        "Publisher 01",
        "Publisher 02",
        "Publisher 03",
    ]
    assert result.total_pages == 3


def test_close_pagination_releases_the_session(paginated_calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)
    first = gateway.list_books_page(1, 2)

    gateway.close_pagination(first.handle)

    assert first.handle not in gateway._sessions
    # Behaves as if the handle was never given - falls back to a correct direct fetch:
    result = gateway.list_books_page(2, 2, handle=first.handle)
    assert [book.title for book in result.items] == ["Book 03", "Book 04"]


def test_close_pagination_is_silent_on_an_unknown_handle(
    paginated_calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(paginated_calibre_metadata_db)

    result = gateway.close_pagination("not-a-real-handle")

    assert result is None  # did not raise, degraded silently


def test_list_books_page_expires_a_session_after_the_timeout(
    paginated_calibre_metadata_db: Path,
):
    fake_time = [0.0]
    gateway = SqliteLibraryGateway(
        paginated_calibre_metadata_db, clock=lambda: fake_time[0]
    )
    first = gateway.list_books_page(1, 2)
    assert first.handle in gateway._sessions

    fake_time[0] = 61.0  # past the 60s session timeout
    result = gateway.list_books_page(2, 2, handle=first.handle)

    # The expired session was dropped before the handle could even be checked - this
    # call fell back to a correct fresh fetch, not a resumed one.
    assert first.handle not in gateway._sessions
    assert [book.title for book in result.items] == ["Book 03", "Book 04"]


def test_list_books_page_raises_library_not_found_error(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_books_page(1, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v -k page`
Expected: FAIL with `AttributeError: 'SqliteLibraryGateway' object has no attribute 'list_books_page'`

- [ ] **Step 3: Implement the pagination mechanism**

In `src/book0_core/sqlite_gateway.py`, update the imports at the top:

```python
import re
import sqlite3
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
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

Add three new query constants right after `_GET_BOOK_DETAILS_QUERY_TEMPLATE`:

```python
_COUNT_BOOKS_QUERY = "SELECT COUNT(*) FROM (SELECT id FROM books LIMIT ?)"
_COUNT_AUTHORS_QUERY = "SELECT COUNT(*) FROM (SELECT id FROM authors LIMIT ?)"
_COUNT_PUBLISHERS_QUERY = "SELECT COUNT(*) FROM (SELECT id FROM publishers LIMIT ?)"

_DEFAULT_MAX_COUNTED_PAGES = 100
_SESSION_TIMEOUT_SECONDS = 60.0
```

Add a small session dataclass right before `class SqliteLibraryGateway`:

```python
@dataclass
class _PaginationSession:
    resource: str
    page_size: int
    expected_next_page: int
    rows_generator: Iterator[list[tuple[object, ...]]]
    last_access: float
```

Update `__init__` (from Task 6a's version) to accept the two new keyword-only parameters and initialize the session table, using `secrets` for handle generation (add `import secrets` alongside the other stdlib imports above):

```python
    def __init__(
        self,
        library_path: Path,
        *,
        max_counted_pages: int = _DEFAULT_MAX_COUNTED_PAGES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db_path = (
            library_path / "metadata.db" if library_path.is_dir() else library_path
        )
        self._connection: sqlite3.Connection | None = None
        self._max_counted_pages = max_counted_pages
        self._clock = clock
        self._sessions: dict[str, _PaginationSession] = {}
```

Add the three public paginated methods and `close_pagination` right after `list_publishers`:

```python
    def list_books_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult:
        rows, out_handle, total_pages, has_more = self._paged_rows(
            resource="books",
            query=_LIST_BOOKS_QUERY,
            count_query=_COUNT_BOOKS_QUERY,
            page=page,
            page_size=page_size,
            handle=handle,
        )
        return PagedBooksResult(
            items=tuple(self._row_to_book(row) for row in rows),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=out_handle,
        )

    def list_authors_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult:
        rows, out_handle, total_pages, has_more = self._paged_rows(
            resource="authors",
            query=_LIST_AUTHORS_QUERY,
            count_query=_COUNT_AUTHORS_QUERY,
            page=page,
            page_size=page_size,
            handle=handle,
        )
        return PagedAuthorsResult(
            items=tuple(Author(id=str(row[0]), name=row[1]) for row in rows),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=out_handle,
        )

    def list_publishers_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult:
        rows, out_handle, total_pages, has_more = self._paged_rows(
            resource="publishers",
            query=_LIST_PUBLISHERS_QUERY,
            count_query=_COUNT_PUBLISHERS_QUERY,
            page=page,
            page_size=page_size,
            handle=handle,
        )
        return PagedPublishersResult(
            items=tuple(Publisher(id=str(row[0]), name=row[1]) for row in rows),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more_than_shown=has_more,
            handle=out_handle,
        )

    def close_pagination(self, handle: str) -> None:
        session = self._sessions.pop(handle, None)
        if session is not None:
            session.rows_generator.close()

    def _paged_rows(
        self,
        *,
        resource: str,
        query: str,
        count_query: str,
        page: int,
        page_size: int,
        handle: str | None,
    ) -> tuple[list[tuple[object, ...]], str | None, int | None, bool]:
        connection = self._connect()
        self._expire_stale_sessions()

        session = self._sessions.get(handle) if handle is not None else None
        if (
            session is not None
            and session.resource == resource
            and session.page_size == page_size
            and session.expected_next_page == page
        ):
            rows = next(session.rows_generator)
            session.expected_next_page += 1
            session.last_access = self._clock()
            active_handle = handle
        else:
            generator = self._paged_rows_generator(connection, query, page_size, page)
            rows = next(generator)
            active_handle = secrets.token_hex(16)
            self._sessions[active_handle] = _PaginationSession(
                resource=resource,
                page_size=page_size,
                expected_next_page=page + 1,
                rows_generator=generator,
                last_access=self._clock(),
            )

        total_pages, has_more = self._count_pages(connection, count_query, page_size)
        out_handle: str | None = active_handle
        if total_pages is not None and page >= total_pages:
            out_handle = None
        if out_handle is None:
            self.close_pagination(active_handle)
        return rows, out_handle, total_pages, has_more

    @staticmethod
    def _paged_rows_generator(
        connection: sqlite3.Connection, query: str, page_size: int, start_page: int
    ) -> Iterator[list[tuple[object, ...]]]:
        # First page: one bounded LIMIT/OFFSET query, seeked directly to start_page -
        # no more expensive than today's unpaginated query, just bounded. Every
        # subsequent page this same generator yields (i.e. reused via a handle) then
        # pulls from one already-open, unbounded-from-here cursor via fetchmany - no
        # new SELECT per continued page. The cursor is opened lazily (only once the
        # caller actually continues past the first page), not on every fresh fetch.
        offset = (start_page - 1) * page_size
        first_rows = connection.execute(
            f"{query} LIMIT ? OFFSET ?", (page_size, offset)
        ).fetchall()
        yield first_rows

        cursor = connection.execute(f"{query} LIMIT -1 OFFSET ?", (offset + page_size,))
        while True:
            yield cursor.fetchmany(page_size)

    def _count_pages(
        self, connection: sqlite3.Connection, count_query: str, page_size: int
    ) -> tuple[int | None, bool]:
        cap = self._max_counted_pages * page_size
        count = connection.execute(count_query, (cap,)).fetchone()[0]
        if count >= cap:
            return None, True
        return -(-count // page_size), False

    def _expire_stale_sessions(self) -> None:
        now = self._clock()
        expired = [
            handle
            for handle, session in self._sessions.items()
            if now - session.last_access > _SESSION_TIMEOUT_SECONDS
        ]
        for handle in expired:
            self._sessions.pop(handle).rows_generator.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v -k page`
Expected: PASS for all new tests

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, no regressions

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_core/sqlite_gateway.py tests/integration/test_sqlite_gateway.py && uv run mypy src`
Expected: no errors. If `mypy` complains about `Iterator[list[tuple[object, ...]]]` vs. the `sqlite3.Cursor.fetchall()` inferred type, add a local `# type: ignore[...]` with the exact error code shown, matching the existing file's style of narrowly-scoped `# type: ignore[index]`/`# type: ignore[arg-type]` comments rather than a broad ignore.

- [ ] **Step 7: Commit**

```bash
git add src/book0_core/sqlite_gateway.py tests/integration/test_sqlite_gateway.py
git commit -m "feat: add list_*_page/close_pagination to SqliteLibraryGateway"
```

---

## Task 7: `book0_api.schemas` — paged wire schemas

**Files:**
- Modify: `src/book0_api/schemas.py`
- Test: `tests/unit/test_book0_api_schemas.py` (check if it exists first: `ls tests/unit/ | grep schema`; add to it if so, else create it)

**Interfaces:**
- Consumes: `PagedBooksResult`/`PagedAuthorsResult`/`PagedPublishersResult` (Task 1), `BookOut`/`AuthorOut`/`PublisherOut` (existing).
- Produces: `PagedBooksOut.from_paged_result(result: PagedBooksResult) -> PagedBooksOut`, `PagedAuthorsOut.from_paged_result(...)`, `PagedPublishersOut.from_paged_result(...)`. Consumed by Task 8 (`book0_api/main.py`).

- [ ] **Step 1: Write the failing tests**

Create/append to `tests/unit/test_book0_api_schemas.py`:

```python
from book0_api.schemas import PagedAuthorsOut, PagedBooksOut, PagedPublishersOut
from book0_core.models import (
    Author,
    Book,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
)


def test_paged_books_out_maps_every_field():
    book = Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01")
    result = PagedBooksResult(
        items=(book,),
        page=2,
        page_size=10,
        total_pages=5,
        has_more_than_shown=False,
        handle="abc123",
    )

    out = PagedBooksOut.from_paged_result(result)

    assert len(out.items) == 1
    assert out.items[0].id == "1"
    assert out.items[0].title == "Dune"
    assert out.items[0].authors == ["Frank Herbert"]
    assert out.items[0].pubdate == "1965-08-01"
    assert out.page == 2
    assert out.page_size == 10
    assert out.total_pages == 5
    assert out.has_more_than_shown is False


def test_paged_books_out_reports_none_total_pages_when_capped():
    result = PagedBooksResult(
        items=(),
        page=1,
        page_size=10,
        total_pages=None,
        has_more_than_shown=True,
        handle=None,
    )

    out = PagedBooksOut.from_paged_result(result)

    assert out.total_pages is None
    assert out.has_more_than_shown is True


def test_paged_authors_out_maps_every_field():
    author = Author(id="1", name="Frank Herbert")
    result = PagedAuthorsResult(
        items=(author,), page=1, page_size=5, total_pages=1, has_more_than_shown=False,
        handle=None,
    )

    out = PagedAuthorsOut.from_paged_result(result)

    assert out.items[0].id == "1"
    assert out.items[0].name == "Frank Herbert"
    assert out.page == 1


def test_paged_publishers_out_maps_every_field():
    publisher = Publisher(id="1", name="Ace Books")
    result = PagedPublishersResult(
        items=(publisher,), page=1, page_size=5, total_pages=1,
        has_more_than_shown=False, handle=None,
    )

    out = PagedPublishersOut.from_paged_result(result)

    assert out.items[0].id == "1"
    assert out.items[0].name == "Ace Books"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'PagedBooksOut'`

- [ ] **Step 3: Add the schemas**

First, update the `from book0_core.models import (...)` block at the top of `src/book0_api/schemas.py` to add the three result types directly (matching the file's existing style of importing every `book0_core.models` type it uses, no quoted forward refs needed):

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

Then append to `src/book0_api/schemas.py`:

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
    def from_paged_result(
        cls, result: PagedPublishersResult
    ) -> "PagedPublishersOut":
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, no regressions

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_api/schemas.py tests/unit/test_book0_api_schemas.py && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/book0_api/schemas.py tests/unit/test_book0_api_schemas.py
git commit -m "feat: add PagedBooksOut/PagedAuthorsOut/PagedPublishersOut wire schemas"
```

---

## Task 8: `book0_api` — paginated routes + server-side page-size resolution

**Files:**
- Modify: `src/book0_api/main.py`
- Modify: `src/book0_api/asgi.py`
- Test: `tests/e2e/test_book0_api_main.py`

**Interfaces:**
- Consumes: `SqliteLibraryGateway.list_books_page`/etc. (Task 6b), `PagedBooksOut`/etc. (Task 7), `LibraryConfig.default_page_size` (Task 3).
- Produces: `create_app(libraries, default_tag=None, default_page_size=None) -> FastAPI` (new third parameter, defaulted so every existing call site keeps working); `GET /libraries/books|authors|publishers` gain `page: int | None = None` and `page_size: int | None = None` query params.

- [ ] **Step 1: Write the failing tests**

Add to `tests/e2e/test_book0_api_main.py`:

```python
def test_list_books_returns_a_page_when_page_size_is_given(
    paginated_calibre_metadata_db: Path,
):
    app = create_app({"fiction": paginated_calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page": 2, "page_size": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["items"]] == ["Book 03", "Book 04"]
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert body["total_pages"] == 4
    assert body["has_more_than_shown"] is False


def test_list_books_is_unpaginated_when_page_size_is_omitted(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    assert response.status_code == 200
    assert isinstance(response.json(), list)  # unchanged shape - not a paged envelope


def test_list_books_server_default_page_size_caps_a_larger_client_request(
    paginated_calibre_metadata_db: Path,
):
    app = create_app(
        {"fiction": paginated_calibre_metadata_db}, default_page_size=2
    )
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page_size": 10}
    )

    body = response.json()
    assert body["page_size"] == 2  # server cap wins
    assert len(body["items"]) == 2


def test_list_books_server_default_page_size_forces_pagination_when_client_omits_it(
    paginated_calibre_metadata_db: Path,
):
    app = create_app(
        {"fiction": paginated_calibre_metadata_db}, default_page_size=3
    )
    client = TestClient(app)

    response = client.get("/libraries/books", params={"tag": "fiction"})

    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 3
    assert len(body["items"]) == 3


def test_list_authors_returns_a_page_when_page_size_is_given(
    paginated_calibre_metadata_db: Path,
):
    app = create_app({"fiction": paginated_calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/authors", params={"tag": "fiction", "page": 1, "page_size": 3}
    )

    body = response.json()
    assert [item["name"] for item in body["items"]] == [
        "Author 01",
        "Author 02",
        "Author 03",
    ]
    assert body["total_pages"] == 3


def test_list_publishers_returns_a_page_when_page_size_is_given(
    paginated_calibre_metadata_db: Path,
):
    app = create_app({"fiction": paginated_calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/publishers", params={"tag": "fiction", "page": 1, "page_size": 3}
    )

    body = response.json()
    assert [item["name"] for item in body["items"]] == [
        "Publisher 01",
        "Publisher 02",
        "Publisher 03",
    ]
    assert body["total_pages"] == 3


def test_list_books_normalizes_a_non_positive_page_to_one(
    paginated_calibre_metadata_db: Path,
):
    app = create_app({"fiction": paginated_calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page": 0, "page_size": 2}
    )

    body = response.json()
    assert body["page"] == 1
    assert [item["title"] for item in body["items"]] == ["Book 01", "Book 02"]


def test_list_books_treats_a_non_positive_page_size_as_unpaginated(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books", params={"tag": "fiction", "page_size": 0}
    )

    assert isinstance(response.json(), list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v -k page`
Expected: FAIL — `page`/`page_size` params are accepted by FastAPI already (unused query params are ignored, not rejected) but the response is always the unpaginated `list[BookOut]` shape, so assertions like `body["items"]` (a dict, not a list) fail with `TypeError`/`KeyError`.

- [ ] **Step 3: Implement server-side resolution and the paginated routes**

In `src/book0_api/main.py`, update the `create_app` signature and add the two resolver closures right after `_resolve_db_path`:

```python
def create_app(
    libraries: dict[str, Path],
    default_tag: str | None = None,
    default_page_size: int | None = None,
) -> FastAPI:
    app = FastAPI()

    def _resolve_db_path(tag: str | None) -> Path:
        resolved_tag = tag if tag is not None else default_tag
        if resolved_tag is None:
            raise TagRequiredError(
                "No tag given and no default-library configured for this server"
            )
        db_path = libraries.get(resolved_tag)
        if db_path is None:
            raise TagRequiredError(f"Unknown library tag: {resolved_tag!r}")
        return db_path

    def _resolve_page_size(page_size: int | None) -> int | None:
        if default_page_size is not None:
            effective = (
                min(page_size, default_page_size)
                if page_size is not None
                else default_page_size
            )
        else:
            effective = page_size
        return effective if effective is not None and effective > 0 else None

    def _resolve_page(page: int | None) -> int:
        resolved = page if page is not None else 1
        return resolved if resolved > 0 else 1
```

Replace `list_books` with:

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

        gateway = SqliteLibraryGateway(db_path)
        effective_page_size = _resolve_page_size(page_size)
        try:
            if effective_page_size is None:
                books = gateway.list_books()
            else:
                paged_books = gateway.list_books_page(
                    _resolve_page(page), effective_page_size
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
        return PagedBooksOut.from_paged_result(paged_books)
```

Replace `list_authors` with the mirrored version:

```python
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

        gateway = SqliteLibraryGateway(db_path)
        effective_page_size = _resolve_page_size(page_size)
        try:
            if effective_page_size is None:
                authors = gateway.list_authors()
            else:
                paged_authors = gateway.list_authors_page(
                    _resolve_page(page), effective_page_size
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
        return PagedAuthorsOut.from_paged_result(paged_authors)
```

Replace `list_publishers` with the mirrored version:

```python
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

        gateway = SqliteLibraryGateway(db_path)
        effective_page_size = _resolve_page_size(page_size)
        try:
            if effective_page_size is None:
                publishers = gateway.list_publishers()
            else:
                paged_publishers = gateway.list_publishers_page(
                    _resolve_page(page), effective_page_size
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
        return PagedPublishersOut.from_paged_result(paged_publishers)
```

Update the `from book0_api.schemas import (...)` block at the top of the file to add the three new schemas:

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
```

(`get_book_details` and `get_book_cover` are untouched by this task - pagination doesn't reach those routes.)

- [ ] **Step 4: Update `book0_api/asgi.py` to pass the new config field**

Change `src/book0_api/asgi.py`'s last line:

```python
app = create_app(config.libraries, config.default_tag, config.default_page_size)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: PASS, all new and existing tests

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, no regressions

- [ ] **Step 7: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_api/main.py src/book0_api/asgi.py tests/e2e/test_book0_api_main.py && uv run mypy src`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add src/book0_api/main.py src/book0_api/asgi.py tests/e2e/test_book0_api_main.py
git commit -m "feat: add pagination query params to book0_api's list routes"
```

---

## Task 9: `HttpLibraryGateway` — stateless paginated client methods

**Files:**
- Modify: `src/book0_cli_remote/http_gateway.py`
- Test: `tests/integration/test_http_gateway.py`

**Interfaces:**
- Consumes: `PagedBooksResult`/etc. (Task 1), the `book0_api` routes from Task 8.
- Produces: `HttpLibraryGateway.list_books_page(page, page_size, handle=None) -> PagedBooksResult`, `.list_authors_page(...)`, `.list_publishers_page(...)`, `.close_pagination(handle) -> None` (no-op). Consumed by Task 12 (`book0_cli_remote/main.py`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_http_gateway.py`:

```python
def test_list_books_page_returns_the_requested_page(
    paginated_calibre_metadata_db: Path,
):
    client = _client_for({"fiction": paginated_calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.list_books_page(2, 2)

    assert [book.title for book in result.items] == ["Book 03", "Book 04"]
    assert result.page == 2
    assert result.page_size == 2
    assert result.total_pages == 4
    assert result.has_more_than_shown is False


def test_list_books_page_never_sends_the_caller_supplied_handle_over_the_wire(
    paginated_calibre_metadata_db: Path,
):
    client = _client_for({"fiction": paginated_calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    sent_requests = []
    original_get = client.get

    def _capturing_get(*args, **kwargs):
        sent_requests.append(kwargs.get("params", {}))
        return original_get(*args, **kwargs)

    client.get = _capturing_get  # type: ignore[method-assign]

    gateway.list_books_page(1, 2, handle="some-client-side-handle-should-not-be-sent")

    assert all("handle" not in params for params in sent_requests)


def test_list_authors_page_returns_the_requested_page(
    paginated_calibre_metadata_db: Path,
):
    client = _client_for({"fiction": paginated_calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.list_authors_page(1, 3)

    assert [author.name for author in result.items] == [
        "Author 01",
        "Author 02",
        "Author 03",
    ]


def test_list_publishers_page_returns_the_requested_page(
    paginated_calibre_metadata_db: Path,
):
    client = _client_for({"fiction": paginated_calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.list_publishers_page(1, 3)

    assert [publisher.name for publisher in result.items] == [
        "Publisher 01",
        "Publisher 02",
        "Publisher 03",
    ]


def test_list_books_page_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_books_page(1, 2)


def test_close_pagination_is_a_no_op(paginated_calibre_metadata_db: Path):
    client = _client_for({"fiction": paginated_calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.close_pagination("anything")

    assert result is None  # did not raise, no network call needed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_http_gateway.py -v -k page`
Expected: FAIL with `AttributeError: 'HttpLibraryGateway' object has no attribute 'list_books_page'`

- [ ] **Step 3: Implement the three methods + no-op `close_pagination`**

In `src/book0_cli_remote/http_gateway.py`, update the `from book0_core.models import (...)` block to add the three result types:

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

Add a small private helper right after `_params`:

```python
    def _page_params(self, page: int, page_size: int) -> dict[str, str | int]:
        params: dict[str, str | int] = dict(self._params())
        params["page"] = page
        params["page_size"] = page_size
        return params
```

Add the three paginated methods and `close_pagination` right after `list_publishers`:

```python
    def list_books_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult:
        response = self._client.get(
            "/libraries/books", params=self._page_params(page, page_size)
        )

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        body = response.json()
        return PagedBooksResult(
            items=tuple(
                Book(
                    id=row["id"],
                    title=row["title"],
                    authors=tuple(row["authors"]),
                    pubdate=row["pubdate"],
                )
                for row in body["items"]
            ),
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
            "/libraries/authors", params=self._page_params(page, page_size)
        )

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        body = response.json()
        return PagedAuthorsResult(
            items=tuple(
                Author(id=row["id"], name=row["name"]) for row in body["items"]
            ),
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
            "/libraries/publishers", params=self._page_params(page, page_size)
        )

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        body = response.json()
        return PagedPublishersResult(
            items=tuple(
                Publisher(id=row["id"], name=row["name"]) for row in body["items"]
            ),
            page=body["page"],
            page_size=body["page_size"],
            total_pages=body["total_pages"],
            has_more_than_shown=body["has_more_than_shown"],
            handle=None,
        )

    def close_pagination(self, handle: str) -> None:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_http_gateway.py -v -k page`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, no regressions

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_cli_remote/http_gateway.py tests/integration/test_http_gateway.py && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/book0_cli_remote/http_gateway.py tests/integration/test_http_gateway.py
git commit -m "feat: add list_*_page/close_pagination to HttpLibraryGateway"
```

---

## Task 10: `book0_presentation.tables` — page-footer rendering

**Files:**
- Modify: `src/book0_presentation/tables.py`
- Test: `tests/unit/test_tables.py`

**Interfaces:**
- Produces: `render_page_footer(page: int, total_pages: int | None) -> str`. Consumed by Task 11 (`book0_cli`) and Task 12 (`book0_cli_remote`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_tables.py`:

```python
def test_render_page_footer_with_a_known_total():
    assert render_page_footer(3, 12) == "Page 3 of 12"


def test_render_page_footer_with_an_unknown_total():
    assert render_page_footer(3, None) == "Page 3 of many"
```

(Add `render_page_footer` to the existing `from book0_presentation.tables import (...)` block at the top of the test file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tables.py -v -k footer`
Expected: FAIL with `ImportError: cannot import name 'render_page_footer'`

- [ ] **Step 3: Implement it**

Append to `src/book0_presentation/tables.py`:

```python
def render_page_footer(page: int, total_pages: int | None) -> str:
    if total_pages is None:
        return f"Page {page} of many"
    return f"Page {page} of {total_pages}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tables.py -v -k footer`
Expected: PASS

- [ ] **Step 5: Run the full suite, lint, and type-check**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: PASS, no errors

- [ ] **Step 6: Commit**

```bash
git add src/book0_presentation/tables.py tests/unit/test_tables.py
git commit -m "feat: add render_page_footer for paginated list output"
```

---

## Task 11: `book0` (local CLI) — `--page`/`--page-size`

**Files:**
- Modify: `src/book0_cli/main.py`
- Test: `tests/integration/test_cli_main.py`

**Interfaces:**
- Consumes: `SqliteLibraryGateway.list_books_page`/etc. (Task 6b), `config.default_page_size` (Task 3, via `LibraryConfig`), `render_page_footer` (Task 10).

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_cli_main.py` (adjust the `_write_config` helper call pattern to match however the existing file writes a `.book0.toml` — check the file's existing helper first and reuse it; if it takes a single tag/path pair, write the TOML directly for the `default-page-size` cases instead):

```python
def test_run_prints_a_page_and_footer_when_page_size_flag_is_given(
    paginated_calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-library = "fiction"\n\n'
        f'[libraries]\nfiction = "{paginated_calibre_metadata_db}"\n'
    )

    exit_code = run(["--page", "2", "--page-size", "2"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Book 03" in out
    assert "Book 04" in out
    assert "Book 01" not in out
    assert "Page 2 of 4" in out


def test_run_uses_default_page_size_from_config_when_flag_is_omitted(
    paginated_calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-library = "fiction"\n'
        f'default-page-size = 3\n\n'
        f'[libraries]\nfiction = "{paginated_calibre_metadata_db}"\n'
    )

    exit_code = run([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page 1 of 3" in out
    assert out.count("Book ") == 3 + 1  # 3 book rows + the footer's own "Book" count is 0, keep simple:


def test_run_is_unpaginated_when_no_page_size_is_resolvable(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-library = "fiction"\n\n'
        f'[libraries]\nfiction = "{calibre_metadata_db}"\n'
    )

    exit_code = run(["--page", "1"])  # --page alone, no resolvable page-size

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page" not in out  # no footer - behaves as fully unpaginated


def test_run_normalizes_a_non_positive_page_to_one(
    paginated_calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-library = "fiction"\n\n'
        f'[libraries]\nfiction = "{paginated_calibre_metadata_db}"\n'
    )

    exit_code = run(["--page", "0", "--page-size", "2"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page 1 of 4" in out
    assert "Book 01" in out


def test_run_treats_a_non_positive_page_size_as_unpaginated(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-library = "fiction"\n\n'
        f'[libraries]\nfiction = "{calibre_metadata_db}"\n'
    )

    exit_code = run(["--page-size", "0"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page" not in out
```

Before running, fix the flaky assertion in the second test (`out.count("Book ")` is a fragile way to count rows) - replace its body's final assertion block with an exact match instead:

```python
def test_run_uses_default_page_size_from_config_when_flag_is_omitted(
    paginated_calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0.toml").write_text(
        f'default-library = "fiction"\n'
        f'default-page-size = 3\n\n'
        f'[libraries]\nfiction = "{paginated_calibre_metadata_db}"\n'
    )

    exit_code = run([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page 1 of 3" in out
    assert "Book 01" in out
    assert "Book 03" in out
    assert "Book 04" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_main.py -v -k page`
Expected: FAIL with `SystemExit` / argparse "unrecognized arguments: --page" (the flag doesn't exist yet)

- [ ] **Step 3: Add the flags and resolution logic**

In `src/book0_cli/main.py`, add `--page`/`--page-size` to the three relevant subparsers in `_build_parser`:

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--tag", help=_TAG_HELP)
    books_parser.add_argument("--page", type=int, help="page number (1-based)")
    books_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--tag", help=_TAG_HELP)
    authors_parser.add_argument("--page", type=int, help="page number (1-based)")
    authors_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--tag", help=_TAG_HELP)
    publishers_parser.add_argument("--page", type=int, help="page number (1-based)")
    publishers_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

    books_detail_parser = subparsers.add_parser("books-detail")
    books_detail_parser.add_argument(
        "--ids", required=True, help="comma-separated list of book ids"
    )
    books_detail_parser.add_argument("--tag", help=_TAG_HELP)

    return parser
```

Add `render_page_footer` to the `from book0_presentation.tables import (...)` block at the top of the file.

Replace the dispatch block inside `run` (the `if args.command == "authors": ... else: print(render_book_table(...))` section) with:

```python
        page_size = getattr(args, "page_size", None)
        if page_size is None:
            page_size = config.default_page_size
        if page_size is not None and page_size <= 0:
            page_size = None
        page = getattr(args, "page", None)
        if page is None:
            page = 1
        if page <= 0:
            page = 1

        if args.command == "authors":
            if page_size is not None:
                paged = gateway.list_authors_page(page, page_size)
                print(render_author_table(list(paged.items)))
                print(render_page_footer(paged.page, paged.total_pages))
            else:
                print(render_author_table(gateway.list_authors()))
        elif args.command == "publishers":
            if page_size is not None:
                paged = gateway.list_publishers_page(page, page_size)
                print(render_publisher_table(list(paged.items)))
                print(render_page_footer(paged.page, paged.total_pages))
            else:
                print(render_publisher_table(gateway.list_publishers()))
        elif args.command == "books-detail":
            ids = (
                [segment.strip() for segment in args.ids.split(",")] if args.ids else []
            )
            result = gateway.get_book_details(ids)
            ordered_books = order_book_details_by_ids(result, ids)
            print(render_book_details_table(ordered_books))
            missing_ids_message = format_missing_ids_message(result.missing_ids)
            if missing_ids_message is not None:
                print(missing_ids_message)
        else:
            if page_size is not None:
                paged = gateway.list_books_page(page, page_size)
                print(render_book_table(list(paged.items)))
                print(render_page_footer(paged.page, paged.total_pages))
            else:
                print(render_book_table(gateway.list_books()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_main.py -v -k page`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, no regressions

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_cli/main.py tests/integration/test_cli_main.py && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/book0_cli/main.py tests/integration/test_cli_main.py
git commit -m "feat: add --page/--page-size to book0's books/authors/publishers subcommands"
```

---

## Task 12: `book0-remote` — `--page`/`--page-size`

**Files:**
- Modify: `src/book0_cli_remote/main.py`
- Test: `tests/integration/test_cli_remote_main.py`

**Interfaces:**
- Consumes: `HttpLibraryGateway.list_books_page`/etc. (Task 9), `load_default_page_size` (Task 4), `render_page_footer` (Task 10).

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_cli_remote_main.py`:

```python
def test_run_prints_a_page_and_footer_when_page_size_flag_is_given(
    paginated_calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": paginated_calibre_metadata_db}))

    exit_code = run(
        [
            "--server", "unused", "--tag", "fiction",
            "--page", "2", "--page-size", "2",
        ],
        client=client,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Book 03" in out
    assert "Book 04" in out
    assert "Page 2 of 4" in out


def test_run_uses_default_page_size_from_client_config_when_flag_is_omitted(
    paginated_calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text(
        'server = "http://127.0.0.1:8000"\ndefault-page-size = 3\n'
    )
    client = TestClient(create_app({"fiction": paginated_calibre_metadata_db}))

    exit_code = run(["--server", "unused", "--tag", "fiction"], client=client)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page 1 of 3" in out
    assert "Book 01" in out
    assert "Book 04" not in out


def test_run_is_unpaginated_when_no_page_size_is_resolvable(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["--server", "unused", "--tag", "fiction", "--page", "1"], client=client
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page" not in out


def test_run_normalizes_a_non_positive_page_to_one(
    paginated_calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": paginated_calibre_metadata_db}))

    exit_code = run(
        [
            "--server", "unused", "--tag", "fiction",
            "--page", "0", "--page-size", "2",
        ],
        client=client,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page 1 of 4" in out
    assert "Book 01" in out


def test_run_treats_a_non_positive_page_size_as_unpaginated(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["--server", "unused", "--tag", "fiction", "--page-size", "0"],
        client=client,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page" not in out
```

Add `render_page_footer` to the test file's `from book0_presentation.tables import (...)` block if it asserts against it directly (these tests assert on raw substrings instead, so no import change is strictly required — but check the file's existing import block for consistency and add it if other tests there already import table-rendering helpers to build expected strings).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v -k page`
Expected: FAIL with argparse "unrecognized arguments: --page"

- [ ] **Step 3: Add the flags and resolution logic**

In `src/book0_cli_remote/main.py`, add `--page`/`--page-size` to the three relevant subparsers in `_build_parser`:

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0-remote")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--server", help=_SERVER_HELP)
    books_parser.add_argument("--tag")
    books_parser.add_argument("--page", type=int, help="page number (1-based)")
    books_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--server", help=_SERVER_HELP)
    authors_parser.add_argument("--tag")
    authors_parser.add_argument("--page", type=int, help="page number (1-based)")
    authors_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--server", help=_SERVER_HELP)
    publishers_parser.add_argument("--tag")
    publishers_parser.add_argument("--page", type=int, help="page number (1-based)")
    publishers_parser.add_argument(
        "--page-size", type=int, help="page size; enables pagination for this call"
    )

    books_detail_parser = subparsers.add_parser("books-detail")
    books_detail_parser.add_argument(
        "--ids", required=True, help="comma-separated list of book ids"
    )
    books_detail_parser.add_argument("--server", help=_SERVER_HELP)
    books_detail_parser.add_argument("--tag")
    books_detail_parser.add_argument(
        "--with-covers",
        action="store_true",
        help="download and cache covers for the requested books",
    )

    return parser
```

Update the `from book0_cli_remote.config import (...)` block to add `load_default_page_size`, and the `from book0_presentation.tables import (...)` block to add `render_page_footer`.

Add page-size resolution right before the `gateway = HttpLibraryGateway(...)` line inside `run`, and update the dispatch block, replacing this section:

```python
        gateway = HttpLibraryGateway(
            client,
            args.tag,
            with_covers=getattr(args, "with_covers", False),
            cache_dir=cache_dir,
        )
        try:
            if args.command == "authors":
                print(render_author_table(gateway.list_authors()))
            elif args.command == "publishers":
                print(render_publisher_table(gateway.list_publishers()))
            elif args.command == "books-detail":
                ids = (
                    [segment.strip() for segment in args.ids.split(",")]
                    if args.ids
                    else []
                )
                result = gateway.get_book_details(ids)
                ordered_books = order_book_details_by_ids(result, ids)
                print(render_book_details_table(ordered_books))
                missing_ids_message = format_missing_ids_message(result.missing_ids)
                if missing_ids_message is not None:
                    print(missing_ids_message)
            else:
                print(render_book_table(gateway.list_books()))
```

with:

```python
        page_size = getattr(args, "page_size", None)
        if page_size is None and args.command != "books-detail":
            page_size_config_path = find_config_file()
            if page_size_config_path is not None:
                try:
                    page_size = load_default_page_size(page_size_config_path)
                except tomllib.TOMLDecodeError as error:
                    print(
                        f"Invalid book0-remote client config file "
                        f"{page_size_config_path}: {error}",
                        file=sys.stderr,
                    )
                    return 1
        if page_size is not None and page_size <= 0:
            page_size = None
        page = getattr(args, "page", None)
        if page is None:
            page = 1
        if page <= 0:
            page = 1

        gateway = HttpLibraryGateway(
            client,
            args.tag,
            with_covers=getattr(args, "with_covers", False),
            cache_dir=cache_dir,
        )
        try:
            if args.command == "authors":
                if page_size is not None:
                    paged = gateway.list_authors_page(page, page_size)
                    print(render_author_table(list(paged.items)))
                    print(render_page_footer(paged.page, paged.total_pages))
                else:
                    print(render_author_table(gateway.list_authors()))
            elif args.command == "publishers":
                if page_size is not None:
                    paged = gateway.list_publishers_page(page, page_size)
                    print(render_publisher_table(list(paged.items)))
                    print(render_page_footer(paged.page, paged.total_pages))
                else:
                    print(render_publisher_table(gateway.list_publishers()))
            elif args.command == "books-detail":
                ids = (
                    [segment.strip() for segment in args.ids.split(",")]
                    if args.ids
                    else []
                )
                result = gateway.get_book_details(ids)
                ordered_books = order_book_details_by_ids(result, ids)
                print(render_book_details_table(ordered_books))
                missing_ids_message = format_missing_ids_message(result.missing_ids)
                if missing_ids_message is not None:
                    print(missing_ids_message)
            else:
                if page_size is not None:
                    paged = gateway.list_books_page(page, page_size)
                    print(render_book_table(list(paged.items)))
                    print(render_page_footer(paged.page, paged.total_pages))
                else:
                    print(render_book_table(gateway.list_books()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v -k page`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, no regressions

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check src/book0_cli_remote/main.py tests/integration/test_cli_remote_main.py && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/book0_cli_remote/main.py tests/integration/test_cli_remote_main.py
git commit -m "feat: add --page/--page-size to book0-remote's books/authors/publishers subcommands"
```

---

## Task 13: Documentation catch-up

**Files:**
- Modify: `README.md`
- Modify: `book0-libraries.toml`
- Modify: `.claude/rules/architecture.md`
- Modify: `docs/superpowers/TODO.md`

No tests in this task (documentation only) — verify by reading the diffs, not by running `pytest`.

- [ ] **Step 1: Update `README.md`**

In the `## \`book0\` - direct CLI` section, after the existing `default-library` paragraph, add a paragraph and update the example command block to show `--page`/`--page-size`, e.g.:

```markdown
Add `--page-size N` to paginate `books`/`authors`/`publishers` output N rows at a time
(`--page` selects which page, defaulting to 1); a config file may set
`default-page-size` so `--page-size` can be omitted. `books-detail` is never paginated.
```

Add the equivalent paragraph to the `## \`book0-remote\` + \`book0_api\` - HTTP-backed CLI` section, noting that `book0-libraries.toml`'s `default-page-size` acts as a server-side ceiling on top of the client's own `default-page-size`/`--page-size`.

- [ ] **Step 2: Update `book0-libraries.toml`**

Add a commented example after the existing `default-library` comment block:

```toml
# Optional: a server-side ceiling on page_size for the three list routes (books,
# authors, publishers) when pagination is requested via ?page_size=... - also forces
# pagination even when a request omits page_size entirely, protecting the server from
# an unbounded query.
# default-page-size = 100
```

- [ ] **Step 3: Update `.claude/rules/architecture.md`**

Update the `gateway.py` line to mention the three new methods and `close_pagination`; update the `models.py` line to mention `PagedBooksResult`/`PagedAuthorsResult`/`PagedPublishersResult`; update the `book0_config/config.py` line to mention `default_page_size`; update the `book0_api/main.py` line to mention the `page`/`page_size` query params; update the `book0_cli_remote/config.py` line to mention `load_default_page_size`; update the `book0_cli/main.py` and `book0_cli_remote/main.py` lines to mention `--page`/`--page-size`. Follow the file's exact existing comment-alignment style (trailing `#`-aligned comments within the code-fenced tree).

- [ ] **Step 4: Update `docs/superpowers/TODO.md`**

Refile the narrower remainder of the item this design absorbed (per the design spec's "Purpose" section) as a new TODO entry:

```markdown
- [ ] **(undesigned) `books-detail` field projection.** The part of the old
  "`books-detail` response projection + pagination" TODO item that
  `docs/superpowers/specs/2026-08-20-list-pagination-design.md` deliberately did not
  absorb: an `--ids-only` mode, a future file-path/download field, description/abstract
  text. No design exists yet; revisit via brainstorming when picked up.
```

- [ ] **Step 5: Final full-repo verification**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: full suite green, no lint/type errors

- [ ] **Step 6: Commit**

```bash
git add README.md book0-libraries.toml .claude/rules/architecture.md docs/superpowers/TODO.md
git commit -m "docs: document --page/--page-size and default-page-size"
```

---

## Final step: open the pull request

Per `.claude/rules/workflow.md`'s new-feature rule, this branch (`feature/list-pagination`) gets a PR instead of a direct merge to `main`:

```bash
git push -u origin feature/list-pagination
gh pr create --title "Add pagination to books/authors/publishers listing" --body "$(cat <<'EOF'
## Summary
- Adds list_books_page/list_authors_page/list_publishers_page + close_pagination to the
  LibraryGateway Protocol, both gateway implementations, book0_api, and both CLIs.
- SqliteLibraryGateway gets a persistent per-instance connection and generator-backed
  pagination sessions (advisory handle, 60s lazy timeout).
- New default-page-size config key (.book0.toml, book0-libraries.toml,
  .book0-client.toml) with server-side capping/forcing.
- See docs/superpowers/specs/2026-08-20-list-pagination-design.md for the full design.

## Test plan
- [ ] uv run pytest
- [ ] uv run ruff check .
- [ ] uv run mypy src
EOF
)"
```
