from pydantic import BaseModel

from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    BookPatch,
    EditBooksResult,
    FieldValue,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    PagedSeriesResult,
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
    publisher: PublisherOut | None = None
    series: SeriesOut | None = None
    series_index: str | None = None
    rating: int | None = None
    has_cover: bool = False

    @classmethod
    def from_book(cls, book: Book) -> "BookOut":
        return cls(
            id=book.id,
            title=book.title,
            authors=list(book.authors),
            pubdate=book.pubdate,
            publisher=(
                PublisherOut.from_publisher(book.publisher)
                if book.publisher is not None
                else None
            ),
            series=(
                SeriesOut.from_series(book.series) if book.series is not None else None
            ),
            series_index=book.series_index,
            rating=book.rating,
            has_cover=book.has_cover,
        )


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


class PagedSeriesOut(BaseModel):
    items: list[SeriesOut]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool

    @classmethod
    def from_paged_result(cls, result: PagedSeriesResult) -> "PagedSeriesOut":
        return cls(
            items=[SeriesOut.from_series(series) for series in result.items],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
            has_more_than_shown=result.has_more_than_shown,
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


class BookPatchIn(BaseModel):
    """PATCH en masse : champ None = non modifié (absent du JSON = None)."""

    publisher_id: str | None = None
    series_id: str | None = None
    series_index: str | None = None
    tags: list[str] | None = None
    rating: int | None = None
    pubdate: str | None = None
    language: str | None = None
    comments: str | None = None

    def to_book_patch(self) -> BookPatch:
        return BookPatch(
            publisher_id=self.publisher_id,
            series_id=self.series_id,
            series_index=self.series_index,
            tags=tuple(self.tags) if self.tags is not None else None,
            rating=self.rating,
            pubdate=self.pubdate,
            language=self.language,
            comments=self.comments,
        )


class PatchBooksIn(BaseModel):
    ids: list[str]
    patch: BookPatchIn
    dry_run: bool = False


class EditBooksOut(BaseModel):
    updated: list[str]
    missing_ids: list[str]

    @classmethod
    def from_result(cls, result: EditBooksResult) -> "EditBooksOut":
        return cls(
            updated=list(result.updated),
            missing_ids=list(result.missing_ids),
        )


class BookIdsIn(BaseModel):
    ids: list[str]


class FieldValueOut(BaseModel):
    value: str
    count: int

    @classmethod
    def from_field_value(cls, field_value: FieldValue) -> "FieldValueOut":
        return cls(value=field_value.value, count=field_value.count)
