from typing import Protocol

from book0_core.models import (
    Author,
    Book,
    BookDetailsResult,
    BookQuery,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    PagedSeriesResult,
    Publisher,
    Series,
)


class ReadLibraryGateway(Protocol):
    def list_books(self) -> list[Book]: ...
    def list_authors(self) -> list[Author]: ...
    def list_publishers(self) -> list[Publisher]: ...
    def list_series(self) -> list[Series]: ...
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
    def list_series_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedSeriesResult: ...
    def query_books_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult: ...
    def query_authors_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult: ...
    def query_publishers_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult: ...
    def query_series_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedSeriesResult: ...
    def close_pagination(self, handle: str) -> None: ...
