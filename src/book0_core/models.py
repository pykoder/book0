from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Literal


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
class Book:
    id: str
    title: str
    authors: tuple[str, ...]
    pubdate: str | None
    publisher: Publisher | None = None
    series: Series | None = None
    series_index: str | None = None
    rating: int | None = None
    has_cover: bool = False


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
    rating: int | None = None


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


class BookSort(Enum):
    TITLE = "title"
    PUBDATE = "pubdate"
    PUBLISHER = "publisher"
    SERIES = "series"
    SERIES_INDEX = "series_index"
    RATING = "rating"
    AUTHOR = "author"


class SortOrder(Enum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True)
class BookQuery:
    author_ids: tuple[str, ...] = ()
    publisher_ids: tuple[str, ...] = ()
    series_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    ratings: tuple[int, ...] = ()
    pubdate_years: tuple[int, ...] = ()
    sort: BookSort = BookSort.TITLE
    order: SortOrder = SortOrder.ASC


@dataclass(frozen=True)
class FieldValue:
    value: str
    count: int


@dataclass(frozen=True)
class PagedSeriesResult:
    items: tuple[Series, ...]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool
    handle: str | None


@dataclass(frozen=True)
class BookPatch:  # champ None = non modifié
    publisher_id: str | None = None
    series_id: str | None = None
    series_index: str | None = None
    tags: tuple[str, ...] | None = None
    rating: int | None = None
    pubdate: str | None = None
    language: str | None = None
    comments: str | None = None


@dataclass(frozen=True)
class EditBooksResult:
    updated: tuple[str, ...]
    missing_ids: tuple[str, ...]


@dataclass(frozen=True)
class BookContent:
    book_id: str
    level: int
    extract: str | None
    markdown: str


class JobAction(Enum):
    CONVERT_MARKDOWN = "convert-markdown"
    SYNC_LIBRARY = "sync-library"


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class JobRequest:
    action: JobAction
    book_ids: tuple[str, ...] = ()
    params: Mapping[str, object] | None = None


@dataclass(frozen=True)
class JobFailure:
    id: str
    reason: str


@dataclass(frozen=True)
class JobOutcome:
    succeeded: tuple[str, ...]
    failed: tuple[JobFailure, ...]


@dataclass(frozen=True)
class Job:
    id: str
    action: JobAction
    status: JobStatus
    created_at: str
    started_at: str | None
    finished_at: str | None
    outcome: JobOutcome | None


@dataclass(frozen=True)
class PagedJobsResult:
    items: tuple[Job, ...]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool
    handle: str | None  # toujours None (jobs : offset SQL simple)


@dataclass(frozen=True)
class AuthorAliasGroup:
    author_id: str  # l'id interrogé
    group: tuple[str, ...]  # ids du groupe, author_id inclus
    names: Mapping[str, str]  # id → nom actuel


@dataclass(frozen=True)
class NameTargetById:
    author_id: str


@dataclass(frozen=True)
class NameTargetByName:
    name: str


NameTarget = NameTargetById | NameTargetByName


@dataclass(frozen=True)
class ApplyNameRequest:
    match: str  # regexp obligatoire
    target: NameTarget
    book_ids: tuple[str, ...] = ()  # vide = tous les livres de l'auteur
    dry_run: bool = False


@dataclass(frozen=True)
class ApplyNameResult:
    applied: tuple[str, ...]
    skipped: tuple[str, ...]
    missing_ids: tuple[str, ...]
