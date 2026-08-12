import pytest

from book0_core.models import Author, Book, Publisher


def test_book_holds_id_title_authors_and_pubdate():
    book = Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01")

    assert book.id == "1"
    assert book.title == "Dune"
    assert book.authors == ("Frank Herbert",)
    assert book.pubdate == "1965-08-01"


def test_book_accepts_none_pubdate():
    book = Book(id="2", title="Unknown", authors=("Someone",), pubdate=None)

    assert book.pubdate is None


def test_book_is_frozen():
    book = Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate=None)

    with pytest.raises(AttributeError):
        book.title = "Other"


def test_author_holds_id_and_name():
    author = Author(id="1", name="Frank Herbert")

    assert author.id == "1"
    assert author.name == "Frank Herbert"


def test_author_is_frozen():
    author = Author(id="1", name="Frank Herbert")

    with pytest.raises(AttributeError):
        author.name = "Other"


def test_publisher_holds_id_and_name():
    publisher = Publisher(id="1", name="Ace Books")

    assert publisher.id == "1"
    assert publisher.name == "Ace Books"


def test_publisher_is_frozen():
    publisher = Publisher(id="1", name="Ace Books")

    with pytest.raises(AttributeError):
        publisher.name = "Other"
