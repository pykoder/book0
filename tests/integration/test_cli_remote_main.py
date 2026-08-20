from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from book0_api.main import create_app
from book0_cli_remote.main import run
from book0_presentation.tables import (
    render_author_table,
    render_book_details_table,
    render_book_table,
    render_publisher_table,
)
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)


def test_run_prints_table_for_a_known_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["--server", "unused", "--tag", "fiction"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_unknown_tag_on_stderr_and_exits_with_status_1(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["--server", "unused", "--tag", "does-not-exist"], client=client)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_library_not_found_on_stderr_and_exits_with_status_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": tmp_path / "does-not-exist.db"}))

    exit_code = run(["--server", "unused", "--tag", "fiction"], client=client)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_unreachable_server_on_stderr_and_exits_with_status_1(
    capsys: pytest.CaptureFixture[str],
):
    exit_code = run(["--server", "http://127.0.0.1:1", "--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_prints_author_table_for_a_known_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["authors", "--server", "unused", "--tag", "fiction"], client=client
    )

    assert exit_code == 0
    assert (
        capsys.readouterr().out == render_author_table(CALIBRE_LIBRARY_AUTHORS) + "\n"
    )


def test_run_reports_unknown_tag_on_stderr_for_authors_and_exits_with_status_1(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["authors", "--server", "unused", "--tag", "does-not-exist"], client=client
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_lists_books_when_subcommand_is_explicit(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["books", "--server", "unused", "--tag", "fiction"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_help_mentions_the_authors_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "authors" in capsys.readouterr().out


def test_run_prints_publisher_table_for_a_known_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["publishers", "--server", "unused", "--tag", "fiction"], client=client
    )

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_publisher_table(CALIBRE_LIBRARY_PUBLISHERS) + "\n"
    )


def test_run_reports_unknown_tag_on_stderr_for_publishers_and_exits_with_status_1(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["publishers", "--server", "unused", "--tag", "does-not-exist"],
        client=client,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_help_mentions_the_publishers_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "publishers" in capsys.readouterr().out


def test_run_prints_book_details_in_the_requested_id_order(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    dune_details, _, good_omens_details = expected_book_details
    dune_details = replace(dune_details, cover_path=False)
    good_omens_details = replace(good_omens_details, cover_path=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "3,1",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_book_details_table([good_omens_details, dune_details]) + "\n"
    )


def test_run_reports_missing_ids_for_book_details(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    dune_details, _, _ = expected_book_details
    dune_details = replace(dune_details, cover_path=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1,999",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert (
        captured == render_book_details_table([dune_details]) + "\nMissing ids: 999\n"
    )


def test_run_dedupes_and_strips_whitespace_from_requested_book_detail_ids(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    expected_book_details: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    dune_details, _, _ = expected_book_details
    dune_details = replace(dune_details, cover_path=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1, 1, 999",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert (
        captured == render_book_details_table([dune_details]) + "\nMissing ids: 999\n"
    )


def test_run_reports_unknown_tag_on_stderr_for_books_detail_and_exits_with_status_1(
    calibre_metadata_db: Path,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1,2",
            "--server",
            "unused",
            "--tag",
            "does-not-exist",
        ],
        client=client,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_usage_error_when_ids_is_omitted_entirely(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["books-detail", "--server", "unused", "--tag", "fiction"])

    assert exc_info.value.code == 2


def test_run_help_mentions_the_books_detail_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "books-detail" in capsys.readouterr().out


def test_run_uses_server_side_default_tag_when_tag_is_omitted(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(
        create_app({"fiction": calibre_metadata_db}, default_tag="fiction")
    )

    exit_code = run(["--server", "unused"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_tag_required_error_on_stderr_and_exits_with_status_1(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["--server", "unused"], client=client)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "No tag given and no default-library configured for this server" in (
        captured.err
    )


def test_run_resolves_server_from_book0_client_toml_when_server_flag_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text('server = "http://127.0.0.1:1"\n')

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Could not reach the book0 server at http://127.0.0.1:1" in captured.err


def test_run_prefers_explicit_server_flag_over_book0_client_toml(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    # Uses valid (but irrelevant/unreachable) TOML rather than syntactically
    # invalid TOML: since Task 12, the config file is also read for
    # default-page-size resolution even when --server is given explicitly
    # (see test_run_uses_default_page_size_from_client_config_when_flag_is_omitted),
    # so a malformed file would now legitimately surface a parse error here
    # instead of proving --server takes precedence. A valid file whose
    # `server` key points nowhere still proves the same thing: if it were
    # used instead of --server, the request would fail to connect.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text('server = "http://127.0.0.1:1"\n')
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["--server", "unused", "--tag", "fiction"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_error_when_server_flag_omitted_and_no_client_config_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "No --server given and no book0-remote client config file found" in (
        captured.err
    )


def test_run_reports_error_for_invalid_book0_client_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text("not valid toml === \n")

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Invalid book0-remote client config file" in captured.err


def test_run_shows_unavailable_cover_when_with_covers_flag_is_omitted(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["books-detail", "--ids", "1", "--server", "unused", "--tag", "fiction"],
        client=client,
    )

    assert exit_code == 0
    assert "(unavailable)" in capsys.readouterr().out


def test_run_downloads_and_caches_cover_when_with_covers_flag_is_given(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    library_root = calibre_metadata_db.parent
    server_cover = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    server_cover.parent.mkdir(parents=True, exist_ok=True)
    server_cover.write_bytes(b"server-bytes")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1",
            "--with-covers",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    cached_cover = (
        tmp_path / "home" / ".cache" / "book0" / "covers" / "fiction" / "1.jpg"
    )
    assert cached_cover.read_bytes() == b"server-bytes"
    assert str(cached_cover) in capsys.readouterr().out


def test_run_uses_cover_cache_dir_from_client_config(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    library_root = calibre_metadata_db.parent
    server_cover = library_root / "Frank Herbert/Dune (1)/cover.jpg"
    server_cover.parent.mkdir(parents=True, exist_ok=True)
    server_cover.write_bytes(b"server-bytes")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    custom_cache_dir = tmp_path / "custom-cache"
    (tmp_path / ".book0-client.toml").write_text(
        f'server = "http://unused"\ncover-cache-dir = "{custom_cache_dir}"\n'
    )
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        [
            "books-detail",
            "--ids",
            "1",
            "--with-covers",
            "--server",
            "unused",
            "--tag",
            "fiction",
        ],
        client=client,
    )

    assert exit_code == 0
    cached_cover = custom_cache_dir / "fiction" / "1.jpg"
    assert cached_cover.read_bytes() == b"server-bytes"


def test_run_reports_error_for_invalid_cover_cache_dir_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text("not valid toml === \n")

    exit_code = run(
        ["books-detail", "--ids", "1", "--server", "unused", "--tag", "fiction"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Invalid book0-remote client config file" in captured.err


def test_run_prints_a_page_and_footer_when_page_size_flag_is_given(
    paginated_calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": paginated_calibre_metadata_db}))

    exit_code = run(
        [
            "--server",
            "unused",
            "--tag",
            "fiction",
            "--page",
            "2",
            "--page-size",
            "2",
        ],
        client=client,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Book 03" in out
    assert "Book 04" in out
    assert "Page 2 of 4" in out


def test_run_uses_default_page_size_from_client_config_when_flag_is_omitted(
    paginated_calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".book0-client.toml").write_text(
        'server = "http://127.0.0.1:8000"\ndefault-page-size = 3\n'
    )
    client = TestClient(create_app({"fiction": paginated_calibre_metadata_db}))

    exit_code = run(["--server", "unused", "--tag", "fiction"], client=client)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page 1 of 3" in out
    assert "Book 01" in out
    assert "Book 04" not in out


def test_run_is_unpaginated_when_no_page_size_is_resolvable(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["--server", "unused", "--tag", "fiction", "--page", "1"], client=client
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page" not in out


def test_run_normalizes_a_non_positive_page_to_one(
    paginated_calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": paginated_calibre_metadata_db}))

    exit_code = run(
        [
            "--server",
            "unused",
            "--tag",
            "fiction",
            "--page",
            "0",
            "--page-size",
            "2",
        ],
        client=client,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page 1 of 4" in out
    assert "Book 01" in out


def test_run_treats_a_non_positive_page_size_as_unpaginated(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["--server", "unused", "--tag", "fiction", "--page-size", "0"],
        client=client,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Page" not in out
