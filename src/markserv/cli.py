from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from cyclopts import App, Parameter
from cyclopts.help import PlainFormatter
from cyclopts.token import Token

from .app import build_config, create_app

app = App(
    name="markserv",
    help="Render a folder of GitHub-flavored markdown with live reload.",
    help_formatter=PlainFormatter(),
    result_action="return_value",
)


def _validate_target(_type_: Any, tokens: tuple[Token, ...]) -> Path:
    raw_path = Path(tokens[0].value)
    build_config(raw_path)
    return raw_path


@app.default
def serve(
    path: Annotated[
        Path,
        Parameter(
            converter=_validate_target,
            help="Markdown file or directory to serve.",
        ),
    ] = Path("."),
    /,
    *,
    host: Annotated[str, Parameter(help="Host interface to bind.")] = "127.0.0.1",
    port: Annotated[int, Parameter(help="Port to listen on.")] = 8000,
    open_browser: Annotated[
        bool,
        Parameter(name="--open", help="Open the app in your default browser after the server starts."),
    ] = False,
) -> None:
    """Serve GitHub-flavored markdown from a file or directory."""
    config = build_config(path)
    url = f"http://{host}:{port}"
    print(f"markserv: serving {config.source} from {config.root_dir}")
    print(f"markserv: {url}")

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(config), host=host, port=port, log_level="info")


def main(argv: list[str] | None = None) -> None:
    app(tokens=argv)
