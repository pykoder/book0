import os
from pathlib import Path

import pytest

from book0_api.cli import run


def test_run_sets_config_env_var_from_config_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    monkeypatch.delenv("BOOK0_API_CONFIG", raising=False)
    monkeypatch.setattr("book0_api.cli.uvicorn.run", lambda *args, **kwargs: None)

    run(["--config", str(config_path)])

    assert os.environ["BOOK0_API_CONFIG"] == str(config_path)


def test_run_starts_uvicorn_on_the_asgi_app_without_reload_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(["--config", str(config_path)])

    assert calls == [
        (("book0_api.asgi:app",), {"host": "127.0.0.1", "port": 8000, "reload": False})
    ]


def test_run_enables_reload_when_reload_flag_is_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(["--config", str(config_path), "--reload"])

    assert calls == [
        (("book0_api.asgi:app",), {"host": "127.0.0.1", "port": 8000, "reload": True})
    ]


def test_run_passes_through_custom_host_and_port_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(["--config", str(config_path), "--host", "0.0.0.0", "--port", "9000"])

    assert calls == [
        (("book0_api.asgi:app",), {"host": "0.0.0.0", "port": 9000, "reload": False})
    ]


def test_run_exits_with_status_2_when_config_flag_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("book0_api.cli.uvicorn.run", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        run([])

    assert exc_info.value.code == 2


def test_run_passes_uds_path_to_uvicorn_when_uds_flag_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "book0-libraries.toml"
    socket_path = tmp_path / "book0-api.sock"
    calls = []
    monkeypatch.setattr(
        "book0_api.cli.uvicorn.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    run(["--config", str(config_path), "--uds", str(socket_path)])

    assert calls == [
        (("book0_api.asgi:app",), {"uds": str(socket_path), "reload": False})
    ]


def test_run_exits_with_status_2_when_uds_and_host_are_both_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    config_path = tmp_path / "book0-libraries.toml"
    monkeypatch.setattr("book0_api.cli.uvicorn.run", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        run(
            [
                "--config",
                str(config_path),
                "--uds",
                str(tmp_path / "book0-api.sock"),
                "--host",
                "0.0.0.0",
            ]
        )

    assert exc_info.value.code == 2
    assert "--uds cannot be combined with --host/--port" in capsys.readouterr().err


def test_run_exits_with_status_2_when_uds_and_port_are_both_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    config_path = tmp_path / "book0-libraries.toml"
    monkeypatch.setattr("book0_api.cli.uvicorn.run", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        run(
            [
                "--config",
                str(config_path),
                "--uds",
                str(tmp_path / "book0-api.sock"),
                "--port",
                "9000",
            ]
        )

    assert exc_info.value.code == 2
    assert "--uds cannot be combined with --host/--port" in capsys.readouterr().err
