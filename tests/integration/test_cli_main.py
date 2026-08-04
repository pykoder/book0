import sqlite3
from pathlib import Path

import pytest

from book0_presentation.tables import render_table
from book0_cli.main import run
from tests.conftest import CALIBRE_LIBRARY_BOOKS


def test_run_prints_table_when_library_path_is_the_metadata_db_file(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    exit_code = run(["--library", str(calibre_metadata_db)])

    assert exit_code == 0
    assert capsys.readouterr().out == render_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_prints_table_when_library_path_is_the_library_directory(
    calibre_metadata_db: Path, capsys: pytest.CaptureFixture[str]
):
    exit_code = run(["--library", str(calibre_metadata_db.parent)])

    assert exit_code == 0
    assert capsys.readouterr().out == render_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_empty_library(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, pubdate TEXT);
            CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY, book INTEGER, author INTEGER
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    exit_code = run(["--library", str(db_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == "No books found.\n"


def test_run_reports_missing_library_on_stderr_and_exits_with_status_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    missing_path = tmp_path / "does-not-exist.db"

    exit_code = run(["--library", str(missing_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_non_calibre_library_on_stderr_and_exits_with_status_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    exit_code = run(["--library", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""
