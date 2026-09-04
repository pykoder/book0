from typing import Literal, Protocol, runtime_checkable

from book0_core.models import (
    ApplyNameRequest,
    ApplyNameResult,
    Author,
    AuthorAliasGroup,
    Book,
    BookContent,
    BookDetailsResult,
    BookPatch,
    BookQuery,
    EditBooksResult,
    FieldValue,
    Job,
    JobAction,
    JobRequest,
    JobStatus,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedJobsResult,
    PagedPublishersResult,
    PagedSeriesResult,
    Publisher,
    Series,
)


@runtime_checkable
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
    def list_field_values(
        self, field: Literal["tags", "languages", "formats", "ratings"]
    ) -> list[FieldValue]: ...
    def close_pagination(self, handle: str) -> None: ...


class MutableLibraryGateway(Protocol):
    def edit_books(
        self, ids: list[str], patch: BookPatch, dry_run: bool = False
    ) -> EditBooksResult: ...
    def get_book_content(
        self, book_id: str, level: int, extract: str | None
    ) -> BookContent: ...
    def create_job(self, request: JobRequest) -> Job: ...
    def get_job(self, job_id: str) -> Job | None: ...
    def list_jobs_page(
        self,
        status: JobStatus | None,
        action: JobAction | None,
        page: int,
        page_size: int,
    ) -> PagedJobsResult: ...
    def get_author_aliases(self, author_id: str) -> AuthorAliasGroup: ...
    def add_author_alias(self, author_id: str, alias_id: str) -> AuthorAliasGroup: ...
    def remove_author_alias(
        self, author_id: str, alias_id: str
    ) -> AuthorAliasGroup: ...
    def apply_author_name(
        self, author_id: str, request: ApplyNameRequest
    ) -> ApplyNameResult: ...
