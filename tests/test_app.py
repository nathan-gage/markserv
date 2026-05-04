from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from markserv.app import WatchPathFilter, build_config, create_app
from markserv.runtime import ReloadBroker
from markserv.site import MarkdownPage, PageIndex
from markserv.web import event_stream_response, is_dev_reload_asset


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


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


def test_event_stream_stops_when_broker_closes() -> None:
    async def run() -> None:
        broker = ReloadBroker()
        response = event_stream_response(broker, retry_ms=1000)
        stream = cast(AsyncIterator[str], response.body_iterator.__aiter__())

        assert await anext(stream) == "retry: 1000\n\n"

        async def read_next_event() -> str:
            return await anext(stream)

        next_event = asyncio.create_task(read_next_event())

        await asyncio.sleep(0)
        await broker.close()

        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(next_event, timeout=1)

    asyncio.run(run())


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


class CountingSite:
    name: str = "docs"
    root_label: str = "/virtual/docs"
    default_doc: str | None = None
    show_navigation: bool = True
    watch_root: Path | None = None
    watch_filter: WatchPathFilter | None = None

    def __init__(self) -> None:
        self.page_index_calls = 0
        self.read_markdown_calls = 0
        self._page_index = PageIndex((MarkdownPage(rel_path="README.md", label="Home"),))

    def page_index(self) -> PageIndex:
        self.page_index_calls += 1
        return self._page_index

    def read_markdown(self, rel_path: str) -> str | None:
        self.read_markdown_calls += 1
        return "# Home\n" if rel_path == "README.md" else None

    def resolve_asset(self, rel_path: str) -> Path | None:
        return None

    def is_directory(self, rel_path: str) -> bool:
        return False


def test_page_index_is_cached_across_requests() -> None:
    site = CountingSite()

    with TestClient(create_app(site)) as client:
        root_response = client.get("/", follow_redirects=False)
        assert root_response.status_code == 307
        assert root_response.headers["location"] == "/docs/README.md"

        page_response = client.get("/docs/README.md")
        assert page_response.status_code == 200

        fragment_response = client.get("/docs/README.md", headers={"HX-Request": "true"})
        assert fragment_response.status_code == 200

    assert site.page_index_calls == 1


def test_docs_view_is_cached_across_requests() -> None:
    site = CountingSite()

    with TestClient(create_app(site)) as client:
        first_response = client.get("/docs/README.md")
        second_response = client.get("/docs/README.md")
        fragment_response = client.get("/docs/README.md", headers={"HX-Request": "true"})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert fragment_response.status_code == 200
    assert site.read_markdown_calls == 1


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
        assert "/public/css/pygments-light.css" in page_response.text
        assert "/public/css/pygments-dark.css" in page_response.text
        assert 'id="github-markdown-light"' in page_response.text
        assert 'id="github-markdown-dark"' in page_response.text
        assert 'id="pygments-light"' in page_response.text
        assert 'id="pygments-dark"' in page_response.text
        assert "/public/js/theme.js" in page_response.text
        assert "/public/js/live-reload.js" in page_response.text
        assert "/public/js/mermaid.js" in page_response.text
        assert 'data-theme-btn="system"' in page_response.text
        assert 'data-theme-btn="light"' in page_response.text
        assert 'data-theme-btn="dark"' in page_response.text
        assert 'class="floating-theme-picker"' in page_response.text
        assert 'class="sidebar-icon-close"' in page_response.text
        assert 'class="sidebar-icon-open"' in page_response.text
        assert 'class="sidebar"' in page_response.text
        assert 'class-="sidebar"' not in page_response.text
        assert "hit-area-1" in page_response.text
        assert "/public/js/sidebar.js" in page_response.text
        assert "/public/vendor/htmx.min.js" in page_response.text
        assert 'name="htmx-config"' in page_response.text
        assert "historyRestoreAsHxRequest" in page_response.text
        assert 'hx-history-elt=""' in page_response.text
        assert 'sse-connect="/_events"' not in page_response.text
        assert 'hx-get="/docs/guide.md"' in page_response.text
        assert 'hx-push-url="/docs/guide.md"' in page_response.text
        assert 'href="/docs/guide.md"' in page_response.text
        assert "guide" in page_response.text

        fragment_response = client.get("/docs/README.md", headers={"HX-Request": "true"})
        assert fragment_response.status_code == 200
        assert 'id="main-shell"' in fragment_response.text
        assert 'id="sidebar-shell"' in fragment_response.text
        assert 'class="sidebar"' in fragment_response.text
        assert 'hx-swap-oob="true"' in fragment_response.text
        assert 'id="favicon"' in fragment_response.text
        assert 'hx-swap-oob="outerHTML"' in fragment_response.text

        asset_response = client.get("/public/css/app.css")
        assert asset_response.status_code == 200
        assert asset_response.headers["content-type"].startswith("text/css")
        assert asset_response.headers["x-content-type-options"] == "nosniff"

        theme_asset_response = client.get("/public/js/theme.js")
        assert theme_asset_response.status_code == 200
        assert "markserv-theme" in theme_asset_response.text
        assert 'const SYSTEM_THEME = "system"' in theme_asset_response.text

        mermaid_asset_response = client.get("/public/js/mermaid.js")
        assert mermaid_asset_response.status_code == 200
        assert "mermaid.run" in mermaid_asset_response.text
        assert "/public/vendor/mermaid.esm.min.mjs" in mermaid_asset_response.text
        assert "cdn.jsdelivr.net" not in mermaid_asset_response.text

        mermaid_vendor_response = client.get("/public/vendor/mermaid.esm.min.mjs")
        assert mermaid_vendor_response.status_code == 200
        assert "./chunks/mermaid.esm.min/" in mermaid_vendor_response.text

        ignored_response = client.get("/docs/.venv/ignored.md")
        assert ignored_response.status_code == 404


def test_htmx_redirects_use_hx_location_for_shell_swaps(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n")
    write_text(docs_root / "guides" / "README.md", "# Guides\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        root_fragment = client.get("/", headers={"HX-Request": "true"})
        section_fragment = client.get("/docs/guides", headers={"HX-Request": "true"})

    assert root_fragment.status_code == 204
    root_location = json.loads(root_fragment.headers["HX-Location"])
    assert root_location == {
        "path": "/docs/README.md",
        "target": "#main-shell",
        "swap": "outerHTML",
        "select": "#main-shell",
    }

    assert section_fragment.status_code == 204
    section_location = json.loads(section_fragment.headers["HX-Location"])
    assert section_location == {
        "path": "/docs/guides/README.md",
        "target": "#main-shell",
        "swap": "outerHTML",
        "select": "#main-shell",
    }


def test_markdown_doc_links_are_htmx_enhanced_without_touching_assets(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(
        docs_root / "README.md",
        "# Home\n\nSee [Guide](guide.md), [Deep guide](guide.md#details), and [Diagram](diagram.png).\n",
    )
    write_text(docs_root / "guide.md", "# Guide\n\n## Details\n")
    write_bytes(docs_root / "diagram.png", b"not-a-real-png")

    with TestClient(create_app(build_config(docs_root))) as client:
        response = client.get("/docs/README.md")

    assert response.status_code == 200
    assert (
        '<a href="/docs/guide.md" hx-get="/docs/guide.md" hx-target="#main-shell" hx-select="#main-shell" hx-swap="outerHTML" hx-push-url="/docs/guide.md" hx-include="#sidebar-state">Guide</a>'
        in response.text
    )
    assert (
        '<a href="/docs/guide.md#details" hx-get="/docs/guide.md" hx-target="#main-shell" hx-select="#main-shell" hx-swap="outerHTML" hx-push-url="/docs/guide.md#details" hx-include="#sidebar-state">Deep guide</a>'
        in response.text
    )
    assert '<a href="diagram.png">Diagram</a>' in response.text


def test_mermaid_fences_render_as_client_diagram_blocks(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n\n```mermaid\ngraph TD\n  A --> B\n```\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        response = client.get("/docs/README.md")

    assert response.status_code == 200
    assert '<pre class="mermaid">graph TD\n  A --&gt; B\n</pre>' in response.text
    assert 'data-language="mermaid"' not in response.text


def test_front_matter_controls_title_navigation_and_hidden_pages(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(
        docs_root / "README.md",
        "---\ntitle: Overview\nnav_label: Project Home\nnav_order: 20\n---\n# Internal heading\n",
    )
    write_text(
        docs_root / "guide.md",
        "---\nnav_label: First Steps\nnav_order: 5\n---\n# Guide\n",
    )
    write_text(
        docs_root / "secret.md",
        "---\nnav_label: Secret Notes\nhidden: true\n---\n# Secret\n",
    )

    config = build_config(docs_root)

    with TestClient(create_app(config)) as client:
        response = client.get("/docs/README.md")
        assert response.status_code == 200
        assert "Overview · markserv" in response.text
        assert ">Project Home<" in response.text
        assert ">First Steps<" in response.text
        assert response.text.index(">First Steps<") < response.text.index(">Project Home<")
        assert "Secret Notes" not in response.text
        assert "title: Overview" not in response.text
        assert "nav_label: Project Home" not in response.text

        hidden_page_response = client.get("/docs/secret.md")
        assert hidden_page_response.status_code == 200
        assert "Secret · markserv" in hidden_page_response.text
        assert "Secret Notes" not in hidden_page_response.text


def test_asset_serving_allows_safe_files_and_blocks_sensitive_or_active_content(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n")
    write_bytes(docs_root / "diagram.png", b"not-a-real-png")
    write_text(docs_root / "notes.txt", "hello\n")
    write_text(docs_root / "logo.svg", '<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    write_text(docs_root / ".env", "TOKEN=secret\n")
    write_text(docs_root / "script.js", "alert('x')\n")
    write_text(docs_root / "page.html", "<script>alert(1)</script>\n")
    write_text(docs_root / "deploy.pem", "pem-data\n")

    config = build_config(docs_root)

    with TestClient(create_app(config)) as client:
        image_response = client.get("/docs/diagram.png")
        assert image_response.status_code == 200
        assert image_response.headers["content-type"].startswith("image/png")
        assert image_response.headers["x-content-type-options"] == "nosniff"

        text_response = client.get("/docs/notes.txt")
        assert text_response.status_code == 200
        assert text_response.headers["content-type"].startswith("text/plain")
        assert text_response.headers["x-content-type-options"] == "nosniff"

        svg_response = client.get("/docs/logo.svg")
        assert svg_response.status_code == 200
        assert svg_response.headers["content-security-policy"] == (
            "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
        )

        assert client.get("/docs/.env").status_code == 404
        assert client.get("/docs/script.js").status_code == 404
        assert client.get("/docs/page.html").status_code == 404
        assert client.get("/docs/deploy.pem").status_code == 404
