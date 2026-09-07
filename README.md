# book0-fastapi

The FastAPI HTTP service (`book0_api`) serving the book0 REST contract over one or more
[Calibre](https://calibre-ebook.com/) libraries: `GET
/libraries/{books,authors,publishers,series}?tag=...`, `POST /libraries/books/detail`,
`GET /libraries/books/{id}/cover`, plus the PG-only write routes (mass edit, markdown
content, author aliases, jobs).

It consumes the shared `book0-core` domain layer (editable path dep). Clients of the
contract:

- **`book0-remote`** - the HTTP-backed CLI, in [`../book0-cli`](../book0-cli).
- **jaquette** - the web UI, a pure REST consumer (no Python).
- **`book0-django`** (future) - an alternative backend serving the same contract.

For the direct CLI (`book0`, reads `metadata.db` without a server), see
[`../book0-cli`](../book0-cli).

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/), plus the sibling
`../book0-core` and `../calibre_pg_sync` checkouts.

```sh
uv sync
```

This creates `.venv/` and installs the `book0-api` console script into it. Every command
below is run through `uv run` - see `CLAUDE.md` for why.

## Start the server

`book0_api` serves one or more libraries, each identified by a short tag you choose. The
mapping from tag to library path is a TOML file passed via `--config`, with a
`[libraries]` shape. Each value can be a library's directory (the gateway appends
`metadata.db` itself) or a `metadata.db` file path directly. A `default-library` set here
is used server-side whenever a request omits `tag`.

The committed template, `book0-libraries.toml`, holds `${VAR_NAME}` placeholders instead of
real paths (safe to commit - no real filesystem paths in the repo). Set the env vars it
references, then start the server with the `book0-api` command:

```sh
FICTION_LIBRARY_PATH="/path/to/fiction" \
WORK_LIBRARY_PATH="/path/to/work" \
uv run book0-api --config book0-libraries.toml --reload
```

Add a library by adding a line to `book0-libraries.toml` (`tag = "${SOME_ENV_VAR}"`) and
setting that env var - no code change needed. A tag whose placeholder references an unset
env var makes the server refuse to start (fail fast, not serve a broken library silently).

By default the server listens on `http://127.0.0.1:8000` - loopback only, unreachable from
other machines. `--listen URL` names the *network interface* (or socket) the process listens
on, not a whitelist of client addresses: with an `http://` URL, `127.0.0.1` binds to loopback
only, `0.0.0.0` binds to every interface on the machine (reachable from any address that can
route to the host), and a specific interface IP binds to just that one. It does not restrict
*who* may connect on that interface - see "Restricting access" below for that. A `unix://` URL
instead has `book0_api` listen on a Unix domain socket - see the section right below for that.

```sh
uv run book0-api --config book0-libraries.toml --listen http://0.0.0.0:9000
```

`--reload` enables uvicorn's auto-reload, for development only.

`--server-config PATH` supplies `--listen` when the flag itself is omitted, from a
`.book0-server.toml` file with a single `listen = "http://host:port"` (or
`listen = "unix:///path"`) key. Unlike the remote CLI's client-side config file (see
`../book0-cli`), `--server-config` is never auto-discovered - the server is started far
less often than clients are invoked, so it always has to be passed explicitly:

```sh
uv run book0-api --config book0-libraries.toml --server-config .book0-server.toml
```

### PostgreSQL catalog mode (`pg-dsn`) and the markdown cache (`markdown-cache-dir`)

Two more optional keys live in `book0-libraries.toml`:

- **`pg-dsn`** - when set, every route is served from the PostgreSQL catalog populated by
  [`calibre_pg_sync`](../calibre_pg_sync/docs/calibre-to-pg-migration.md) instead of the
  SQLite `metadata.db` paths above: the `[libraries]` mapping is ignored and the requested
  tag resolves against the `libraries.name` table. One deliberate divergence between the
  backends: an unknown tag is reported as `404 LibraryNotFoundError` in PG mode but as
  `400 TagRequiredError` in SQLite mode - do not detect an unknown tag from the status
  code alone. All the write routes - `PATCH /libraries/books`,
  `GET /libraries/books/{id}/content`, the author-alias routes,
  `POST /libraries/authors/{id}/apply-name`, and the `/libraries/jobs` routes - require
  this mode; in SQLite mode they answer `501`.
- **`markdown-cache-dir`** - PG mode only. Names the directory where
  `GET /libraries/books/{id}/content` caches the markdown it converts from each book's
  EPUB (cache files are keyed by book id, requested level, the EPUB's mtime and a short
  hash of the requested extract, so a changed EPUB invalidates its own entries and two
  distinct extracts never share a file). Leave it out and every content request converts
  the EPUB from scratch.

The routes and gateway protocols behind these keys are specified in
`docs/superpowers/specs/2026-08-31-grimoire-api-librarygateway-design.md` (API contract)
and `docs/superpowers/specs/2026-08-31-grimoire-pg-schema-design.md` (PG schema).

### Running behind nginx (Unix domain socket)

For a production deployment behind nginx, use a `unix://` `--listen` URL to have `book0_api`
listen on a Unix domain socket instead of a TCP host/port:

```sh
uv run book0-api --config book0-libraries.toml --listen unix:///run/book0-api.sock
```

Point nginx at that socket:

```nginx
server {
    listen 80;
    server_name books.example.com;

    location / {
        proxy_pass http://unix:/run/book0-api.sock:/;
        proxy_set_header Host $host;
    }
}
```

`book0_api` creates the socket file (with permissions letting nginx connect) when it starts.
If the process was killed rather than shut down cleanly, remove the stale socket file
(`rm /run/book0-api.sock`) before starting it again, or the bind will fail with "address
already in use".

### Restricting access

`book0_api` has no authentication/authorization of its own (by design - see
`docs/superpowers/specs/2026-08-04-book0-api-and-remote-cli-design.md`'s "out of scope"
section), and `--listen` only controls which interface or socket it listens on, not which
clients may connect to it. To allow only specific addresses or a subnet, use the layer in
front of `book0_api` instead:

- Behind nginx, `allow`/`deny` in the `location`/`server` block:

  ```nginx
  location / {
      allow 10.0.0.0/24;
      allow 203.0.113.5;
      deny all;
      proxy_pass http://unix:/run/book0-api.sock:/;
      proxy_set_header Host $host;
  }
  ```

- Without nginx (e.g. `--listen http://0.0.0.0:<port>` directly), restrict the port at the OS
  firewall (`ufw`, `iptables`, `pf`) to the same specific addresses/subnet instead.

## Development

```sh
uv run pytest              # full test suite (PG tests need docker)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy src            # type-check
```

`tests/integration/test_http_gateway.py` is the REST contract suite: it drives the real
`HttpLibraryGateway` from the `book0-cli` repo (dev-only path dependency) against the real
app, pinning the JSON shapes and status codes every consumer relies on.

See `CLAUDE.md` and `.claude/rules/` for the architecture, conventions, and workflow this
project follows, and `docs/superpowers/specs/` for the design docs behind each feature.
