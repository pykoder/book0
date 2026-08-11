# Publishers List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Publishers list to book0 that mirrors the existing Authors list at every
layer — domain model, gateway (SQLite + HTTP), API route, table rendering, and CLI
subcommand — on both `book0` and `book0-remote`.

**Architecture:** `book0_core.models.Publisher` (frozen dataclass, `id` + `name`) flows
through a new `list_publishers()` method on the `LibraryGateway` Protocol, implemented
identically in `SqliteLibraryGateway` (a plain `SELECT id, name FROM publishers ORDER BY
name`, no join needed) and `HttpLibraryGateway` (`GET /libraries/{tag}/publishers`, same error
reconstruction as `list_authors`). `book0_api` exposes the new route with the same
unknown-tag/404/500 shape as the authors route. `book0_presentation.tables` gains
`render_publisher_table`. Both CLIs grow a third `publishers` argparse subcommand alongside
`books` (still the default) and `authors`.

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
  `publisher` field on `Book`/`BookOut`, no sort-key option).
- Design doc: `docs/superpowers/specs/2026-08-12-publishers-list-design.md`.

---

### Task 1: `Publisher` domain model

**Files:**
- Modify: `src/book0_core/models.py`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `book0_core.models.Publisher(id: int, name: str)`, frozen dataclass, used by every
  later task.

- [ ] **Step 1: Write the failing tests**

Change the import line in `tests/unit/test_models.py` and append:

```python
from book0_core.models import Author, Book, Publisher
```

```python
def test_publisher_holds_id_and_name():
    publisher = Publisher(id=1, name="Ace Books")

    assert publisher.id == 1
    assert publisher.name == "Ace Books"


def test_publisher_is_frozen():
    publisher = Publisher(id=1, name="Ace Books")

    with pytest.raises(AttributeError):
        publisher.name = "Other"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Publisher'`

- [ ] **Step 3: Implement `Publisher`**

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


@dataclass(frozen=True)
class Publisher:
    id: int
    name: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: PASS (7 tests: 5 existing `Book`/`Author` tests + 2 new `Publisher` tests)

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/models.py tests/unit/test_models.py
git commit -m "feat: add Publisher domain model"
```

---

### Task 2: `LibraryGateway.list_publishers` + `SqliteLibraryGateway.list_publishers`

**Files:**
- Modify: `src/book0_core/gateway.py`
- Modify: `src/book0_core/sqlite_gateway.py`
- Modify: `tests/conftest.py`
- Test: `tests/integration/test_sqlite_gateway.py`

**Interfaces:**
- Consumes: `Publisher` from Task 1.
- Produces: `LibraryGateway.list_publishers() -> list[Publisher]` (Protocol method every
  implementation must have); `SqliteLibraryGateway.list_publishers() -> list[Publisher]`;
  `tests.conftest.CALIBRE_LIBRARY_PUBLISHERS: list[Publisher]` (fixture data every later test
  task imports).

- [ ] **Step 1: Add the fixture data other tasks will import**

In `tests/conftest.py`, change the import line and add a `publishers` table +
`books_publishers_link` to the schema, plus the matching constant. The fixture models a book
with a publisher (Dune → Ace Books, Good Omens → Gollancz) and a book with none (The Hobbit —
Calibre allows a book with no publisher set):

```python
from book0_core.models import Author, Book, Publisher
```

```python
# Publishers as inserted into the fixture DB, already in the order
# list_publishers() is expected to return them (sorted by name). The Hobbit
# (book id 2) is deliberately left unlinked - Calibre allows a book with no
# publisher set.
CALIBRE_LIBRARY_PUBLISHERS = [
    Publisher(id=1, name="Ace Books"),
    Publisher(id=2, name="Gollancz"),
]
```

Add to the `executescript` call, after the existing `CREATE TABLE books_authors_link (...)`:

```sql
CREATE TABLE publishers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE books_publishers_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    publisher INTEGER NOT NULL
);
```

Add after the existing `books_authors_link` inserts:

```python
connection.executemany(
    "INSERT INTO publishers (id, name) VALUES (?, ?)",
    [
        (1, "Ace Books"),
        (2, "Gollancz"),
    ],
)
connection.executemany(
    "INSERT INTO books_publishers_link (book, publisher) VALUES (?, ?)",
    [(1, 1), (3, 2)],
)
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/integration/test_sqlite_gateway.py`, adding `CALIBRE_LIBRARY_PUBLISHERS` to
the existing `from tests.conftest import ...` import line:

```python
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)
```

```python
def test_list_publishers_returns_publishers_sorted_by_name(calibre_metadata_db: Path):
    gateway = SqliteLibraryGateway(calibre_metadata_db)

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_list_publishers_opens_the_database_read_only(
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

    gateway.list_publishers()

    assert captured_calls == [(f"file:{calibre_metadata_db}?mode=ro", True)]


def test_list_publishers_resolves_metadata_db_when_given_a_directory(
    calibre_metadata_db: Path,
):
    gateway = SqliteLibraryGateway(calibre_metadata_db.parent)

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_missing_file_raises_library_not_found_error_for_publishers(tmp_path: Path):
    gateway = SqliteLibraryGateway(tmp_path / "does-not-exist.db")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_publishers()


def test_non_calibre_sqlite_file_raises_not_a_calibre_library_error_for_publishers(
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
        gateway.list_publishers()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py -v`
Expected: FAIL with `AttributeError: 'SqliteLibraryGateway' object has no attribute
'list_publishers'`

- [ ] **Step 4: Implement the Protocol method and the SQLite implementation**

`src/book0_core/gateway.py` becomes:

```python
from typing import Protocol

from book0_core.models import Author, Book, Publisher


class LibraryGateway(Protocol):
    def list_books(self) -> list[Book]: ...
    def list_authors(self) -> list[Author]: ...
    def list_publishers(self) -> list[Publisher]: ...
```

In `src/book0_core/sqlite_gateway.py`, add the import and query constant:

```python
from book0_core.models import Author, Book, Publisher
```

```python
_LIST_PUBLISHERS_QUERY = "SELECT id, name FROM publishers ORDER BY name"
```

Add the method to `SqliteLibraryGateway`, right after `list_authors`:

```python
    def list_publishers(self) -> list[Publisher]:
        if not self._db_path.exists():
            raise LibraryNotFoundError(f"Calibre library not found: {self._db_path}")

        connection = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            self._check_is_calibre_library(connection)
            rows = connection.execute(_LIST_PUBLISHERS_QUERY).fetchall()
        finally:
            connection.close()

        return [Publisher(id=row[0], name=row[1]) for row in rows]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_sqlite_gateway.py tests/unit/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/book0_core/gateway.py src/book0_core/sqlite_gateway.py tests/conftest.py \
        tests/integration/test_sqlite_gateway.py
git commit -m "feat: add list_publishers to LibraryGateway and SqliteLibraryGateway"
```

---

### Task 3: `PublisherOut` API schema

**Files:**
- Modify: `src/book0_api/schemas.py`
- Test: `tests/unit/test_book0_api_schemas.py`

**Interfaces:**
- Consumes: `Publisher` from Task 1.
- Produces: `book0_api.schemas.PublisherOut(id: int, name: str)` with
  `PublisherOut.from_publisher(publisher: Publisher) -> PublisherOut`, used by Task 4.

- [ ] **Step 1: Write the failing test**

Change the import line in `tests/unit/test_book0_api_schemas.py` and append:

```python
from book0_api.schemas import AuthorOut, BookOut, PublisherOut
from book0_core.models import Author, Book, Publisher
```

```python
def test_from_publisher_converts_publisher_to_publisher_out():
    publisher = Publisher(id=1, name="Ace Books")

    publisher_out = PublisherOut.from_publisher(publisher)

    assert publisher_out == PublisherOut(id=1, name="Ace Books")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'PublisherOut'`

- [ ] **Step 3: Implement `PublisherOut`**

Add to `src/book0_api/schemas.py`, changing the model import and adding the class after
`AuthorOut`:

```python
from book0_core.models import Author, Book, Publisher
```

```python
class PublisherOut(BaseModel):
    id: int
    name: str

    @classmethod
    def from_publisher(cls, publisher: Publisher) -> "PublisherOut":
        return cls(id=publisher.id, name=publisher.name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/schemas.py tests/unit/test_book0_api_schemas.py
git commit -m "feat: add PublisherOut API schema"
```

---

### Task 4: `GET /libraries/{tag}/publishers` route

**Files:**
- Modify: `src/book0_api/main.py`
- Test: `tests/e2e/test_book0_api_main.py`

**Interfaces:**
- Consumes: `PublisherOut` from Task 3, `SqliteLibraryGateway.list_publishers` from Task 2.
- Produces: `GET /libraries/{tag}/publishers` route on the app returned by `create_app`, used
  by Task 5's `HttpLibraryGateway.list_publishers`.

- [ ] **Step 1: Write the failing tests**

Add `CALIBRE_LIBRARY_PUBLISHERS` to the existing import line in
`tests/e2e/test_book0_api_main.py`:

```python
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)
```

Append:

```python
def test_list_publishers_returns_expected_publishers_for_a_known_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/fiction/publishers")

    assert response.status_code == 200
    assert response.json() == [
        {"id": publisher.id, "name": publisher.name}
        for publisher in CALIBRE_LIBRARY_PUBLISHERS
    ]


def test_list_publishers_returns_empty_list_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/does-not-exist/publishers")

    assert response.status_code == 200
    assert response.json() == []


def test_list_publishers_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/fiction/publishers")

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_list_publishers_returns_500_when_configured_path_is_not_a_calibre_library(
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

    response = client.get("/libraries/fiction/publishers")

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: FAIL with 404 "Not Found" (route doesn't exist) on the new tests

- [ ] **Step 3: Implement the route**

In `src/book0_api/main.py`, change the schema import and add the route after `list_authors`:

```python
from book0_api.schemas import AuthorOut, BookOut, PublisherOut
```

```python
    @app.get("/libraries/{tag}/publishers", response_model=None)
    def list_publishers(tag: str) -> list[PublisherOut] | JSONResponse:
        db_path = libraries.get(tag)
        if db_path is None:
            return []

        gateway = SqliteLibraryGateway(db_path)
        try:
            publishers = gateway.list_publishers()
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

        return [PublisherOut.from_publisher(publisher) for publisher in publishers]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/main.py tests/e2e/test_book0_api_main.py
git commit -m "feat: add GET /libraries/{tag}/publishers route"
```

---

### Task 5: `HttpLibraryGateway.list_publishers`

**Files:**
- Modify: `src/book0_cli_remote/http_gateway.py`
- Test: `tests/integration/test_http_gateway.py`

**Interfaces:**
- Consumes: `Publisher` from Task 1, the route from Task 4.
- Produces: `HttpLibraryGateway.list_publishers() -> list[Publisher]`, used by Task 8.

- [ ] **Step 1: Write the failing tests**

Add `CALIBRE_LIBRARY_PUBLISHERS` to the existing import line in
`tests/integration/test_http_gateway.py`:

```python
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)
```

Append:

```python
def test_list_publishers_returns_expected_publishers_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_list_publishers_returns_empty_list_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    assert gateway.list_publishers() == []


def test_list_publishers_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_publishers()


def test_list_publishers_raises_not_a_calibre_library_error(tmp_path: Path):
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
        gateway.list_publishers()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: FAIL with `AttributeError: 'HttpLibraryGateway' object has no attribute
'list_publishers'`

- [ ] **Step 3: Implement `list_publishers`**

In `src/book0_cli_remote/http_gateway.py`, change the model import and add the method after
`list_authors`:

```python
from book0_core.models import Author, Book, Publisher
```

```python
    def list_publishers(self) -> list[Publisher]:
        response = self._client.get(f"/libraries/{self._tag}/publishers")

        if response.status_code in (404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [
            Publisher(id=row["id"], name=row["name"]) for row in response.json()
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_http_gateway.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/http_gateway.py tests/integration/test_http_gateway.py
git commit -m "feat: add list_publishers to HttpLibraryGateway"
```

---

### Task 6: `render_publisher_table`

**Files:**
- Modify: `src/book0_presentation/tables.py`
- Test: `tests/unit/test_tables.py`

**Interfaces:**
- Consumes: `Publisher` from Task 1.
- Produces: `render_publisher_table(publishers: list[Publisher]) -> str`, used by Tasks 7-8.

- [ ] **Step 1: Write the failing tests**

Change the import lines in `tests/unit/test_tables.py` and append:

```python
from book0_core.models import Author, Book, Publisher
from book0_presentation.tables import (
    render_author_table,
    render_book_table,
    render_publisher_table,
)
```

```python
def test_render_publisher_table_aligns_columns_with_headers():
    publishers = [
        Publisher(id=1, name="Ace Books"),
        Publisher(id=2, name="Gollancz"),
    ]

    output = render_publisher_table(publishers)

    assert output == "ID  Name\n1   Ace Books\n2   Gollancz"


def test_render_publisher_table_reports_empty_library():
    assert render_publisher_table([]) == "No publishers found."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_publisher_table'`

- [ ] **Step 3: Implement `render_publisher_table`**

In `src/book0_presentation/tables.py`, change the model import, add the headers constant next
to `_AUTHOR_HEADERS`, and add the function after `render_author_table`:

```python
from book0_core.models import Author, Book, Publisher
```

```python
_PUBLISHER_HEADERS = ("ID", "Name")
```

```python
def render_publisher_table(publishers: list[Publisher]) -> str:
    if not publishers:
        return "No publishers found."

    rows: list[tuple[str, ...]] = [
        (str(publisher.id), publisher.name) for publisher in publishers
    ]
    return _align_rows(_PUBLISHER_HEADERS, rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_presentation/tables.py tests/unit/test_tables.py
git commit -m "feat: add render_publisher_table"
```

---

### Task 7: `publishers` subcommand on `book0`

**Files:**
- Modify: `src/book0_cli/main.py`
- Test: `tests/integration/test_cli_main.py`

**Interfaces:**
- Consumes: `render_publisher_table` from Task 6, `SqliteLibraryGateway.list_publishers` from
  Task 2.
- Produces: `book0 publishers [--tag TAG]` CLI behavior.

- [ ] **Step 1: Write the failing tests**

Add `CALIBRE_LIBRARY_PUBLISHERS` to the existing import line and the renderer import in
`tests/integration/test_cli_main.py`:

```python
from book0_presentation.tables import render_author_table, render_book_table, render_publisher_table
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)
```

Append:

```python
def test_run_prints_publisher_table_using_default_library_path_when_tag_is_omitted(
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

    exit_code = run(["publishers"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_publisher_table(CALIBRE_LIBRARY_PUBLISHERS) + "\n"
    )


def test_run_prints_publisher_table_when_tag_resolves_via_local_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["publishers", "--tag", "fiction"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_publisher_table(CALIBRE_LIBRARY_PUBLISHERS) + "\n"
    )


def test_run_reports_empty_library_for_publishers(
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
            CREATE TABLE publishers (id INTEGER PRIMARY KEY, name TEXT);
            """
        )
        connection.commit()
    finally:
        connection.close()
    _write_config(tmp_path / ".book0.toml", "empty", db_path)

    exit_code = run(["publishers", "--tag", "empty"])

    assert exit_code == 0
    assert capsys.readouterr().out == "No publishers found.\n"


def test_run_help_mentions_the_publishers_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "publishers" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_main.py -v`
Expected: FAIL — `run(["publishers"])` exits 2 (argparse: invalid choice), and
`"publishers"` is absent from `--help` output

- [ ] **Step 3: Implement the `publishers` subcommand**

In `src/book0_cli/main.py`:

```python
from book0_presentation.tables import render_author_table, render_book_table, render_publisher_table

_SUBCOMMANDS = ("books", "authors", "publishers")
```

```python
    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--tag", help=_TAG_HELP)

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--tag", help=_TAG_HELP)

    return parser
```

```python
    try:
        if args.command == "authors":
            print(render_author_table(gateway.list_authors()))
        elif args.command == "publishers":
            print(render_publisher_table(gateway.list_publishers()))
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
git commit -m "feat: add publishers subcommand to book0"
```

---

### Task 8: `publishers` subcommand on `book0-remote`

**Files:**
- Modify: `src/book0_cli_remote/main.py`
- Test: `tests/integration/test_cli_remote_main.py`

**Interfaces:**
- Consumes: `render_publisher_table` from Task 6, `HttpLibraryGateway.list_publishers` from
  Task 5.
- Produces: `book0-remote publishers --server URL --tag TAG` CLI behavior.

- [ ] **Step 1: Write the failing tests**

Add `CALIBRE_LIBRARY_PUBLISHERS` to the existing import line and the renderer import in
`tests/integration/test_cli_remote_main.py`:

```python
from book0_presentation.tables import render_author_table, render_book_table, render_publisher_table
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)
```

Append:

```python
def test_run_prints_publisher_table_for_a_known_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["publishers", "--server", "unused", "--tag", "fiction"], client=client
    )

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_publisher_table(CALIBRE_LIBRARY_PUBLISHERS) + "\n"
    )


def test_run_prints_no_publishers_found_for_an_unknown_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["publishers", "--server", "unused", "--tag", "does-not-exist"], client=client
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "No publishers found.\n"


def test_run_help_mentions_the_publishers_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "publishers" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: FAIL — `run(["publishers", ...])` exits 2 (argparse: invalid choice), and
`"publishers"` is absent from `--help` output

- [ ] **Step 3: Implement the `publishers` subcommand**

In `src/book0_cli_remote/main.py`:

```python
from book0_presentation.tables import render_author_table, render_book_table, render_publisher_table

_SUBCOMMANDS = ("books", "authors", "publishers")
```

```python
    authors_parser = subparsers.add_parser("authors")
    authors_parser.add_argument("--server", required=True)
    authors_parser.add_argument("--tag", required=True)

    publishers_parser = subparsers.add_parser("publishers")
    publishers_parser.add_argument("--server", required=True)
    publishers_parser.add_argument("--tag", required=True)

    return parser
```

```python
            if args.command == "authors":
                print(render_author_table(gateway.list_authors()))
            elif args.command == "publishers":
                print(render_publisher_table(gateway.list_publishers()))
            else:
                print(render_book_table(gateway.list_books()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/main.py tests/integration/test_cli_remote_main.py
git commit -m "feat: add publishers subcommand to book0-remote"
```

---

### Task 9: Update `architecture.md` and `README.md`

**Files:**
- Modify: `.claude/rules/architecture.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only, no code interfaces).
- Produces: nothing consumed by another task — this is the last task.

- [ ] **Step 1: Update `.claude/rules/architecture.md`**

Apply these exact replacements:

```
-│   ├── models.py               # Book: frozen dataclass (id, title, authors, pubdate);
-│                                  # Author: frozen dataclass (id, name)
+│   ├── models.py               # Book: frozen dataclass (id, title, authors, pubdate);
+│                                  # Author: frozen dataclass (id, name); Publisher: frozen
+│                                  # dataclass (id, name)
```

```
-│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book],
-│                                    # list_authors() -> list[Author]
+│   ├── gateway.py                # LibraryGateway(Protocol): list_books() -> list[Book],
+│                                    # list_authors() -> list[Author],
+│                                    # list_publishers() -> list[Publisher]
```

```
-│   └── tables.py                  # render_book_table(list[Book]) -> str, render_author_table(list[Author]) -> str,
-│                                    # aligned plain-text tables
+│   └── tables.py                  # render_book_table(list[Book]) -> str, render_author_table(list[Author]) -> str,
+│                                    # render_publisher_table(list[Publisher]) -> str, aligned plain-text tables
```

```
-├── book0_cli/
-│   ├── config.py                  # default_library_path(), xdg_config_path(), find_config_file()
-│   └── main.py                    # `book0` entry point: `books`/`authors` subcommands (books is
-│                                    # the default), --tag TAG (optional) -> SqliteLibraryGateway
+├── book0_cli/
+│   ├── config.py                  # default_library_path(), xdg_config_path(), find_config_file()
+│   └── main.py                    # `book0` entry point: `books`/`authors`/`publishers`
+│                                    # subcommands (books is the default), --tag TAG (optional)
+│                                    # -> SqliteLibraryGateway
```

```
-│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate;
-│                                    # AuthorOut: id, name
+│   └── schemas.py                 # BookOut: id, title, authors: list[str], pubdate;
+│                                    # AuthorOut: id, name; PublisherOut: id, name
```

```
-└── book0_cli_remote/
-    ├── main.py                    # `book0-remote` entry point: `books`/`authors` subcommands
-    │                                (books is the default), --server URL --tag TAG -> HttpLibraryGateway
+└── book0_cli_remote/
+    ├── main.py                    # `book0-remote` entry point: `books`/`authors`/`publishers`
+    │                                subcommands (books is the default), --server URL --tag TAG
+    │                                -> HttpLibraryGateway
```

```
-`tests/conftest.py` holds the shared Calibre-shaped SQLite fixture (`calibre_metadata_db`) and
-its expected `Book` list (`CALIBRE_LIBRARY_BOOKS`) and `Author` list (`CALIBRE_LIBRARY_AUTHORS`)
-- `book0_core`, `book0_api`, and both CLIs' tests all build on it rather than each defining
-their own fixture DB.
+`tests/conftest.py` holds the shared Calibre-shaped SQLite fixture (`calibre_metadata_db`) and
+its expected `Book` list (`CALIBRE_LIBRARY_BOOKS`), `Author` list (`CALIBRE_LIBRARY_AUTHORS`),
+and `Publisher` list (`CALIBRE_LIBRARY_PUBLISHERS`) - `book0_core`, `book0_api`, and both
+CLIs' tests all build on it rather than each defining their own fixture DB.
```

```
-- `book0_presentation` depends only on `book0_core` (needs `Book`/`Author` for
-  `render_book_table`'s/`render_author_table`'s signatures). No CLI, no web framework.
+- `book0_presentation` depends only on `book0_core` (needs `Book`/`Author`/`Publisher` for
+  `render_book_table`'s/`render_author_table`'s/`render_publisher_table`'s signatures). No
+  CLI, no web framework.
```

- [ ] **Step 2: Update `README.md`**

Apply these exact replacements:

```
-Lists the books or authors in a [Calibre](https://calibre-ebook.com/) library. Two ways to run it:
+Lists the books, authors, or publishers in a [Calibre](https://calibre-ebook.com/) library. Two ways to run it:
```

```
-Calibre's own default library. Choose `books` or `authors` - `books` is the default:
+Calibre's own default library. Choose `books`, `authors`, or `publishers` - `books` is the
+default:

 ```sh
 uv run book0 books --tag <tag>      # or just `uv run book0 --tag <tag>` - `books` is the default
 uv run book0 authors --tag <tag>
+uv run book0 publishers --tag <tag>
 # or, with no --tag:
 uv run book0                        # reads Calibre's default library (books)
 ```
```

Immediately after the existing `ID  Name` / `1   Frank Herbert` sample block, add:

```
+```
+ID  Name
+1   Ace Books
+```
+
```

```
-An empty library prints `No books found.` (or `No authors found.` for `authors`). A missing
+An empty library prints `No books found.` (or `No authors found.` for `authors`, or
+`No publishers found.` for `publishers`). A missing
```

```
 uv run book0-remote books --server http://127.0.0.1:8000 --tag fiction
 # or just `uv run book0-remote --server ... --tag fiction` - `books` is the default
 uv run book0-remote authors --server http://127.0.0.1:8000 --tag fiction
+uv run book0-remote publishers --server http://127.0.0.1:8000 --tag fiction
```

```
-Same table output, same `No books found.` / `No authors found.` for an empty library. A tag
+Same table output, same `No books found.` / `No authors found.` / `No publishers found.` for
+an empty library. A tag
```

- [ ] **Step 3: Verify the full suite, lint, and type-check still pass**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all pass, no new warnings

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/architecture.md README.md
git commit -m "docs: document publishers subcommand in architecture.md and README"
```

---

## Out of scope (see design doc)

- No `publisher` field on `Book`/`BookOut`.
- No change to tag resolution, `book0_config`, or `book0_cli/config.py`.
- Language, Series, and Tags listings — separate future features, not part of this plan.
