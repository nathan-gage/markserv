from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from markserv.app import build_config, create_app


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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

        ignored_response = client.get("/docs/.venv/ignored.md")
        assert ignored_response.status_code == 404
