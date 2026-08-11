from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from book0_api.main import create_app
from book0_cli_remote.main import run
from book0_presentation.tables import render_author_table, render_book_table
from tests.conftest import CALIBRE_LIBRARY_AUTHORS, CALIBRE_LIBRARY_BOOKS


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
