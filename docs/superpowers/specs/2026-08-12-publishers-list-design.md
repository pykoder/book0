# Publishers list — design

## Purpose

Add a Publishers list to book0, mirroring the existing Authors list at every layer: the same
`LibraryGateway` abstraction, the same two implementations (`SqliteLibraryGateway`,
`HttpLibraryGateway`), the same API surface shape, and the same rendering/CLI pattern. `Book`
and `BookOut` are untouched — this is a new, independent listing, not a new field on Book.

## Domain model

`book0_core/models.py` gains:

```python
@dataclass(frozen=True)
class Publisher:
    id: int
    name: str
```

Same shape as `Author` — no book count, no book titles, no `sort` field. Calibre's
`publishers` table has more columns, but nothing pulls a cross-entity aggregate onto
`Publisher` itself, matching the reasoning already applied to `Author`.

## Gateway

`book0_core/gateway.py`'s `LibraryGateway` Protocol grows one method:

```python
def list_publishers(self) -> list[Publisher]: ...
```

Both implementations grow the matching method:

- **`SqliteLibraryGateway.list_publishers()`** — same existence check
  (`LibraryNotFoundError`) and same Calibre-schema check (`NotACalibreLibraryError`) as
  `list_authors()`. Query:

  ```sql
  SELECT id, name FROM publishers ORDER BY name
  ```

  No join needed — a publisher's own name is already on the `publishers` row, same reasoning
  as `list_authors()` vs. `list_books()`.

- **`HttpLibraryGateway.list_publishers()`** — `GET /libraries/{tag}/publishers`, same error
  reconstruction (`_ERROR_TYPES` table, same 404/500 handling) as `list_authors()`.

## API

`book0_api/schemas.py` gains `PublisherOut(id: int, name: str)` with a `from_publisher`
classmethod, mirroring `AuthorOut`/`from_author`.

`book0_api/main.py` gains `GET /libraries/{tag}/publishers`, structurally identical to
`list_authors`: unknown tag → `[]`, `LibraryNotFoundError` → 404
`{"error": "LibraryNotFoundError", ...}`, `NotACalibreLibraryError` → 500
`{"error": "NotACalibreLibraryError", ...}`, success → `list[PublisherOut]`.

## Presentation

`book0_presentation/tables.py` gains `render_publisher_table(publishers: list[Publisher]) ->
str` (headers `"ID", "Name"`; empty-list message `"No publishers found."`), built the same way
as `render_author_table`.

## CLI UX

Both `book0` and `book0-remote` gain a third argparse subcommand, `publishers`, alongside
`books` (still the default) and `authors`. Each subcommand keeps the flags it already has:

- `book0 [books|authors|publishers] [--tag TAG]`
- `book0-remote [books|authors|publishers] --server URL --tag TAG`

Dispatch only changes which gateway method and renderer get called:

- `publishers` → `gateway.list_publishers()` / `render_publisher_table`

Tag resolution, error handling, and exit codes are unchanged and shared across all three
subcommands.

## Error handling

Identical to Authors/Books, no new error types:

- `SqliteLibraryGateway.list_publishers()` raises the same `book0_core.errors` types as
  `list_authors()` for the same conditions (missing file, non-Calibre file).
- `book0_api`'s new route maps them the same way the authors route does.
- `HttpLibraryGateway.list_publishers()` reconstructs them the same way.
- An unconfigured tag on `book0_api` / `book0-remote` → empty list (matches
  Authors/Books). `book0`'s `--tag` still hard-errors on an unknown tag regardless of
  subcommand.

## Testing

Mirrors every existing Authors test file with a Publishers counterpart:

- `tests/conftest.py`: add a `publishers` table and a `books_publishers_link` table to
  `calibre_metadata_db` (mirroring Calibre's real schema, even though `list_publishers`
  doesn't need the join — same as `books_authors_link` today), with fixture data covering a
  book with one publisher and a book with no publisher (an unlinked/`NULL` case, which
  `authors` doesn't currently exercise but `publishers` should, since Calibre allows a book
  with no publisher set). Add `CALIBRE_LIBRARY_PUBLISHERS` alongside
  `CALIBRE_LIBRARY_AUTHORS`.
- Unit: `Publisher`, `PublisherOut.from_publisher`, `render_publisher_table` (empty, one
  publisher, several publishers).
- Integration: `SqliteLibraryGateway.list_publishers` (nominal, empty library, missing file,
  non-Calibre file, directory-vs-file resolution), `HttpLibraryGateway.list_publishers`
  (nominal, both error mappings, unreachable server), both CLIs' `run()` for the new
  `publishers` subcommand.
- E2E: new API route (nominal, unknown tag, both error mappings).

## Out of scope

- No book count, book list, or any other computed field on `Publisher`.
- No `publisher` field added to `Book`/`BookOut` — publishers are a standalone listing, not a
  join back onto Books, matching how Authors shipped.
- No change to how tags resolve to library paths.
- No change to `book0_config`, `book0_cli/config.py`, or the API's config loading.
- No sorting option beyond alphabetical by name.
- Language, Series, and Tags listings are follow-up features, not part of this design. Series
  and Tags are expected to need schema/behavior specific to them (unlike this list-of-names
  shape) and will get their own design when picked up.
