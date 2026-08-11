from book0_core.models import Book
from book0_presentation.tables import render_table


def test_render_table_aligns_columns_with_headers():
    books = [
        Book(id=1, title="Dune", authors=("Frank Herbert",), pubdate="1965-08-01"),
        Book(
            id=3,
            title="Good Omens",
            authors=("Neil Gaiman", "Terry Pratchett"),
            pubdate="1990-05-01",
        ),
        Book(id=2, title="The Hobbit", authors=("J.R.R. Tolkien",), pubdate=None),
    ]

    output = render_table(books)

    assert output == (
        "ID  Title       Author(s)                     Pub Date\n"
        "1   Dune        Frank Herbert                 1965-08-01\n"
        "3   Good Omens  Neil Gaiman, Terry Pratchett  1990-05-01\n"
        "2   The Hobbit  J.R.R. Tolkien"
    )


def test_render_table_reports_empty_library():
    assert render_table([]) == "No books found."


def test_render_table_shows_date_only_when_pubdate_has_a_time_component():
    books = [
        Book(
            id=1,
            title="Dune",
            authors=("Frank Herbert",),
            pubdate="1965-08-01T23:00:00+00:00",
        ),
    ]

    output = render_table(books)

    assert output == (
        "ID  Title  Author(s)      Pub Date\n1   Dune   Frank Herbert  1965-08-01"
    )


def test_render_table_shows_empty_pubdate_when_none():
    books = [
        Book(id=1, title="Dune", authors=("Frank Herbert",), pubdate=None),
    ]

    output = render_table(books)

    assert output == "ID  Title  Author(s)      Pub Date\n1   Dune   Frank Herbert"
