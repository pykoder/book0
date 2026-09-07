import sqlite3
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from book0_cli_remote.http_gateway import HttpLibraryGateway
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)
from book0_core.gateway import ReadLibraryGateway
from book0_core.models import (
    BookDetails,
    BookQuery,
    PagedAuthorsResult,
    PagedBooksResult,
    PagedPublishersResult,
    PagedSeriesResult,
)
from book0_core.testing import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    CALIBRE_LIBRARY_SERIES,
)
from fastapi.testclient import TestClient

from book0_api.main import create_app


def _client_for(
    libraries: dict[str, Path], default_tag: str | None = None
) -> httpx.Client:
    return TestClient(create_app(libraries, default_tag))


def _without_local_cover(details: BookDetails) -> BookDetails:
    """A gateway constructed with no cache_dir can never report a real local
    path - has_cover=True books resolve to False (unavailable), not the
    server's real path."""
    if details.cover_path is None:
        return details
    return replace(details, cover_path=False)


def test_list_books_returns_expected_books_for_a_known_tag(calibre_metadata_db: Path):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS


def test_list_books_raises_tag_required_error_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    with pytest.raises(TagRequiredError):
        gateway.list_books()


def test_list_books_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_books()


def test_list_books_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_books()


def test_list_authors_returns_expected_authors_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_authors() == CALIBRE_LIBRARY_AUTHORS


def test_list_authors_raises_tag_required_error_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    with pytest.raises(TagRequiredError):
        gateway.list_authors()


def test_list_authors_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_authors()


def test_list_authors_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_authors()


def test_list_publishers_returns_expected_publishers_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_list_publishers_raises_tag_required_error_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    with pytest.raises(TagRequiredError):
        gateway.list_publishers()


def test_list_publishers_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_publishers()


def test_list_publishers_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_publishers()


def test_list_series_returns_expected_series_for_a_known_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_series() == CALIBRE_LIBRARY_SERIES


def test_list_series_raises_tag_required_error_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    with pytest.raises(TagRequiredError):
        gateway.list_series()


def test_list_series_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.list_series()


def test_list_series_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.list_series()


def test_http_gateway_satisfies_the_library_gateway_protocol(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway: ReadLibraryGateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_list_books_uses_server_side_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db}, default_tag="fiction")
    gateway = HttpLibraryGateway(client, None)

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS


def test_list_books_raises_tag_required_error_when_no_default_configured(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, None)

    with pytest.raises(TagRequiredError):
        gateway.list_books()


def test_get_book_details_uses_server_side_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db}, default_tag="fiction")
    gateway = HttpLibraryGateway(client, None)

    result = gateway.get_book_details(["1"])

    assert result.books == (_without_local_cover(dune_details),)
    assert result.missing_ids == ()


def test_get_book_details_returns_expected_details_for_a_known_tag(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, hobbit_details, good_omens_details = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.get_book_details(["3", "1", "2"])

    assert set(result.books) == {
        _without_local_cover(dune_details),
        hobbit_details,
        _without_local_cover(good_omens_details),
    }
    assert result.missing_ids == ()


def test_get_book_details_reports_missing_ids_for_a_known_tag(
    calibre_metadata_db: Path,
    expected_book_details: tuple,
):
    dune_details, _, _ = expected_book_details
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result = gateway.get_book_details(["1", "999"])

    assert result.books == (_without_local_cover(dune_details),)
    assert result.missing_ids == ("999",)


def test_get_book_details_raises_tag_required_error_for_an_unknown_tag(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "does-not-exist")

    with pytest.raises(TagRequiredError):
        gateway.get_book_details(["1", "2"])


def test_get_book_details_raises_library_not_found_error(tmp_path: Path):
    client = _client_for({"fiction": tmp_path / "does-not-exist.db"})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(LibraryNotFoundError):
        gateway.get_book_details(["1"])


def test_get_book_details_raises_not_a_calibre_library_error(tmp_path: Path):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    client = _client_for({"fiction": db_path})
    gateway = HttpLibraryGateway(client, "fiction")

    with pytest.raises(NotACalibreLibraryError):
        gateway.get_book_details(["1"])


def test_get_book_details_uses_cached_cover_without_making_an_http_request(
    calibre_metadata_db: Path, tmp_path: Path
):
    cache_dir = tmp_path / "cache"
    cached_cover = cache_dir / "fiction" / "1.jpg"
    cached_cover.parent.mkdir(parents=True)
    cached_cover.write_bytes(b"cached-bytes")
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction", cache_dir=cache_dir)

    result = gateway.get_book_details(["1"])

    assert result.books[0].cover_path == str(cached_cover)


def test_get_book_details_reports_false_cover_path_when_not_cached_and_with_covers_is_off(
    calibre_metadata_db: Path, tmp_path: Path
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction", cache_dir=tmp_path / "cache")

    result = gateway.get_book_details(["1"])

    assert result.books[0].cover_path is False


def test_get_book_details_downloads_and_caches_the_cover_when_with_covers_is_set(
    calibre_metadata_db: Path, tmp_path: Path
):
    library_root = calibre_metadata_db.parent
    server_cover = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    server_cover.parent.mkdir(parents=True, exist_ok=True)
    server_cover.write_bytes(b"server-bytes")
    cache_dir = tmp_path / "cache"
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(
        client, "fiction", with_covers=True, cache_dir=cache_dir
    )

    result = gateway.get_book_details(["1"])

    expected_path = cache_dir / "fiction" / "1.jpg"
    assert result.books[0].cover_path == str(expected_path)
    assert expected_path.read_bytes() == b"server-bytes"


def test_get_book_details_caches_the_cover_under_the_default_namespace_when_tag_is_none(
    calibre_metadata_db: Path, tmp_path: Path
):
    library_root = calibre_metadata_db.parent
    server_cover = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    server_cover.parent.mkdir(parents=True, exist_ok=True)
    server_cover.write_bytes(b"server-bytes")
    cache_dir = tmp_path / "cache"
    client = _client_for({"fiction": calibre_metadata_db}, default_tag="fiction")
    gateway = HttpLibraryGateway(client, None, with_covers=True, cache_dir=cache_dir)

    result = gateway.get_book_details(["1"])

    expected_path = cache_dir / "_default" / "1.jpg"
    assert result.books[0].cover_path == str(expected_path)
    assert expected_path.read_bytes() == b"server-bytes"


def test_get_book_details_reports_false_cover_path_when_the_fetch_fails(
    calibre_metadata_db: Path, tmp_path: Path
):
    # Dune (id 1) has has_cover=1 in the fixture DB but no real cover.jpg
    # file on disk, so the server's own cover route 404s - the fetch must
    # fail without raising.
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(
        client, "fiction", with_covers=True, cache_dir=tmp_path / "cache"
    )

    result = gateway.get_book_details(["1"])

    assert result.books[0].cover_path is False


class _CoverInjectionResponse:
    """Minimal stand-in for an httpx.Response, just enough of the surface
    HttpLibraryGateway actually uses."""

    def __init__(
        self,
        status_code: int,
        json_data: object = None,
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.content = content

    def json(self) -> object:
        return self._json_data

    def raise_for_status(self) -> None:
        pass


class _CoverInjectionClient:
    """Stub httpx.Client whose books-detail response smuggles a
    path-traversal book id, simulating a malicious/compromised server (or a
    MITM on plaintext http://) trying to make HttpLibraryGateway write a
    cover file outside the configured cache_dir."""

    def __init__(self, malicious_id: str) -> None:
        self._malicious_id = malicious_id

    def post(
        self, url: str, params: object = None, json: object = None
    ) -> _CoverInjectionResponse:
        return _CoverInjectionResponse(
            200,
            {
                "books": [
                    {
                        "id": self._malicious_id,
                        "title": "Evil",
                        "pubdate": None,
                        "authors": [],
                        "tags": [],
                        "publisher": None,
                        "series": None,
                        "has_cover": True,
                    }
                ],
                "missing_ids": [],
            },
        )

    def get(self, url: str, params: object = None) -> _CoverInjectionResponse:
        return _CoverInjectionResponse(200, content=b"malicious-bytes")


def test_list_books_page_returns_the_requested_page(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result: PagedBooksResult = gateway.list_books_page(1, 2)

    assert [book.title for book in result.items] == ["Book 1", "Book 2"]
    assert result.page == 1
    assert result.page_size == 2
    assert result.total_pages == 4


def test_list_books_page_never_sends_the_handle_over_the_wire(
    many_books_db: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client_for({"fiction": many_books_db})
    captured_params: list[dict[str, str]] = []
    real_get = client.get

    def spying_get(url: str, **kwargs: object) -> httpx.Response:
        captured_params.append(dict(kwargs.get("params", {})))  # type: ignore[arg-type]
        return real_get(url, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(client, "get", spying_get)
    gateway = HttpLibraryGateway(client, "fiction")

    gateway.list_books_page(2, 2, handle="some-handle-from-a-previous-call")

    assert all("handle" not in params for params in captured_params)


def test_close_pagination_is_a_no_op(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    gateway.close_pagination("any-handle")  # no exception


def test_list_authors_page_returns_the_requested_page(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result: PagedAuthorsResult = gateway.list_authors_page(1, 2)

    assert [author.name for author in result.items] == ["Author 1", "Author 2"]


def test_list_publishers_page_returns_the_requested_page(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result: PagedPublishersResult = gateway.list_publishers_page(1, 2)

    assert [publisher.name for publisher in result.items] == [
        "Publisher 1",
        "Publisher 2",
    ]


def test_list_series_page_returns_the_requested_page(many_books_db: Path):
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")

    result: PagedSeriesResult = gateway.list_series_page(1, 2)

    assert [series.name for series in result.items] == ["Series 1", "Series 2"]
    assert result.page == 1
    assert result.page_size == 2
    assert result.total_pages == 4


def test_query_methods_fail_fast_until_the_rest_contract_carries_filters(
    many_books_db: Path,
):
    # The REST contract has no filter parameters yet, so the remote gateway
    # cannot honor a BookQuery; it must fail fast rather than silently ignore
    # the filters (HttpLibraryGateway still satisfies ReadLibraryGateway).
    client = _client_for({"fiction": many_books_db})
    gateway = HttpLibraryGateway(client, "fiction")
    query = BookQuery(tags=("fantasy",))

    with pytest.raises(NotImplementedError):
        gateway.query_books_page(query, 1, 10)
    with pytest.raises(NotImplementedError):
        gateway.query_authors_page(query, 1, 10)
    with pytest.raises(NotImplementedError):
        gateway.query_publishers_page(query, 1, 10)
    with pytest.raises(NotImplementedError):
        gateway.query_series_page(query, 1, 10)


def test_list_books_transparently_fetches_every_page_when_server_forces_pagination(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)
    gateway = HttpLibraryGateway(client, "fiction")

    books = gateway.list_books()

    assert [book.title for book in books] == [f"Book {i}" for i in range(1, 8)]


def test_collect_all_book_pages_does_not_hang_when_page_size_is_zero(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)
    gateway = HttpLibraryGateway(client, "fiction")
    first_page = client.get("/libraries/books", params={"tag": "fiction"}).json()
    first_page["page_size"] = 0

    books = gateway._collect_all_book_pages(first_page)

    assert [book.title for book in books] == ["Book 1", "Book 2"]


def test_list_authors_transparently_fetches_every_page_when_server_forces_pagination(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)
    gateway = HttpLibraryGateway(client, "fiction")

    authors = gateway.list_authors()

    assert [author.name for author in authors] == [f"Author {i}" for i in range(1, 8)]


def test_list_series_transparently_fetches_every_page_when_server_forces_pagination(
    many_books_db: Path,
):
    app = create_app({"fiction": many_books_db}, default_page_size=2)
    client = TestClient(app)
    gateway = HttpLibraryGateway(client, "fiction")

    series = gateway.list_series()

    assert [item.name for item in series] == [f"Series {i}" for i in range(1, 8)]


def test_list_books_returns_plain_list_unchanged_when_server_does_not_force_pagination(
    calibre_metadata_db: Path,
):
    client = _client_for({"fiction": calibre_metadata_db})
    gateway = HttpLibraryGateway(client, "fiction")

    assert gateway.list_books() == CALIBRE_LIBRARY_BOOKS


def test_resolve_cover_rejects_a_path_traversal_book_id(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    client = _CoverInjectionClient("../../outside")
    gateway = HttpLibraryGateway(
        client, "fiction", with_covers=True, cache_dir=cache_dir
    )

    result = gateway.get_book_details(["../../outside"])

    assert result.books[0].cover_path is False
    # The would-be traversal target the un-validated code wrote to
    # (cache_dir/fiction/../../outside.jpg resolves to tmp_path/outside.jpg)
    # must not exist.
    assert not (tmp_path / "outside.jpg").exists()
    # Nothing should have been written anywhere under cache_dir either.
    assert not cache_dir.exists() or not any(cache_dir.rglob("*"))
