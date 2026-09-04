from contextlib import closing
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from book0_api.filters import parse_id_list, parse_int_list, parse_text_list
from book0_api.schemas import (
    AuthorOut,
    BookDetailsResultOut,
    BookIdsIn,
    BookOut,
    FieldValueOut,
    PagedAuthorsOut,
    PagedBooksOut,
    PagedPublishersOut,
    PagedSeriesOut,
    PublisherOut,
    SeriesOut,
)
from book0_core.errors import (
    InvalidFilterError,
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.models import BookQuery, BookSort, SortOrder
from book0_core.pg_gateway import PgLibraryGateway
from book0_core.sqlite_gateway import SqliteLibraryGateway

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
) -> FastAPI:
    app = FastAPI()

    def _resolve_gateway(tag: str | None) -> PgLibraryGateway | SqliteLibraryGateway:
        resolved_tag = tag if tag is not None else default_tag
        if resolved_tag is None:
            raise TagRequiredError(
                "No tag given and no default-library configured for this server"
            )
        if pg_dsn is not None:
            # Toutes les routes basculent sur PG ; le dict libraries de chemins
            # est ignoré. Un tag inconnu lève LibraryNotFoundError (-> 404).
            return PgLibraryGateway(pg_dsn, resolved_tag)
        db_path = libraries.get(resolved_tag)
        if db_path is None:
            raise TagRequiredError(f"Unknown library tag: {resolved_tag!r}")
        return SqliteLibraryGateway(db_path)

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
        order: Literal["asc", "desc"] | None = None,
    ) -> list[SeriesOut] | PagedSeriesOut | JSONResponse:
        # Sort whitelist: "name" only, default name,asc - which is exactly what
        # list_series' and query_series_page's fixed ORDER BY name already
        # produce, so sort/order need no SQL-side handling until a second sort
        # key exists.
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

    return app
