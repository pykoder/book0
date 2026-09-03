import pytest

from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    BookQuery,
    BookSort,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
    Series,
    SeriesItem,
    SortOrder,
)


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


def test_series_holds_id_and_name():
    series = Series(id="1", name="Dune Chronicles")

    assert series.id == "1"
    assert series.name == "Dune Chronicles"


def test_series_is_frozen():
    series = Series(id="1", name="Dune Chronicles")

    with pytest.raises(AttributeError):
        series.name = "Other"


def test_series_item_holds_series_and_index():
    series_item = SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0")

    assert series_item.series == Series(id="1", name="Dune Chronicles")
    assert series_item.index == "1.0"


def test_series_item_accepts_none_index():
    series_item = SeriesItem(series=Series(id="1", name="Dune Chronicles"), index=None)

    assert series_item.index is None


def test_series_item_is_frozen():
    series_item = SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0")

    with pytest.raises(AttributeError):
        series_item.index = "2.0"


def test_book_details_holds_all_fields():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate="1965-08-01",
        authors=("Frank Herbert",),
        tags=("sci-fi", "classic"),
        publisher=Publisher(id="1", name="Ace Books"),
        series=SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0"),
    )

    assert book_details.id == "1"
    assert book_details.title == "Dune"
    assert book_details.pubdate == "1965-08-01"
    assert book_details.authors == ("Frank Herbert",)
    assert book_details.tags == ("sci-fi", "classic")
    assert book_details.publisher == Publisher(id="1", name="Ace Books")
    assert book_details.series == SeriesItem(
        series=Series(id="1", name="Dune Chronicles"), index="1.0"
    )


def test_book_details_accepts_none_publisher_and_series():
    book_details = BookDetails(
        id="2",
        title="The Hobbit",
        pubdate=None,
        authors=("J.R.R. Tolkien",),
        tags=(),
        publisher=None,
        series=None,
    )

    assert book_details.publisher is None
    assert book_details.series is None


def test_book_details_is_frozen():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )

    with pytest.raises(AttributeError):
        book_details.title = "Other"


def test_book_details_result_holds_books_and_missing_ids():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )
    result = BookDetailsResult(books=(book_details,), missing_ids=("99",))

    assert result.books == (book_details,)
    assert result.missing_ids == ("99",)


def test_book_details_result_is_frozen():
    result = BookDetailsResult(books=(), missing_ids=())

    with pytest.raises(AttributeError):
        result.missing_ids = ("1",)


def test_paged_books_result_holds_items_and_page_metadata():
    result = PagedBooksResult(
        items=(Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate=None),),
        page=1,
        page_size=20,
        total_pages=3,
        has_more_than_shown=False,
        handle="abc123",
    )

    assert result.page == 1
    assert result.page_size == 20
    assert result.total_pages == 3
    assert result.has_more_than_shown is False
    assert result.handle == "abc123"


def test_paged_books_result_accepts_none_total_pages_and_none_handle():
    result = PagedBooksResult(
        items=(),
        page=5,
        page_size=20,
        total_pages=None,
        has_more_than_shown=True,
        handle=None,
    )

    assert result.total_pages is None
    assert result.handle is None


def test_paged_books_result_is_frozen():
    result = PagedBooksResult(
        items=(),
        page=1,
        page_size=20,
        total_pages=0,
        has_more_than_shown=False,
        handle=None,
    )

    with pytest.raises(AttributeError):
        result.page = 2


def test_paged_authors_result_holds_items_and_page_metadata():
    result = PagedAuthorsResult(
        items=(Author(id="1", name="Frank Herbert"),),
        page=1,
        page_size=20,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    assert result.items == (Author(id="1", name="Frank Herbert"),)
    assert result.total_pages == 1


def test_paged_publishers_result_holds_items_and_page_metadata():
    result = PagedPublishersResult(
        items=(Publisher(id="1", name="Ace Books"),),
        page=1,
        page_size=20,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    assert result.items == (Publisher(id="1", name="Ace Books"),)
    assert result.total_pages == 1


def test_book_nouveaux_champs_optionnels():
    b = Book(id="1", title="T", authors=("A",), pubdate=None)
    assert b.publisher is None and b.series is None
    assert b.series_index is None and b.rating is None and b.has_cover is False


def test_book_query_defaut_vide():
    q = BookQuery()
    assert q.author_ids == () and q.ratings == ()
    assert q.sort is BookSort.TITLE and q.order is SortOrder.ASC


def test_book_sort_valeurs():
    assert BookSort("series_index") is BookSort.SERIES_INDEX
    assert SortOrder("desc") is SortOrder.DESC
