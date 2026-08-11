from book0_api.schemas import AuthorOut, BookOut, PublisherOut
from book0_core.models import Author, Book, Publisher


def test_from_book_converts_authors_tuple_to_list():
    book = Book(
        id=3,
        title="Good Omens",
        authors=("Neil Gaiman", "Terry Pratchett"),
        pubdate="1990-05-01",
    )

    book_out = BookOut.from_book(book)

    assert book_out == BookOut(
        id=3,
        title="Good Omens",
        authors=["Neil Gaiman", "Terry Pratchett"],
        pubdate="1990-05-01",
    )


def test_from_book_keeps_none_pubdate():
    book = Book(id=2, title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None)

    book_out = BookOut.from_book(book)

    assert book_out.pubdate is None


def test_from_author_converts_author_to_author_out():
    author = Author(id=3, name="Neil Gaiman")

    author_out = AuthorOut.from_author(author)

    assert author_out == AuthorOut(id=3, name="Neil Gaiman")


def test_from_publisher_converts_publisher_to_publisher_out():
    publisher = Publisher(id=1, name="Ace Books")

    publisher_out = PublisherOut.from_publisher(publisher)

    assert publisher_out == PublisherOut(id=1, name="Ace Books")
