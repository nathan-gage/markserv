from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

import markserv.cli as cli


class FakeServer:
    def __init__(self) -> None:
        self.should_exit = False
        self.force_exit = False
        self.run_called = False

    def run(self) -> None:
        self.run_called = True


def test_help_uses_plain_formatter(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["--help"])
    captured = capsys.readouterr()
    assert "Usage: markserv [OPTIONS] [ARGS]" in captured.out
    assert "Arguments:" in captured.out
    assert "Parameters:" in captured.out
    assert "--open, --no-open" in captured.out
    assert "╭" not in captured.out


def test_cli_parses_options_and_invokes_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    markdown_file = tmp_path / "README.md"
    markdown_file.write_text("# Home\n", encoding="utf-8")

    observed: dict[str, object] = {}
    fake_server = FakeServer()

    class ImmediateTimer:
        def __init__(self, interval: float, function: object) -> None:
            observed["timer_interval"] = interval
            observed["timer_function"] = function

        def start(self) -> None:
            timer_function = observed["timer_function"]
            assert callable(timer_function)
            timer_function()

    def fake_open(url: str) -> bool:
        observed["opened_url"] = url
        return True

    def fake_create_app(config: object) -> object:
        observed["config"] = config
        return {"config": config}

    def fake_create_server(app: object, *, host: str, port: int) -> FakeServer:
        observed["app"] = app
        observed["host"] = host
        observed["port"] = port
        return fake_server

    def fake_run_server(server: object) -> None:
        observed["server"] = server

    monkeypatch.setattr("markserv.cli.threading.Timer", ImmediateTimer)
    monkeypatch.setattr("markserv.cli.webbrowser.open", fake_open)
    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setattr(cli, "create_server", fake_create_server)
    monkeypatch.setattr(cli, "run_server", fake_run_server)

    cli.main([str(markdown_file), "--host", "0.0.0.0", "--port", "9000"])

    assert observed["host"] == "0.0.0.0"
    assert observed["port"] == 9000
    assert observed["server"] is fake_server
    assert observed["opened_url"] == "http://localhost:9000"
    assert observed["timer_interval"] == 0.8


def test_cli_allows_disabling_browser_open(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    markdown_file = tmp_path / "README.md"
    markdown_file.write_text("# Home\n", encoding="utf-8")

    observed: dict[str, object] = {}
    fake_server = FakeServer()

    def fail_timer(_interval: float, _function: object) -> object:
        raise AssertionError("Timer should not be created when --no-open is passed")

    def fake_create_app(config: object) -> object:
        observed["config"] = config
        return {"config": config}

    def fake_create_server(app: object, *, host: str, port: int) -> FakeServer:
        observed["app"] = app
        observed["host"] = host
        observed["port"] = port
        return fake_server

    def fake_run_server(server: object) -> None:
        observed["server"] = server

    monkeypatch.setattr("markserv.cli.threading.Timer", fail_timer)
    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setattr(cli, "create_server", fake_create_server)
    monkeypatch.setattr(cli, "run_server", fake_run_server)

    cli.main([str(markdown_file), "--no-open"])

    assert observed["server"] is fake_server
    assert observed["host"] == cli.DEFAULT_HOST
    assert observed["port"] == cli.DEFAULT_PORT


def test_cli_uses_uvicorn_reload_when_env_var_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    markdown_file = tmp_path / "README.md"
    markdown_file.write_text("# Home\n", encoding="utf-8")

    observed: dict[str, object] = {}

    class ImmediateTimer:
        def __init__(self, interval: float, function: object) -> None:
            observed["timer_interval"] = interval
            observed["timer_function"] = function

        def start(self) -> None:
            timer_function = observed["timer_function"]
            assert callable(timer_function)
            timer_function()

    def fake_open(url: str) -> bool:
        observed["opened_url"] = url
        return True

    def fake_run_python_reloading_server(app_factory: str, *, host: str, port: int) -> None:
        observed["app_factory"] = app_factory
        observed["kwargs"] = {
            "factory": True,
            "host": host,
            "port": port,
            "reload": True,
            "reload_dirs": [str(cli.PYTHON_RELOAD_DIR)],
            "log_level": "warning",
            "access_log": False,
            "log_config": None,
            "timeout_graceful_shutdown": cli.SHUTDOWN_GRACE_SECONDS,
        }
        observed["target_env"] = os.environ.get(cli.TARGET_ENV_VAR)

    def fail_create_app(_site: object) -> object:
        raise AssertionError("create_app should not be called when Python reload is enabled")

    monkeypatch.setenv(cli.PYTHON_RELOAD_ENV_VAR, "1")
    monkeypatch.setattr("markserv.cli.threading.Timer", ImmediateTimer)
    monkeypatch.setattr("markserv.cli.webbrowser.open", fake_open)
    monkeypatch.setattr(cli, "create_app", fail_create_app)
    monkeypatch.setattr(cli, "run_python_reloading_server", fake_run_python_reloading_server)

    cli.main([str(markdown_file), "--host", "0.0.0.0", "--port", "9000"])

    assert observed["app_factory"] == "markserv.cli:create_app_from_env"
    assert observed["target_env"] == str(markdown_file.resolve())
    assert observed["opened_url"] == "http://localhost:9000"
    assert observed["timer_interval"] == 0.8
    assert observed["kwargs"] == {
        "factory": True,
        "host": "0.0.0.0",
        "port": 9000,
        "reload": True,
        "reload_dirs": [str(cli.PYTHON_RELOAD_DIR)],
        "log_level": "warning",
        "access_log": False,
        "log_config": None,
        "timeout_graceful_shutdown": cli.SHUTDOWN_GRACE_SECONDS,
    }
    assert cli.TARGET_ENV_VAR not in os.environ


def test_request_server_shutdown_marks_server_and_event() -> None:
    server = FakeServer()
    stop_event = threading.Event()

    cli._request_server_shutdown(server, stop_event)

    assert server.should_exit is True
    assert server.force_exit is False
    assert stop_event.is_set()
