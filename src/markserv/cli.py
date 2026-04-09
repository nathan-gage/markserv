from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .app import build_config, create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="markserv",
        description="Render a folder of GitHub-flavored markdown with live reload.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Markdown file or directory to serve (default: current directory).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000).")
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the app in your default browser after the server starts.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = build_config(Path(args.path))
    except ValueError as exc:
        parser.error(str(exc))
        return

    url = f"http://{args.host}:{args.port}"
    print(f"markserv: serving {config.source} from {config.root_dir}")
    print(f"markserv: {url}")

    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(config), host=args.host, port=args.port, log_level="info")
