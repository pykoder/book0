from datetime import datetime

from book0_core.models import Book

_HEADERS = ("ID", "Title", "Author(s)", "Pub Date")
_COLUMN_GAP = "  "


def _format_pubdate(pubdate: str | None) -> str:
    if pubdate is None:
        return ""
    return datetime.fromisoformat(pubdate).date().isoformat()


def render_table(books: list[Book]) -> str:
    if not books:
        return "No books found."

    rows = [_HEADERS] + [
        (
            str(book.id),
            book.title,
            ", ".join(book.authors),
            _format_pubdate(book.pubdate),
        )
        for book in books
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(len(_HEADERS))]

    lines = [
        _COLUMN_GAP.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in rows
    ]
    return "\n".join(lines)
