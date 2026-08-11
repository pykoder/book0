import sqlite3
from pathlib import Path

import pytest

from book0_core.models import Author, Book, Publisher

# Books as inserted into the fixture DB, already in the order list_books()
# is expected to return them (sorted by title).
CALIBRE_LIBRARY_BOOKS = [
    Book(id=1, title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01"),
    Book(
        id=3,
        title="Good Omens",
        authors=("Neil Gaiman", "Terry Pratchett"),
        pubdate="1990-05-01",
    ),
    Book(id=2, title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None),
]

# Authors as inserted into the fixture DB, already in the order list_authors()
# is expected to return them (sorted by name).
CALIBRE_LIBRARY_AUTHORS = [
    Author(id=1, name="Frank Herbert"),
    Author(id=2, name="J.R.R. Tolkien"),
    Author(id=3, name="Neil Gaiman"),
    Author(id=4, name="Terry Pratchett"),
]

# Publishers as inserted into the fixture DB, already in the order
# list_publishers() is expected to return them (sorted by name). The Hobbit
# (book id 2) is deliberately left unlinked - Calibre allows a book with no
# publisher set.
CALIBRE_LIBRARY_PUBLISHERS = [
    Publisher(id=1, name="Ace Books"),
    Publisher(id=2, name="Gollancz"),
]


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
                pubdate TEXT
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
            """
        )
        connection.executemany(
            "INSERT INTO books (id, title, pubdate) VALUES (?, ?, ?)",
            [
                (1, "Dune", "1965-08-01"),
                (2, "The Hobbit", None),
                (3, "Good Omens", "1990-05-01"),
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
        connection.commit()
    finally:
        connection.close()
    return db_path
