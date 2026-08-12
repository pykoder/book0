# book0

Lists the books, authors, or publishers in a [Calibre](https://calibre-ebook.com/) library. Two ways to run it:

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

This creates `.venv/` and installs all three console scripts (`book0`, `book0-remote`,
`book0-api`) into it. Every command below is run through `uv run` - see `CLAUDE.md` for why.

## `book0` - direct CLI

Point it at a library by tag (configured via `./.book0.toml`, or `~/.config/book0/config.toml` / `$XDG_CONFIG_HOME/book0/config.toml` as fallback), or use no flag to read
Calibre's own default library. Choose `books`, `authors`, or `publishers` - `books` is the
default:

```sh
uv run book0 books --tag <tag>      # or just `uv run book0 --tag <tag>` - `books` is the default
uv run book0 authors --tag <tag>
uv run book0 publishers --tag <tag>
# or, with no --tag:
uv run book0                        # reads Calibre's default library (books)
```

```
ID  Title       Author(s)      Pub Date
1   Dune        Frank Herbert  1965-08-01
```

```
ID  Name
1   Frank Herbert
```

```
ID  Name
1   Ace Books
```

`.book0.toml` (or the XDG fallback) maps tags to library paths, same shape as
`book0-libraries.toml`:

```toml
[libraries]
fiction = "/path/to/fiction"
```

`${VAR_NAME}` placeholders are expanded against the environment here too - see the
`book0-remote` + `book0_api` section below for the full explanation.

An empty library prints `No books found.` (or `No authors found.` for `authors`, or
`No publishers found.` for `publishers`). A missing
path or a file that isn't a Calibre library, no config file found for a given `--tag`, or a
config file found that doesn't list that tag, all print a one-line error to stderr and exit
with status 1. Unlike `book0-remote` (below), an unconfigured `--tag` is treated as an error
here, not as an empty library.

## `book0-remote` + `book0_api` - HTTP-backed CLI

### 1. Start the server

`book0_api` serves one or more libraries, each identified by a short tag you choose. The
mapping from tag to library path is a TOML file passed via `--config` - same `[libraries]`
shape as `book0`'s own `.book0.toml` (see above), so either CLI can read the same file. Each
value can be a library's directory (`book0_api` appends `metadata.db` itself, just like
`book0` does) or a `metadata.db` file path directly.

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

By default the server listens on `127.0.0.1:8000` - loopback only, unreachable from other
machines. `--host` names the *network interface* the process listens on, not a whitelist of
client addresses: `127.0.0.1` binds to loopback only, `0.0.0.0` binds to every interface on
the machine (reachable from any address that can route to the host), and a specific interface
IP binds to just that one. It does not restrict *who* may connect on that interface - see
"Restricting access" below for that.

```sh
uv run book0-api --config book0-libraries.toml --host 0.0.0.0 --port 9000
```

`--reload` enables uvicorn's auto-reload, for development only.

#### Running behind nginx (Unix domain socket)

For a production deployment behind nginx, use `--uds` to have `book0_api` listen on a Unix
domain socket instead of a TCP host/port (`--uds` and `--host`/`--port` are mutually
exclusive - pick one):

```sh
uv run book0-api --config book0-libraries.toml --uds /run/book0-api.sock
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

#### Restricting access

`book0_api` has no authentication/authorization of its own (by design - see
`docs/superpowers/specs/2026-08-04-book0-api-and-remote-cli-design.md`'s "out of scope"
section), and `--host`/`--port`/`--uds` only control which interface or socket it listens on,
not which clients may connect to it. To allow only specific addresses or a subnet, use the
layer in front of `book0_api` instead:

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

- Without nginx (e.g. `--host 0.0.0.0` directly), restrict the port at the OS firewall
  (`ufw`, `iptables`, `pf`) to the same specific addresses/subnet instead.

### 2. Run the CLI against it

```sh
uv run book0-remote books --server http://127.0.0.1:8000 --tag fiction
# or just `uv run book0-remote --server ... --tag fiction` - `books` is the default
uv run book0-remote authors --server http://127.0.0.1:8000 --tag fiction
uv run book0-remote publishers --server http://127.0.0.1:8000 --tag fiction
```

Same table output, same `No books found.` / `No authors found.` / `No publishers found.` for
an empty library. A tag
that isn't configured on the server behaves like an empty library rather than an error. A
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
