from pathlib import Path
from typing import Literal

import httpx

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
    UnknownJobError,
)
from book0_core.models import (
    Author,
    Book,
    BookDetails,
    BookDetailsResult,
    BookQuery,
    FieldValue,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    PagedSeriesResult,
    Publisher,
    Series,
    SeriesItem,
)

_ERROR_TYPES = {
    "LibraryNotFoundError": LibraryNotFoundError,
    "NotACalibreLibraryError": NotACalibreLibraryError,
    "TagRequiredError": TagRequiredError,
    "BookNotFoundError": BookNotFoundError,
    "NoEpubError": NoEpubError,
    "InvalidExtractError": InvalidExtractError,
    "InvalidFilterError": InvalidFilterError,
    "InvalidPatchError": InvalidPatchError,
    "UnknownJobError": UnknownJobError,
    "UnknownJobActionError": UnknownJobActionError,
    "AuthorNotFoundError": AuthorNotFoundError,
    "AuthorNameMismatchError": AuthorNameMismatchError,
    "InvalidAliasError": InvalidAliasError,
    "InvalidApplyNameError": InvalidApplyNameError,
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

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.status_code in (400, 404, 500):
            body = response.json()
            error_type = _ERROR_TYPES[body["error"]]
            raise error_type(body["detail"])
        response.raise_for_status()

    def list_books(self) -> list[Book]:
        response = self._client.get("/libraries/books", params=self._params())
        self._raise_for_error(response)

        body = response.json()
        if isinstance(body, dict):
            return self._collect_all_book_pages(body)
        return [self._book_from_json(row) for row in body]

    def _collect_all_book_pages(self, first_page: dict[str, object]) -> list[Book]:
        page_size = first_page["page_size"]
        page = first_page["page"]
        items = first_page["items"]  # type: ignore[assignment]
        books = [self._book_from_json(row) for row in items]  # type: ignore[attr-defined]
        while page_size and len(items) == page_size:  # type: ignore[arg-type]
            page += 1  # type: ignore[operator]
            response = self._client.get(
                "/libraries/books",
                params={
                    **self._params(),
                    "page": str(page),
                    "page_size": str(page_size),
                },
            )
            self._raise_for_error(response)
            next_page = response.json()
            items = next_page["items"]
            books.extend(self._book_from_json(row) for row in items)
        return books

    def list_authors(self) -> list[Author]:
        response = self._client.get("/libraries/authors", params=self._params())
        self._raise_for_error(response)

        body = response.json()
        if isinstance(body, dict):
            return self._collect_all_author_pages(body)
        return [self._author_from_json(row) for row in body]

    def _collect_all_author_pages(self, first_page: dict[str, object]) -> list[Author]:
        page_size = first_page["page_size"]
        page = first_page["page"]
        items = first_page["items"]  # type: ignore[assignment]
        authors = [self._author_from_json(row) for row in items]  # type: ignore[attr-defined]
        while page_size and len(items) == page_size:  # type: ignore[arg-type]
            page += 1  # type: ignore[operator]
            response = self._client.get(
                "/libraries/authors",
                params={
                    **self._params(),
                    "page": str(page),
                    "page_size": str(page_size),
                },
            )
            self._raise_for_error(response)
            next_page = response.json()
            items = next_page["items"]
            authors.extend(self._author_from_json(row) for row in items)
        return authors

    def list_publishers(self) -> list[Publisher]:
        response = self._client.get("/libraries/publishers", params=self._params())
        self._raise_for_error(response)

        body = response.json()
        if isinstance(body, dict):
            return self._collect_all_publisher_pages(body)
        return [self._publisher_from_json(row) for row in body]

    def _collect_all_publisher_pages(
        self, first_page: dict[str, object]
    ) -> list[Publisher]:
        page_size = first_page["page_size"]
        page = first_page["page"]
        items = first_page["items"]  # type: ignore[assignment]
        publishers = [self._publisher_from_json(row) for row in items]  # type: ignore[attr-defined]
        while page_size and len(items) == page_size:  # type: ignore[arg-type]
            page += 1  # type: ignore[operator]
            response = self._client.get(
                "/libraries/publishers",
                params={
                    **self._params(),
                    "page": str(page),
                    "page_size": str(page_size),
                },
            )
            self._raise_for_error(response)
            next_page = response.json()
            items = next_page["items"]
            publishers.extend(self._publisher_from_json(row) for row in items)
        return publishers

    def list_series(self) -> list[Series]:
        response = self._client.get("/libraries/series", params=self._params())
        self._raise_for_error(response)

        body = response.json()
        if isinstance(body, dict):
            return self._collect_all_series_pages(body)
        return [self._series_from_json(row) for row in body]

    def _collect_all_series_pages(self, first_page: dict[str, object]) -> list[Series]:
        page_size = first_page["page_size"]
        page = first_page["page"]
        items = first_page["items"]  # type: ignore[assignment]
        series = [self._series_from_json(row) for row in items]  # type: ignore[attr-defined]
        while page_size and len(items) == page_size:  # type: ignore[arg-type]
            page += 1  # type: ignore[operator]
            response = self._client.get(
                "/libraries/series",
                params={
                    **self._params(),
                    "page": str(page),
                    "page_size": str(page_size),
                },
            )
            self._raise_for_error(response)
            next_page = response.json()
            items = next_page["items"]
            series.extend(self._series_from_json(row) for row in items)
        return series

    def list_books_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult:
        response = self._client.get(
            "/libraries/books",
            params={**self._params(), "page": str(page), "page_size": str(page_size)},
        )
        self._raise_for_error(response)
        body = response.json()
        return PagedBooksResult(
            items=tuple(self._book_from_json(row) for row in body["items"]),
            page=body["page"],
            page_size=body["page_size"],
            total_pages=body["total_pages"],
            has_more_than_shown=body["has_more_than_shown"],
            handle=None,
        )

    def list_authors_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult:
        response = self._client.get(
            "/libraries/authors",
            params={**self._params(), "page": str(page), "page_size": str(page_size)},
        )
        self._raise_for_error(response)
        body = response.json()
        return PagedAuthorsResult(
            items=tuple(self._author_from_json(row) for row in body["items"]),
            page=body["page"],
            page_size=body["page_size"],
            total_pages=body["total_pages"],
            has_more_than_shown=body["has_more_than_shown"],
            handle=None,
        )

    def list_publishers_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult:
        response = self._client.get(
            "/libraries/publishers",
            params={**self._params(), "page": str(page), "page_size": str(page_size)},
        )
        self._raise_for_error(response)
        body = response.json()
        return PagedPublishersResult(
            items=tuple(self._publisher_from_json(row) for row in body["items"]),
            page=body["page"],
            page_size=body["page_size"],
            total_pages=body["total_pages"],
            has_more_than_shown=body["has_more_than_shown"],
            handle=None,
        )

    def list_series_page(
        self, page: int, page_size: int, handle: str | None = None
    ) -> PagedSeriesResult:
        response = self._client.get(
            "/libraries/series",
            params={**self._params(), "page": str(page), "page_size": str(page_size)},
        )
        self._raise_for_error(response)
        body = response.json()
        return PagedSeriesResult(
            items=tuple(self._series_from_json(row) for row in body["items"]),
            page=body["page"],
            page_size=body["page_size"],
            total_pages=body["total_pages"],
            has_more_than_shown=body["has_more_than_shown"],
            handle=None,
        )

    def close_pagination(self, handle: str) -> None:
        pass

    # The query_*_page methods exist on ReadLibraryGateway (and are served by
    # book0_api's SQLite gateway server-side), but the REST contract does not
    # carry the filter parameters yet - book0-remote cannot express a BookQuery
    # over the wire today. They fail fast rather than silently ignoring the
    # filters; wiring them is future work, not a silent no-op.

    def query_books_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedBooksResult:
        raise NotImplementedError("book0-remote does not support filtered queries yet")

    def query_authors_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedAuthorsResult:
        raise NotImplementedError("book0-remote does not support filtered queries yet")

    def query_publishers_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedPublishersResult:
        raise NotImplementedError("book0-remote does not support filtered queries yet")

    def query_series_page(
        self, query: BookQuery, page: int, page_size: int, handle: str | None = None
    ) -> PagedSeriesResult:
        raise NotImplementedError("book0-remote does not support filtered queries yet")

    def list_field_values(
        self, field: Literal["tags", "languages", "formats", "ratings"]
    ) -> list[FieldValue]:
        raise NotImplementedError("book0-remote does not support facet queries yet")

    def get_book_details(self, ids: list[str]) -> BookDetailsResult:
        response = self._client.post(
            "/libraries/books/detail", params=self._params(), json={"ids": ids}
        )
        self._raise_for_error(response)

        body = response.json()
        return BookDetailsResult(
            books=tuple(self._book_details_from_json(row) for row in body["books"]),
            missing_ids=tuple(body["missing_ids"]),
        )

    @staticmethod
    def _book_from_json(row: dict[str, object]) -> Book:
        publisher_row = row["publisher"]
        series_row = row["series"]
        return Book(
            id=row["id"],  # type: ignore[arg-type]
            title=row["title"],  # type: ignore[arg-type]
            authors=tuple(row["authors"]),  # type: ignore[arg-type]
            pubdate=row["pubdate"],  # type: ignore[arg-type]
            publisher=(
                Publisher(id=publisher_row["id"], name=publisher_row["name"])  # type: ignore[index]
                if publisher_row is not None
                else None
            ),
            series=(
                Series(id=series_row["id"], name=series_row["name"])  # type: ignore[index]
                if series_row is not None
                else None
            ),
            series_index=row["series_index"],  # type: ignore[arg-type]
            rating=row["rating"],  # type: ignore[arg-type]
            has_cover=bool(row["has_cover"]),
        )

    @staticmethod
    def _author_from_json(row: dict[str, object]) -> Author:
        return Author(id=row["id"], name=row["name"])  # type: ignore[arg-type]

    @staticmethod
    def _publisher_from_json(row: dict[str, object]) -> Publisher:
        return Publisher(id=row["id"], name=row["name"])  # type: ignore[arg-type]

    @staticmethod
    def _series_from_json(row: dict[str, object]) -> Series:
        return Series(id=row["id"], name=row["name"])  # type: ignore[arg-type]

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
        if Path(book_id).name != book_id:
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
