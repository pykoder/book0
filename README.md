# book0

Lists the books in a [Calibre](https://calibre-ebook.com/) library. Two ways to run it:

- **`book0`** - reads the library's `metadata.db` SQLite file directly (read-only).
- **`book0-remote`** - talks over HTTP to `book0_api`, a small FastAPI service that reads
  `metadata.db` on the server's behalf, for one of several tag-named libraries configured
  server-side.

Both produce identical output for the same library.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

This creates `.venv/` and installs both console scripts (`book0`, `book0-remote`) into it.
Every command below is run through `uv run` - see `CLAUDE.md` for why.

## `book0` - direct CLI

Point it at a library by tag (configured in `~/.config/book0.toml`), or use no flag to read
Calibre's own default library:

```sh
uv run book0 --tag <tag>
# or
uv run book0                  # reads Calibre's default library
```

```
ID  Title       Author(s)      Pub Date
1   Dune        Frank Herbert  1965-08-01
```

An empty library prints `No books found.`. A missing path or a file that isn't a Calibre
library prints a one-line error to stderr and exits with status 1.

## `book0-remote` + `book0_api` - HTTP-backed CLI

### 1. Start the server

`book0_api` serves one or more libraries, each identified by a short tag you choose. The
mapping from tag to `metadata.db` path is a TOML file pointed to by `BOOK0_API_CONFIG`.

The committed template, `book0-libraries.toml`, holds `${VAR_NAME}` placeholders instead of
real paths (safe to commit - no real filesystem paths in the repo). Set the env vars it
references, then start the server:

```sh
FICTION_LIBRARY_PATH="/path/to/fiction/metadata.db" \
WORK_LIBRARY_PATH="/path/to/work/metadata.db" \
BOOK0_API_CONFIG="book0-libraries.toml" \
uv run uvicorn book0_api.asgi:app --reload
```

Add a library by adding a line to `book0-libraries.toml` (`tag = "${SOME_ENV_VAR}"`) and
setting that env var - no code change needed. A tag whose placeholder references an unset
env var makes the server refuse to start (fail fast, not serve a broken library silently).

### 2. Run the CLI against it

```sh
uv run book0-remote --server http://127.0.0.1:8000 --tag fiction
```

Same table output, same `No books found.` for an empty library. A tag that isn't configured
on the server behaves like an empty library (`No books found.`) rather than an error. A
configured-but-broken library on the server (missing file, not a Calibre library) or an
unreachable server both print a one-line error to stderr and exit with status 1.

## Development

```sh
uv run pytest              # full test suite
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy src            # type-check
```

See `CLAUDE.md` and `.claude/rules/` for the architecture, conventions, and workflow this
project follows, and `docs/superpowers/specs/` for the design docs behind each feature.
