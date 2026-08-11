from datetime import datetime

from book0_core.models import Author, Book

_BOOK_HEADERS = ("ID", "Title", "Author(s)", "Pub Date")
_AUTHOR_HEADERS = ("ID", "Name")
_COLUMN_GAP = "  "


def _format_pubdate(pubdate: str | None) -> str:
    if pubdate is None:
        return ""
    return datetime.fromisoformat(pubdate).date().isoformat()


def _align_rows(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    table = [headers] + rows
    widths = [max(len(row[i]) for row in table) for i in range(len(headers))]
    lines = [
        _COLUMN_GAP.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in table
    ]
    return "\n".join(lines)


def render_book_table(books: list[Book]) -> str:
    if not books:
        return "No books found."

    rows: list[tuple[str, ...]] = [
        (
            str(book.id),
            book.title,
            ", ".join(book.authors),
            _format_pubdate(book.pubdate),
        )
        for book in books
    ]
    return _align_rows(_BOOK_HEADERS, rows)


def render_author_table(authors: list[Author]) -> str:
    if not authors:
        return "No authors found."

    rows: list[tuple[str, ...]] = [(str(author.id), author.name) for author in authors]
    return _align_rows(_AUTHOR_HEADERS, rows)
