from __future__ import annotations

import contextlib
import logging
import os
import select
import sys
import threading
import webbrowser
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Protocol

import uvicorn
from cyclopts import App, Parameter
from cyclopts.help import PlainFormatter
from cyclopts.token import Token
from rich.console import Console
from rich.logging import RichHandler
from uvicorn import Config, Server

from .app import create_app
from .site import build_config, build_file_site


class StoppableServer(Protocol):
    should_exit: bool

    def run(self) -> None: ...


console = Console(stderr=True)
QUIT_KEYS = {"q", "Q", "\x1b"}
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 4422
PYTHON_RELOAD_ENV_VAR = "MARKSERV_PYTHON_RELOAD"
TARGET_ENV_VAR = "MARKSERV_TARGET"
PYTHON_RELOAD_DIR = Path(__file__).resolve().parent

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
                console=console,
            )
        ],
        force=True,
    )


def browser_url(host: str, port: int) -> str:
    public_host = "localhost" if host in {"127.0.0.1", "0.0.0.0", "localhost"} else host
    return f"http://{public_host}:{port}"


def python_reload_enabled() -> bool:
    value = os.environ.get(PYTHON_RELOAD_ENV_VAR, "")
    return value.lower() in {"1", "true", "yes", "on"}


@contextlib.contextmanager
def temporary_env(updates: Mapping[str, str]) -> Any:
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def print_startup_banner(*, source: str, root_dir: str, url: str, open_browser: bool, python_reload: bool) -> None:
    quit_hint = (
        "Press Ctrl+C to quit."
        if python_reload
        else "Press Q or Esc to quit."
        if _supports_quit_prompt()
        else "Press Ctrl+C to quit."
    )
    browser_hint = "Browser opens automatically." if open_browser else "Browser auto-open disabled."
    reload_hint = "Python reload enabled via MARKSERV_PYTHON_RELOAD." if python_reload else None
    display_url = url.removeprefix("http://")

    console.print(f"[bold cyan]markserv[/] serving {source}")
    console.print(f"[cyan]root[/] {root_dir}")
    console.print(f"[cyan]url[/] [link={url}][underline]{display_url}[/underline][/link]")
    console.print(f"[dim]{browser_hint}[/]")
    if reload_hint is not None:
        console.print(f"[dim]{reload_hint}[/]")
    console.print(f"[dim]{quit_hint}[/]")


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


def run_python_reloading_server(app_factory_import: str, *, host: str, port: int) -> None:
    uvicorn.run(
        app_factory_import,
        factory=True,
        host=host,
        port=port,
        reload=True,
        reload_dirs=[str(PYTHON_RELOAD_DIR)],
        log_level="warning",
        access_log=False,
        log_config=None,
    )


def _supports_quit_prompt() -> bool:
    return sys.stdin.isatty() and os.name != "nt"


def _request_server_shutdown(server: StoppableServer, stop_event: threading.Event) -> None:
    if stop_event.is_set():
        return
    console.print("[dim]Stopping server...[/dim]")
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


def serve_application(
    application: Any | None,
    *,
    source: str,
    root_dir: str,
    host: str,
    port: int,
    open_browser: bool,
    app_factory_import: str | None = None,
    env_updates: Mapping[str, str] | None = None,
) -> None:
    configure_logging()
    url = browser_url(host, port)
    python_reload = python_reload_enabled()
    print_startup_banner(
        source=source,
        root_dir=root_dir,
        url=url,
        open_browser=open_browser,
        python_reload=python_reload,
    )

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    if python_reload:
        if app_factory_import is None:
            raise ValueError("app_factory_import is required when Python reload is enabled")
        with temporary_env(dict(env_updates or {})):
            run_python_reloading_server(app_factory_import, host=host, port=port)
        return

    if application is None:
        raise ValueError("application is required when Python reload is disabled")

    server = create_server(application, host=host, port=port)
    run_server(server)


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
    host: Annotated[str, Parameter(help="Host interface to bind.")] = DEFAULT_HOST,
    port: Annotated[int, Parameter(help="Port to listen on.")] = DEFAULT_PORT,
    open_browser: Annotated[
        bool,
        Parameter(name="--open", help="Open the app in your default browser after the server starts."),
    ] = True,
) -> None:
    """Serve GitHub-flavored markdown from a file or directory."""
    config = build_config(path)
    site = build_file_site(config)
    serve_application(
        None if python_reload_enabled() else create_app(site),
        source=str(config.source),
        root_dir=str(config.root_dir),
        host=host,
        port=port,
        open_browser=open_browser,
        app_factory_import="markserv.cli:create_app_from_env",
        env_updates={TARGET_ENV_VAR: str(config.source)},
    )


def create_app_from_env() -> Any:
    target = os.environ.get(TARGET_ENV_VAR)
    if not target:
        raise RuntimeError(f"{TARGET_ENV_VAR} must be set when Python reload is enabled")
    config = build_config(Path(target))
    return create_app(build_file_site(config))


def main(argv: list[str] | None = None) -> None:
    app(tokens=argv)
