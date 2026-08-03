import pytest

from book0_core.models import Book


def test_book_holds_id_title_authors_and_pubdate():
    book = Book(id=1, title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01")

    assert book.id == 1
    assert book.title == "Dune"
    assert book.authors == ("Frank Herbert",)
    assert book.pubdate == "1965-08-01"


def test_book_accepts_none_pubdate():
    book = Book(id=2, title="Unknown", authors=("Someone",), pubdate=None)

    assert book.pubdate is None


def test_book_is_frozen():
    book = Book(id=1, title="Dune", authors=("Frank Herbert",), pubdate=None)

    with pytest.raises(AttributeError):
        book.title = "Other"
