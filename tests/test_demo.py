from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import markserv.cli as cli
import markserv.demo as demo
from markserv.app import create_app


def test_demo_site_contains_nested_markdown() -> None:
    site = demo.build_demo_site()
    markdown_files = {page.rel_path for page in site.page_index().pages}

    assert "README.md" in markdown_files
    assert "guides/quickstart.md" in markdown_files
    assert "guides/features/gfm.md" in markdown_files
    assert "guides/nested/deep-dive.md" in markdown_files
    assert "reference/notes.md" in markdown_files


def test_demo_site_renders_without_filesystem_fixture() -> None:
    with TestClient(create_app(demo.build_demo_site())) as client:
        root_response = client.get("/", follow_redirects=False)
        assert root_response.status_code == 307
        assert root_response.headers["location"] == "/docs/README.md"

        page_response = client.get("/docs/guides/features/gfm.md")
        assert page_response.status_code == 200
        assert "GitHub-flavored markdown examples · markserv" in page_response.text
        assert 'data-theme-btn="system"' in page_response.text


def test_demo_uses_uvicorn_reload_when_env_var_set(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

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
        }

    def fail_create_app(_site: object) -> object:
        raise AssertionError("create_app should not be called when Python reload is enabled")

    monkeypatch.setenv(cli.PYTHON_RELOAD_ENV_VAR, "1")
    monkeypatch.setattr(demo, "create_app", fail_create_app)
    monkeypatch.setattr(cli, "run_python_reloading_server", fake_run_python_reloading_server)

    demo.main(["--no-open", "--port", "9001"])

    assert observed["app_factory"] == "markserv.demo:create_demo_app"
    assert observed["kwargs"] == {
        "factory": True,
        "host": demo.DEFAULT_HOST,
        "port": 9001,
        "reload": True,
        "reload_dirs": [str(cli.PYTHON_RELOAD_DIR)],
        "log_level": "warning",
        "access_log": False,
        "log_config": None,
    }


def test_demo_main_invokes_demo_server(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_serve_demo(*, host: str, port: int, open_browser: bool) -> None:
        observed["host"] = host
        observed["port"] = port
        observed["open_browser"] = open_browser

    monkeypatch.setattr(demo, "serve_demo", fake_serve_demo)

    demo.main(["--no-open", "--port", "9001"])

    assert observed == {
        "host": demo.DEFAULT_HOST,
        "port": 9001,
        "open_browser": False,
    }
