---
paths:
  - "src/**"
  - "tests/**"
---

# Architecture and real source layout

Before touching a file, identify which package it belongs to.

## Current layout

```
book0-libraries.toml            # committed template for book0-api --config: ${VAR_NAME}
                                # placeholders, never real paths - see book0_config below
src/
└── book0_api/
    ├── main.py                 # create_app(libraries: dict[str, Path], default_tag:
    │                           # str | None = None, default_page_size: int | None =
    │                           # None, pg_dsn: str | None = None, markdown_cache_dir:
    │                           # Path | None = None) -> FastAPI; routes take `tag` as an
    │                           # optional `?tag=...` query parameter (not a `{tag}` path
    │                           # segment), falling back to default_tag, raising
    │                           # TagRequiredError (mapped to 400) if neither is set; the
    │                           # list routes also take optional `page`/`page_size` query
    │                           # params, `page_size` capped/forced by default_page_size
    ├── asgi.py                 # `app` wired from CONFIG_ENV_VAR (BOOK0_API_CONFIG) - the
    │                           # real uvicorn import target ("book0_api.asgi:app")
    ├── cli.py                  # `book0-api` entry point: --config PATH (required),
    │                           # --reload, --listen URL (default http://127.0.0.1:8000):
    │                           # http://host:port or unix:///path/to/socket,
    │                           # --server-config PATH (optional, never auto-discovered)
    │                           # -> sets BOOK0_API_CONFIG, then uvicorn.run(...)
    ├── filters.py              # raw filter-param parsing (parse_id_list, parse_text_list,
    │                           # parse_int_list) raising InvalidFilterError
    ├── jobs.py                 # run_job: background execution of PG jobs
    │                           # (create_job -> 202 -> background task)
    └── schemas.py              # the wire format: BookOut: id, title, authors: list[str],
                               # pubdate; AuthorOut/PublisherOut/SeriesOut: id, name;
                               # SeriesItemOut: series, index; BookDetailsOut: id, title,
                               # pubdate, authors, tags, publisher, series, has_cover;
                               # BookDetailsResultOut: books, missing_ids; BookIdsIn: ids;
                               # plus the write-route schemas (PatchBooksIn, JobCreateIn,
                               # alias/apply-name, ...)
tests/
├── unit/                       # book0_api schemas - no I/O, no network
├── integration/
│   └── test_http_gateway.py    # the REST contract suite: HttpLibraryGateway (from
│                              # ../book0-cli, dev path dep) driven against the real
│                              # create_app(...) via TestClient - this is what pins the
│                              # JSON shapes and status codes the consumers rely on
└── e2e/                        # book0_api's routes via FastAPI's TestClient
```

Shared fixtures live in `book0_core.testing` (the `book0-core` repo) - `tests/conftest.py`
only wraps them as pytest fixtures (`calibre_metadata_db`, `many_books_db`,
`expected_book_details`, and the PG fixtures). Never duplicate a fixture here.

## Dependency direction

- `book0_api` depends on `book0_core` (gateway Protocols, both implementations, domain
  errors, models) **and `book0_config`** (tag-to-path TOML resolution), both as editable
  path deps on `../book0-core`.
- `book0_api` never imports `book0_cli`, `book0_cli_remote`, or `book0_presentation` - the
  API returns JSON, it never renders a table, and it never parses CLI flags.
- `book0-cli` (dev path dep `../book0-cli`) is used ONLY by
  `tests/integration/test_http_gateway.py`: the contract suite drives the real
  `HttpLibraryGateway` against the real app to pin the REST contract from the consumer's
  side. Runtime code never imports it - the dependency direction (consumers depend on
  core, never the reverse) is unchanged.
- Code that talks to `metadata.db` (SQL, `sqlite3.connect`, schema assumptions, the
  `metadata.db` filename itself) lives only in `book0-core`'s `sqlite_gateway.py`.
  `book0_api` calls `SqliteLibraryGateway` exactly like a CLI consumer would, and
  `book0-libraries.toml` values may name either a library directory or a `metadata.db`
  file directly - the gateway's `__init__` resolves that, not the routes.
- All PG access goes through `book0-core`'s `PgLibraryGateway` (calibre_pg_sync schema).
- Consumers of this service: `book0-remote` (in `../book0-cli`), jaquette (REST only, no
  Python), and a future `../book0-django` backend serving the same contract. A change to a
  route's JSON shape or status codes is a contract change - update
  `tests/integration/test_http_gateway.py` and coordinate with `../book0-cli`.

## Error-mapping contract

Every route maps recognized `book0_core` domain errors to `{"error": "<Name>",
"detail": str}` bodies with the documented status codes - `TagRequiredError` → 400,
`LibraryNotFoundError` → 404, `NotACalibreLibraryError` → 500, plus the write-route errors
(422 for invalid input, 404 for missing book/job/author). `HttpLibraryGateway`
reconstructs the named exception client-side from the body; a new domain error must be
mapped in every route that can raise it (see `../book0-cli`'s
`tests/unit/test_error_types.py`).

## Zone rule

- Greenfield - align strictly on the pattern above. If you find an inconsistency, report it
  rather than assuming it is intentional.
