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
from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.sqlite_gateway import SqliteLibraryGateway


def create_app(libraries: dict[str, Path]) -> FastAPI:
    app = FastAPI()

    @app.get("/libraries/{tag}/books", response_model=None)
    def list_books(tag: str) -> list[BookOut] | JSONResponse:
        db_path = libraries.get(tag)
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

    @app.get("/libraries/{tag}/authors", response_model=None)
    def list_authors(tag: str) -> list[AuthorOut] | JSONResponse:
        db_path = libraries.get(tag)
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

    @app.get("/libraries/{tag}/publishers", response_model=None)
    def list_publishers(tag: str) -> list[PublisherOut] | JSONResponse:
        db_path = libraries.get(tag)
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

    @app.post("/libraries/{tag}/books/detail", response_model=None)
    def get_book_details(
        tag: str, body: BookIdsIn
    ) -> BookDetailsResultOut | JSONResponse:
        db_path = libraries.get(tag)
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
