from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from book0_api.schemas import (
    AuthorOut,
    BookDetailsResultOut,
    BookIdsIn,
    BookOut,
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


def create_app(libraries: dict[str, Path], default_tag: str | None = None) -> FastAPI:
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

    @app.get("/libraries/books", response_model=None)
    def list_books(tag: str | None = None) -> list[BookOut] | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )

        gateway = SqliteLibraryGateway(db_path)
        try:
            books = gateway.list_books()
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

        return [BookOut.from_book(book) for book in books]

    @app.get("/libraries/authors", response_model=None)
    def list_authors(tag: str | None = None) -> list[AuthorOut] | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )

        gateway = SqliteLibraryGateway(db_path)
        try:
            authors = gateway.list_authors()
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

        return [AuthorOut.from_author(author) for author in authors]

    @app.get("/libraries/publishers", response_model=None)
    def list_publishers(tag: str | None = None) -> list[PublisherOut] | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )

        gateway = SqliteLibraryGateway(db_path)
        try:
            publishers = gateway.list_publishers()
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

        return [PublisherOut.from_publisher(publisher) for publisher in publishers]

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
