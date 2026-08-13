from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

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


def create_app(libraries: dict[str, Path], default_tag: str | None = None) -> FastAPI:
    app = FastAPI()

    def _resolve_db_path(tag: str | None) -> Path | None:
        resolved_tag = tag if tag is not None else default_tag
        if resolved_tag is None:
            raise TagRequiredError(
                "No tag given and no default-library configured for this server"
            )
        return libraries.get(resolved_tag)

    @app.get("/libraries/books", response_model=None)
    def list_books(tag: str | None = None) -> list[BookOut] | JSONResponse:
        try:
            db_path = _resolve_db_path(tag)
        except TagRequiredError as error:
            return JSONResponse(
                status_code=400,
                content={"error": "TagRequiredError", "detail": str(error)},
            )
        if db_path is None:
            return []

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
        if db_path is None:
            return []

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
        if db_path is None:
            return []

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
        if db_path is None:
            return BookDetailsResultOut(books=[], missing_ids=body.ids)

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

    return app
