from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Book:
    id: str
    title: str
    authors: tuple[str, ...]
    pubdate: str | None


@dataclass(frozen=True)
class Author:
    id: str
    name: str


@dataclass(frozen=True)
class Publisher:
    id: str
    name: str


@dataclass(frozen=True)
class Series:
    id: str
    name: str


@dataclass(frozen=True)
class SeriesItem:
    series: Series
    index: str | None


@dataclass(frozen=True)
class BookDetails:
    id: str
    title: str
    pubdate: str | None
    authors: tuple[str, ...]
    tags: tuple[str, ...]
    publisher: Publisher | None
    series: SeriesItem | None
    cover_path: str | None | Literal[False] = None


@dataclass(frozen=True)
class BookDetailsResult:
    books: tuple[BookDetails, ...]
    missing_ids: tuple[str, ...]


@dataclass(frozen=True)
class PagedBooksResult:
    items: tuple[Book, ...]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool
    handle: str | None


@dataclass(frozen=True)
class PagedAuthorsResult:
    items: tuple[Author, ...]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool
    handle: str | None


@dataclass(frozen=True)
class PagedPublishersResult:
    items: tuple[Publisher, ...]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool
    handle: str | None
