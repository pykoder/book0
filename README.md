# book0

Lists the books, authors, or publishers in a [Calibre](https://calibre-ebook.com/) library,
and fetches richer joined details (publisher, series, tags) for a specific set of book ids.
Two ways to run it:

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

Point it at a library by tag (configured via `./.book0.toml`, or `~/.config/book0/config.toml` / `$XDG_CONFIG_HOME/book0/config.toml` as fallback), or omit `--tag` to use the config
file's `default-library`, if set. Choose `books`, `authors`, `publishers`, or `books-detail` -
`books` is the default:

```sh
uv run book0 books --tag <tag>      # or just `uv run book0 --tag <tag>` - `books` is the default
uv run book0 authors --tag <tag>
uv run book0 publishers --tag <tag>
uv run book0 books --tag <tag> --page-size 20              # paginate 20 rows per page
uv run book0 books --tag <tag> --page-size 20 --page 2     # second page
uv run book0 books-detail --ids 1,2,3 --tag <tag>
# or, with no --tag:
uv run book0                        # uses the config file's default-library (books)
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

```
ID  Title  Authors        Publisher  Series           Series Index  Tags              Pub Date    Cover Path
1   Dune   Frank Herbert  Ace Books  Dune Chronicles  1.0           sci-fi & classic  1965-08-01  /path/to/fiction/Frank Herbert/Dune (1)/cover.jpg
```

`books-detail` never errors on an unknown id - it prints a `Missing ids: ...` line after the
table (or on its own, if none of the requested ids were found) instead.

`.book0.toml` (or the XDG fallback) maps tags to library paths, same shape as
`book0-libraries.toml`:

```toml
default-library = "fiction"

[libraries]
fiction = "/path/to/fiction"
```

`default-library` is optional - it names the tag `book0` uses when `--tag` is omitted. Leave
it out and an omitted `--tag` is an error (see below).

Add `--page-size N` to paginate `books`/`authors`/`publishers` output N rows at a time
(`--page` selects which page, defaulting to 1); a config file may set `default-page-size` so
`--page-size` can be omitted. `books-detail` is never paginated.

`${VAR_NAME}` placeholders are expanded against the environment here too - see the
`book0-remote` + `book0_api` section below for the full explanation.

An empty library prints `No books found.` (or `No authors found.` for `authors`, or
`No publishers found.` for `publishers`; `books-detail` prints `No book details found.` when
none of the requested ids match). A missing path or a file that isn't a Calibre library, no config file found at all (a config
file is required whether or not `--tag` is given, since it also supplies `default-library`), a
config file found that doesn't list the resolved tag, or `--tag` omitted with no
`default-library` set in the config file, all print a one-line error to stderr and exit with
status 1. Unlike `book0-remote` (below), an unconfigured tag is treated as an error here, not
as an empty library.

## `book0-remote` + `book0_api` - HTTP-backed CLI

### 1. Start the server

`book0_api` serves one or more libraries, each identified by a short tag you choose. The
mapping from tag to library path is a TOML file passed via `--config` - same `[libraries]`
shape (including the optional `default-library` key) as `book0`'s own `.book0.toml` (see
above), so either CLI can read the same file. Each value can be a library's directory
(`book0_api` appends `metadata.db` itself, just like `book0` does) or a `metadata.db` file
path directly. A `default-library` set here is used server-side whenever a `book0-remote`
request omits `--tag` - it is independent of any `default-library` in a `book0` client's own
`.book0.toml`.

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
`listen = "unix:///path"`) key. Unlike `book0-remote`'s client-side config file (see below),
`--server-config` is never auto-discovered - the server is started far less often than either
CLI is invoked, so it always has to be passed explicitly:

```sh
uv run book0-api --config book0-libraries.toml --server-config .book0-server.toml
```

#### Running behind nginx (Unix domain socket)

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

#### Restricting access

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

### 2. Run the CLI against it

`--server` may be omitted - `book0-remote` then falls back to a `.book0-client.toml` file
(checked in the current directory, then `~/.config/book0/client.toml` /
`$XDG_CONFIG_HOME/book0/client.toml`), mirroring how `.book0.toml` (above) supplies
`default-library`:

```toml
server = "http://127.0.0.1:8000"
cover-cache-dir = "/path/to/local/cover/cache"
```

`cover-cache-dir` is optional - it names the local directory `books-detail --with-covers`
downloads and caches cover images into (see below). Leave it out and `book0-remote` falls back
to an XDG cache directory: `~/.cache/book0/covers` / `$XDG_CACHE_HOME/book0/covers`.

Like `book0`, add `--page-size N` to paginate `books`/`authors`/`publishers` output N rows at a
time (`--page` selects which page, defaulting to 1); a client config file may set
`default-page-size` so `--page-size` can be omitted. The server's `book0-libraries.toml` may
also set `default-page-size` as a server-side ceiling on top of the client's own
`default-page-size`/`--page-size`, protecting the server from an unbounded query.
`books-detail` is never paginated.

```sh
uv run book0-remote books --server http://127.0.0.1:8000 --tag fiction
# or just `uv run book0-remote --server ... --tag fiction` - `books` is the default
uv run book0-remote authors --server http://127.0.0.1:8000 --tag fiction
uv run book0-remote publishers --server http://127.0.0.1:8000 --tag fiction
uv run book0-remote books --server http://127.0.0.1:8000 --tag fiction --page-size 20
uv run book0-remote books --server http://127.0.0.1:8000 --tag fiction --page-size 20 --page 2
uv run book0-remote books-detail --ids 1,2,3 --server http://127.0.0.1:8000 --tag fiction
uv run book0-remote books-detail --ids 1,2,3 --with-covers --server http://127.0.0.1:8000 --tag fiction
# or, with no --tag - relies on the *server's* configured default-library, not any
# client-side setting:
uv run book0-remote --server http://127.0.0.1:8000
```

Same table output, same `No books found.` / `No authors found.` / `No publishers found.` /
`No book details found.` for an empty library. A tag
that isn't configured on the server behaves like an empty library rather than an error. A
configured-but-broken library on the server (missing file, not a Calibre library), `--tag`
omitted with no `default-library` configured on the server, or an unreachable server all print
a one-line error to stderr and exit with status 1.

`books-detail`'s `Cover Path` column shows the local filesystem path to a cover once it has
been downloaded and cached, or `(unavailable)` when the server reports the book has a cover but
it hasn't been cached locally yet - pass `--with-covers` to download and cache it (a book with
no cover at all leaves the cell blank). Without `--with-covers`, `book0-remote` still reports an
already-cached cover's local path; it just doesn't fetch anything new over the network.

## Development

```sh
uv run pytest              # full test suite
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy src            # type-check
```

See `CLAUDE.md` and `.claude/rules/` for the architecture, conventions, and workflow this
project follows, and `docs/superpowers/specs/` for the design docs behind each feature.
