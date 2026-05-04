from __future__ import annotations

import contextlib
import logging
import os
import select
import socket
import sys
import threading
import webbrowser
from collections.abc import Awaitable, Callable, Iterator, Mapping
from pathlib import Path
from typing import Annotated, Protocol

import uvicorn
from cyclopts import App, Parameter
from cyclopts.help import PlainFormatter
from cyclopts.token import Token
from fastapi import FastAPI
from rich.console import Console
from rich.logging import RichHandler
from uvicorn import Config, Server

from .app import MarkservApplication, create_app, create_markserv_application
from .content import ServeConfig, SiteSource, build_config, build_file_site
from .settings import PYTHON_RELOAD_ENV_VAR as _PYTHON_RELOAD_ENV_VAR
from .settings import TARGET_ENV_VAR as _TARGET_ENV_VAR
from .settings import python_reload_enabled, target_from_env


class StoppableServer(Protocol):
    should_exit: bool
    force_exit: bool

    def run(self) -> None: ...


ShutdownHook = Callable[[], Awaitable[None]]

console = Console(stderr=True)
QUIT_KEYS = {"q", "Q", "\x1b"}
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 4422
PYTHON_RELOAD_ENV_VAR = _PYTHON_RELOAD_ENV_VAR
TARGET_ENV_VAR = _TARGET_ENV_VAR
PYTHON_RELOAD_DIR = Path(__file__).resolve().parent
SHUTDOWN_GRACE_SECONDS = 1

app = App(
    name="markserv",
    help="Render a folder of GitHub-flavored markdown with live reload.",
    help_formatter=PlainFormatter(),
    result_action="return_value",
)


class MarkservServer(Server):
    def __init__(
        self,
        config: Config,
        *,
        before_shutdown: ShutdownHook,
    ) -> None:
        super().__init__(config)
        self._before_shutdown = before_shutdown

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        await self._before_shutdown()
        await super().shutdown(sockets)


def _validate_target(_type_: object, tokens: tuple[Token, ...]) -> Path:
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


@contextlib.contextmanager
def temporary_env(updates: Mapping[str, str]) -> Iterator[None]:
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
    reload_hint = f"Python reload enabled via {PYTHON_RELOAD_ENV_VAR}." if python_reload else None
    display_url = url.removeprefix("http://")

    console.print(f"[bold cyan]markserv[/] serving {source}")
    console.print(f"[cyan]root[/] {root_dir}")
    console.print(f"[cyan]url[/] [link={url}][underline]{display_url}[/underline][/link]")
    console.print(f"[dim]{browser_hint}[/]")
    if reload_hint is not None:
        console.print(f"[dim]{reload_hint}[/]")
    console.print(f"[dim]{quit_hint}[/]")


def create_server(
    application: FastAPI,
    *,
    host: str,
    port: int,
    before_shutdown: ShutdownHook,
) -> Server:
    return MarkservServer(
        Config(
            application,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None,
            timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS,
        ),
        before_shutdown=before_shutdown,
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
        timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS,
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
    application: FastAPI | None,
    *,
    source: str,
    root_dir: str,
    host: str,
    port: int,
    open_browser: bool,
    app_factory_import: str | None = None,
    env_updates: Mapping[str, str] | None = None,
    before_shutdown: ShutdownHook | None = None,
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
    if before_shutdown is None:
        raise ValueError("before_shutdown is required when Python reload is disabled")

    server = create_server(application, host=host, port=port, before_shutdown=before_shutdown)
    run_server(server)


def _application_for_serving(config_or_site: ServeConfig | SiteSource) -> MarkservApplication | None:
    return None if python_reload_enabled() else create_markserv_application(config_or_site)


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
    markserv_application = _application_for_serving(site)
    serve_application(
        None if markserv_application is None else markserv_application.app,
        source=str(config.source),
        root_dir=str(config.root_dir),
        host=host,
        port=port,
        open_browser=open_browser,
        app_factory_import="markserv.cli:create_app_from_env",
        env_updates={TARGET_ENV_VAR: str(config.source)},
        before_shutdown=None if markserv_application is None else markserv_application.runtime.shutdown,
    )


def create_app_from_env() -> FastAPI:
    target = target_from_env()
    if target is None:
        raise RuntimeError(f"{TARGET_ENV_VAR} must be set when Python reload is enabled")
    config = build_config(target)
    return create_app(build_file_site(config))


def main(argv: list[str] | None = None) -> None:
    app(tokens=argv)
