import argparse
import os
import sys
import urllib.parse

import uvicorn

CONFIG_ENV_VAR = "BOOK0_API_CONFIG"
_DEFAULT_LISTEN = "http://127.0.0.1:8000"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0-api")
    parser.add_argument(
        "--config", required=True, help="path to the libraries TOML config file"
    )
    parser.add_argument(
        "--reload", action="store_true", help="enable uvicorn's auto-reload"
    )
    parser.add_argument(
        "--listen",
        default=None,
        help=(
            "URL to listen on: http://host:port or unix:///path/to/socket "
            f"(default: {_DEFAULT_LISTEN})"
        ),
    )
    return parser


def _listen_kwargs(
    listen: str, parser: argparse.ArgumentParser
) -> dict[str, str | int]:
    parsed = urllib.parse.urlsplit(listen)
    if parsed.scheme == "unix":
        return {"uds": parsed.path}
    if parsed.scheme == "http":
        return {"host": parsed.hostname or "127.0.0.1", "port": parsed.port or 8000}
    parser.error(
        f"Unsupported --listen scheme: {parsed.scheme!r} (expected http or unix)"
    )
    raise AssertionError("unreachable")  # parser.error always exits


def run(argv: list[str] | None = None) -> None:
    raw_argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    os.environ[CONFIG_ENV_VAR] = args.config

    listen = args.listen if args.listen is not None else _DEFAULT_LISTEN

    uvicorn.run(
        "book0_api.asgi:app",
        reload=args.reload,
        **_listen_kwargs(listen, parser),  # type: ignore[arg-type]
    )


def main() -> None:
    run()
