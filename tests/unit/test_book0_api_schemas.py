from book0_api.schemas import BookOut
from book0_core.models import Book


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
