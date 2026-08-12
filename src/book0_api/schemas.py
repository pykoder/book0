from pydantic import BaseModel

from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
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
