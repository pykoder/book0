from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from book0_api.schemas import BookOut
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

    return app
