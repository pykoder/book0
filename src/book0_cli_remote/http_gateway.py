import httpx

from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError
from book0_core.models import Author, Book

_ERROR_TYPES = {
    "LibraryNotFoundError": LibraryNotFoundError,
    "NotACalibreLibraryError": NotACalibreLibraryError,
}


class HttpLibraryGateway:
    def __init__(self, client: httpx.Client, tag: str) -> None:
        self._client = client
        self._tag = tag

    def list_books(self) -> list[Book]:
        response = self._client.get(f"/libraries/{self._tag}/books")

        if response.status_code in (404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [
            Book(
                id=row["id"],
                title=row["title"],
                authors=tuple(row["authors"]),
                pubdate=row["pubdate"],
            )
            for row in response.json()
        ]

    def list_authors(self) -> list[Author]:
        response = self._client.get(f"/libraries/{self._tag}/authors")

        if response.status_code in (404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [Author(id=row["id"], name=row["name"]) for row in response.json()]
