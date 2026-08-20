from typing import Protocol

from book0_core.models import (
    Author,
    Book,
    BookDetailsResult,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    Publisher,
)


class LibraryGateway(Protocol):
    def list_books(self) -> list[Book]: ...
    def list_authors(self) -> list[Author]: ...
    def list_publishers(self) -> list[Publisher]: ...
    def get_book_details(self, ids: list[str]) -> BookDetailsResult: ...
    def list_books_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult: ...
    def list_authors_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult: ...
    def list_publishers_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult: ...
    def close_pagination(self, handle: str) -> None: ...
