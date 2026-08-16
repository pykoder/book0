import sqlite3
from pathlib import Path

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
# is expected to return them (sorted by title).
CALIBRE_LIBRARY_BOOKS = [
    Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01"),
    Book(
        id="3",
        title="Good Omens",
        authors=("Neil Gaiman", "Terry Pratchett"),
        pubdate="1990-05-01",
    ),
    Book(id="2", title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None),
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
            cover_path=str(
                library_root / "Frank Herbert/Dune (1)/cover.jpg"
            ),
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
            cover_path=str(
                library_root / "Neil Gaiman/Good Omens (3)/cover.jpg"
            ),
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
