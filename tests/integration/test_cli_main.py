import shutil
import sqlite3
from pathlib import Path

import pytest

from book0_cli.main import run
from book0_presentation.tables import (
    render_author_table,
    render_book_table,
    render_publisher_table,
)
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
)


def _write_config(config_path: Path, tag: str, library_path: Path) -> None:
    config_path.write_text(f'[libraries]\n{tag} = "{library_path}"\n')


def test_run_prints_table_using_default_library_path_when_tag_is_omitted(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    default_library_dir = home / "Calibre Library"
    default_library_dir.mkdir(parents=True)
    shutil.copy(calibre_metadata_db, default_library_dir / "metadata.db")
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run([])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_missing_library_at_default_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_prints_table_when_tag_resolves_via_local_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["--tag", "fiction"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_prints_table_when_tag_resolves_to_the_library_directory(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db.parent)

    exit_code = run(["--tag", "fiction"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_prints_table_when_tag_resolves_via_xdg_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    config_path = home / ".config" / "book0" / "config.toml"
    config_path.parent.mkdir(parents=True)
    _write_config(config_path, "fiction", calibre_metadata_db)

    exit_code = run(["--tag", "fiction"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_reports_missing_config_file_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_unknown_tag_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", tmp_path / "fiction.db")

    exit_code = run(["--tag", "work"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_empty_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

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
    _write_config(tmp_path / ".book0.toml", "empty", db_path)

    exit_code = run(["--tag", "empty"])

    assert exit_code == 0
    assert capsys.readouterr().out == "No books found.\n"


def test_run_reports_malformed_config_file_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    config_path = tmp_path / ".book0.toml"
    config_path.write_text("this is not valid toml [[[")

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_config_file_missing_libraries_table_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    config_path = tmp_path / ".book0.toml"
    config_path.write_text("[other]\nx = 1\n")

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_config_file_with_unset_env_var_placeholder_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("NOPE_UNSET_VAR_XYZ", raising=False)
    config_path = tmp_path / ".book0.toml"
    config_path.write_text(
        '[libraries]\nfiction = "${NOPE_UNSET_VAR_XYZ}/metadata.db"\n'
    )

    exit_code = run(["--tag", "fiction"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_reports_non_calibre_library_on_stderr_and_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    db_path = tmp_path / "not-calibre.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    _write_config(tmp_path / ".book0.toml", "bad", db_path)

    exit_code = run(["--tag", "bad"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() != ""


def test_run_prints_author_table_using_default_library_path_when_tag_is_omitted(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    default_library_dir = home / "Calibre Library"
    default_library_dir.mkdir(parents=True)
    shutil.copy(calibre_metadata_db, default_library_dir / "metadata.db")
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run(["authors"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out == render_author_table(CALIBRE_LIBRARY_AUTHORS) + "\n"
    )


def test_run_prints_author_table_when_tag_resolves_via_local_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["authors", "--tag", "fiction"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out == render_author_table(CALIBRE_LIBRARY_AUTHORS) + "\n"
    )


def test_run_reports_empty_library_for_authors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

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
    _write_config(tmp_path / ".book0.toml", "empty", db_path)

    exit_code = run(["authors", "--tag", "empty"])

    assert exit_code == 0
    assert capsys.readouterr().out == "No authors found.\n"


def test_run_lists_books_when_subcommand_is_explicit(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    default_library_dir = home / "Calibre Library"
    default_library_dir.mkdir(parents=True)
    shutil.copy(calibre_metadata_db, default_library_dir / "metadata.db")
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run(["books"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_book_table(CALIBRE_LIBRARY_BOOKS) + "\n"


def test_run_help_mentions_the_authors_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "authors" in capsys.readouterr().out


def test_run_prints_publisher_table_using_default_library_path_when_tag_is_omitted(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    home = tmp_path / "home"
    default_library_dir = home / "Calibre Library"
    default_library_dir.mkdir(parents=True)
    shutil.copy(calibre_metadata_db, default_library_dir / "metadata.db")
    monkeypatch.setattr(Path, "home", lambda: home)

    exit_code = run(["publishers"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_publisher_table(CALIBRE_LIBRARY_PUBLISHERS) + "\n"
    )


def test_run_prints_publisher_table_when_tag_resolves_via_local_config_file(
    calibre_metadata_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _write_config(tmp_path / ".book0.toml", "fiction", calibre_metadata_db)

    exit_code = run(["publishers", "--tag", "fiction"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == render_publisher_table(CALIBRE_LIBRARY_PUBLISHERS) + "\n"
    )


def test_run_reports_empty_library_for_publishers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, pubdate TEXT);
            CREATE TABLE publishers (id INTEGER PRIMARY KEY, name TEXT);
            """
        )
        connection.commit()
    finally:
        connection.close()
    _write_config(tmp_path / ".book0.toml", "empty", db_path)

    exit_code = run(["publishers", "--tag", "empty"])

    assert exit_code == 0
    assert capsys.readouterr().out == "No publishers found.\n"


def test_run_help_mentions_the_publishers_subcommand(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as exc_info:
        run(["--help"])

    assert exc_info.value.code == 0
    assert "publishers" in capsys.readouterr().out
