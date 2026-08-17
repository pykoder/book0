from pathlib import Path
from typing import Literal

import httpx

from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    Publisher,
    Series,
    SeriesItem,
)

_ERROR_TYPES = {
    "LibraryNotFoundError": LibraryNotFoundError,
    "NotACalibreLibraryError": NotACalibreLibraryError,
    "TagRequiredError": TagRequiredError,
}


class HttpLibraryGateway:
    def __init__(
        self,
        client: httpx.Client,
        tag: str | None,
        *,
        with_covers: bool = False,
        cache_dir: Path | None = None,
    ) -> None:
        self._client = client
        self._tag = tag
        self._with_covers = with_covers
        self._cache_dir = cache_dir

    def _params(self) -> dict[str, str]:
        return {"tag": self._tag} if self._tag is not None else {}

    def list_books(self) -> list[Book]:
        response = self._client.get("/libraries/books", params=self._params())

        if response.status_code in (400, 404, 500):
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
        response = self._client.get("/libraries/authors", params=self._params())

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [Author(id=row["id"], name=row["name"]) for row in response.json()]

    def list_publishers(self) -> list[Publisher]:
        response = self._client.get("/libraries/publishers", params=self._params())

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        return [Publisher(id=row["id"], name=row["name"]) for row in response.json()]

    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        response = self._client.post(
            "/libraries/books/detail", params=self._params(), json={"ids": ids}
        )

        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

        body = response.json()
        return BookDetailsResult(
            books=tuple(self._book_details_from_json(row) for row in body["books"]),
            missing_ids=tuple(body["missing_ids"]),
        )

    def _book_details_from_json(self, row: dict[str, object]) -> BookDetails:
        publisher_row = row["publisher"]
        publisher = (
            Publisher(id=publisher_row["id"], name=publisher_row["name"])  # type: ignore[index]
            if publisher_row is not None
            else None
        )
        series_row = row["series"]
        series = (
            SeriesItem(
                series=Series(
                    id=series_row["series"]["id"],  # type: ignore[index]
                    name=series_row["series"]["name"],  # type: ignore[index]
                ),
                index=series_row["index"],  # type: ignore[index]
            )
            if series_row is not None
            else None
        )
        return BookDetails(
            id=row["id"],  # type: ignore[arg-type]
            title=row["title"],  # type: ignore[arg-type]
            pubdate=row["pubdate"],  # type: ignore[arg-type]
            authors=tuple(row["authors"]),  # type: ignore[arg-type]
            tags=tuple(row["tags"]),  # type: ignore[arg-type]
            publisher=publisher,
            series=series,
            cover_path=self._resolve_cover(row["id"], row["has_cover"]),  # type: ignore[arg-type]
        )

    def _resolve_cover(
        self, book_id: str, has_cover: bool
    ) -> str | None | Literal[False]:
        if not has_cover:
            return None
        if self._cache_dir is None:
            return False

        cache_path = self._cover_cache_path(book_id)
        if cache_path.is_file():
            return str(cache_path)
        if not self._with_covers:
            return False

        try:
            response = self._client.get(
                f"/libraries/books/{book_id}/cover", params=self._params()
            )
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
        return str(cache_path)

    def _cover_cache_path(self, book_id: str) -> Path:
        return self._cache_dir / (self._tag or "_default") / f"{book_id}.jpg"  # type: ignore[operator]
