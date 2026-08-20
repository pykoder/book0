from book0_api.schemas import (
    AuthorOut,
    BookDetailsOut,
    BookDetailsResultOut,
    BookOut,
    PagedAuthorsOut,
    PagedBooksOut,
    PagedPublishersOut,
    PublisherOut,
    SeriesItemOut,
    SeriesOut,
)
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
    Series,
    SeriesItem,
)


def test_from_book_converts_authors_tuple_to_list():
    book = Book(
        id="3",
        title="Good Omens",
        authors=("Neil Gaiman", "Terry Pratchett"),
        pubdate="1990-05-01",
    )

    book_out = BookOut.from_book(book)

    assert book_out == BookOut(
        id="3",
        title="Good Omens",
        authors=["Neil Gaiman", "Terry Pratchett"],
        pubdate="1990-05-01",
    )


def test_from_book_keeps_none_pubdate():
    book = Book(id="2", title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None)

    book_out = BookOut.from_book(book)

    assert book_out.pubdate is None


def test_from_author_converts_author_to_author_out():
    author = Author(id="3", name="Neil Gaiman")

    author_out = AuthorOut.from_author(author)

    assert author_out == AuthorOut(id="3", name="Neil Gaiman")


def test_from_publisher_converts_publisher_to_publisher_out():
    publisher = Publisher(id="1", name="Ace Books")

    publisher_out = PublisherOut.from_publisher(publisher)

    assert publisher_out == PublisherOut(id="1", name="Ace Books")


def test_from_series_converts_series_to_series_out():
    series = Series(id="1", name="Dune Chronicles")

    series_out = SeriesOut.from_series(series)

    assert series_out == SeriesOut(id="1", name="Dune Chronicles")


def test_from_series_item_converts_series_item_to_series_item_out():
    series_item = SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0")

    series_item_out = SeriesItemOut.from_series_item(series_item)

    assert series_item_out == SeriesItemOut(
        series=SeriesOut(id="1", name="Dune Chronicles"), index="1.0"
    )


def test_from_book_details_converts_book_details_with_everything_populated():
    book_details = BookDetails(
        id="1",
        title="Dune",
        pubdate="1965-08-01",
        authors=("Frank Herbert",),
        tags=("sci-fi", "classic"),
        publisher=Publisher(id="1", name="Ace Books"),
        series=SeriesItem(series=Series(id="1", name="Dune Chronicles"), index="1.0"),
        cover_path="/library/Frank Herbert/Dune (1)/cover.jpg",
    )

    book_details_out = BookDetailsOut.from_book_details(book_details)

    assert book_details_out == BookDetailsOut(
        id="1",
        title="Dune",
        pubdate="1965-08-01",
        authors=["Frank Herbert"],
        tags=["sci-fi", "classic"],
        publisher=PublisherOut(id="1", name="Ace Books"),
        series=SeriesItemOut(
            series=SeriesOut(id="1", name="Dune Chronicles"), index="1.0"
        ),
        has_cover=True,
    )


def test_from_book_details_converts_book_details_with_no_publisher_or_series():
    book_details = BookDetails(
        id="2",
        title="The Hobbit",
        pubdate=None,
        authors=("J.R.R. Tolkien",),
        tags=(),
        publisher=None,
        series=None,
    )

    book_details_out = BookDetailsOut.from_book_details(book_details)

    assert book_details_out.publisher is None
    assert book_details_out.series is None
    assert book_details_out.tags == []
    assert book_details_out.has_cover is False


def test_from_book_details_result_converts_books_and_missing_ids():
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

    result_out = BookDetailsResultOut.from_book_details_result(result)

    assert result_out == BookDetailsResultOut(
        books=[BookDetailsOut.from_book_details(book_details)],
        missing_ids=["99"],
    )


def test_paged_books_out_maps_every_field():
    book = Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01")
    result = PagedBooksResult(
        items=(book,),
        page=2,
        page_size=10,
        total_pages=5,
        has_more_than_shown=False,
        handle="abc123",
    )

    out = PagedBooksOut.from_paged_result(result)

    assert len(out.items) == 1
    assert out.items[0].id == "1"
    assert out.items[0].title == "Dune"
    assert out.items[0].authors == ["Frank Herbert"]
    assert out.items[0].pubdate == "1965-08-01"
    assert out.page == 2
    assert out.page_size == 10
    assert out.total_pages == 5
    assert out.has_more_than_shown is False


def test_paged_books_out_reports_none_total_pages_when_capped():
    result = PagedBooksResult(
        items=(),
        page=1,
        page_size=10,
        total_pages=None,
        has_more_than_shown=True,
        handle=None,
    )

    out = PagedBooksOut.from_paged_result(result)

    assert out.total_pages is None
    assert out.has_more_than_shown is True


def test_paged_authors_out_maps_every_field():
    author = Author(id="1", name="Frank Herbert")
    result = PagedAuthorsResult(
        items=(author,),
        page=1,
        page_size=5,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    out = PagedAuthorsOut.from_paged_result(result)

    assert out.items[0].id == "1"
    assert out.items[0].name == "Frank Herbert"
    assert out.page == 1


def test_paged_publishers_out_maps_every_field():
    publisher = Publisher(id="1", name="Ace Books")
    result = PagedPublishersResult(
        items=(publisher,),
        page=1,
        page_size=5,
        total_pages=1,
        has_more_than_shown=False,
        handle=None,
    )

    out = PagedPublishersOut.from_paged_result(result)

    assert out.items[0].id == "1"
    assert out.items[0].name == "Ace Books"
