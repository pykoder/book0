# Remote Cover Download and Local Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `book0-remote books-detail` show and locally cache book covers, replacing today's
useless server-local absolute path with a real download-and-cache flow.

**Architecture:** Add a `GET /libraries/books/{id}/cover` byte-serving endpoint to `book0_api`
reusing the existing `SqliteLibraryGateway.get_book_details`; replace `BookDetailsOut.cover_path`
with `has_cover: bool` on the wire; widen `book0_core.BookDetails.cover_path` to a tri-state
(`None`/`str`/`False`) so `book0_cli_remote`'s `HttpLibraryGateway` can distinguish "no cover"
from "cover exists but not locally cached"; add an opt-in `--with-covers` flag to
`book0-remote books-detail` that checks a local disk cache first and only fetches on a miss.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, httpx, stdlib `sqlite3`/`tomllib`/`pathlib`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-17-remote-cover-cache-design.md`

## Global Constraints

- `book0_core` never opens a Calibre library for write; `book0_api` routes stay plain `def`
  (no blocking I/O inside `async def`); `book0_api` never imports `book0_cli_remote` or
  `book0_presentation`; `book0_cli_remote` never imports `book0_api` or `book0_config`.
- No new `book0_core.errors` class for this feature — `CoverNotFoundError` is a `book0_api`-local
  JSON body key only, never added to `http_gateway.py`'s `_ERROR_TYPES`.
- Every command goes through `uv run` (`uv run pytest`, `uv run ruff check .`,
  `uv run ruff format .`, `uv run mypy src`) — never a bare binary.
- Type-hint every function signature; no bare `Any`; no mutable default arguments.
- Never disable, comment out, or weaken an existing test to make it pass — update it to match
  the new spec, with a clear reason.

---

## Task 1: `book0_core.BookDetails.cover_path` tri-state + presentation rendering

**Files:**
- Modify: `src/book0_core/models.py`
- Modify: `src/book0_presentation/tables.py`
- Test: `tests/unit/test_tables.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `BookDetails.cover_path: str | None | Literal[False]` — every later task that
  constructs or reads `BookDetails.cover_path` relies on this type accepting `False`.
  `book0_presentation.tables._cover_path_cell(cover_path: str | None | Literal[False]) -> str`
  — not exported, but its behavior (`False` → `"(unavailable)"`) is relied on by every later
  task's `books-detail` output assertions.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_tables.py`, right after
`test_render_book_details_table_reports_empty_list`:

```python
def test_render_book_details_table_shows_unavailable_for_a_cover_that_is_not_local():
    books = [
        BookDetails(
            id="1",
            title="Dune",
            pubdate=None,
            authors=(),
            tags=(),
            publisher=None,
            series=None,
            cover_path=False,
        ),
    ]

    output = render_book_details_table(books)

    assert "(unavailable)" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_tables.py::test_render_book_details_table_shows_unavailable_for_a_cover_that_is_not_local -v`
Expected: FAIL with `AttributeError: 'bool' object has no attribute 'ljust'` — today's
`_or_empty(book.cover_path)` treats `False` as "not None" and passes the bare `False` value
straight into `_align_rows`'s column-padding code.

- [ ] **Step 3: Write minimal implementation**

In `src/book0_core/models.py`, add the import and widen the field:

```python
from dataclasses import dataclass
from typing import Literal
```

```python
@dataclass(frozen=True)
class BookDetails:
    id: str
    title: str
    pubdate: str | None
    authors: tuple[str, ...]
    tags: tuple[str, ...]
    publisher: Publisher | None
    series: SeriesItem | None
    cover_path: str | None | Literal[False] = None
```

In `src/book0_presentation/tables.py`, add the import and a dedicated helper (kept separate
from `_or_empty`, which stays `str | None`-only for the publisher/series/series-index
columns):

```python
from datetime import datetime
from typing import Literal

from book0_core.models import Author, Book, BookDetails, BookDetailsResult, Publisher
```

```python
def _or_empty(value: str | None) -> str:
    return value if value is not None else ""


def _cover_path_cell(cover_path: str | None | Literal[False]) -> str:
    if cover_path is False:
        return "(unavailable)"
    return _or_empty(cover_path)
```

Change the last element of the row tuple inside `render_book_details_table`:

```python
            _format_pubdate(book.pubdate),
            _cover_path_cell(book.cover_path),
```

(replacing `_or_empty(book.cover_path)`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_tables.py -v`
Expected: PASS (all tests in the file, including the new one and every pre-existing one — the
`None` case is already covered by e.g. `test_render_book_details_table_aligns_columns_with_headers`'s
Hobbit row).

- [ ] **Step 5: Commit**

```bash
git add src/book0_core/models.py src/book0_presentation/tables.py tests/unit/test_tables.py
git commit -m "feat: widen BookDetails.cover_path to a None/str/False tri-state"
```

---

## Task 2: `book0_api` cover-serving endpoint

**Files:**
- Modify: `src/book0_api/main.py`
- Test: `tests/e2e/test_book0_api_main.py`

**Interfaces:**
- Consumes: `SqliteLibraryGateway.get_book_details` (existing, unchanged),
  `_resolve_db_path` (existing helper inside `create_app`).
- Produces: `GET /libraries/books/{id}/cover?tag=...` — 200 with raw JPEG bytes
  (`media_type="image/jpeg"`) on success; 404 `{"error": "CoverNotFoundError", "detail": ...}`
  for an unconfigured tag, unknown id, book with no cover, or a cover file missing on disk;
  404/500 `LibraryNotFoundError`/`NotACalibreLibraryError` (existing shape); 400
  `TagRequiredError` (existing shape). Later tasks' `HttpLibraryGateway` fetch this route.

This task is purely additive — no existing route or schema changes, so no other test file is
touched.

- [ ] **Step 1: Write the failing test**

Add to `tests/e2e/test_book0_api_main.py`, at the end of the file:

```python
def test_get_book_cover_returns_the_cover_bytes_for_a_known_book(
    calibre_metadata_db: Path,
):
    library_root = calibre_metadata_db.parent
    cover_path = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(b"fake-jpeg-bytes")
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover", params={"tag": "fiction"})

    assert response.status_code == 200
    assert response.content == b"fake-jpeg-bytes"
    assert response.headers["content-type"] == "image/jpeg"


def test_get_book_cover_returns_404_for_a_book_with_no_cover(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/2/cover", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "CoverNotFoundError"


def test_get_book_cover_returns_404_when_cover_file_is_missing_on_disk(
    calibre_metadata_db: Path,
):
    # Dune (id 1) has has_cover=1 in the fixture DB, but the fixture never
    # creates a real cover.jpg file on disk - the defensive "file missing"
    # case.
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "CoverNotFoundError"


def test_get_book_cover_returns_404_for_an_unknown_book_id(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/999/cover", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "CoverNotFoundError"


def test_get_book_cover_returns_404_for_an_unconfigured_tag(calibre_metadata_db: Path):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get(
        "/libraries/books/1/cover", params={"tag": "does-not-exist"}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "CoverNotFoundError"


def test_get_book_cover_returns_400_when_tag_omitted_and_no_default_configured(
    calibre_metadata_db: Path,
):
    app = create_app({"fiction": calibre_metadata_db})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover")

    assert response.status_code == 400
    assert response.json()["error"] == "TagRequiredError"


def test_get_book_cover_returns_404_when_configured_path_is_missing(tmp_path: Path):
    app = create_app({"fiction": tmp_path / "does-not-exist.db"})
    client = TestClient(app)

    response = client.get("/libraries/books/1/cover", params={"tag": "fiction"})

    assert response.status_code == 404
    assert response.json()["error"] == "LibraryNotFoundError"


def test_get_book_cover_returns_500_when_configured_path_is_not_a_calibre_library(
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

    response = client.get("/libraries/books/1/cover", params={"tag": "fiction"})

    assert response.status_code == 500
    assert response.json()["error"] == "NotACalibreLibraryError"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -k get_book_cover -v`
Expected: every new test FAILs with a 404 `{"detail": "Not Found"}` (FastAPI's default for an
undefined route) instead of the expected body/status — the route doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

In `src/book0_api/main.py`, add `Response` to the existing import and add a module-level
helper plus the new route inside `create_app`, just before `return app`:

```python
from fastapi.responses import JSONResponse, Response
```

```python
def _cover_not_found(id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "CoverNotFoundError", "detail": f"No cover found for book {id}"},
    )
```

(module-level, placed after the imports, before `def create_app`)

```python
    @app.get("/libraries/books/{id}/cover", response_model=None)
    def get_book_cover(id: str, tag: str | None = None) -> Response | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        if db_path is None:
            return _cover_not_found(id)

        gateway = SqliteLibraryGateway(db_path)
        try:
            result = gateway.get_book_details([id])
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

        if not result.books:
            return _cover_not_found(id)
        cover_path = result.books[0].cover_path
        if cover_path is None or not Path(cover_path).is_file():
            return _cover_not_found(id)

        return Response(content=Path(cover_path).read_bytes(), media_type="image/jpeg")

    return app
```

(the new route goes immediately before the existing `return app`)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/e2e/test_book0_api_main.py -v`
Expected: PASS (all tests in the file, new and pre-existing).

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/main.py tests/e2e/test_book0_api_main.py
git commit -m "feat: add GET /libraries/books/{id}/cover endpoint to book0_api"
```

---

## Task 3: Wire contract rename (`has_cover`) + client-side cache-aware resolution

**Files:**
- Modify: `src/book0_api/schemas.py`
- Modify: `src/book0_cli_remote/http_gateway.py`
- Test: `tests/unit/test_book0_api_schemas.py`
- Test: `tests/e2e/test_book0_api_main.py`
- Test: `tests/integration/test_http_gateway.py`

**Interfaces:**
- Consumes: `GET /libraries/books/{id}/cover` (Task 2), `BookDetails.cover_path` tri-state
  (Task 1).
- Produces: `BookDetailsOut.has_cover: bool` (wire field, replaces `cover_path`).
  `HttpLibraryGateway.__init__(self, client, tag, *, with_covers: bool = False,
  cache_dir: Path | None = None)` — Task 5 constructs it with these two new keyword
  parameters.

This task must land the server rename and the client's consumption of it together: renaming
`BookDetailsOut.cover_path` to `has_cover` on its own would leave `HttpLibraryGateway`
reading a wire field that no longer exists, breaking `tests/integration/test_http_gateway.py`'s
existing assertions (which compare against `conftest.py`'s `expected_book_details` fixture —
real absolute path strings). Landing both halves in one task keeps every suite green
throughout.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_book0_api_schemas.py`, change
`test_from_book_details_converts_book_details_with_everything_populated`'s expected value —
replace the last two lines:

```python
        series=SeriesItemOut(
            series=SeriesOut(id="1", name="Dune Chronicles"), index="1.0"
        ),
        cover_path="/library/Frank Herbert/Dune (1)/cover.jpg",
    )
```

with:

```python
        series=SeriesItemOut(
            series=SeriesOut(id="1", name="Dune Chronicles"), index="1.0"
        ),
        has_cover=True,
    )
```

(the `book_details` input at the top of that test keeps `cover_path="/library/Frank Herbert/Dune (1)/cover.jpg"` unchanged — it's the domain object, still a valid `str`)

Add one line to `test_from_book_details_converts_book_details_with_no_publisher_or_series`:

```python
    assert book_details_out.publisher is None
    assert book_details_out.series is None
    assert book_details_out.tags == []
    assert book_details_out.has_cover is False
```

In `tests/e2e/test_book0_api_main.py`, change
`test_get_book_details_returns_expected_details_for_a_known_tag`'s expected body — replace:

```python
        "cover_path": str(
            library_root / "Frank Herbert/Dune (1)/cover.jpg"
        ),
    }
```

with:

```python
        "has_cover": True,
    }
```

(the `library_root = calibre_metadata_db.parent` line above it becomes unused — delete it)

In `tests/integration/test_http_gateway.py`, add the import and a local helper right after the
existing imports:

```python
from dataclasses import replace
```

```python
def _without_local_cover(details: BookDetails) -> BookDetails:
    """A gateway constructed with no cache_dir can never report a real local
    path - has_cover=True books resolve to False (unavailable), not the
    server's real path."""
    if details.cover_path is None:
        return details
    return replace(details, cover_path=False)
```

(`BookDetails` needs adding to the existing `from book0_core.models import ...` — wait, that
import doesn't exist in this file yet; add `from book0_core.models import BookDetails` as a
new import line)

Update the three existing tests that compare against `expected_book_details` for books with a
cover (Dune id `"1"`, Good Omens id `"3"`) — none of the gateways they construct pass
`cache_dir`, so every `has_cover=True` book must resolve to `False`:

```python
def test_get_book_details_uses_server_side_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db}, default_tag="fiction")
    gateway = HttpLibraryGateway(client, None)

    result = gateway.get_book_details(["1"])

    assert result.books == (_without_local_cover(dune_details),)
    assert result.missing_ids == ()


def test_get_book_details_returns_expected_details_for_a_known_tag(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, hobbit_details, good_omens_details = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.get_book_details(["3", "1", "2"])

    assert set(result.books) == {
        _without_local_cover(dune_details),
        hobbit_details,
        _without_local_cover(good_omens_details),
    }
    assert result.missing_ids == ()


def test_get_book_details_reports_missing_ids_for_a_known_tag(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.get_book_details(["1", "999"])

    assert result.books == (_without_local_cover(dune_details),)
    assert result.missing_ids == ("999",)
```

Add new tests covering the cache-first behavior directly, at the end of the file:

```python
def test_get_book_details_uses_cached_cover_without_making_an_http_request(
    calibre_metadata_db: Path, tmp_path: Path
):
    cache_dir = tmp_path / "cache"
    cached_cover = cache_dir / "fiction" / "1.jpg"
    cached_cover.parent.mkdir(parents=True)
    cached_cover.write_bytes(b"cached-bytes")
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction", cache_dir=cache_dir)

    result = gateway.get_book_details(["1"])

    assert result.books[0].cover_path == str(cached_cover)


def test_get_book_details_reports_false_cover_path_when_not_cached_and_with_covers_is_off(
    calibre_metadata_db: Path, tmp_path: Path
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction", cache_dir=tmp_path / "cache")

    result = gateway.get_book_details(["1"])

    assert result.books[0].cover_path is False


def test_get_book_details_downloads_and_caches_the_cover_when_with_covers_is_set(
    calibre_metadata_db: Path, tmp_path: Path
):
    library_root = calibre_metadata_db.parent
    server_cover = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    server_cover.parent.mkdir(parents=True, exist_ok=True)
    server_cover.write_bytes(b"server-bytes")
    cache_dir = tmp_path / "cache"
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(
        client, "fiction", with_covers=True, cache_dir=cache_dir
    )

    result = gateway.get_book_details(["1"])

    expected_path = cache_dir / "fiction" / "1.jpg"
    assert result.books[0].cover_path == str(expected_path)
    assert expected_path.read_bytes() == b"server-bytes"


def test_get_book_details_reports_false_cover_path_when_the_fetch_fails(
    calibre_metadata_db: Path, tmp_path: Path
):
    # Dune (id 1) has has_cover=1 in the fixture DB but no real cover.jpg
    # file on disk, so the server's own cover route 404s - the fetch must
    # fail without raising.
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(
        client, "fiction", with_covers=True, cache_dir=tmp_path / "cache"
    )

    result = gateway.get_book_details(["1"])

    assert result.books[0].cover_path is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py tests/e2e/test_book0_api_main.py tests/integration/test_http_gateway.py -v`
Expected: FAIL — `test_book0_api_schemas.py` with a pydantic `ValidationError` (`has_cover` is
an unknown/extra kwarg while `cover_path` is still required and missing); the e2e test the same
way; `test_http_gateway.py`'s new/updated tests with assertion mismatches (the gateway still
echoes the old, now-nonexistent `cover_path` wire key via `.get()`, always producing `None`).

- [ ] **Step 3: Write minimal implementation**

In `src/book0_api/schemas.py`, change `BookDetailsOut`:

```python
class BookDetailsOut(BaseModel):
    id: str
    title: str
    pubdate: str | None
    authors: list[str]
    tags: list[str]
    publisher: PublisherOut | None
    series: SeriesItemOut | None
    has_cover: bool

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
            has_cover=book_details.cover_path is not None,
        )
```

In `src/book0_cli_remote/http_gateway.py`, add imports:

```python
from pathlib import Path
from typing import Literal

import httpx
```

Turn `_book_details_from_json` into an instance method (delete the free function, add this
method to `HttpLibraryGateway`), reading `has_cover` instead of `cover_path`:

```python
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

Change the constructor and `get_book_details`'s call site:

```python
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
```

```python
    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        response = self._client.post(
            "/libraries/books/detail", params=self._params(), json={"ids": ids}
        )

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        body = response.json()
        return BookDetailsResult(
            books=tuple(self._book_details_from_json(row) for row in body["books"]),
            missing_ids=tuple(body["missing_ids"]),
        )
```

(the only change from today: `_book_details_from_json(row)` → `self._book_details_from_json(row)`)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_book0_api_schemas.py tests/e2e/test_book0_api_main.py tests/integration/test_http_gateway.py -v`
Expected: PASS (all tests in all three files).

Then run the full suite to catch any other consumer: `uv run pytest -v`
Expected: PASS (no other file references the old `cover_path` wire field or the free
`_book_details_from_json` function — confirmed by a full-repo grep before writing this plan).

- [ ] **Step 5: Commit**

```bash
git add src/book0_api/schemas.py src/book0_cli_remote/http_gateway.py \
  tests/unit/test_book0_api_schemas.py tests/e2e/test_book0_api_main.py \
  tests/integration/test_http_gateway.py
git commit -m "feat: replace cover_path wire field with has_cover + client-side cache resolution"
```

---

## Task 4: `book0_cli_remote/config.py` — cover cache dir + XDG default

**Files:**
- Modify: `src/book0_cli_remote/config.py`
- Test: `tests/unit/test_cli_remote_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `load_cover_cache_dir(config_path: Path) -> Path | None`,
  `xdg_cache_path() -> Path` — Task 5's `main.py` calls both.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_cli_remote_config.py`, change the import line:

```python
from book0_cli_remote.config import (
    find_config_file,
    load_cover_cache_dir,
    load_server,
    xdg_cache_path,
    xdg_config_path,
)
```

Add at the end of the file:

```python
def test_xdg_cache_path_uses_xdg_cache_home_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    xdg_cache_home = tmp_path / "xdg-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache_home))

    assert xdg_cache_path() == xdg_cache_home / "book0" / "covers"


def test_xdg_cache_path_falls_back_to_home_dot_cache_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert xdg_cache_path() == tmp_path / ".cache" / "book0" / "covers"


def test_load_cover_cache_dir_returns_the_configured_path(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text(
        'server = "http://127.0.0.1:8000"\ncover-cache-dir = "/tmp/covers"\n'
    )

    assert load_cover_cache_dir(config_path) == Path("/tmp/covers")


def test_load_cover_cache_dir_returns_none_when_key_is_absent(tmp_path: Path):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text('server = "http://127.0.0.1:8000"\n')

    assert load_cover_cache_dir(config_path) is None


def test_load_cover_cache_dir_raises_toml_decode_error_for_invalid_toml(
    tmp_path: Path,
):
    config_path = tmp_path / ".book0-client.toml"
    config_path.write_text("not valid toml === \n")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_cover_cache_dir(config_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_remote_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_cover_cache_dir'` (the new import
line at the top of the file fails before any test even runs).

- [ ] **Step 3: Write minimal implementation**

In `src/book0_cli_remote/config.py`, update the module docstring and add the new constant and
functions:

```python
"""Client-side config discovery/loading for `book0-remote`'s `--server` fallback.

Reads `.book0-client.toml`, a personal/local file (gitignored, not committed) holding a
`server = "http://host:port"` key (required) and an optional `cover-cache-dir = "/path"` key
(falls back to an XDG cache directory when absent) - the schema may grow further, but no other
key is designed yet.
"""

import os
import tomllib
from pathlib import Path

LOCAL_CONFIG_FILENAME = ".book0-client.toml"
_XDG_CONFIG_SUBPATH = Path("book0") / "client.toml"
_XDG_CACHE_SUBPATH = Path("book0") / "covers"


def xdg_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return config_home / _XDG_CONFIG_SUBPATH


def xdg_cache_path() -> Path:
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    cache_home = Path(xdg_cache_home) if xdg_cache_home else Path.home() / ".cache"
    return cache_home / _XDG_CACHE_SUBPATH


def find_config_file() -> Path | None:
    local_config = Path.cwd() / LOCAL_CONFIG_FILENAME
    if local_config.is_file():
        return local_config

    candidate = xdg_config_path()
    if candidate.is_file():
        return candidate

    return None


def load_server(config_path: Path) -> str:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return data["server"]


def load_cover_cache_dir(config_path: Path) -> Path | None:
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    value = data.get("cover-cache-dir")
    return Path(value) if value is not None else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_remote_config.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/config.py tests/unit/test_cli_remote_config.py
git commit -m "feat: add cover-cache-dir config key and XDG cache default"
```

---

## Task 5: `book0-remote books-detail --with-covers`

**Files:**
- Modify: `src/book0_cli_remote/main.py`
- Test: `tests/integration/test_cli_remote_main.py`

**Interfaces:**
- Consumes: `HttpLibraryGateway(client, tag, *, with_covers, cache_dir)` (Task 3),
  `load_cover_cache_dir`/`xdg_cache_path` (Task 4).
- Produces: `book0-remote books-detail --with-covers` — the last piece; nothing later depends
  on this task.

`cache_dir` is resolved for every `books-detail` invocation regardless of `--with-covers`
(only the network fetch is gated by the flag — see Task 3's `_resolve_cover`), via
`find_config_file()`/`Path.home()`, exactly like the existing `--server` fallback. Four
existing `books-detail` tests inject `--server`/`client` explicitly and never previously
touched the filesystem for config resolution — they must gain the same `tmp_path`/
`monkeypatch.setattr(Path, "home", ...)` isolation the `--server`-fallback tests already use,
or they'd silently read the real developer's `~/.config`/`~/.cache` during test runs.
(`test_run_reports_usage_error_when_ids_is_omitted_entirely` and
`test_run_help_mentions_the_books_detail_subcommand` both exit via argparse before reaching
this code and need no changes.)

- [ ] **Step 1: Write the failing test**

In `tests/integration/test_cli_remote_main.py`, add isolation to the four affected existing
tests — each gains `tmp_path: Path, monkeypatch: pytest.MonkeyPatch` parameters and two lines
at the top of the body:

```python
def test_run_prints_book_details_in_the_requested_id_order(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    dune_details, _, good_omens_details = expected_book_details
    client = TestClient(create_app({"fiction": calibre_metadata_db}))
    ...
```

```python
def test_run_reports_missing_ids_for_book_details(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    dune_details, _, _ = expected_book_details
    client = TestClient(create_app({"fiction": calibre_metadata_db}))
    ...
```

```python
def test_run_dedupes_and_strips_whitespace_from_requested_book_detail_ids(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    dune_details, _, _ = expected_book_details
    client = TestClient(create_app({"fiction": calibre_metadata_db}))
    ...
```

```python
def test_run_reports_all_ids_missing_for_an_unconfigured_tag(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    client = TestClient(create_app({"fiction": calibre_metadata_db}))
    ...
```

(in each case, only the signature and the two new lines are added — the rest of each test body
is unchanged from today)

Note that `expected_book_details` now includes covers resolved with no `cache_dir` — since
`books-detail` calls in these four tests never pass `--with-covers`, `cache_dir` resolves to
an XDG default under the isolated `tmp_path / "home"`, no file is ever cached there, and
`cover_path` still comes out `False` for Dune/Good Omens exactly as `_without_local_cover`
produced in Task 3 — so `expected_book_details`'s raw (real-path) tuples can no longer be
passed directly to `render_book_details_table` for comparison either. Apply the same
`_without_local_cover`-style fix used in Task 3, this time as an inline `dataclasses.replace`
since this file doesn't otherwise need a shared helper — add the import and update the three
tests that build expected output from `dune_details`/`good_omens_details`:

```python
from dataclasses import replace
```

```python
def test_run_prints_book_details_in_the_requested_id_order(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    dune_details, _, good_omens_details = expected_book_details
    dune_details = replace(dune_details, cover_path=False)
    good_omens_details = replace(good_omens_details, cover_path=False)
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
        == render_book_details_table([good_omens_details, dune_details]) + "\n"
    )
```

```python
def test_run_reports_missing_ids_for_book_details(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    dune_details, _, _ = expected_book_details
    dune_details = replace(dune_details, cover_path=False)
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
    assert (
        captured == render_book_details_table([dune_details]) + "\nMissing ids: 999\n"
    )
```

```python
def test_run_dedupes_and_strips_whitespace_from_requested_book_detail_ids(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    dune_details, _, _ = expected_book_details
    dune_details = replace(dune_details, cover_path=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1, 1, 999",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert (
        captured == render_book_details_table([dune_details]) + "\nMissing ids: 999\n"
    )
```

Add the four new tests for `--with-covers` itself, at the end of the file:

```python
def test_run_shows_unavailable_cover_when_with_covers_flag_is_omitted(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["books-detail", "--ids", "1", "--server", "unused", "--tag", "fiction"],
        client=client,
    )

    assert exit_code == 0
    assert "(unavailable)" in capsys.readouterr().out


def test_run_downloads_and_caches_cover_when_with_covers_flag_is_given(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    library_root = calibre_metadata_db.parent
    server_cover = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    server_cover.parent.mkdir(parents=True, exist_ok=True)
    server_cover.write_bytes(b"server-bytes")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1",
            "--with-covers",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    cached_cover = (
        tmp_path / "home" / ".cache" / "book0" / "covers" / "fiction" / "1.jpg"
    )
    assert cached_cover.read_bytes() == b"server-bytes"
    assert str(cached_cover) in capsys.readouterr().out


def test_run_uses_cover_cache_dir_from_client_config(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    library_root = calibre_metadata_db.parent
    server_cover = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    server_cover.parent.mkdir(parents=True, exist_ok=True)
    server_cover.write_bytes(b"server-bytes")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    custom_cache_dir = tmp_path / "custom-cache"
    (tmp_path / ".book0-client.toml").write_text(
        f'server = "http://unused"\ncover-cache-dir = "{custom_cache_dir}"\n'
    )
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1",
            "--with-covers",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    cached_cover = custom_cache_dir / "fiction" / "1.jpg"
    assert cached_cover.read_bytes() == b"server-bytes"


def test_run_reports_error_for_invalid_cover_cache_dir_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / ".book0-client.toml").write_text("not valid toml === \n")

    exit_code = run(
        ["books-detail", "--ids", "1", "--server", "unused", "--tag", "fiction"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Invalid book0-remote client config file" in captured.err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: FAIL — the isolation-only edits to the four pre-existing tests still pass (no
behavior change yet, since `cache_dir`/`with_covers` don't exist as gateway params from
`main.py`'s perspective until Step 3); the eight new/changed `--with-covers`-related
assertions FAIL, since `run()` still constructs `HttpLibraryGateway(client, args.tag)` with no
`with_covers`/`cache_dir` at all, `books-detail`'s parser has no `--with-covers` flag (`FAIL`
with `error: unrecognized arguments: --with-covers` / `SystemExit(2)` for the tests that pass
it), and the plain-flag-omitted test still shows `""` instead of `"(unavailable)"` (today's
pre-Task-1-fix output, since `cache_dir` is never even computed today).

- [ ] **Step 3: Write minimal implementation**

In `src/book0_cli_remote/main.py`, update the config import:

```python
from book0_cli_remote.config import (
    LOCAL_CONFIG_FILENAME,
    find_config_file,
    load_cover_cache_dir,
    load_server,
    xdg_cache_path,
    xdg_config_path,
)
```

Add the `--with-covers` flag to `books_detail_parser` in `_build_parser`:

```python
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
```

Replace the gateway-construction section of `run()`:

```python
    owns_client = client is None
    if client is None:
        client = httpx.Client(base_url=server)

    try:
        cache_dir = None
        if args.command == "books-detail":
            cache_config_path = find_config_file()
            if cache_config_path is not None:
                try:
                    cache_dir = load_cover_cache_dir(cache_config_path)
                except tomllib.TOMLDecodeError as error:
                    print(
                        f"Invalid book0-remote client config file "
                        f"{cache_config_path}: {error}",
                        file=sys.stderr,
                    )
                    return 1
            if cache_dir is None:
                cache_dir = xdg_cache_path()

        gateway = HttpLibraryGateway(
            client,
            args.tag,
            with_covers=getattr(args, "with_covers", False),
            cache_dir=cache_dir,
        )
        try:
```

(this replaces today's `try:\n        gateway = HttpLibraryGateway(client, args.tag)\n        try:` — the outer `try`/`finally: if owns_client: client.close()` around it is unchanged, so an early `return 1` for invalid cache config still closes an owned client)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_cli_remote_main.py -v`
Expected: PASS (all tests in the file).

Then run the full suite: `uv run pytest -v`
Expected: PASS.

Then the project's standard checks:

```bash
uv run ruff check .
uv run ruff format .
uv run mypy src
```

Expected: no new lint/format/type errors.

- [ ] **Step 5: Commit**

```bash
git add src/book0_cli_remote/main.py tests/integration/test_cli_remote_main.py
git commit -m "feat: add book0-remote books-detail --with-covers flag"
```

---

## Post-implementation

- [ ] Remove item 7 from `docs/superpowers/TODO.md` (the line and its bullet body) — this plan
  resolves it.
