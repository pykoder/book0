# Opaque string ids — design

## Purpose

`Book.id`, `Author.id`, and `Publisher.id` are currently `int`, mirroring Calibre's actual
`INTEGER PRIMARY KEY` columns directly in the domain model. That leaks an implementation
detail of one specific backend (Calibre's SQLite schema) into `book0_core`, which is meant to
stay backend-agnostic — nothing in `book0_core` should assume an id is numeric, since a future
gateway backend (or a future evolution of the id scheme itself) may not use integers. This
retrofit changes all three ids to `str`, treated as an opaque identifier by every layer above
the SQLite query itself.

This is a pure type/representation change — no new behavior, no new fields, no query changes.
It must land and be green before the book-details feature (a separate design) begins, since
that feature's new types (`BookDetails.id`, `get_book_details`'s `ids` parameter,
`missing_ids`) are `str` from the start and would otherwise be inconsistent with the rest of
the domain.

## Scope

`book0_core/models.py`, `book0_core/sqlite_gateway.py`, `book0_api/schemas.py`, and every
existing test that constructs a `Book`/`Author`/`Publisher` or asserts against their `id`
field or the API's JSON body. `book0_cli_remote/http_gateway.py` needs no code change (see
below). `book0_config`, tag resolution, and the CLI's `--tag` handling are untouched — this is
about the identity of a *book/author/publisher*, not a *library*.

## Domain model

```python
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

Only the `id` field's type changes; nothing else about these three models changes.

## SQLite gateway

Calibre's own `books`/`authors`/`publishers` tables keep their `INTEGER` primary keys
unchanged — this retrofit never touches SQL. Each `list_*` method wraps the row's id value as
`str(row[0])` when constructing the domain object, e.g.:

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

Same one-line change in `list_authors` and `list_publishers` (`Author(id=str(row[0]), ...)`,
`Publisher(id=str(row[0]), ...)`). No zero-padding, no other formatting — plain
stringification of whatever Calibre's autoincrement integer happens to be.

## API schema and wire format

`book0_api/schemas.py`'s `BookOut.id`, `AuthorOut.id`, `PublisherOut.id` become `str`. Their
`from_book`/`from_author`/`from_publisher` classmethods are unchanged (`id=book.id` etc. — the
value is already a `str` coming out of the domain model, Pydantic just serializes it as a JSON
string instead of a JSON number).

This changes the wire format: `GET /libraries/{tag}/books` (and `/authors`, `/publishers`)
today return `"id": 1`; after this retrofit they return `"id": "1"`. This is an accepted
breaking change to the JSON contract — `book0-remote` (the only consumer) is updated in the
same retrofit, and there is no other consumer today.

## HTTP gateway

`HttpLibraryGateway` needs **no code change**. It already builds domain objects straight from
the parsed JSON body with no cast (`Book(id=row["id"], ...)`, etc.) — `row["id"]` will simply
be a `str` once the server sends a JSON string instead of a JSON number, and the domain model's
new `id: str` field accepts it without any adjustment on the client side.

## Presentation

`book0_presentation/tables.py` currently calls `str(book.id)` (and the equivalent for
`author.id`/`publisher.id`) to build each row's ID column text. Once `id` is already a `str`,
that call becomes a redundant `str(str)` no-op. Simplify each to reference `.id` directly — a
direct consequence of the type change, not an unrelated cleanup.

## Testing

Every existing test that constructs a `Book`/`Author`/`Publisher` with a literal id, or asserts
against one, changes that literal from an int to the equivalent string:

- `tests/conftest.py`: `CALIBRE_LIBRARY_BOOKS`, `CALIBRE_LIBRARY_AUTHORS`,
  `CALIBRE_LIBRARY_PUBLISHERS` — every `id=N` becomes `id="N"`.
- `tests/unit/test_models.py`, `tests/unit/test_tables.py`,
  `tests/unit/test_book0_api_schemas.py` — same literal updates, plus any table-rendering
  assertions that hardcode an expected id string (already strings in the rendered output
  today, since `render_*_table` always stringified for display — no assertion text changes,
  only the constructor literals feeding them).
- `tests/integration/test_sqlite_gateway.py`, `tests/integration/test_http_gateway.py`,
  `tests/integration/test_cli_main.py`, `tests/integration/test_cli_remote_main.py` — these
  mostly compare against the `conftest.py` fixtures rather than hardcoding ids themselves, so
  most needs no change beyond what the fixture update already provides; spot-check each file
  for any literal id assertion missed by that.
- `tests/e2e/test_book0_api_main.py` — JSON body assertions already reference
  `book.id`/`author.id`/`publisher.id` from the fixtures rather than hardcoding `1`, so these
  update automatically once the fixtures do; no literal changes needed here, just confirm this
  during implementation rather than assume it blindly.

No new test cases are needed — this changes representation, not behavior. Every existing test
must still pass, with only its id literals adjusted.

## Out of scope

- No change to Calibre's SQL schema or query text.
- No change to tag resolution, `book0_config`, or either CLI's `--tag` handling.
- No id-scoping-by-library-tag scheme (raised during design, deliberately deferred).
- No special convention distinguishing a "Calibre-internal integer id" from the domain's
  opaque string id (raised during design, deliberately deferred).
- No change to `book0_cli_remote/http_gateway.py`'s code (confirmed above — the JSON parsing
  already flows through untyped).
