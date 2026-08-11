# Authors List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Authors list to book0 that mirrors the existing Books list at every layer —
domain model, gateway (SQLite + HTTP), API route, table rendering, and CLI subcommand — on
both `book0` and `book0-remote`.

**Architecture:** `book0_core.models.Author` (frozen dataclass, `id` + `name`) flows through a
new `list_authors()` method on the `LibraryGateway` Protocol, implemented identically in
`SqliteLibraryGateway` (a plain `SELECT id, name FROM authors ORDER BY name`, no join needed)
and `HttpLibraryGateway` (`GET /libraries/{tag}/authors`, same error reconstruction as
`list_books`). `book0_api` exposes the new route with the same unknown-tag/404/500 shape as
the books route. `book0_presentation.tables` gains `render_author_table` alongside a renamed
`render_book_table` (was `render_table`). Both CLIs grow `books`/`authors` argparse
subcommands, defaulting to `books` so today's invocations keep working unchanged.

**Tech Stack:** Python 3.12, stdlib `sqlite3`/`argparse`, FastAPI + Pydantic, `httpx`,
`pytest`, `uv`.

## Global Constraints

- Every command goes through `uv run <tool>` — never a bare `python`/`pytest`/`ruff`/`mypy`.
- `book0_core` never opens `metadata.db` for write (`mode=ro` always).
- `book0_core` never depends on `book0_cli`, `book0_cli_remote`, `book0_api`, or `argparse`.
- `book0_api`'s routes stay plain `def` (never `async def`) — `SqliteLibraryGateway` does
  blocking I/O.
- `book0_api` never returns a raw `sqlite3.OperationalError` or unmapped 500 — every
  `book0_core` domain error it recognizes maps to the documented status code + body.
- `book0_cli` and `book0_cli_remote` do not share a run-loop function — this is deliberate,
  not duplication to fix.
- Every new function/class ships with a test in the same commit (unit/integration/e2e as
  appropriate — see `.claude/rules/testing.md`).
- Ship no config option, flag, or abstraction the spec did not ask for (no book count, no
  book-titles-per-author, no sort-key option).

---

### Task 1: `Author` domain model

**Files:**
- Modify: `src/book0_core/models.py:1-9`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `book0_core.models.Author(id: int, name: str)`, frozen dataclass, used by every
  later task.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_models.py`:

```python
from book0_core.models import Author


def test_author_holds_id_and_name():
    author = Author(id=1, name="Frank Herbert")

    assert author.id == 1
    assert author.name == "Frank Herbert"


def test_author_is_frozen():
    author = Author(id=1, name="Frank Herbert")

    with pytest.raises(AttributeError):
        author.name = "Other"
```

(Add `Author` to the existing `from book0_core.models import Book` import line rather than a
second import line: `from book0_core.models import Author, Book`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Author'`

- [ ] **Step 3: Implement `Author`**

`src/book0_core/models.py` becomes:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    id: int
    title: str
    authors: tuple[str, ...]
    pubdate: str | None


@dataclass(frozen=True)
class Author:
    id: int
    name: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: PASS (5 tests: 3 existing `Book` tests + 2 new `Author` tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/models.py tests/unit/test_models.py
git commit -m "feat: add Author domain model"
```

---

### Task 2: `LibraryGateway.list_authors` + `SqliteLibraryGateway.list_authors`

**Files:**
- Modify: `src/book0_core/gateway.py:1-7`
- Modify: `src/book0_core/sqlite_gateway.py:1-62`
- Modify: `tests/conftest.py`
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: `Author` from Task 1.
- Produces: `LibraryGateway.list_authors() -> list[Author]` (Protocol method every
  implementation must have); `SqliteLibraryGateway.list_authors() -> list[Author]`;
  `tests.conftest.CALIBRE_LIBRARY_AUTHORS: list[Author]` (fixture data every later test task
  imports).

- [ ] **Step 1: Add the fixture data other tasks will import**

In `tests/conftest.py`, change the import line and add the constant, right after
`CALIBRE_LIBRARY_BOOKS`:

```python
from book0_core.models import Author, Book
```

```python
# Authors as inserted into the fixture DB, already in the order list_authors()
# is expected to return them (sorted by name).
CALIBRE_LIBRARY_AUTHORS = [
    Author(id=1, name="Frank Herbert"),
    Author(id=2, name="J.R.R. Tolkien"),
    Author(id=3, name="Neil Gaiman"),
    Author(id=4, name="Terry Pratchett"),
]
```

(The `authors` table rows in `calibre_metadata_db` are already inserted in this order — see
the existing `executemany` in the same file — so no fixture-schema change is needed.)

- [ ] **Step 2: Write the failing tests**

Append to `tests/integration/test_sqlite_gateway.py`, and add `CALIBRE_LIBRARY_AUTHORS` to
the existing `from tests.conftest import CALIBRE_LIBRARY_BOOKS` import line:

```python
def test_list_authors_returns_authors_sorted_by_name(calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    assert gateway.list_authors() == CALIBRE_LIBRARY_AUTHORS


def test_list_authors_opens_the_database_read_only(
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

    gateway.list_authors()

    assert captured_calls == [(f"file:{calibre_metadata_db}?mode=ro", True)]


def test_missing_file_raises_library_not_found_error_for_authors(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_authors()


def test_non_calibre_sqlite_file_raises_not_a_calibre_library_error_for_authors(
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
        gateway.list_authors()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: FAIL with `AttributeError: 'SqliteLibraryGateway' object has no attribute
'list_authors'`

- [ ] **Step 4: Implement `list_authors` on the Protocol and the SQLite gateway**

`src/book0_core/gateway.py` becomes:

```python
from typing import Protocol

from book0_core.models import Author, Book


class LibraryGateway(Protocol):
    def list_books(self) -> list[Book]: ...
    def list_authors(self) -> list[Author]: ...
```

In `src/book0_core/sqlite_gateway.py`: change `from book0_core.models import Book` to
`from book0_core.models import Author, Book`; add the query constant next to
`_LIST_BOOKS_QUERY`:

```python
_LIST_AUTHORS_QUERY = "SELECT id, name FROM authors ORDER BY name"
```

Add the method to `SqliteLibraryGateway` (after `list_books`, before `_normalize_pubdate`):

```python
    def list_authors(self) -> list[Author]:
        if not self._db_path.exists():
            raise LibraryNotFoundError(f"Calibre library not found: {self._db_path}")

        connection = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            self._check_is_calibre_library(connection)
            rows = connection.execute(_LIST_AUTHORS_QUERY).fetchall()
        finally:
            connection.close()

        return [Author(id=row[0], name=row[1]) for row in rows]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: PASS (all tests, existing books tests + 4 new authors tests)

- [ ] **Step 6: Commit**

```bash
git add src/book0_core/gateway.py src/book0_core/sqlite_gateway.py tests/conftest.py \
    tests/integration/test_sqlite_gateway.py
git commit -m "feat: add list_authors to LibraryGateway and SqliteLibraryGateway"
```

---

### Task 3: `AuthorOut` API schema

**Files:**
- Modify: `src/book0_api/schemas.py:1-19`
- Test: `tests/unit/test_book0_api_schemas.py`

**Interfaces:**
- Consumes: `Author` from Task 1.
- Produces: `book0_api.schemas.AuthorOut(id: int, name: str)` with
  `AuthorOut.from_author(author: Author) -> AuthorOut`, used by Task 4's route.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_book0_api_schemas.py`, adding `AuthorOut` and `Author` to the
existing import lines:

```python
def test_from_author_converts_author_to_author_out():
    author = Author(id=3, name="Neil Gaiman")

    author_out = AuthorOut.from_author(author)

    assert author_out == AuthorOut(id=3, name="Neil Gaiman")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'AuthorOut'`

- [ ] **Step 3: Implement `AuthorOut`**

Add to `src/book0_api/schemas.py` (change the model import line to
`from book0_core.models import Author, Book`):

```python
class AuthorOut(BaseModel):
    id: int
    name: str

    @classmethod
    def from_author(cls, author: Author) -> "AuthorOut":
        return cls(id=author.id, name=author.name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/schemas.py tests/unit/test_book0_api_schemas.py
git commit -m "feat: add AuthorOut API schema"
```

---

### Task 4: `GET /libraries/{tag}/authors` route

**Files:**
- Modify: `src/book0_api/main.py:1-36`
- Test: `tests/e2e/test_book0_api_main.py`

**Interfaces:**
- Consumes: `AuthorOut` from Task 3, `SqliteLibraryGateway.list_authors` from Task 2.
- Produces: `GET /libraries/{tag}/authors` — same response shape as the books route (unknown
  tag → `[]`; `LibraryNotFoundError` → 404 `{"error": "LibraryNotFoundError", "detail": ...}`;
  `NotACalibreLibraryError` → 500 `{"error": "NotACalibreLibraryError", "detail": ...}`;
  success → `list[AuthorOut]`), used by Task 5's `HttpLibraryGateway`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/e2e/test_book0_api_main.py`, adding `CALIBRE_LIBRARY_AUTHORS` to the existing
`from tests.conftest import CALIBRE_LIBRARY_BOOKS` import line:

```python
def test_list_authors_returns_expected_authors_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/fiction/authors")

    assert response.status_code == 200
    assert response.json() == [
        {"id": author.id, "name": author.name} for author in CALIBRE_LIBRARY_AUTHORS
    ]


def test_list_authors_returns_empty_list_for_an_unknown_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/does-not-exist/authors")

    assert response.status_code == 200
    assert response.json() == []


def test_list_authors_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/fiction/authors")

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_authors_returns_500_when_configured_path_is_not_a_calibre_library(
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

    response = client.get("/libraries/fiction/authors")

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: FAIL with 404 "Not Found" (no route registered) instead of the asserted bodies

- [ ] **Step 3: Implement the route**

`src/book0_api/main.py` becomes:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from book0_api.schemas import AuthorOut, BookOut
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.sqlite_gateway import SqliteLibraryGateway


def create_app(libraries: dict[str, Path]) -> FastAPI:
    app = FastAPI()

    @app.get("/libraries/{tag}/books", response_model=None)
    def list_books(tag: str) -> list[BookOut] | JSONResponse:
        db_path = libraries.get(tag)
        if db_path is None:
            return []

        gateway = SqliteLibraryGateway(db_path)
        try:
            books = gateway.list_books()
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

        return [BookOut.from_book(book) for book in books]

    @app.get("/libraries/{tag}/authors", response_model=None)
    def list_authors(tag: str) -> list[AuthorOut] | JSONResponse:
        db_path = libraries.get(tag)
        if db_path is None:
            return []

        gateway = SqliteLibraryGateway(db_path)
        try:
            authors = gateway.list_authors()
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

        return [AuthorOut.from_author(author) for author in authors]

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: PASS (all books tests + 4 new authors tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/main.py tests/e2e/test_book0_api_main.py
git commit -m "feat: add GET /libraries/{tag}/authors route"
```

---

### Task 5: `HttpLibraryGateway.list_authors`

**Files:**
- Modify: `src/book0_cli_remote/http_gateway.py:1-34`
- Test: `tests/integration/test_http_gateway.py`

**Interfaces:**
- Consumes: `Author` from Task 1, the `/libraries/{tag}/authors` route from Task 4.
- Produces: `HttpLibraryGateway.list_authors() -> list[Author]`, used by Task 8's CLI.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_http_gateway.py`, adding `CALIBRE_LIBRARY_AUTHORS` to the
existing `from tests.conftest import CALIBRE_LIBRARY_BOOKS` import line:

```python
def test_list_authors_returns_expected_authors_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_authors() == CALIBRE_LIBRARY_AUTHORS


def test_list_authors_returns_empty_list_for_an_unknown_tag(calibre_metadata_db: Path):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    assert gateway.list_authors() == []


def test_list_authors_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_authors()


def test_list_authors_raises_not_a_calibre_library_error(tmp_path: Path):
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
        gateway.list_authors()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: FAIL with `AttributeError: 'HttpLibraryGateway' object has no attribute
'list_authors'`

- [ ] **Step 3: Implement `list_authors`**

`src/book0_cli_remote/http_gateway.py` becomes:

```python
import httpx

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.models import Author, Book

_ERROR_TYPES = {
    "LibraryNotFoundError": LibraryNotFoundError,
    "NotACalibreLibraryError": NotACalibreLibraryError,
}


class HttpLibraryGateway:
    def __init__(self, client: httpx.Client, tag: str) -> None:
        self._client = client
        self._tag = tag

    def list_books(self) -> list[Book]:
        response = self._client.get(f"/libraries/{self._tag}/books")

        if response.status_code in (404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [
            Book(
                id=row["id"],
                title=row["title"],
                authors=tuple(row["authors"]),
                pubdate=row["pubdate"],
            )
            for row in response.json()
        ]

    def list_authors(self) -> list[Author]:
        response = self._client.get(f"/libraries/{self._tag}/authors")

        if response.status_code in (404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [Author(id=row["id"], name=row["name"]) for row in response.json()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: PASS (all books tests + 4 new authors tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/http_gateway.py tests/integration/test_http_gateway.py
git commit -m "feat: add list_authors to HttpLibraryGateway"
```

---

### Task 6: `render_author_table` + rename `render_table` to `render_book_table`

**Files:**
- Modify: `src/book0_presentation/tables.py:1-34`
- Modify: `src/book0_cli/main.py` (import + one call site only — subcommands come in Task 7)
- Modify: `src/book0_cli_remote/main.py` (import + one call site only — subcommands come in
  Task 8)
- Modify: `tests/integration/test_cli_main.py` (import line only)
- Modify: `tests/integration/test_cli_remote_main.py` (import line only)
- Test: `tests/unit/test_tables.py`

**Interfaces:**
- Consumes: `Author` from Task 1.
- Produces: `render_book_table(books: list[Book]) -> str` (renamed from `render_table`),
  `render_author_table(authors: list[Author]) -> str`, both used by Tasks 7 and 8.

This task renames `render_table` and must update every caller in the same commit, or the
repo is left with a broken import between commits.

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `tests/unit/test_tables.py` with:

```python
from book0_core.models import Author, Book
from book0_presentation.tables import render_author_table, render_book_table


def test_render_book_table_aligns_columns_with_headers():
    books = [
        Book(id=1, title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01"),
        Book(
            id=3,
            title="Good Omens",
            authors=("Neil Gaiman", "Terry Pratchett"),
            pubdate="1990-05-01",
        ),
        Book(id=2, title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None),
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
            id=1,
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
        Book(id=1, title="Dune", authors=("Frank Herbert",), pubdate=None),
    ]

    output = render_book_table(books)

    assert output == "ID  Title  Author(s)      Pub Date\n1   Dune   Frank Herbert"


def test_render_author_table_aligns_columns_with_headers():
    authors = [
        Author(id=1, name="Frank Herbert"),
        Author(id=3, name="Neil Gaiman"),
        Author(id=2, name="J.R.R. Tolkien"),
    ]

    output = render_author_table(authors)

    assert output == (
        "ID  Name\n1   Frank Herbert\n3   Neil Gaiman\n2   J.R.R. Tolkien"
    )


def test_render_author_table_reports_empty_library():
    assert render_author_table([]) == "No authors found."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_author_table'`

- [ ] **Step 3: Implement the rename and the new renderer**

Replace the full contents of `src/book0_presentation/tables.py` with:

```python
from datetime import datetime

from book0_core.models import Author, Book

_BOOK_HEADERS = ("ID", "Title", "Author(s)", "Pub Date")
_AUTHOR_HEADERS = ("ID", "Name")
_COLUMN_GAP = "  "


def _format_pubdate(pubdate: str | None) -> str:
    if pubdate is None:
        return ""
    return datetime.fromisoformat(pubdate).date().isoformat()


def _align_rows(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    table = [headers] + rows
    widths = [max(len(row[i]) for row in table) for i in range(len(headers))]
    lines = [
        _COLUMN_GAP.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in table
    ]
    return "\n".join(lines)


def render_book_table(books: list[Book]) -> str:
    if not books:
        return "No books found."

    rows = [
        (
            str(book.id),
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

    rows = [(str(author.id), author.name) for author in authors]
    return _align_rows(_AUTHOR_HEADERS, rows)
```

Now fix the two callers so the repo still imports cleanly:

In `src/book0_cli/main.py`, change:
```python
from book0_presentation.tables import render_table
```
to:
```python
from book0_presentation.tables import render_book_table
```
and change:
```python
    print(render_table(books))
```
to:
```python
    print(render_book_table(books))
```

In `src/book0_cli_remote/main.py`, make the same two changes (import line and the
`print(render_table(books))` call site).

And in the two integration test files, update the import line only (no other changes yet —
Task 7/8 add the new test cases):

In `tests/integration/test_cli_main.py`, change
`from book0_presentation.tables import render_table` to
`from book0_presentation.tables import render_book_table`, and every
`render_table(CALIBRE_LIBRARY_BOOKS)` call in that file to `render_book_table(CALIBRE_LIBRARY_BOOKS)`.

In `tests/integration/test_cli_remote_main.py`, make the same two kinds of changes (import
line, and every `render_table(CALIBRE_LIBRARY_BOOKS)` call to `render_book_table(CALIBRE_LIBRARY_BOOKS)`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tables.py tests/integration/test_cli_main.py tests/integration/test_cli_remote_main.py -v`
Expected: PASS (all tests, no import errors)

- [ ] **Step 5: Commit**

```bash
git add src/book0_presentation/tables.py src/book0_cli/main.py src/book0_cli_remote/main.py \
    tests/unit/test_tables.py tests/integration/test_cli_main.py \
    tests/integration/test_cli_remote_main.py
git commit -m "feat: add render_author_table, rename render_table to render_book_table"
```

---

### Task 7: `book0` gains `books`/`authors` subcommands (books default)

**Files:**
- Modify: `src/book0_cli/main.py`
- Test: `tests/integration/test_cli_main.py`

**Interfaces:**
- Consumes: `SqliteLibraryGateway.list_authors` (Task 2), `render_author_table` (Task 6).
- Produces: `book0 [books|authors] [--tag TAG]`; `book0 --tag foo` keeps meaning
  `book0 books --tag foo`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_cli_main.py`, and add `render_author_table` to the existing
`from book0_presentation.tables import render_book_table` import line (making it
`from book0_presentation.tables import render_author_table, render_book_table`), and add
`CALIBRE_LIBRARY_AUTHORS` to the existing `from tests.conftest import CALIBRE_LIBRARY_BOOKS`
import line:

```python
def test_run_prints_author_table_using_default_library_path_when_tag_is_omitted(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    default_library_dir = home / "Calibre Library"
    default_library_dir.mkdir(parents=True)
    shutil.copy(calibre_metadata_db, default_library_dir / "metadata.db")
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run(["authors"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out == render_author_table(CALIBRE_LIBRARY_AUTHORS) + "\n"
    )


def test_run_prints_author_table_when_tag_resolves_via_local_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["authors", "--tag", "fiction"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out == render_author_table(CALIBRE_LIBRARY_AUTHORS) + "\n"
    )


def test_run_reports_empty_library_for_authors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, pubdate TEXT);
            CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY, book INTEGER, author INTEGER
            );
            """
        )
        connection.commit()
    finally:
        connection.close()
    _write_config(tmp_path / ".book0.toml", "empty", db_path)

    exit_code = run(["authors", "--tag", "empty"])

    assert exit_code == 0
    assert capsys.readouterr().out == "No authors found.\n"


def test_run_lists_books_when_subcommand_is_explicit(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    default_library_dir = home / "Calibre Library"
    default_library_dir.mkdir(parents=True)
    shutil.copy(calibre_metadata_db, default_library_dir / "metadata.db")
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run(["books"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: FAIL — `run(["authors"])` / `run(["books"])` are rejected by the current parser
(`error: unrecognized arguments`) since there is no subcommand support yet

- [ ] **Step 3: Implement the subcommands**

Replace the full contents of `src/book0_cli/main.py` with:

```python
import argparse
import sys
import tomllib
from pathlib import Path

from book0_cli.config import (
    LOCAL_CONFIG_FILENAME,
    default_library_path,
    find_config_file,
    xdg_config_path,
)
from book0_config.config import load_libraries
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.sqlite_gateway import SqliteLibraryGateway
from book0_presentation.tables import render_author_table, render_book_table

_SUBCOMMANDS = ("books", "authors")
_TAG_HELP = (
    "library tag to look up in a .book0.toml config file; "
    "omit to use Calibre's default library"
)


def _resolve_db_path(library_path: Path) -> Path:
    if library_path.is_dir():
        return library_path / "metadata.db"
    return library_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--tag", help=_TAG_HELP)

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--tag", help=_TAG_HELP)

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv or argv[0] not in _SUBCOMMANDS:
        return ["books", *argv]
    return argv


def run(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(_normalize_argv(raw_argv))

    if args.tag is None:
        library_path = default_library_path()
    else:
        config_path = find_config_file()
        if config_path is None:
            print(
                f"No book0 config file found (looked for ./{LOCAL_CONFIG_FILENAME} "
                f"and {xdg_config_path()})",
                file=sys.stderr,
            )
            return 1

        try:
            libraries = load_libraries(config_path)
        except (tomllib.TOMLDecodeError, KeyError) as error:
            print(f"Invalid book0 config file {config_path}: {error}", file=sys.stderr)
            return 1

        tagged_library_path = libraries.get(args.tag)
        if tagged_library_path is None:
            print(f"Unknown library tag: {args.tag!r}", file=sys.stderr)
            return 1
        library_path = tagged_library_path

    db_path = _resolve_db_path(library_path)
    gateway = SqliteLibraryGateway(db_path)

    try:
        if args.command == "authors":
            print(render_author_table(gateway.list_authors()))
        else:
            print(render_book_table(gateway.list_books()))
    except (LibraryNotFoundError, NotACalibreLibraryError) as error:
        print(str(error), file=sys.stderr)
        return 1

    return 0


def main() -> None:
    sys.exit(run())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: PASS (all existing books tests still pass unchanged, plus 4 new tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli/main.py tests/integration/test_cli_main.py
git commit -m "feat: add books/authors subcommands to book0"
```

---

### Task 8: `book0-remote` gains `books`/`authors` subcommands (books default)

**Files:**
- Modify: `src/book0_cli_remote/main.py`
- Test: `tests/integration/test_cli_remote_main.py`

**Interfaces:**
- Consumes: `HttpLibraryGateway.list_authors` (Task 5), `render_author_table` (Task 6).
- Produces: `book0-remote [books|authors] --server URL --tag TAG`; `book0-remote --server url
  --tag foo` keeps meaning `book0-remote books --server url --tag foo`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_cli_remote_main.py`, and add `render_author_table` to the
existing `from book0_presentation.tables import render_book_table` import line, and add
`CALIBRE_LIBRARY_AUTHORS` to the existing `from tests.conftest import CALIBRE_LIBRARY_BOOKS`
import line:

```python
def test_run_prints_author_table_for_a_known_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["authors", "--server", "unused", "--tag", "fiction"], client=client
    )

    assert exit_code == 0
    assert (
        capsys.readouterr().out == render_author_table(CALIBRE_LIBRARY_AUTHORS) + "\n"
    )


def test_run_prints_no_authors_found_for_an_unknown_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["authors", "--server", "unused", "--tag", "does-not-exist"], client=client
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "No authors found.\n"


def test_run_lists_books_when_subcommand_is_explicit(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["books", "--server", "unused", "--tag", "fiction"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: FAIL — `run(["authors", ...])` / `run(["books", ...])` rejected by the current
parser (`error: unrecognized arguments`)

- [ ] **Step 3: Implement the subcommands**

Replace the full contents of `src/book0_cli_remote/main.py` with:

```python
import argparse
import sys

import httpx

from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_presentation.tables import render_author_table, render_book_table

_SUBCOMMANDS = ("books", "authors")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0-remote")
    subparsers = parser.add_subparsers(dest="command")

    books_parser = subparsers.add_parser("books")
    books_parser.add_argument("--server", required=True)
    books_parser.add_argument("--tag", required=True)

    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--server", required=True)
    authors_parser.add_argument("--tag", required=True)

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv or argv[0] not in _SUBCOMMANDS:
        return ["books", *argv]
    return argv


def run(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(_normalize_argv(raw_argv))

    owns_client = client is None
    if client is None:
        client = httpx.Client(base_url=args.server)

    try:
        gateway = HttpLibraryGateway(client, args.tag)
        try:
            if args.command == "authors":
                print(render_author_table(gateway.list_authors()))
            else:
                print(render_book_table(gateway.list_books()))
        except (LibraryNotFoundError, NotACalibreLibraryError) as error:
            print(str(error), file=sys.stderr)
            return 1
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            print(
                f"Could not reach the book0 server at {args.server}: {error}",
                file=sys.stderr,
            )
            return 1
    finally:
        if owns_client:
            client.close()

    return 0


def main() -> None:
    sys.exit(run())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: PASS (all existing books tests still pass unchanged, plus 3 new tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/main.py tests/integration/test_cli_remote_main.py
git commit -m "feat: add books/authors subcommands to book0-remote"
```

---

### Task 9: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`
Expected: PASS, zero failures, zero skips

- [ ] **Step 2: Lint and format**

Run: `uv run ruff check .`
Expected: no findings (fix any and re-run if there are)

Run: `uv run ruff format .`
Expected: no files reformatted (or re-run tests after it reformats anything)

- [ ] **Step 3: Type-check**

Run: `uv run mypy src`
Expected: no errors

- [ ] **Step 4: Walk the workflow.md "New feature" end-of-task checklist by hand**

Confirm each of these explicitly (this is not a command to run — it's a manual review):
- Every new function/class has a test and is used by more than a "for later" caller.
- `book0_core`'s `Author`/`list_authors` addition is reflected in **both** gateway
  implementations' tests (Task 2 + Task 5), `book0_api`'s error-mapping (Task 4), and both
  CLIs' rendering (Task 7 + Task 8) — not just one.
- No config option, flag, or abstraction was added beyond what the spec asked for.
- `book0_cli` and `book0_cli_remote` still do not share a run-loop function.

- [ ] **Step 5: Final commit if any lint/format fixes were needed**

```bash
git add -A
git commit -m "chore: apply lint/format fixes after authors list feature"
```

(Skip this step entirely if Steps 1-3 produced no changes to stage.)
