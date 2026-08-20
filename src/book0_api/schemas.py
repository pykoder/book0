from pydantic import BaseModel

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


class AuthorOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_author(cls, author: Author) -> "AuthorOut":
        return cls(id=author.id, name=author.name)


class PublisherOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_publisher(cls, publisher: Publisher) -> "PublisherOut":
        return cls(id=publisher.id, name=publisher.name)


class SeriesOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_series(cls, series: Series) -> "SeriesOut":
        return cls(id=series.id, name=series.name)


class SeriesItemOut(BaseModel):
    series: SeriesOut
    index: str | None

    @classmethod
    def from_series_item(cls, series_item: SeriesItem) -> "SeriesItemOut":
        return cls(
            series=SeriesOut.from_series(series_item.series),
            index=series_item.index,
        )


class BookOut(BaseModel):
    id: str
    title: str
    authors: list[str]
    pubdate: str | None

    @classmethod
    def from_book(cls, book: Book) -> "BookOut":
        return cls(
            id=book.id,
            title=book.title,
            authors=list(book.authors),
            pubdate=book.pubdate,
        )


class BookDetailsOut(BaseModel):
    id: str
    title: str
    pubdate: str | None
    authors: list[str]
    tags: list[str]
    publisher: PublisherOut | None
    series: SeriesItemOut | None
    has_cover: bool

    @classmethod
    def from_book_details(cls, book_details: BookDetails) -> "BookDetailsOut":
        return cls(
            id=book_details.id,
            title=book_details.title,
            pubdate=book_details.pubdate,
            authors=list(book_details.authors),
            tags=list(book_details.tags),
            publisher=(
                PublisherOut.from_publisher(book_details.publisher)
                if book_details.publisher is not None
                else None
            ),
            series=(
                SeriesItemOut.from_series_item(book_details.series)
                if book_details.series is not None
                else None
            ),
            has_cover=book_details.cover_path is not None,
        )


class BookDetailsResultOut(BaseModel):
    books: list[BookDetailsOut]
    missing_ids: list[str]

    @classmethod
    def from_book_details_result(
        cls, result: BookDetailsResult
    ) -> "BookDetailsResultOut":
        return cls(
            books=[BookDetailsOut.from_book_details(book) for book in result.books],
            missing_ids=list(result.missing_ids),
        )


class BookIdsIn(BaseModel):
    ids: list[str]


class PagedBooksOut(BaseModel):
    items: list[BookOut]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool

    @classmethod
    def from_paged_result(cls, result: PagedBooksResult) -> "PagedBooksOut":
        return cls(
            items=[BookOut.from_book(book) for book in result.items],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
            has_more_than_shown=result.has_more_than_shown,
        )


class PagedAuthorsOut(BaseModel):
    items: list[AuthorOut]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool

    @classmethod
    def from_paged_result(cls, result: PagedAuthorsResult) -> "PagedAuthorsOut":
        return cls(
            items=[AuthorOut.from_author(author) for author in result.items],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
            has_more_than_shown=result.has_more_than_shown,
        )


class PagedPublishersOut(BaseModel):
    items: list[PublisherOut]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool

    @classmethod
    def from_paged_result(cls, result: PagedPublishersResult) -> "PagedPublishersOut":
        return cls(
            items=[
                PublisherOut.from_publisher(publisher) for publisher in result.items
            ],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
            has_more_than_shown=result.has_more_than_shown,
        )
