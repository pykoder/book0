import argparse
import os
import sys

import uvicorn

CONFIG_ENV_VAR = "BOOK0_API_CONFIG"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book0-api")
    parser.add_argument(
        "--config", required=True, help="path to the libraries TOML config file"
    )
    parser.add_argument(
        "--reload", action="store_true", help="enable uvicorn's auto-reload"
    )
    parser.add_argument(
        "--host", default=None, help="address to listen on (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=None, help="port to listen on (default: 8000)"
    )
    parser.add_argument(
        "--uds",
        default=None,
        help="Unix domain socket path to listen on, instead of --host/--port",
    )
    return parser


def run(argv: list[str] | None = None) -> None:
    raw_argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    os.environ[CONFIG_ENV_VAR] = args.config

    if args.uds is not None:
        if args.host is not None or args.port is not None:
            parser.error("--uds cannot be combined with --host/--port")
        uvicorn.run("book0_api.asgi:app", uds=args.uds, reload=args.reload)
    else:
        uvicorn.run(
            "book0_api.asgi:app",
            host=args.host if args.host is not None else "127.0.0.1",
            port=args.port if args.port is not None else 8000,
            reload=args.reload,
        )


def main() -> None:
    run()
