from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from book0_api.schemas import (
    AuthorOut,
    BookDetailsResultOut,
    BookIdsIn,
    BookOut,
    PagedAuthorsOut,
    PagedBooksOut,
    PagedPublishersOut,
    PublisherOut,
)
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.sqlite_gateway import SqliteLibraryGateway


def _cover_not_found(id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "CoverNotFoundError",
            "detail": f"No cover found for book {id}",
        },
    )


def create_app(
    libraries: dict[str, Path],
    default_tag: str | None = None,
    default_page_size: int | None = None,
) -> FastAPI:
    app = FastAPI()

    def _resolve_db_path(tag: str | None) -> Path:
        resolved_tag = tag if tag is not None else default_tag
        if resolved_tag is None:
            raise TagRequiredError(
                "No tag given and no default-library configured for this server"
            )
        db_path = libraries.get(resolved_tag)
        if db_path is None:
            raise TagRequiredError(f"Unknown library tag: {resolved_tag!r}")
        return db_path

    def _resolve_page_size(page_size: int | None) -> int | None:
        effective: int | None
        if default_page_size is not None:
            effective = (
                min(page_size, default_page_size)
                if page_size is not None
                else default_page_size
            )
        else:
            effective = page_size
        return effective if effective is not None and effective > 0 else None

    def _resolve_page(page: int | None) -> int:
        resolved = page if page is not None else 1
        return resolved if resolved > 0 else 1

    @app.get("/libraries/books", response_model=None)
    def list_books(
        tag: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[BookOut] | PagedBooksOut | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )

        gateway = SqliteLibraryGateway(db_path)
        effective_page_size = _resolve_page_size(page_size)
        try:
            if effective_page_size is None:
                books = gateway.list_books()
            else:
                paged_books = gateway.list_books_page(
                    _resolve_page(page), effective_page_size
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

        if effective_page_size is None:
            return [BookOut.from_book(book) for book in books]
        return PagedBooksOut.from_paged_result(paged_books)

    @app.get("/libraries/authors", response_model=None)
    def list_authors(
        tag: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[AuthorOut] | PagedAuthorsOut | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )

        gateway = SqliteLibraryGateway(db_path)
        effective_page_size = _resolve_page_size(page_size)
        try:
            if effective_page_size is None:
                authors = gateway.list_authors()
            else:
                paged_authors = gateway.list_authors_page(
                    _resolve_page(page), effective_page_size
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

        if effective_page_size is None:
            return [AuthorOut.from_author(author) for author in authors]
        return PagedAuthorsOut.from_paged_result(paged_authors)

    @app.get("/libraries/publishers", response_model=None)
    def list_publishers(
        tag: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[PublisherOut] | PagedPublishersOut | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )

        gateway = SqliteLibraryGateway(db_path)
        effective_page_size = _resolve_page_size(page_size)
        try:
            if effective_page_size is None:
                publishers = gateway.list_publishers()
            else:
                paged_publishers = gateway.list_publishers_page(
                    _resolve_page(page), effective_page_size
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

        if effective_page_size is None:
            return [PublisherOut.from_publisher(publisher) for publisher in publishers]
        return PagedPublishersOut.from_paged_result(paged_publishers)

    @app.post("/libraries/books/detail", response_model=None)
    def get_book_details(
        body: BookIdsIn, tag: str | None = None
    ) -> BookDetailsResultOut | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )

        gateway = SqliteLibraryGateway(db_path)
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
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )

        gateway = SqliteLibraryGateway(db_path)
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
        if cover_path is None or cover_path is False or not Path(cover_path).is_file():
            return _cover_not_found(id)

        return Response(content=Path(cover_path).read_bytes(), media_type="image/jpeg")

    return app
