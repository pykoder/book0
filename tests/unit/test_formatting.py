from book0_cli.formatting import render_table
from book0_core.models import Book


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
