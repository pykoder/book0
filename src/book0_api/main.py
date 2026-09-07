from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Literal

from book0_core.errors import (
    AuthorNameMismatchError,
    AuthorNotFoundError,
    BookNotFoundError,
    InvalidAliasError,
    InvalidApplyNameError,
    InvalidExtractError,
    InvalidFilterError,
    InvalidPatchError,
    LibraryNotFoundError,
    NoEpubError,
    NotACalibreLibraryError,
    TagRequiredError,
    UnknownJobActionError,
)
from book0_core.models import (
    BookQuery,
    BookSort,
    JobAction,
    JobRequest,
    JobStatus,
    SortOrder,
)
from book0_core.pg_gateway import PgLibraryGateway
from book0_core.sqlite_gateway import SqliteLibraryGateway
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse, Response

from book0_api.filters import parse_id_list, parse_int_list, parse_text_list
from book0_api.jobs import run_job
from book0_api.schemas import (
    ApplyNameIn,
    ApplyNameOut,
    AuthorAliasGroupOut,
    AuthorAliasIn,
    AuthorOut,
    BookContentOut,
    BookDetailsResultOut,
    BookIdsIn,
    BookOut,
    EditBooksOut,
    FieldValueOut,
    JobCreateIn,
    JobOut,
    PagedAuthorsOut,
    PagedBooksOut,
    PagedJobsOut,
    PagedPublishersOut,
    PagedSeriesOut,
    PatchBooksIn,
    PublisherOut,
    SeriesOut,
)

# Whitelist of the facet fields served by GET /libraries/values/{field}. The
# dict (not a bare membership set) lets the str path param narrow to the
# Literal type the gateway Protocol expects.
_FacetField = Literal["tags", "languages", "formats", "ratings"]
_FACET_FIELDS: dict[str, _FacetField] = {
    "tags": "tags",
    "languages": "languages",
    "formats": "formats",
    "ratings": "ratings",
}

# Enums acceptés en valeur de filtre sur GET /libraries/jobs (status/action) :
# une valeur hors énumération lève UnknownJobActionError (-> 422).

# Page size used by the query_*_page routes when the request carries filters
# but no explicit pagination: a single oversized page returns everything the
# filters matched, so the unpaginated response shape is preserved.
_QUERY_ALL_PAGE_SIZE = 100_000


def _cover_not_found(id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "CoverNotFoundError",
            "detail": f"No cover found for book {id}",
        },
    )


def _parse_job_enum[T: (JobAction, JobStatus)](
    value: str | None, enum_type: type[T], field: str
) -> T | None:
    """Convertit un filtre status/action de GET /libraries/jobs en valeur
    d'enum ; une valeur hors énumération lève UnknownJobActionError (-> 422)."""
    if value is None:
        return None
    try:
        return enum_type(value)
    except ValueError:
        raise UnknownJobActionError(
            f"paramètre '{field}' : valeur inconnue : {value!r}"
        ) from None


def _resolve_effective_page(page: int | None) -> int:
    return page if page is not None and page > 0 else 1


def _resolve_effective_page_size(
    requested_page_size: int | None, server_default: int | None
) -> int | None:
    normalized_request = (
        requested_page_size
        if requested_page_size is not None and requested_page_size > 0
        else None
    )
    normalized_default = (
        server_default if server_default is not None and server_default > 0 else None
    )
    if normalized_default is not None:
        return (
            min(normalized_request, normalized_default)
            if normalized_request is not None
            else normalized_default
        )
    return normalized_request


def _build_book_query(
    author_id: str | None,
    publisher_id: str | None,
    series_id: str | None,
    tags: str | None,
    languages: str | None,
    formats: str | None,
    ratings: str | None,
    pubdate: str | None,
    sort: str | None,
    order: str | None,
) -> tuple[BookQuery, bool]:
    """Parse the raw filter params into a BookQuery.

    Every present param is parsed with the Task 6 conventions (raises
    InvalidFilterError on bad input); sort/order are converted through the
    BookSort/SortOrder enums, an unknown value raising InvalidFilterError too.
    Returns (query, has_filters): has_filters is True when any filter param is
    present, or when sort/order deviate from the defaults - either switches the
    caller to the query_*_page path.
    """
    parsed_author_ids: tuple[str, ...] = ()
    parsed_publisher_ids: tuple[str, ...] = ()
    parsed_series_ids: tuple[str, ...] = ()
    parsed_tags: tuple[str, ...] = ()
    parsed_languages: tuple[str, ...] = ()
    parsed_formats: tuple[str, ...] = ()
    parsed_ratings: tuple[int, ...] = ()
    parsed_pubdate_years: tuple[int, ...] = ()
    if author_id is not None:
        parsed_author_ids = parse_id_list(author_id, "author_id")
    if publisher_id is not None:
        parsed_publisher_ids = parse_id_list(publisher_id, "publisher_id")
    if series_id is not None:
        parsed_series_ids = parse_id_list(series_id, "series_id")
    if tags is not None:
        parsed_tags = parse_text_list(tags, "tags")
    if languages is not None:
        parsed_languages = parse_text_list(languages, "languages")
    if formats is not None:
        parsed_formats = parse_text_list(formats, "formats")
    if ratings is not None:
        parsed_ratings = parse_int_list(ratings, "ratings", comparable=True)
    if pubdate is not None:
        parsed_pubdate_years = parse_int_list(pubdate, "pubdate", comparable=True)
    has_filters = any(
        (
            author_id is not None,
            publisher_id is not None,
            series_id is not None,
            tags is not None,
            languages is not None,
            formats is not None,
            ratings is not None,
            pubdate is not None,
        )
    )

    query_sort = BookSort.TITLE
    query_order = SortOrder.ASC
    if sort is not None:
        try:
            query_sort = BookSort(sort)
        except ValueError:
            raise InvalidFilterError(
                f"filter 'sort': valeur inconnue : {sort!r}"
            ) from None
    if order is not None:
        try:
            query_order = SortOrder(order)
        except ValueError:
            raise InvalidFilterError(
                f"filter 'order': valeur inconnue : {order!r}"
            ) from None

    return (
        BookQuery(
            author_ids=parsed_author_ids,
            publisher_ids=parsed_publisher_ids,
            series_ids=parsed_series_ids,
            tags=parsed_tags,
            languages=parsed_languages,
            formats=parsed_formats,
            ratings=parsed_ratings,
            pubdate_years=parsed_pubdate_years,
            sort=query_sort,
            order=query_order,
        ),
        has_filters or sort is not None or order is not None,
    )


def create_app(
    libraries: dict[str, Path],
    default_tag: str | None = None,
    default_page_size: int | None = None,
    pg_dsn: str | None = None,
    markdown_cache_dir: Path | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Un job 'running' survivant d'un arrêt brutal ne reprendra jamais :
        # au démarrage, une seule passe sur la passerelle non scopée (tag=None)
        # bascule les jobs 'running' de TOUTES les bibliothèques PG en
        # 'interrupted' — le dict libraries de chemins n'est pas consulté (en
        # déploiement PG réel il peut être minimal/vide). Sans PG (mode
        # SQLite), rien à faire.
        if pg_dsn is not None:
            gateway = PgLibraryGateway(pg_dsn, None, markdown_cache_dir)
            with closing(gateway):
                gateway.mark_interrupted_jobs()
        yield

    app = FastAPI(lifespan=lifespan)

    def _resolve_gateway(tag: str | None) -> PgLibraryGateway | SqliteLibraryGateway:
        resolved_tag = tag if tag is not None else default_tag
        if resolved_tag is None:
            raise TagRequiredError(
                "No tag given and no default-library configured for this server"
            )
        if pg_dsn is not None:
            # Toutes les routes basculent sur PG ; le dict libraries de chemins
            # est ignoré. Un tag inconnu lève LibraryNotFoundError (-> 404).
            return PgLibraryGateway(pg_dsn, resolved_tag, markdown_cache_dir)
        db_path = libraries.get(resolved_tag)
        if db_path is None:
            raise TagRequiredError(f"Unknown library tag: {resolved_tag!r}")
        return SqliteLibraryGateway(db_path)

    def _resolve_jobs_gateway(dsn: str, tag: str | None) -> PgLibraryGateway:
        """Résolution de gateway spécifique aux lectures de jobs (GET
        /libraries/jobs*) : un tag explicite (ou le default-library) scope les
        jobs à sa bibliothèque, mais son absence n'est pas une erreur — les
        ids de jobs étant des uuid4, les lectures se font alors sur toutes les
        bibliothèques (console de jobs du serveur). Un tag explicite inconnu
        lève LibraryNotFoundError (-> 404). Mode PG uniquement (la route
        répond 501 en SQLite avant d'appeler)."""
        resolved_tag = tag if tag is not None else default_tag
        return PgLibraryGateway(dsn, resolved_tag, markdown_cache_dir)

    @app.get("/libraries/books", response_model=None)
    def list_books(
        tag: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        author_id: str | None = None,
        publisher_id: str | None = None,
        series_id: str | None = None,
        tags: str | None = None,
        languages: str | None = None,
        formats: str | None = None,
        ratings: str | None = None,
        pubdate: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> list[BookOut] | PagedBooksOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        try:
            query, has_filters = _build_book_query(
                author_id,
                publisher_id,
                series_id,
                tags,
                languages,
                formats,
                ratings,
                pubdate,
                sort,
                order,
            )
        except InvalidFilterError as error:
            return JSONResponse(
                status_code=422,
                content={"error": "InvalidFilterError", "detail": str(error)},
            )

        effective_page_size = _resolve_effective_page_size(page_size, default_page_size)

        with closing(gateway):
            try:
                if has_filters:
                    query_page_size = (
                        effective_page_size
                        if effective_page_size is not None
                        else _QUERY_ALL_PAGE_SIZE
                    )
                    query_result = gateway.query_books_page(
                        query, _resolve_effective_page(page), query_page_size
                    )
                elif effective_page_size is None:
                    books = gateway.list_books()
                else:
                    paged_result = gateway.list_books_page(
                        _resolve_effective_page(page), effective_page_size
                    )
            except LibraryNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "LibraryNotFoundError", "detail": str(error)},
                )
            except NotACalibreLibraryError as error:
                return JSONResponse(
                    status_code=500,
                    content={"error": "NotACalibreLibraryError", "detail": str(error)},
                )

            if has_filters:
                if effective_page_size is None:
                    return [BookOut.from_book(book) for book in query_result.items]
                return PagedBooksOut.from_paged_result(query_result)
            if effective_page_size is None:
                return [BookOut.from_book(book) for book in books]
            return PagedBooksOut.from_paged_result(paged_result)

    @app.get("/libraries/authors", response_model=None)
    def list_authors(
        tag: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        author_id: str | None = None,
        publisher_id: str | None = None,
        series_id: str | None = None,
        tags: str | None = None,
        languages: str | None = None,
        formats: str | None = None,
        ratings: str | None = None,
        pubdate: str | None = None,
    ) -> list[AuthorOut] | PagedAuthorsOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        try:
            query, has_filters = _build_book_query(
                author_id,
                publisher_id,
                series_id,
                tags,
                languages,
                formats,
                ratings,
                pubdate,
                None,
                None,
            )
        except InvalidFilterError as error:
            return JSONResponse(
                status_code=422,
                content={"error": "InvalidFilterError", "detail": str(error)},
            )

        effective_page_size = _resolve_effective_page_size(page_size, default_page_size)

        with closing(gateway):
            try:
                if has_filters:
                    query_page_size = (
                        effective_page_size
                        if effective_page_size is not None
                        else _QUERY_ALL_PAGE_SIZE
                    )
                    query_result = gateway.query_authors_page(
                        query, _resolve_effective_page(page), query_page_size
                    )
                elif effective_page_size is None:
                    authors = gateway.list_authors()
                else:
                    paged_result = gateway.list_authors_page(
                        _resolve_effective_page(page), effective_page_size
                    )
            except LibraryNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "LibraryNotFoundError", "detail": str(error)},
                )
            except NotACalibreLibraryError as error:
                return JSONResponse(
                    status_code=500,
                    content={"error": "NotACalibreLibraryError", "detail": str(error)},
                )

            if has_filters:
                if effective_page_size is None:
                    return [
                        AuthorOut.from_author(author) for author in query_result.items
                    ]
                return PagedAuthorsOut.from_paged_result(query_result)
            if effective_page_size is None:
                return [AuthorOut.from_author(author) for author in authors]
            return PagedAuthorsOut.from_paged_result(paged_result)

    @app.get("/libraries/publishers", response_model=None)
    def list_publishers(
        tag: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        author_id: str | None = None,
        publisher_id: str | None = None,
        series_id: str | None = None,
        tags: str | None = None,
        languages: str | None = None,
        formats: str | None = None,
        ratings: str | None = None,
        pubdate: str | None = None,
    ) -> list[PublisherOut] | PagedPublishersOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        try:
            query, has_filters = _build_book_query(
                author_id,
                publisher_id,
                series_id,
                tags,
                languages,
                formats,
                ratings,
                pubdate,
                None,
                None,
            )
        except InvalidFilterError as error:
            return JSONResponse(
                status_code=422,
                content={"error": "InvalidFilterError", "detail": str(error)},
            )

        effective_page_size = _resolve_effective_page_size(page_size, default_page_size)

        with closing(gateway):
            try:
                if has_filters:
                    query_page_size = (
                        effective_page_size
                        if effective_page_size is not None
                        else _QUERY_ALL_PAGE_SIZE
                    )
                    query_result = gateway.query_publishers_page(
                        query, _resolve_effective_page(page), query_page_size
                    )
                elif effective_page_size is None:
                    publishers = gateway.list_publishers()
                else:
                    paged_result = gateway.list_publishers_page(
                        _resolve_effective_page(page), effective_page_size
                    )
            except LibraryNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "LibraryNotFoundError", "detail": str(error)},
                )
            except NotACalibreLibraryError as error:
                return JSONResponse(
                    status_code=500,
                    content={"error": "NotACalibreLibraryError", "detail": str(error)},
                )

            if has_filters:
                if effective_page_size is None:
                    return [
                        PublisherOut.from_publisher(publisher)
                        for publisher in query_result.items
                    ]
                return PagedPublishersOut.from_paged_result(query_result)
            if effective_page_size is None:
                return [
                    PublisherOut.from_publisher(publisher) for publisher in publishers
                ]
            return PagedPublishersOut.from_paged_result(paged_result)

    @app.get("/libraries/series", response_model=None)
    def list_series(
        tag: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        author_id: str | None = None,
        publisher_id: str | None = None,
        series_id: str | None = None,
        tags: str | None = None,
        languages: str | None = None,
        formats: str | None = None,
        ratings: str | None = None,
        pubdate: str | None = None,
        sort: Literal["name"] | None = None,
        order: Literal["asc"] | None = None,
    ) -> list[SeriesOut] | PagedSeriesOut | JSONResponse:
        # Sort whitelist: "name" only, default name,asc - which is exactly what
        # list_series' and query_series_page's fixed ORDER BY name already
        # produce, so sort/order need no SQL-side handling until a second sort
        # key exists. "desc" is deliberately absent from the Literal until a
        # gateway honors a directional ORDER BY: FastAPI answers 422 rather
        # than silently accepting and ignoring it.
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        try:
            query, has_filters = _build_book_query(
                author_id,
                publisher_id,
                series_id,
                tags,
                languages,
                formats,
                ratings,
                pubdate,
                None,
                None,
            )
        except InvalidFilterError as error:
            return JSONResponse(
                status_code=422,
                content={"error": "InvalidFilterError", "detail": str(error)},
            )

        effective_page_size = _resolve_effective_page_size(page_size, default_page_size)

        with closing(gateway):
            try:
                if has_filters:
                    query_page_size = (
                        effective_page_size
                        if effective_page_size is not None
                        else _QUERY_ALL_PAGE_SIZE
                    )
                    query_result = gateway.query_series_page(
                        query, _resolve_effective_page(page), query_page_size
                    )
                elif effective_page_size is None:
                    series = gateway.list_series()
                else:
                    paged_result = gateway.list_series_page(
                        _resolve_effective_page(page), effective_page_size
                    )
            except LibraryNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "LibraryNotFoundError", "detail": str(error)},
                )
            except NotACalibreLibraryError as error:
                return JSONResponse(
                    status_code=500,
                    content={"error": "NotACalibreLibraryError", "detail": str(error)},
                )

            if has_filters:
                if effective_page_size is None:
                    return [SeriesOut.from_series(item) for item in query_result.items]
                return PagedSeriesOut.from_paged_result(query_result)
            if effective_page_size is None:
                return [SeriesOut.from_series(series) for series in series]
            return PagedSeriesOut.from_paged_result(paged_result)

    @app.get("/libraries/values/{field}", response_model=None)
    def get_values(
        field: str, tag: str | None = None
    ) -> list[FieldValueOut] | JSONResponse:
        facet_field = _FACET_FIELDS.get(field)
        if facet_field is None:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "InvalidFilterError",
                    "detail": f"filter 'field': valeur inconnue : {field!r}",
                },
            )

        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            try:
                values = gateway.list_field_values(facet_field)
            except LibraryNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "LibraryNotFoundError", "detail": str(error)},
                )
            except NotACalibreLibraryError as error:
                return JSONResponse(
                    status_code=500,
                    content={"error": "NotACalibreLibraryError", "detail": str(error)},
                )

            return [FieldValueOut.from_field_value(value) for value in values]

    @app.post("/libraries/books/detail", response_model=None)
    def get_book_details(
        body: BookIdsIn, tag: str | None = None
    ) -> BookDetailsResultOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            try:
                result = gateway.get_book_details(body.ids)
            except LibraryNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "LibraryNotFoundError", "detail": str(error)},
                )
            except NotACalibreLibraryError as error:
                return JSONResponse(
                    status_code=500,
                    content={"error": "NotACalibreLibraryError", "detail": str(error)},
                )

            return BookDetailsResultOut.from_book_details_result(result)

    @app.patch("/libraries/books", response_model=None)
    def patch_books(
        body: PatchBooksIn, tag: str | None = None
    ) -> EditBooksOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            if not isinstance(gateway, PgLibraryGateway):
                # SqliteLibraryGateway est en lecture seule par construction
                # (metadata.db Calibre ne doit jamais être modifiée) :
                # l'édition en masse n'est servie qu'en mode PG.
                return JSONResponse(
                    status_code=501,
                    content={
                        "error": "NotImplementedError",
                        "detail": (
                            "PATCH /libraries/books requires a PG-backed library"
                        ),
                    },
                )
            try:
                result = gateway.edit_books(
                    body.ids, body.patch.to_book_patch(), body.dry_run
                )
            except InvalidPatchError as error:
                return JSONResponse(
                    status_code=422,
                    content={"error": "InvalidPatchError", "detail": str(error)},
                )
            except LibraryNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "LibraryNotFoundError", "detail": str(error)},
                )
            except NotACalibreLibraryError as error:
                return JSONResponse(
                    status_code=500,
                    content={"error": "NotACalibreLibraryError", "detail": str(error)},
                )

            return EditBooksOut.from_result(result)

    @app.get("/libraries/books/{id}/cover", response_model=None)
    def get_book_cover(id: str, tag: str | None = None) -> Response | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            try:
                result = gateway.get_book_details([id])
            except LibraryNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "LibraryNotFoundError", "detail": str(error)},
                )
            except NotACalibreLibraryError as error:
                return JSONResponse(
                    status_code=500,
                    content={"error": "NotACalibreLibraryError", "detail": str(error)},
                )

            if not result.books:
                return _cover_not_found(id)
            cover_path = result.books[0].cover_path
            if (
                cover_path is None
                or cover_path is False
                or not Path(cover_path).is_file()
            ):
                return _cover_not_found(id)

            return Response(
                content=Path(cover_path).read_bytes(), media_type="image/jpeg"
            )

    @app.get("/libraries/books/{id}/content", response_model=None)
    def get_book_content(
        id: str,
        tag: str | None = None,
        level: int = 7,
        extract: str | None = None,
    ) -> BookContentOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            if not isinstance(gateway, PgLibraryGateway):
                # get_book_content (conversion epub2md + cache disque) n'est
                # implémenté que sur PgLibraryGateway : le mode SQLite reste
                # en 501, même convention que PATCH /libraries/books.
                return JSONResponse(
                    status_code=501,
                    content={
                        "error": "NotImplementedError",
                        "detail": (
                            "GET /libraries/books/{id}/content requires a"
                            " PG-backed library"
                        ),
                    },
                )
            try:
                content = gateway.get_book_content(id, level, extract)
            except BookNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "BookNotFoundError", "detail": str(error)},
                )
            except NoEpubError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "NoEpubError", "detail": str(error)},
                )
            except InvalidExtractError as error:
                return JSONResponse(
                    status_code=400,
                    content={"error": "InvalidExtractError", "detail": str(error)},
                )

            return BookContentOut.from_book_content(content)

    @app.get("/libraries/authors/{id}/aliases", response_model=None)
    def get_author_aliases(
        id: str, tag: str | None = None
    ) -> AuthorAliasGroupOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            if not isinstance(gateway, PgLibraryGateway):
                # Les groupes d'alias vivent dans author_entity (PG uniquement) :
                # le mode SQLite reste en 501, même convention que
                # PATCH /libraries/books.
                return JSONResponse(
                    status_code=501,
                    content={
                        "error": "NotImplementedError",
                        "detail": (
                            "GET /libraries/authors/{id}/aliases requires a"
                            " PG-backed library"
                        ),
                    },
                )
            try:
                group = gateway.get_author_aliases(id)
            except AuthorNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "AuthorNotFoundError", "detail": str(error)},
                )

            return AuthorAliasGroupOut.from_group(group)

    @app.post("/libraries/authors/{id}/aliases", response_model=None)
    def add_author_alias(
        id: str, body: AuthorAliasIn, tag: str | None = None
    ) -> AuthorAliasGroupOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            if not isinstance(gateway, PgLibraryGateway):
                return JSONResponse(
                    status_code=501,
                    content={
                        "error": "NotImplementedError",
                        "detail": (
                            "POST /libraries/authors/{id}/aliases requires a"
                            " PG-backed library"
                        ),
                    },
                )
            try:
                group = gateway.add_author_alias(id, body.alias_id)
            except AuthorNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "AuthorNotFoundError", "detail": str(error)},
                )
            except InvalidAliasError as error:
                return JSONResponse(
                    status_code=422,
                    content={"error": "InvalidAliasError", "detail": str(error)},
                )

            return AuthorAliasGroupOut.from_group(group)

    @app.delete("/libraries/authors/{id}/aliases/{alias_id}", response_model=None)
    def remove_author_alias(
        id: str, alias_id: str, tag: str | None = None
    ) -> AuthorAliasGroupOut | JSONResponse:
        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            if not isinstance(gateway, PgLibraryGateway):
                return JSONResponse(
                    status_code=501,
                    content={
                        "error": "NotImplementedError",
                        "detail": (
                            "DELETE /libraries/authors/{id}/aliases/{alias_id}"
                            " requires a PG-backed library"
                        ),
                    },
                )
            try:
                group = gateway.remove_author_alias(id, alias_id)
            except AuthorNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "AuthorNotFoundError", "detail": str(error)},
                )
            except InvalidAliasError as error:
                return JSONResponse(
                    status_code=422,
                    content={"error": "InvalidAliasError", "detail": str(error)},
                )

            return AuthorAliasGroupOut.from_group(group)

    @app.post("/libraries/authors/{id}/apply-name", response_model=None)
    def apply_author_name(
        id: str, body: ApplyNameIn, tag: str | None = None
    ) -> ApplyNameOut | JSONResponse:
        try:
            request = body.to_apply_name_request()
        except InvalidApplyNameError as error:
            return JSONResponse(
                status_code=422,
                content={"error": "InvalidApplyNameError", "detail": str(error)},
            )

        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            if not isinstance(gateway, PgLibraryGateway):
                return JSONResponse(
                    status_code=501,
                    content={
                        "error": "NotImplementedError",
                        "detail": (
                            "POST /libraries/authors/{id}/apply-name requires a"
                            " PG-backed library"
                        ),
                    },
                )
            try:
                result = gateway.apply_author_name(id, request)
            except AuthorNotFoundError as error:
                return JSONResponse(
                    status_code=404,
                    content={"error": "AuthorNotFoundError", "detail": str(error)},
                )
            except AuthorNameMismatchError as error:
                return JSONResponse(
                    status_code=422,
                    content={"error": "AuthorNameMismatchError", "detail": str(error)},
                )
            except InvalidApplyNameError as error:
                return JSONResponse(
                    status_code=422,
                    content={"error": "InvalidApplyNameError", "detail": str(error)},
                )
            except InvalidAliasError as error:
                return JSONResponse(
                    status_code=422,
                    content={"error": "InvalidAliasError", "detail": str(error)},
                )

            return ApplyNameOut.from_result(result)

    @app.post("/libraries/jobs", response_model=None)
    def create_job(
        body: JobCreateIn,
        background_tasks: BackgroundTasks,
        tag: str | None = None,
    ) -> JSONResponse:
        try:
            action = JobAction(body.action)
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "UnknownJobActionError",
                    "detail": f"action : valeur inconnue : {body.action!r}",
                },
            )

        if pg_dsn is None:
            # Les jobs de fond ne s'exécutent qu'en mode PG (écritures
            # job/outcome + exécuteur) : le mode SQLite reste en 501, et ce
            # avant toute résolution de tag (le test e2e n'en passe pas).
            return JSONResponse(
                status_code=501,
                content={
                    "error": "NotImplementedError",
                    "detail": "POST /libraries/jobs requires a PG-backed library",
                },
            )

        try:
            gateway = _resolve_gateway(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        if not isinstance(gateway, PgLibraryGateway):
            return JSONResponse(
                status_code=501,
                content={
                    "error": "NotImplementedError",
                    "detail": "POST /libraries/jobs requires a PG-backed library",
                },
            )
        try:
            job = gateway.create_job(
                JobRequest(
                    action=action,
                    book_ids=tuple(body.book_ids),
                    params=body.params,
                )
            )
        except BaseException:
            # run_job n'a pas pu prendre possession du gateway : on le ferme
            # ici (sinon fuite de connexion) avant de propager l'erreur.
            gateway.close()
            raise
        # Le gateway n'est PAS fermé ici : run_job l'exécute après la réponse
        # et en prend possession (fermeture dans son finally).
        background_tasks.add_task(
            run_job,
            gateway,
            job.id,
            action,
            tuple(body.book_ids),
            body.params,
        )
        return JSONResponse(
            status_code=202, content={"id": job.id, "status": "pending"}
        )

    @app.get("/libraries/jobs", response_model=None)
    def list_jobs(
        tag: str | None = None,
        status: str | None = None,
        action: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> PagedJobsOut | JSONResponse:
        try:
            job_status = _parse_job_enum(status, JobStatus, "status")
            job_action = _parse_job_enum(action, JobAction, "action")
        except UnknownJobActionError as error:
            return JSONResponse(
                status_code=422,
                content={"error": "UnknownJobActionError", "detail": str(error)},
            )

        if pg_dsn is None:
            # Les jobs ne sont persistés qu'en PG : le mode SQLite reste en
            # 501, même convention que POST /libraries/jobs.
            return JSONResponse(
                status_code=501,
                content={
                    "error": "NotImplementedError",
                    "detail": "GET /libraries/jobs requires a PG-backed library",
                },
            )

        try:
            gateway = _resolve_jobs_gateway(pg_dsn, tag)
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        # Pas de variante non paginée pour les jobs : sans page_size explicite
        # (ni default_page_size serveur), une seule page surdimensionnée
        # rend tout, même convention que les routes query_*_page.
        effective_page_size = _resolve_effective_page_size(page_size, default_page_size)

        with closing(gateway):
            paged_result = gateway.list_jobs_page(
                job_status,
                job_action,
                _resolve_effective_page(page),
                (
                    effective_page_size
                    if effective_page_size is not None
                    else _QUERY_ALL_PAGE_SIZE
                ),
            )
            return PagedJobsOut.from_paged_result(paged_result)

    @app.get("/libraries/jobs/{job_id}", response_model=None)
    def get_job(job_id: str, tag: str | None = None) -> JobOut | JSONResponse:
        if pg_dsn is None:
            return JSONResponse(
                status_code=501,
                content={
                    "error": "NotImplementedError",
                    "detail": "GET /libraries/jobs requires a PG-backed library",
                },
            )

        try:
            gateway = _resolve_jobs_gateway(pg_dsn, tag)
        except LibraryNotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"error": "LibraryNotFoundError", "detail": str(error)},
            )

        with closing(gateway):
            job = gateway.get_job(job_id)
            if job is None:
                # get_job renvoie aussi None pour un job_id non-UUID :
                # même sémantique « pas trouvé » (-> 404).
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "UnknownJobError",
                        "detail": f"Job not found: {job_id}",
                    },
                )
            return JobOut.from_job(job)

    return app
