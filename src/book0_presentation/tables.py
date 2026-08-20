from datetime import datetime
from typing import Literal

from book0_core.models import Author, Book, BookDetails, BookDetailsResult, Publisher

_BOOK_HEADERS = ("ID", "Title", "Author(s)", "Pub Date")
_AUTHOR_HEADERS = ("ID", "Name")
_PUBLISHER_HEADERS = ("ID", "Name")
_BOOK_DETAILS_HEADERS = (
    "ID",
    "Title",
    "Authors",
    "Publisher",
    "Series",
    "Series Index",
    "Tags",
    "Pub Date",
    "Cover Path",
)
_COLUMN_GAP = "  "
_LIST_SEPARATOR = " & "


def _format_pubdate(pubdate: str | None) -> str:
    if pubdate is None:
        return ""
    return datetime.fromisoformat(pubdate).date().isoformat()


def _or_empty(value: str | None) -> str:
    return value if value is not None else ""


def _cover_path_cell(cover_path: str | None | Literal[False]) -> str:
    if cover_path is False:
        return "(unavailable)"
    return _or_empty(cover_path)


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
            book.id,
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

    rows: list[tuple[str, ...]] = [(author.id, author.name) for author in authors]
    return _align_rows(_AUTHOR_HEADERS, rows)


def render_publisher_table(publishers: list[Publisher]) -> str:
    if not publishers:
        return "No publishers found."

    rows: list[tuple[str, ...]] = [
        (publisher.id, publisher.name) for publisher in publishers
    ]
    return _align_rows(_PUBLISHER_HEADERS, rows)


def render_book_details_table(books: list[BookDetails]) -> str:
    if not books:
        return "No book details found."

    rows: list[tuple[str, ...]] = [
        (
            book.id,
            book.title,
            _LIST_SEPARATOR.join(book.authors),
            _or_empty(book.publisher.name if book.publisher is not None else None),
            _or_empty(book.series.series.name if book.series is not None else None),
            _or_empty(book.series.index if book.series is not None else None),
            _LIST_SEPARATOR.join(book.tags),
            _format_pubdate(book.pubdate),
            _cover_path_cell(book.cover_path),
        )
        for book in books
    ]
    return _align_rows(_BOOK_DETAILS_HEADERS, rows)


def order_book_details_by_ids(
    result: BookDetailsResult, ids: list[str]
) -> list[BookDetails]:
    books_by_id = {book.id: book for book in result.books}
    seen: set[str] = set()
    ordered: list[BookDetails] = []
    for requested_id in ids:
        if requested_id in books_by_id and requested_id not in seen:
            seen.add(requested_id)
            ordered.append(books_by_id[requested_id])
    return ordered


def format_missing_ids_message(missing_ids: tuple[str, ...]) -> str | None:
    if not missing_ids:
        return None
    return f"Missing ids: {', '.join(missing_ids)}"


def render_page_footer(page: int, total_pages: int | None) -> str:
    if total_pages is None:
        return f"Page {page} of many"
    return f"Page {page} of {total_pages}"
