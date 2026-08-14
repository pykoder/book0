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
    DUNE_DETAILS,
    GOOD_OMENS_DETAILS,
)


def test_run_prints_table_for_a_known_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["--server", "unused", "--tag", "fiction"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_prints_no_books_found_for_an_unknown_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(["--server", "unused", "--tag", "does-not-exist"], client=client)

    assert exit_code == 0
    assert capsys.readouterr().out == "No books found.\n"


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


def test_run_prints_no_authors_found_for_an_unknown_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["authors", "--server", "unused", "--tag", "does-not-exist"], client=client
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "No authors found.\n"


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


def test_run_prints_no_publishers_found_for_an_unknown_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    client = TestClient(create_app({"fiction": calibre_metadata_db}))

    exit_code = run(
        ["publishers", "--server", "unused", "--tag", "does-not-exist"],
        client=client,
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "No publishers found.\n"


def test_run_help_mentions_the_publishers_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "publishers" in capsys.readouterr().out


def test_run_prints_book_details_in_the_requested_id_order(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
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
        == render_book_details_table([GOOD_OMENS_DETAILS, DUNE_DETAILS]) + "\n"
    )


def test_run_reports_missing_ids_for_book_details(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
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
        captured == render_book_details_table([DUNE_DETAILS]) + "\nMissing ids: 999\n"
    )


def test_run_reports_all_ids_missing_for_an_unconfigured_tag(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
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

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert captured == "No book details found.\nMissing ids: 1, 2\n"


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
