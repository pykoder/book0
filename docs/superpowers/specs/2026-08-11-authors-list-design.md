# Authors list — design

## Purpose

Add an Authors list to book0, mirroring the existing Books list at every layer: the same
`LibraryGateway` abstraction, the same two implementations (`SqliteLibraryGateway`,
`HttpLibraryGateway`), the same API surface shape, and the same rendering/CLI pattern.

## Domain model

`book0_core/models.py` gains:

```python
@dataclass(frozen=True)
class Author:
    id: int
    name: str
```

No book count, no book titles, no `sort`/`link` fields — Calibre's `authors` table has more
columns, but nothing in the current Books feature pulls in cross-entity aggregates onto the
"other side" (`Book` doesn't carry a computed field about its authors beyond their names,
which it needs to render itself), so `Author` stays to what describes an author.

## Gateway

`book0_core/gateway.py`'s `LibraryGateway` Protocol grows one method:

```python
def list_authors(self) -> list[Author]: ...
```

Both implementations grow the matching method:

- **`SqliteLibraryGateway.list_authors()`** — same existence check
  (`LibraryNotFoundError`) and same Calibre-schema check (`NotACalibreLibraryError`) as
  `list_books()`. Query:

  ```sql
  SELECT id, name FROM authors ORDER BY name
  ```

  No join needed — unlike `list_books()`, which joins `books_authors_link`/`authors` to
  pull author names onto each book row, an author's own name is already on the `authors`
  row.

- **`HttpLibraryGateway.list_authors()`** — `GET /libraries/{tag}/authors`, same error
  reconstruction (`_ERROR_TYPES` table, same 404/500 handling) as `list_books()`.

## API

`book0_api/schemas.py` gains `AuthorOut(id: int, name: str)` with a `from_author` classmethod,
mirroring `BookOut`/`from_book`.

`book0_api/main.py` gains `GET /libraries/{tag}/authors`, structurally identical to
`list_books`: unknown tag → `[]`, `LibraryNotFoundError` → 404
`{"error": "LibraryNotFoundError", ...}`, `NotACalibreLibraryError` → 500
`{"error": "NotACalibreLibraryError", ...}`, success → `list[AuthorOut]`.

## Presentation

`book0_presentation/tables.py` gains `render_author_table(authors: list[Author]) -> str`
(headers `"ID", "Name"`; empty-list message `"No authors found."`), built the same way as the
existing table renderer.

The existing `render_table` is renamed to `render_book_table` for symmetry with the new
`render_author_table` (both names now say what they render). Callers updated:
`book0_cli/main.py`, `book0_cli_remote/main.py`. `tests/unit/test_tables.py` updated to match.

## CLI UX

Both `book0` and `book0-remote` gain argparse subparsers: `books` and `authors`, with `books`
as the default subcommand when none is given — `book0 --tag foo` and `book0-remote --server
url --tag foo` keep working exactly as they do today, unchanged. Each subcommand keeps the
flags it has today:

- `book0 [books|authors] [--tag TAG]`
- `book0-remote [books|authors] --server URL --tag TAG`

Dispatch only changes which gateway method and renderer get called:

- `books` → `gateway.list_books()` / `render_book_table`
- `authors` → `gateway.list_authors()` / `render_author_table`

Tag resolution (`book0`'s config-file lookup, `book0-remote`'s required `--server`/`--tag`),
error handling, and exit codes are unchanged and shared across both subcommands — nothing
about how a tag resolves to a library path differs by subcommand.

## Error handling

Identical to Books, no new error types:

- `SqliteLibraryGateway.list_authors()` raises the same `book0_core.errors` types as
  `list_books()` for the same conditions (missing file, non-Calibre file).
- `book0_api`'s new route maps them the same way the books route does.
- `HttpLibraryGateway.list_authors()` reconstructs them the same way.
- An unconfigured tag on `book0_api` / `book0-remote` → empty list (matches Books).
  `book0`'s `--tag` still hard-errors on an unknown tag regardless of subcommand (matches
  Books; this is existing `book0_cli` behavior, not new).

## Testing

Mirrors every existing Books test file with an Authors counterpart:

- `tests/conftest.py`: add `CALIBRE_LIBRARY_AUTHORS` (Frank Herbert, J.R.R. Tolkien, Neil
  Gaiman, Terry Pratchett — already alphabetical given the existing fixture data) alongside
  `CALIBRE_LIBRARY_BOOKS`, built from the same `calibre_metadata_db` fixture.
- Unit: `Author`, `AuthorOut.from_author`, `render_author_table` (empty, one author, several
  authors), `render_book_table` (renamed test, same cases as before).
- Integration: `SqliteLibraryGateway.list_authors` (nominal, empty library, missing file,
  non-Calibre file), `HttpLibraryGateway.list_authors` (nominal, both error mappings,
  unreachable server), both CLIs' `run()` for the new `authors` subcommand and for the
  default-to-`books` case.
- E2E: new API route (nominal, unknown tag, both error mappings).

## Out of scope

- No book count, book list, or any other computed field on `Author`.
- No change to how tags resolve to library paths.
- No change to `book0_config`, `book0_cli/config.py`, or the API's config loading.
- No sorting option beyond alphabetical by name.
