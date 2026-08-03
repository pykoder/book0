# Calibre book lister — direct-SQLite CLI (design)

## Overview

A command-line tool that lists the books in a Calibre library by querying the
library's `metadata.db` SQLite file directly — no dependency on the `calibredb`
CLI or the Calibre Content Server API.

The domain logic (what a "book" is, how to list them) lives in a package
separate from the CLI so a second delivery mechanism can be added later: a
FastAPI server exposing the same data over HTTP, and a second CLI (or CLI mode)
that talks to that server instead of the database. **That second version is
out of scope for this task** — the only requirement here is to shape the
seam (a repository `Protocol`) so it can be added later without reworking
`book0_core`.

## Architecture

```
src/
├── book0_core/
│   ├── models.py               # Book: id, title, authors (tuple[str, ...]), pubdate (str | None)
│   ├── repository.py           # BookRepository(Protocol): list_books() -> list[Book]
│   └── sqlite_repository.py    # SqliteBookRepository(db_path: Path) implementing BookRepository
└── book0_cli/
    ├── main.py                 # argparse entry point; wires SqliteBookRepository, calls formatting
    └── formatting.py           # render list[Book] as an aligned plain-text table
```

Dependency direction: `book0_cli` → `book0_core`. `book0_core` has no
dependency on `book0_cli` and no dependency on any web/HTTP framework.

When the API version is added later, a `book0_api` package (FastAPI) will
depend on `book0_core` and implement `BookRepository` (or wrap it) behind
HTTP endpoints; a second repository implementation (an HTTP client) will
satisfy the same `BookRepository` Protocol for the API-backed CLI. Neither
`book0_core` nor the existing CLI needs to change to support that — this is
the reason the Protocol seam exists now even though only one implementation
is built today.

## Core behavior (`book0_core`)

- `Book` is a frozen dataclass: `id: int`, `title: str`, `authors: tuple[str, ...]`, `pubdate: str | None`.
- `BookRepository` is a `typing.Protocol` with one method: `list_books(self) -> list[Book]`.
- `SqliteBookRepository`:
  - Takes a resolved path to a `metadata.db` file.
  - Opens it **read-only**: `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` — the tool must
    never write to a user's Calibre library.
  - Runs one query joining `books`, `books_authors_link`, `authors`, grouping
    authors per book (`GROUP_CONCAT(authors.name, ', ')`), ordered by `books.title`.
  - Raises `book0_core.errors.LibraryNotFoundError` if the file doesn't exist,
    and `book0_core.errors.NotACalibreLibraryError` if the file opens but lacks
    a `books` table (`sqlite3.OperationalError` on the query, or an explicit
    `sqlite_master` check before querying).

## CLI (`book0_cli`)

- Entry point `book0` (console script), one required argument: `--library PATH`.
- `PATH` may be either the Calibre library folder or the `metadata.db` file
  itself. Resolution: if `PATH` is a directory, use `PATH/metadata.db`;
  otherwise use `PATH` as given.
- Output: an aligned plain-text table with columns `ID`, `Title`,
  `Author(s)`, `Pub Date`, one row per book, sorted by title (as returned by
  the repository).
- Empty library (query returns zero rows): print `No books found.` instead of
  a header-only table.

## Error handling

- `LibraryNotFoundError` / `NotACalibreLibraryError` (or the path not
  existing at all, checked before construction) → print a one-line, clear
  message to stderr (no stack trace) and exit with status `1`.
- Any other unexpected exception is allowed to propagate (not swallowed) —
  this tool has no reason to mask a real bug behind a generic error message.

## Testing

- **`book0_core` (integration-style, real SQLite):** build a temporary SQLite
  file with a minimal Calibre-shaped schema (`books`, `authors`,
  `books_authors_link` — just the columns this query touches) and known rows
  in a pytest fixture. Assert `SqliteBookRepository(path).list_books()`
  returns the expected `Book` list, including a book with multiple authors
  and a book with a `NULL` pubdate.
- **`book0_core` errors:** a missing file raises `LibraryNotFoundError`; a
  valid SQLite file without a `books` table raises `NotACalibreLibraryError`.
- **`book0_cli`:** using the same fixture DB, invoke `main()` (or the
  argparse-parsed function it delegates to) and assert the printed table
  matches expected output, including the empty-library case and the
  missing-file case (stderr message + exit code 1).

## Tooling / settings fix

The repo's `CLAUDE.md` and `.claude/rules/*.md` currently describe a generic
FastAPI + SQLAlchemy + Alembic layered web-app template, which does not match
this project (no web framework, no ORM, no migrations, at least in this
phase). As part of this task:

- Rewrite `CLAUDE.md` to describe the real stack (Python 3.12+, stdlib
  `sqlite3`, `argparse`, `pytest`, managed with `uv`) and the real structure
  (`book0_core` / `book0_cli` today, `book0_api` planned).
- Replace `.claude/rules/architecture.md`, `python-design.md`, `testing.md`,
  and `workflow.md` with versions scoped to this structure and to the
  repository-Protocol pattern, dropping FastAPI-router/Pydantic-schema/
  SQLAlchemy-model/Alembic-specific guidance that doesn't apply.
- Drop the unused `Bash(uv run alembic *)` permission from
  `.claude/settings.local.json`.

## Out of scope for this task

- The FastAPI server (`book0_api`) and the HTTP-backed `BookRepository`
  implementation / second CLI mode.
- Any Calibre metadata beyond id/title/authors/pubdate (series, tags, rating,
  covers, custom columns).
- Packaging/distribution (PyPI publishing, Docker, etc.).
