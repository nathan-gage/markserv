from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from markserv.app import WatchPathFilter, build_config, create_app
from markserv.web import is_dev_reload_asset


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_watch_filter_only_accepts_markdown_and_gitignore(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / ".gitignore", ".venv/\n")
    write_text(docs_root / "README.md", "# Home\n")
    write_text(docs_root / "notes.markdown", "# Notes\n")
    write_text(docs_root / "app.py", "print('hi')\n")
    write_text(docs_root / ".venv" / "ignored.md", "# Hidden\n")

    path_filter = WatchPathFilter(docs_root)

    assert path_filter(None, str(docs_root / "README.md")) is True
    assert path_filter(None, str(docs_root / "notes.markdown")) is True
    assert path_filter(None, str(docs_root / ".gitignore")) is True
    assert path_filter(None, str(docs_root / "app.py")) is False
    assert path_filter(None, str(docs_root / ".venv" / "ignored.md")) is False


def test_dev_reload_asset_filter_matches_css_and_js_only() -> None:
    assert is_dev_reload_asset("src/markserv/public/css/app.css") is True
    assert is_dev_reload_asset("src/markserv/public/js/theme.js") is True
    assert is_dev_reload_asset("src/markserv/public/licenses/htmx.LICENSE") is False
    assert is_dev_reload_asset("src/markserv/rendering.py") is False


def test_python_reload_mode_includes_dev_reload_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n")

    config = build_config(docs_root)
    monkeypatch.setenv("MARKSERV_PYTHON_RELOAD", "1")

    with TestClient(create_app(config)) as client:
        page_response = client.get("/docs/README.md")
        assert page_response.status_code == 200
        assert "/public/js/dev-reload.js" in page_response.text
        assert 'data-dev-reload="true"' in page_response.text


def test_directory_mode_redirects_to_readme_and_hides_gitignored_files(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / ".gitignore", ".venv/\n")
    write_text(docs_root / "README.md", "# Home\n\nSee [Guide](guide.md).\n")
    write_text(docs_root / "guide.md", "# Guide\n")
    write_text(docs_root / ".venv" / "ignored.md", "# Hidden\n")

    config = build_config(docs_root)

    with TestClient(create_app(config)) as client:
        root_response = client.get("/", follow_redirects=False)
        assert root_response.status_code == 307
        assert root_response.headers["location"] == "/docs/README.md"

        page_response = client.get("/docs/README.md")
        assert page_response.status_code == 200
        assert "Home · markserv" in page_response.text
        assert "/public/css/app.css" in page_response.text
        assert "/public/css/github-markdown-light.css" in page_response.text
        assert "/public/css/github-markdown-dark.css" in page_response.text
        assert 'id="github-markdown-light"' in page_response.text
        assert 'id="github-markdown-dark"' in page_response.text
        assert "/public/js/theme.js" in page_response.text
        assert 'data-theme-btn="system"' in page_response.text
        assert 'data-theme-btn="light"' in page_response.text
        assert 'data-theme-btn="dark"' in page_response.text
        assert "hit-area-1" in page_response.text
        assert "hit-area-2" in page_response.text
        assert "hit-area-x-2" in page_response.text
        assert "/public/vendor/htmx.min.js" in page_response.text
        assert 'hx-trigger="sse:reload"' in page_response.text
        assert "guide" in page_response.text

        fragment_response = client.get("/_live/docs/README.md", headers={"HX-Request": "true"})
        assert fragment_response.status_code == 200
        assert 'id="page-shell"' in fragment_response.text
        assert 'hx-swap-oob="true"' in fragment_response.text

        asset_response = client.get("/public/css/app.css")
        assert asset_response.status_code == 200
        assert asset_response.headers["content-type"].startswith("text/css")

        theme_asset_response = client.get("/public/js/theme.js")
        assert theme_asset_response.status_code == 200
        assert "markserv-theme" in theme_asset_response.text
        assert 'const SYSTEM_THEME = "system"' in theme_asset_response.text

        ignored_response = client.get("/docs/.venv/ignored.md")
        assert ignored_response.status_code == 404
