from __future__ import annotations

from pathlib import Path

import pytest

import markserv.cli as cli


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

    def fake_run(
        app: object,
        *,
        host: str,
        port: int,
        log_level: str,
        access_log: bool,
        log_config: object,
    ) -> None:
        observed["app"] = app
        observed["host"] = host
        observed["port"] = port
        observed["log_level"] = log_level
        observed["access_log"] = access_log
        observed["log_config"] = log_config

    monkeypatch.setattr("markserv.cli.threading.Timer", ImmediateTimer)
    monkeypatch.setattr("markserv.cli.webbrowser.open", fake_open)
    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setattr("markserv.cli.uvicorn.run", fake_run)

    cli.main([str(markdown_file), "--host", "0.0.0.0", "--port", "9000"])

    assert observed["host"] == "0.0.0.0"
    assert observed["port"] == 9000
    assert observed["log_level"] == "warning"
    assert observed["access_log"] is False
    assert observed["log_config"] is None
    assert observed["opened_url"] == "http://0.0.0.0:9000"
    assert observed["timer_interval"] == 0.8


def test_cli_allows_disabling_browser_open(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    markdown_file = tmp_path / "README.md"
    markdown_file.write_text("# Home\n", encoding="utf-8")

    observed: dict[str, object] = {}

    def fail_timer(_interval: float, _function: object) -> object:
        raise AssertionError("Timer should not be created when --no-open is passed")

    def fake_create_app(config: object) -> object:
        observed["config"] = config
        return {"config": config}

    def fake_run(app: object, **kwargs: object) -> None:
        observed["app"] = app
        observed.update(kwargs)

    monkeypatch.setattr("markserv.cli.threading.Timer", fail_timer)
    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setattr("markserv.cli.webbrowser.open", lambda _url: True)
    monkeypatch.setattr("markserv.cli.uvicorn.run", fake_run)

    cli.main([str(markdown_file), "--no-open"])

    assert observed["host"] == "127.0.0.1"
    assert observed["port"] == 8000
