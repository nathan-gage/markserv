from __future__ import annotations

import contextlib
import logging
import os
import select
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Annotated, Any, Protocol

from cyclopts import App, Parameter
from cyclopts.help import PlainFormatter
from cyclopts.token import Token
from rich.logging import RichHandler
from uvicorn import Config, Server

from .app import build_config, create_app


class StoppableServer(Protocol):
    should_exit: bool

    def run(self) -> None: ...


logger = logging.getLogger("markserv")
QUIT_KEYS = {"q", "Q", "\x1b"}
DEFAULT_PORT = 4422

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


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[
            RichHandler(
                show_time=False,
                show_level=False,
                show_path=False,
                markup=False,
                rich_tracebacks=True,
            )
        ],
        force=True,
    )


def create_server(app: Any, *, host: str, port: int) -> Server:
    return Server(
        Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None,
        )
    )


def _supports_quit_prompt() -> bool:
    return sys.stdin.isatty() and os.name != "nt"


def _request_server_shutdown(server: StoppableServer, stop_event: threading.Event) -> None:
    if stop_event.is_set():
        return
    logger.info("Stopping server...")
    server.should_exit = True
    stop_event.set()


def _listen_for_quit_keys(server: StoppableServer, stop_event: threading.Event) -> None:
    import termios
    import tty

    with contextlib.suppress(termios.error, ValueError, OSError):
        fd = sys.stdin.fileno()
        original_attrs = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not stop_event.is_set():
                readable, _writable, _errors = select.select([sys.stdin], [], [], 0.1)
                if not readable:
                    continue
                key = sys.stdin.read(1)
                if key in QUIT_KEYS:
                    _request_server_shutdown(server, stop_event)
                    return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)


def run_server(server: StoppableServer) -> None:
    stop_event = threading.Event()
    listener: threading.Thread | None = None

    if _supports_quit_prompt():
        logger.info("Press Q or Esc to quit.")
        listener = threading.Thread(
            target=_listen_for_quit_keys,
            args=(server, stop_event),
            daemon=True,
            name="markserv-quit-listener",
        )
        listener.start()

    try:
        server.run()
    finally:
        stop_event.set()
        if listener is not None:
            listener.join(timeout=0.2)


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
    port: Annotated[int, Parameter(help="Port to listen on.")] = DEFAULT_PORT,
    open_browser: Annotated[
        bool,
        Parameter(name="--open", help="Open the app in your default browser after the server starts."),
    ] = True,
) -> None:
    """Serve GitHub-flavored markdown from a file or directory."""
    configure_logging()
    config = build_config(path)
    url = f"http://{host}:{port}"
    logger.info("Serving %s from %s", config.source, config.root_dir)
    logger.info("Listening on %s", url)

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    server = create_server(create_app(config), host=host, port=port)
    run_server(server)


def main(argv: list[str] | None = None) -> None:
    app(tokens=argv)
