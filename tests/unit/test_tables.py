from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    Publisher,
    Series,
    SeriesItem,
)
from book0_presentation.tables import (
    format_missing_ids_message,
    order_book_details_by_ids,
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)


def test_render_book_table_aligns_columns_with_headers():
    books = [
        Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01"),
        Book(
            id="3",
            title="Good Omens",
            authors=("Neil Gaiman", "Terry Pratchett"),
            pubdate="1990-05-01",
        ),
        Book(id="2", title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None),
    ]

    output = render_book_table(books)

    assert output == (
        "ID  Title       Author(s)                     Pub Date\n"
        "1   Dune        Frank Herbert                 1965-08-01\n"
        "3   Good Omens  Neil Gaiman, Terry Pratchett  1990-05-01\n"
        "2   The Hobbit  J.R.R. Tolkien"
    )


def test_render_book_table_reports_empty_library():
    assert render_book_table([]) == "No books found."


def test_render_book_table_shows_date_only_when_pubdate_has_a_time_component():
    books = [
        Book(
            id="1",
            title="Dune",
            authors=("Frank Herbert",),
            pubdate="1965-08-01T23:00:00+00:00",
        ),
    ]

    output = render_book_table(books)

    assert output == (
        "ID  Title  Author(s)      Pub Date\n1   Dune   Frank Herbert  1965-08-01"
    )


def test_render_book_table_shows_empty_pubdate_when_none():
    books = [
        Book(id="1", title="Dune", authors=("Frank Herbert",), pubdate=None),
    ]

    output = render_book_table(books)

    assert output == "ID  Title  Author(s)      Pub Date\n1   Dune   Frank Herbert"


def test_render_author_table_aligns_columns_with_headers():
    authors = [
        Author(id="1", name="Frank Herbert"),
        Author(id="3", name="Neil Gaiman"),
        Author(id="2", name="J.R.R. Tolkien"),
    ]

    output = render_author_table(authors)

    assert output == (
        "ID  Name\n1   Frank Herbert\n3   Neil Gaiman\n2   J.R.R. Tolkien"
    )


def test_render_author_table_reports_empty_library():
    assert render_author_table([]) == "No authors found."


def test_render_publisher_table_aligns_columns_with_headers():
    publishers = [
        Publisher(id="1", name="Ace Books"),
        Publisher(id="2", name="Gollancz"),
    ]

    output = render_publisher_table(publishers)

    assert output == "ID  Name\n1   Ace Books\n2   Gollancz"


def test_render_publisher_table_reports_empty_library():
    assert render_publisher_table([]) == "No publishers found."


def test_render_book_details_table_aligns_columns_with_headers():
    books = [
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
            cover_path="/library/Frank Herbert/Dune (1)/cover.jpg",
        ),
        BookDetails(
            id="2",
            title="The Hobbit",
            pubdate=None,
            authors=("J.R.R. Tolkien",),
            tags=(),
            publisher=None,
            series=None,
        ),
    ]

    output = render_book_details_table(books)
    # Compare with runs of whitespace collapsed to a single space, so this
    # test checks column content/order, not exact padding widths (which
    # _align_rows already has dedicated coverage for via the other
    # render_*_table tests).
    lines = [" ".join(line.split()) for line in output.splitlines()]

    assert lines[0] == "ID Title Authors Publisher Series Series Index Tags Pub Date Cover Path"
    assert lines[1] == (
        "1 Dune Frank Herbert Ace Books Dune Chronicles 1.0 sci-fi & classic"
        " 1965-08-01 /library/Frank Herbert/Dune (1)/cover.jpg"
    )
    assert lines[2] == "2 The Hobbit J.R.R. Tolkien"


def test_render_book_details_table_joins_multiple_authors_and_tags_with_ampersand():
    books = [
        BookDetails(
            id="3",
            title="Good Omens",
            pubdate="1990-05-01",
            authors=("Neil Gaiman", "Terry Pratchett"),
            tags=("fantasy", "humor"),
            publisher=Publisher(id="2", name="Gollancz"),
            series=None,
        ),
    ]

    output = render_book_details_table(books)

    assert "Neil Gaiman & Terry Pratchett" in output
    assert "fantasy & humor" in output


def test_render_book_details_table_reports_empty_list():
    assert render_book_details_table([]) == "No book details found."


def test_order_book_details_by_ids_reorders_to_match_requested_order():
    dune = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )
    hobbit = BookDetails(
        id="2",
        title="The Hobbit",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )
    result = BookDetailsResult(books=(dune, hobbit), missing_ids=())

    ordered = order_book_details_by_ids(result, ["2", "1"])

    assert ordered == [hobbit, dune]


def test_order_book_details_by_ids_skips_ids_not_in_the_result():
    dune = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )
    result = BookDetailsResult(books=(dune,), missing_ids=("999",))

    ordered = order_book_details_by_ids(result, ["1", "999"])

    assert ordered == [dune]


def test_order_book_details_by_ids_skips_duplicate_requested_ids():
    dune = BookDetails(
        id="1",
        title="Dune",
        pubdate=None,
        authors=(),
        tags=(),
        publisher=None,
        series=None,
    )
    result = BookDetailsResult(books=(dune,), missing_ids=())

    ordered = order_book_details_by_ids(result, ["1", "1"])

    assert ordered == [dune]


def test_format_missing_ids_message_returns_none_when_empty():
    assert format_missing_ids_message(()) is None


def test_format_missing_ids_message_joins_ids():
    assert format_missing_ids_message(("1", "2")) == "Missing ids: 1, 2"
