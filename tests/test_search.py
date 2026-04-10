from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from markserv.app import build_config, create_app


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_search_ui_assets_are_included_in_rendered_page(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n\nSearch me.\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        response = client.get("/docs/README.md")

    assert response.status_code == 200
    assert "/public/js/search.js" in response.text
    assert 'data-search-open=""' in response.text
    assert 'data-search-dialog=""' in response.text
    assert 'data-search-input=""' in response.text
    assert 'data-search-results=""' in response.text
    assert 'hx-trigger="input changed delay:100ms, search"' in response.text
    assert 'hx-sync="this:replace"' in response.text


def test_search_endpoint_matches_titles_labels_headings_body_and_hidden_pages(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(
        docs_root / "README.md",
        "---\ntitle: Overview\n---\n# Home\n\nSee the deployment checklist for release notes.\n",
    )
    write_text(
        docs_root / "guides" / "quickstart.md",
        "---\nnav_label: First Steps\n---\n# Quickstart guide\n\n## Deployment checklist\n\nRun the smoke tests before publishing.\n",
    )
    write_text(
        docs_root / "reference" / "hidden-page.md",
        "---\nhidden: true\n---\n# Secret launch notes\n\nInternal docs only.\n",
    )

    with TestClient(create_app(build_config(docs_root))) as client:
        title_response = client.get("/_search", params={"q": "overview"})
        label_response = client.get("/_search", params={"q": "first steps"})
        heading_response = client.get("/_search", params={"q": "deployment checklist"})
        hidden_response = client.get("/_search", params={"q": "secret launch"})
        empty_response = client.get("/_search", params={"q": "   "})

    assert title_response.status_code == 200
    title_results = title_response.json()["results"]
    assert title_results[0]["href"] == "/docs/README.md"
    assert title_results[0]["title"] == "Overview"

    assert label_response.status_code == 200
    label_results = label_response.json()["results"]
    assert label_results[0]["href"] == "/docs/guides/quickstart.md"
    assert label_results[0]["title"] == "First Steps"

    assert heading_response.status_code == 200
    heading_results = heading_response.json()["results"]
    assert heading_results[0]["href"] == "/docs/guides/quickstart.md"
    assert "Deployment checklist" in (heading_results[0]["snippet"] or "")

    assert hidden_response.status_code == 200
    hidden_results = hidden_response.json()["results"]
    assert hidden_results[0]["href"] == "/docs/reference/hidden-page.md"

    assert empty_response.status_code == 200
    assert empty_response.json() == {"results": []}
