import socket
import sqlite3
import subprocess
import time
import uuid as uuid_module
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from book0_core.models import (
    Author,
    Book,
    BookDetails,
    Publisher,
    Series,
    SeriesItem,
)

# Books as inserted into the fixture DB, already in the order list_books()
# is expected to return them (sorted by title). The enriched fields mirror the
# ratings link (Dune, Calibre rating 8 -> 4/5), publisher/series links, and
# has_cover flags seeded below.
CALIBRE_LIBRARY_BOOKS = [
    Book(
        id="1",
        title="Dune",
        authors=("Frank Herbert",),
        pubdate="1965-08-01",
        publisher=Publisher(id="1", name="Ace Books"),
        series=Series(id="1", name="Dune Chronicles"),
        series_index="1.0",
        rating=4,
        has_cover=True,
    ),
    Book(
        id="3",
        title="Good Omens",
        authors=("Neil Gaiman", "Terry Pratchett"),
        pubdate="1990-05-01",
        publisher=Publisher(id="2", name="Gollancz"),
        series=None,
        series_index=None,
        rating=None,
        has_cover=True,
    ),
    Book(
        id="2",
        title="The Hobbit",
        authors=("J.R.R. Tolkien",),
        pubdate=None,
        publisher=None,
        series=None,
        series_index=None,
        rating=None,
        has_cover=False,
    ),
]

# Authors as inserted into the fixture DB, already in the order list_authors()
# is expected to return them (sorted by name).
CALIBRE_LIBRARY_AUTHORS = [
    Author(id="1", name="Frank Herbert"),
    Author(id="2", name="J.R.R. Tolkien"),
    Author(id="3", name="Neil Gaiman"),
    Author(id="4", name="Terry Pratchett"),
]

# Publishers as inserted into the fixture DB, already in the order
# list_publishers() is expected to return them (sorted by name). The Hobbit
# (book id 2) is deliberately left unlinked - Calibre allows a book with no
# publisher set.
CALIBRE_LIBRARY_PUBLISHERS = [
    Publisher(id="1", name="Ace Books"),
    Publisher(id="2", name="Gollancz"),
]

# Series as inserted into the fixture DB, already in the order list_series()
# is expected to return them (sorted by name).
CALIBRE_LIBRARY_SERIES = [
    Series(id="1", name="Dune Chronicles"),
]

# BookDetails for the three books in the fixture DB, covering: a book with a
# publisher, series, and tags (Dune); a book with none of them (The Hobbit);
# a book with only some (Good Omens - publisher and tags, no series).
DUNE_DETAILS = BookDetails(
    id="1",
    title="Dune",
    pubdate="1965-08-01",
    authors=("Frank Herbert",),
    tags=("sci-fi", "classic"),
    publisher=Publisher(id="1", name="Ace Books"),
    series=SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0"),
    cover_path=None,
)

HOBBIT_DETAILS = BookDetails(
    id="2",
    title="The Hobbit",
    pubdate=None,
    authors=("J.R.R. Tolkien",),
    tags=(),
    publisher=None,
    series=None,
    cover_path=None,
)

GOOD_OMENS_DETAILS = BookDetails(
    id="3",
    title="Good Omens",
    pubdate="1990-05-01",
    authors=("Neil Gaiman", "Terry Pratchett"),
    tags=("fantasy", "humor"),
    publisher=Publisher(id="2", name="Gollancz"),
    series=None,
    cover_path=None,
)


# Expected BookDetails with absolute cover_path values, computed from a library root.
def _expected_details_with_cover(
    library_root: Path,
) -> tuple[BookDetails, BookDetails, BookDetails]:
    return (
        BookDetails(
            id="1",
            title="Dune",
            pubdate="1965-08-01",
            authors=("Frank Herbert",),
            tags=("sci-fi", "classic"),
            publisher=Publisher(id="1", name="Ace Books"),
            series=SeriesItem(
                series=Series(id="1", name="Dune Chronicles"), index="1.0"
            ),
            cover_path=str(library_root / "Frank Herbert/Dune (1)/cover.jpg"),
        ),
        BookDetails(
            id="2",
            title="The Hobbit",
            pubdate=None,
            authors=("J.R.R. Tolkien",),
            tags=(),
            publisher=None,
            series=None,
            cover_path=None,
        ),
        BookDetails(
            id="3",
            title="Good Omens",
            pubdate="1990-05-01",
            authors=("Neil Gaiman", "Terry Pratchett"),
            tags=("fantasy", "humor"),
            publisher=Publisher(id="2", name="Gollancz"),
            series=None,
            cover_path=str(library_root / "Neil Gaiman/Good Omens (3)/cover.jpg"),
        ),
    )


@pytest.fixture
def calibre_metadata_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                pubdate TEXT,
                series_index REAL,
                path TEXT,
                has_cover INTEGER
            );
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                author INTEGER NOT NULL
            );
            CREATE TABLE publishers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE books_publishers_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                publisher INTEGER NOT NULL
            );
            CREATE TABLE series (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE books_series_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                series INTEGER NOT NULL
            );
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE books_tags_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                tag INTEGER NOT NULL
            );
            CREATE TABLE ratings (
                id INTEGER PRIMARY KEY,
                rating INTEGER
            );
            CREATE TABLE books_ratings_link (
                book INTEGER,
                rating INTEGER
            );
            CREATE TABLE languages (
                id INTEGER PRIMARY KEY,
                lang_code TEXT
            );
            CREATE TABLE books_languages_link (
                book INTEGER,
                lang_code INTEGER,
                item_order INTEGER DEFAULT 0
            );
            CREATE TABLE data (
                id INTEGER PRIMARY KEY,
                book INTEGER,
                format TEXT,
                name TEXT,
                uncompressed_size INTEGER
            );
            """
        )
        connection.executemany(
            "INSERT INTO books (id, title, pubdate, series_index, path, has_cover)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "Dune", "1965-08-01", 1.0, "Frank Herbert/Dune (1)/", 1),
                (2, "The Hobbit", None, None, "J.R.R. Tolkien/The Hobbit (2)/", 0),
                (3, "Good Omens", "1990-05-01", None, "Neil Gaiman/Good Omens (3)/", 1),
            ],
        )
        connection.executemany(
            "INSERT INTO authors (id, name) VALUES (?, ?)",
            [
                (1, "Frank Herbert"),
                (2, "J.R.R. Tolkien"),
                (3, "Neil Gaiman"),
                (4, "Terry Pratchett"),
            ],
        )
        connection.executemany(
            "INSERT INTO books_authors_link (book, author) VALUES (?, ?)",
            [(1, 1), (2, 2), (3, 3), (3, 4)],
        )
        connection.executemany(
            "INSERT INTO publishers (id, name) VALUES (?, ?)",
            [
                (1, "Ace Books"),
                (2, "Gollancz"),
            ],
        )
        connection.executemany(
            "INSERT INTO books_publishers_link (book, publisher) VALUES (?, ?)",
            [(1, 1), (3, 2)],
        )
        connection.executemany(
            "INSERT INTO series (id, name) VALUES (?, ?)",
            [(1, "Dune Chronicles")],
        )
        connection.executemany(
            "INSERT INTO books_series_link (book, series) VALUES (?, ?)",
            [(1, 1)],
        )
        connection.executemany(
            "INSERT INTO tags (id, name) VALUES (?, ?)",
            [
                (1, "sci-fi"),
                (2, "classic"),
                (3, "fantasy"),
                (4, "humor"),
            ],
        )
        connection.executemany(
            "INSERT INTO books_tags_link (book, tag) VALUES (?, ?)",
            [(1, 1), (1, 2), (3, 3), (3, 4)],
        )
        # Calibre stores ratings on a 0-10 scale (2 points per star): id 1 is 4 stars.
        connection.executemany(
            "INSERT INTO ratings (id, rating) VALUES (?, ?)",
            [(1, 8)],
        )
        connection.executemany(
            "INSERT INTO books_ratings_link (book, rating) VALUES (?, ?)",
            [(1, 1)],
        )
        connection.executemany(
            "INSERT INTO languages (id, lang_code) VALUES (?, ?)",
            [(1, "fra")],
        )
        connection.executemany(
            "INSERT INTO books_languages_link (book, lang_code) VALUES (?, ?)",
            [(1, 1), (2, 1), (3, 1)],
        )
        connection.executemany(
            "INSERT INTO data (id, book, format, name, uncompressed_size)"
            " VALUES (?, ?, ?, ?, ?)",
            [(1, 1, "EPUB", "Dune", 671088)],
        )
        connection.commit()
    finally:
        connection.close()
    return db_path


@pytest.fixture
def expected_book_details(
    calibre_metadata_db: Path,
) -> tuple[BookDetails, BookDetails, BookDetails]:
    """Expected BookDetails with absolute cover_path values for the fixture library."""
    return _expected_details_with_cover(calibre_metadata_db.parent)


@pytest.fixture
def many_books_db(tmp_path: Path) -> Path:
    """7 books/authors/publishers, deliberately unlinked to each other - only counts
    and title/name ordering matter for exercising pagination beyond a single page."""
    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                pubdate TEXT,
                series_index REAL,
                path TEXT,
                has_cover INTEGER
            );
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                author INTEGER NOT NULL
            );
            CREATE TABLE publishers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE books_publishers_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                publisher INTEGER NOT NULL
            );
            CREATE TABLE series (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE books_series_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                series INTEGER NOT NULL
            );
            CREATE TABLE ratings (
                id INTEGER PRIMARY KEY,
                rating INTEGER
            );
            CREATE TABLE books_ratings_link (
                book INTEGER,
                rating INTEGER
            );
            """
        )
        connection.executemany(
            "INSERT INTO books (id, title) VALUES (?, ?)",
            [(i, f"Book {i}") for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO authors (id, name) VALUES (?, ?)",
            [(i, f"Author {i}") for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO publishers (id, name) VALUES (?, ?)",
            [(i, f"Publisher {i}") for i in range(1, 8)],
        )
        connection.executemany(
            "INSERT INTO series (id, name) VALUES (?, ?)",
            [(i, f"Series {i}") for i in range(1, 8)],
        )
        connection.commit()
    finally:
        connection.close()
    return db_path


# --- Fixtures PostgreSQL (schéma calibre_pg_sync) ---

# Copie verbatim de la DDL de
# ../../calibre_pg_sync/src/calibre_pg_sync/schema.sql (miroirs books/authors/...
# scopés par library_uuid + jobs/author_entity de P1). Le projet book0 ne dépend
# PAS du paquet calibre_pg_sync - cette constante est la seule source du schéma
# pour les tests, à resynchroniser manuellement si la DDL source change.
PG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS libraries (
    library_uuid   UUID PRIMARY KEY,
    name           TEXT NOT NULL,
    base_path      TEXT NOT NULL,
    calibre_version TEXT,
    imported_at    TIMESTAMPTZ DEFAULT now(),
    last_sync_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS books (
    book_pk        BIGSERIAL PRIMARY KEY,
    library_uuid   UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    local_id       INTEGER NOT NULL,
    uuid           TEXT,
    title          TEXT NOT NULL,
    title_sort     TEXT,
    author_sort    TEXT,
    pubdate        TIMESTAMPTZ,
    timestamp      TIMESTAMPTZ,
    last_modified  TIMESTAMPTZ NOT NULL,
    series_index   REAL,
    isbn           TEXT,
    lccn           TEXT,
    path           TEXT NOT NULL,
    flags          INTEGER,
    has_cover      BOOLEAN,
    UNIQUE (library_uuid, local_id)
);

CREATE TABLE IF NOT EXISTS authors (
    id            BIGSERIAL PRIMARY KEY,
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    local_id      INTEGER NOT NULL,
    name          TEXT NOT NULL,
    name_sort     TEXT,
    link          TEXT,
    UNIQUE (library_uuid, local_id)
);

CREATE TABLE IF NOT EXISTS books_authors_link (
    book_pk      BIGINT NOT NULL REFERENCES books(book_pk) ON DELETE CASCADE,
    author_id    BIGINT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    PRIMARY KEY (book_pk, author_id)
);

CREATE TABLE IF NOT EXISTS tags (
    id            BIGSERIAL PRIMARY KEY,
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    local_id      INTEGER NOT NULL,
    name          TEXT NOT NULL,
    UNIQUE (library_uuid, local_id)
);

CREATE TABLE IF NOT EXISTS books_tags_link (
    book_pk      BIGINT NOT NULL REFERENCES books(book_pk) ON DELETE CASCADE,
    tag_id       BIGINT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (book_pk, tag_id)
);

CREATE TABLE IF NOT EXISTS data (
    id           BIGSERIAL PRIMARY KEY,
    book_pk      BIGINT NOT NULL REFERENCES books(book_pk) ON DELETE CASCADE,
    format       TEXT NOT NULL,
    name         TEXT NOT NULL,
    uncompressed_size BIGINT,
    UNIQUE (book_pk, format)
);

CREATE TABLE IF NOT EXISTS comments (
    book_pk      BIGINT PRIMARY KEY REFERENCES books(book_pk) ON DELETE CASCADE,
    text         TEXT
);

CREATE TABLE IF NOT EXISTS identifiers (
    id           BIGSERIAL PRIMARY KEY,
    book_pk      BIGINT NOT NULL REFERENCES books(book_pk) ON DELETE CASCADE,
    type         TEXT NOT NULL,
    val          TEXT NOT NULL,
    UNIQUE (book_pk, type)
);

CREATE TABLE IF NOT EXISTS sync_state (
    library_uuid  UUID PRIMARY KEY REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    last_synced_modified  TIMESTAMPTZ,
    last_sync_run_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS tombstones (
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    local_id      INTEGER NOT NULL,
    deleted_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (library_uuid, local_id)
);

-- Dimensions supplémentaires (spec 2026-08-31-migrate-series-publishers-ratings-languages)

CREATE TABLE IF NOT EXISTS series (
    id            BIGSERIAL PRIMARY KEY,
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    local_id      INTEGER NOT NULL,
    name          TEXT NOT NULL,
    name_sort     TEXT,
    UNIQUE (library_uuid, local_id)
);

CREATE TABLE IF NOT EXISTS publishers (
    id            BIGSERIAL PRIMARY KEY,
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    local_id      INTEGER NOT NULL,
    name          TEXT NOT NULL,
    name_sort     TEXT,
    UNIQUE (library_uuid, local_id)
);

CREATE TABLE IF NOT EXISTS ratings (
    id            BIGSERIAL PRIMARY KEY,
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    local_id      INTEGER NOT NULL,
    rating        INTEGER NOT NULL,
    UNIQUE (library_uuid, local_id)
);

CREATE TABLE IF NOT EXISTS languages (
    id            BIGSERIAL PRIMARY KEY,
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    local_id      INTEGER NOT NULL,
    lang_code     TEXT NOT NULL,
    name          TEXT,
    UNIQUE (library_uuid, local_id)
);

CREATE TABLE IF NOT EXISTS books_series_link (
    book_pk      BIGINT NOT NULL REFERENCES books(book_pk) ON DELETE CASCADE,
    series_id    BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    ord          REAL,
    PRIMARY KEY (book_pk, series_id)
);

CREATE TABLE IF NOT EXISTS books_publishers_link (
    book_pk        BIGINT NOT NULL REFERENCES books(book_pk) ON DELETE CASCADE,
    publisher_id   BIGINT NOT NULL REFERENCES publishers(id) ON DELETE CASCADE,
    PRIMARY KEY (book_pk, publisher_id)
);

CREATE TABLE IF NOT EXISTS books_ratings_link (
    book_pk     BIGINT NOT NULL REFERENCES books(book_pk) ON DELETE CASCADE,
    rating_id   BIGINT NOT NULL REFERENCES ratings(id) ON DELETE CASCADE,
    PRIMARY KEY (book_pk, rating_id)
);

CREATE TABLE IF NOT EXISTS books_languages_link (
    book_pk      BIGINT NOT NULL REFERENCES books(book_pk) ON DELETE CASCADE,
    language_id  BIGINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
    item_order   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (book_pk, language_id)
);

-- Notes et liens (spec 2026-08-31-notes-and-links-design)

ALTER TABLE authors    ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE series     ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE publishers ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE tags       ADD COLUMN IF NOT EXISTS note TEXT;

CREATE TABLE IF NOT EXISTS links (
    id            BIGSERIAL PRIMARY KEY,
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    entity_type   TEXT NOT NULL CHECK (entity_type IN ('author','series','publisher','tag')),
    entity_id     BIGINT NOT NULL,
    url           TEXT NOT NULL,
    label         TEXT,
    UNIQUE (entity_type, entity_id, url)
);

CREATE INDEX IF NOT EXISTS idx_links_entity ON links (entity_type, entity_id);

-- ============================================================
-- Grimoire API (specs 2026-08-31) : jobs de fond
-- ============================================================

CREATE TABLE IF NOT EXISTS jobs (
    id            UUID PRIMARY KEY,
    library_uuid  UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    action        TEXT NOT NULL CHECK (action IN ('convert-markdown', 'sync-library')),
    status        TEXT NOT NULL CHECK (status IN ('pending', 'running', 'done', 'failed', 'interrupted')),
    params        JSONB,
    outcome       JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    CHECK ((status IN ('done', 'failed')) = (outcome IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_jobs_library_status_created
    ON jobs (library_uuid, status, created_at);

-- ============================================================
-- Grimoire API (specs 2026-08-31) : groupes d'alias d'auteurs
-- ============================================================

CREATE TABLE IF NOT EXISTS author_entity (
    id                UUID PRIMARY KEY,
    library_uuid      UUID NOT NULL REFERENCES libraries(library_uuid) ON DELETE CASCADE,
    display_author_id BIGINT REFERENCES authors(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS author_entity_member (
    entity_id UUID NOT NULL REFERENCES author_entity(id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    PRIMARY KEY (entity_id, author_id),
    UNIQUE (author_id)
);
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def pg_dsn():
    """PostgreSQL docker jetable (postgres:16-alpine, port libre, 60 s max)."""
    port = _free_port()
    name = f"book0-pgtest-{uuid_module.uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=test",
            "-e",
            "POSTGRES_DB=test",
            "-p",
            f"{port}:5432",
            "postgres:16-alpine",
        ],
        check=True,
        capture_output=True,
    )
    dsn = f"postgresql://postgres:test@localhost:{port}/test"
    try:
        deadline = time.time() + 60
        while True:
            try:
                psycopg.connect(dsn, connect_timeout=3).close()
                break
            except psycopg.OperationalError:
                if time.time() > deadline:
                    raise RuntimeError("Conteneur PostgreSQL non prêt après 60 s")
                time.sleep(1)
        yield dsn
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)


@pytest.fixture
def pg_schema(pg_dsn):
    """Réinitialise le schéma public et applique la DDL calibre_pg_sync."""
    conn = psycopg.connect(pg_dsn)
    try:
        with conn.cursor() as cur:
            # Ferme les connexions de gateways encore ouvertes par le test
            # précédent, sinon leur verrou ACCESS SHARE bloque le DROP SCHEMA.
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                " WHERE datname = current_database()"
                " AND pid <> pg_backend_pid()"
            )
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            cur.execute(PG_SCHEMA_SQL)
        conn.commit()
        yield conn
    finally:
        conn.close()


# Bibliothèque seedée : mêmes ids locaux, mêmes noms que la fixture SQLite
# calibre_metadata_db, pour que les tests SQLite et PG partagent les listes
# attendues (CALIBRE_LIBRARY_*) et tournent en parallèle.
GRIMOIRE_TEST_LIBRARY_UUID = "5b1a2c3d-0000-4000-8000-00000000abcd"


@pytest.fixture
def pg_library_root(tmp_path: Path) -> Path:
    """Répertoire racine de la bibliothèque PG seedée (pour les cover_path)."""
    root = tmp_path / "grimoire-test"
    root.mkdir()
    return root


@pytest.fixture
def pg_library(pg_dsn, pg_schema, pg_library_root: Path) -> str:
    """Bibliothèque PG 'grimoire-test' seedée à l'identique de calibre_metadata_db."""
    lib_uuid = GRIMOIRE_TEST_LIBRARY_UUID
    conn = pg_schema
    stamp = datetime(2024, 1, 1, tzinfo=UTC)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO libraries (library_uuid, name, base_path) VALUES (%s, %s, %s)",
            (lib_uuid, "grimoire-test", str(pg_library_root)),
        )
        cur.executemany(
            "INSERT INTO books (library_uuid, local_id, uuid, title, title_sort,"
            " author_sort, pubdate, timestamp, last_modified, series_index, path,"
            " flags, has_cover)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    lib_uuid,
                    1,
                    "uuid-book-1",
                    "Dune",
                    "Dune",
                    "Herbert, Frank",
                    datetime(1965, 8, 1, tzinfo=UTC),
                    stamp,
                    stamp,
                    1.0,
                    "Frank Herbert/Dune (1)/",
                    1,
                    True,
                ),
                (
                    lib_uuid,
                    2,
                    "uuid-book-2",
                    "The Hobbit",
                    "Hobbit, The",
                    "Tolkien, J.R.R.",
                    None,
                    stamp,
                    stamp,
                    None,
                    "J.R.R. Tolkien/The Hobbit (2)/",
                    1,
                    False,
                ),
                (
                    lib_uuid,
                    3,
                    "uuid-book-3",
                    "Good Omens",
                    "Good Omens",
                    "Gaiman, Neil, Pratchett, Terry",
                    datetime(1990, 5, 1, tzinfo=UTC),
                    stamp,
                    stamp,
                    None,
                    "Neil Gaiman/Good Omens (3)/",
                    1,
                    True,
                ),
            ],
        )
        cur.executemany(
            "INSERT INTO authors (library_uuid, local_id, name) VALUES (%s, %s, %s)",
            [
                (lib_uuid, 1, "Frank Herbert"),
                (lib_uuid, 2, "J.R.R. Tolkien"),
                (lib_uuid, 3, "Neil Gaiman"),
                (lib_uuid, 4, "Terry Pratchett"),
            ],
        )
        cur.executemany(
            "INSERT INTO books_authors_link (book_pk, author_id) VALUES (%s, %s)",
            [(1, 1), (2, 2), (3, 3), (3, 4)],
        )
        cur.executemany(
            "INSERT INTO publishers (library_uuid, local_id, name) VALUES (%s, %s, %s)",
            [(lib_uuid, 1, "Ace Books"), (lib_uuid, 2, "Gollancz")],
        )
        cur.executemany(
            "INSERT INTO books_publishers_link (book_pk, publisher_id) VALUES (%s, %s)",
            [(1, 1), (3, 2)],
        )
        cur.execute(
            "INSERT INTO series (library_uuid, local_id, name) VALUES (%s, %s, %s)",
            (lib_uuid, 1, "Dune Chronicles"),
        )
        cur.execute(
            "INSERT INTO books_series_link (book_pk, series_id, ord)"
            " VALUES (%s, %s, %s)",
            (1, 1, 1.0),
        )
        cur.executemany(
            "INSERT INTO tags (library_uuid, local_id, name) VALUES (%s, %s, %s)",
            [
                (lib_uuid, 1, "sci-fi"),
                (lib_uuid, 2, "classic"),
                (lib_uuid, 3, "fantasy"),
                (lib_uuid, 4, "humor"),
            ],
        )
        cur.executemany(
            "INSERT INTO books_tags_link (book_pk, tag_id) VALUES (%s, %s)",
            [(1, 1), (1, 2), (3, 3), (3, 4)],
        )
        # Calibre stocke les notes sur 0-10 (2 points par étoile) : id 1 = 4 étoiles.
        cur.execute(
            "INSERT INTO ratings (library_uuid, local_id, rating) VALUES (%s, %s, %s)",
            (lib_uuid, 1, 8),
        )
        cur.execute(
            "INSERT INTO books_ratings_link (book_pk, rating_id) VALUES (%s, %s)",
            (1, 1),
        )
        cur.execute(
            "INSERT INTO languages (library_uuid, local_id, lang_code, name)"
            " VALUES (%s, %s, %s, %s)",
            (lib_uuid, 1, "fra", "French"),
        )
        cur.executemany(
            "INSERT INTO books_languages_link (book_pk, language_id, item_order)"
            " VALUES (%s, %s, %s)",
            [(1, 1, 0), (2, 1, 0), (3, 1, 0)],
        )
        cur.execute(
            "INSERT INTO data (book_pk, format, name, uncompressed_size)"
            " VALUES (%s, %s, %s, %s)",
            (1, "EPUB", "Dune", 671088),
        )
    conn.commit()
    return pg_dsn


@pytest.fixture
def pg_library_with_sentinel_pubdate(pg_library):
    """pg_library + un 4e livre à pubdate sentinelle Calibre (année 101).

    Calibre encode « pas de date de publication » comme la sentinelle
    calibre.utils.date.UNDEFINED_DATE (an 101) et non comme NULL : _PUBDATE_SQL
    doit la neutraliser exactement comme un vrai NULL. Fixture dérivée pour ne
    pas désynchroniser pg_library du seed SQLite que les listes attendues
    (CALIBRE_LIBRARY_*) partagent entre les deux backends.
    """
    conn = psycopg.connect(pg_library)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO books (library_uuid, local_id, uuid, title, title_sort,"
                " author_sort, pubdate, timestamp, last_modified, series_index, path,"
                " flags, has_cover)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    GRIMOIRE_TEST_LIBRARY_UUID,
                    4,
                    "uuid-book-4",
                    "Sentinel Book",
                    "Sentinel Book",
                    "Unknown, Author",
                    datetime(101, 1, 1, tzinfo=UTC),  # sentinelle Calibre an 101
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 1, tzinfo=UTC),
                    None,
                    "Unknown/Sentinel Book (4)/",
                    1,
                    False,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return pg_library
