from pydantic import BaseModel

from book0_core.errors import InvalidApplyNameError
from book0_core.models import (
    ApplyNameRequest,
    ApplyNameResult,
    Author,
    AuthorAliasGroup,
    Book,
    BookContent,
    BookDetails,
    BookDetailsResult,
    BookPatch,
    EditBooksResult,
    FieldValue,
    Job,
    JobOutcome,
    NameTarget,
    NameTargetById,
    NameTargetByName,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedJobsResult,
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


class JobCreateIn(BaseModel):
    """Corps de POST /libraries/jobs. action reste un str : c'est la route qui
    le convertit en enum JobAction pour lever UnknownJobActionError (-> 422)
    sur une valeur hors énumération, avec le corps d'erreur standard du projet."""

    action: str
    book_ids: list[str] = []
    params: dict[str, object] | None = None


class JobFailureOut(BaseModel):
    id: str
    reason: str


class JobOutcomeOut(BaseModel):
    succeeded: list[str]
    failed: list[JobFailureOut]

    @classmethod
    def from_job_outcome(cls, outcome: JobOutcome) -> "JobOutcomeOut":
        return cls(
            succeeded=list(outcome.succeeded),
            failed=[
                JobFailureOut(id=failure.id, reason=failure.reason)
                for failure in outcome.failed
            ],
        )


class JobOut(BaseModel):
    id: str
    action: str
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    outcome: JobOutcomeOut | None

    @classmethod
    def from_job(cls, job: Job) -> "JobOut":
        return cls(
            id=job.id,
            action=job.action.value,
            status=job.status.value,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            outcome=(
                JobOutcomeOut.from_job_outcome(job.outcome)
                if job.outcome is not None
                else None
            ),
        )


class PagedJobsOut(BaseModel):
    items: list[JobOut]
    page: int
    page_size: int
    total_pages: int | None
    has_more_than_shown: bool

    @classmethod
    def from_paged_result(cls, result: PagedJobsResult) -> "PagedJobsOut":
        return cls(
            items=[JobOut.from_job(job) for job in result.items],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
            has_more_than_shown=result.has_more_than_shown,
        )


class BookContentOut(BaseModel):
    book_id: str
    level: int
    extract: str | None
    markdown: str

    @classmethod
    def from_book_content(cls, content: BookContent) -> "BookContentOut":
        return cls(
            book_id=content.book_id,
            level=content.level,
            extract=content.extract,
            markdown=content.markdown,
        )


class FieldValueOut(BaseModel):
    value: str
    count: int

    @classmethod
    def from_field_value(cls, field_value: FieldValue) -> "FieldValueOut":
        return cls(value=field_value.value, count=field_value.count)


class AuthorAliasIn(BaseModel):
    """Corps de POST /libraries/authors/{id}/aliases."""

    alias_id: str


class AuthorAliasGroupOut(BaseModel):
    """Forme wire d'un groupe d'alias : ids membres + noms actuels."""

    group: list[str]
    names: dict[str, str]

    @classmethod
    def from_group(cls, group: AuthorAliasGroup) -> "AuthorAliasGroupOut":
        return cls(group=list(group.group), names=dict(group.names))


class NameTargetIn(BaseModel):
    """target de POST /libraries/authors/{id}/apply-name : exactement une des
    deux formes author_id / name (les deux, ou aucune, lèvent
    InvalidApplyNameError à la conversion)."""

    author_id: str | None = None
    name: str | None = None


class ApplyNameIn(BaseModel):
    """Corps de POST /libraries/authors/{id}/apply-name. book_ids omis = tous
    les livres de l'auteur ; fourni vide ([]), la conversion lève
    InvalidApplyNameError (une liste vide explicite n'a pas de sens)."""

    match: str
    target: NameTargetIn
    book_ids: list[str] | None = None
    dry_run: bool = False

    def to_apply_name_request(self) -> ApplyNameRequest:
        target: NameTarget
        if self.target.author_id is not None and self.target.name is not None:
            raise InvalidApplyNameError(
                "target : fournir exactement une des formes author_id / name"
            )
        if self.target.author_id is not None:
            target = NameTargetById(author_id=self.target.author_id)
        elif self.target.name is not None:
            target = NameTargetByName(name=self.target.name)
        else:
            raise InvalidApplyNameError(
                "target : fournir exactement une des formes author_id / name"
            )
        if self.book_ids is not None and not self.book_ids:
            raise InvalidApplyNameError(
                "book_ids : une liste fournie ne peut pas être vide"
            )
        return ApplyNameRequest(
            match=self.match,
            target=target,
            book_ids=tuple(self.book_ids) if self.book_ids is not None else (),
            dry_run=self.dry_run,
        )


class ApplyNameOut(BaseModel):
    applied: list[str]
    skipped: list[str]
    missing_ids: list[str]

    @classmethod
    def from_result(cls, result: ApplyNameResult) -> "ApplyNameOut":
        return cls(
            applied=list(result.applied),
            skipped=list(result.skipped),
            missing_ids=list(result.missing_ids),
        )
