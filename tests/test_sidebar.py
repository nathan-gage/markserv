from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from markserv.app import build_config, create_app


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_sidebar_folder_toggles_use_htmx_partial_updates(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n\nSee the [Guide](guides/guide.md).\n")
    write_text(docs_root / "guides" / "guide.md", "# Guide\n")
    write_text(docs_root / "guides" / "nested" / "deep-dive.md", "# Deep Dive\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        response = client.get("/docs/README.md")

    assert response.status_code == 200
    assert 'id="sidebar-shell"' in response.text
    assert "/public/js/sidebar.js" in response.text
    assert 'hx-get="/docs/README.md?nav_state=1&amp;nav=guides"' in response.text
    assert 'hx-target="#sidebar-shell"' in response.text
    assert 'hx-select="#sidebar-shell"' in response.text


def test_sidebar_state_is_preserved_in_nav_and_markdown_links(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n\nSee the [Guide](guides/guide.md).\n")
    write_text(docs_root / "guides" / "guide.md", "# Guide\n")
    write_text(docs_root / "guides" / "nested" / "deep-dive.md", "# Deep Dive\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        response = client.get("/docs/README.md", params=[("nav", "guides")])

    assert response.status_code == 200
    assert 'class="nav-folder is-open"' in response.text
    assert '<input type="hidden" name="nav" value="guides"/>' in response.text
    assert 'href="/docs/guides/guide.md"' in response.text
    assert 'hx-get="/docs/guides/guide.md"' in response.text
    assert 'hx-include="#sidebar-state"' in response.text
    assert 'hx-get="/docs/README.md?nav_state=1&amp;nav=guides&amp;nav=guides/nested"' in response.text


def test_active_folder_can_be_collapsed_even_when_viewing_a_page_inside_it(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n")
    write_text(docs_root / "examples" / "README.md", "# Examples\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        open_response = client.get("/docs/examples/README.md", params=[("nav", "examples")])
        collapsed_response = client.get("/docs/examples/README.md", params=[("nav_state", "1"), ("nav", "")])

    assert open_response.status_code == 200
    assert 'hx-get="/docs/examples/README.md?nav_state=1&amp;nav="' in open_response.text

    assert collapsed_response.status_code == 200
    assert 'class="nav-folder is-open"' not in collapsed_response.text
    assert 'class="nav-folder-header is-active-branch is-highlighted"' in collapsed_response.text
    assert '<input type="hidden" name="nav_state" value="1"/>' in collapsed_response.text


def test_collapsing_parent_preserves_expanded_child_state(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n")
    write_text(docs_root / "examples" / "folder-a" / "file.md", "# A\n")
    write_text(docs_root / "examples" / "folder-b" / "file2.md", "# B\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        expanded = client.get(
            "/docs/README.md",
            params=[("nav_state", "1"), ("nav", "examples"), ("nav", "examples/folder-a")],
        )
        collapsed = client.get(
            "/docs/README.md",
            params=[("nav_state", "1"), ("nav", "examples/folder-a")],
        )
        restored = client.get(
            "/docs/README.md",
            params=[("nav_state", "1"), ("nav", "examples"), ("nav", "examples/folder-a")],
        )

    assert expanded.status_code == 200
    assert 'class="nav-folder is-open"' in expanded.text
    assert "folder a</span>" in expanded.text

    assert collapsed.status_code == 200
    assert 'hx-get="/docs/README.md?nav_state=1&amp;nav=examples&amp;nav=examples/folder-a"' in collapsed.text
    assert "folder a</span>" not in collapsed.text

    assert restored.status_code == 200
    assert 'class="nav-folder is-open"' in restored.text
    assert "folder a</span>" in restored.text
    assert "folder b</span>" in restored.text


def test_single_path_folder_chains_are_inlined_when_collapsed(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n")
    write_text(docs_root / "examples" / "part-a" / "subfolder" / "file.md", "# Deep File\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        collapsed_response = client.get("/docs/README.md", params=[("nav", "")])
        parent_open_response = client.get("/docs/README.md", params=[("nav", "examples")])

    assert collapsed_response.status_code == 200
    assert 'examples</span><span class="nav-folder-suffix"> / part a / subfolder</span>' in collapsed_response.text
    assert (
        'hx-get="/docs/README.md?nav_state=1&amp;nav=examples&amp;nav=examples/part-a&amp;nav=examples/part-a/subfolder"'
        in collapsed_response.text
    )

    assert parent_open_response.status_code == 200
    assert 'part a</span><span class="nav-folder-suffix"> / subfolder</span>' in parent_open_response.text


def test_single_path_folder_chains_remain_inlined_when_child_state_is_preserved(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n")
    write_text(docs_root / "examples" / "part-a" / "subfolder" / "file.md", "# Deep File\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        response = client.get(
            "/docs/README.md",
            params=[("nav_state", "1"), ("nav", "examples/part-a/subfolder")],
        )

    assert response.status_code == 200
    assert 'examples</span><span class="nav-folder-suffix"> / part a / subfolder</span>' in response.text
    assert (
        'hx-get="/docs/README.md?nav_state=1&amp;nav=examples&amp;nav=examples/part-a&amp;nav=examples/part-a/subfolder"'
        in response.text
    )


def test_search_results_preserve_sidebar_state_from_current_url(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    write_text(docs_root / "README.md", "# Home\n\nSee the guide.\n")
    write_text(docs_root / "guides" / "guide.md", "# Guide\n\nThe deployment guide lives here.\n")

    with TestClient(create_app(build_config(docs_root))) as client:
        response = client.get(
            "/_search",
            params={"q": "guide", "nav_state": "1", "nav": "guides"},
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert 'href="/docs/guides/guide.md"' in response.text
    assert 'hx-get="/docs/guides/guide.md"' in response.text
    assert 'hx-include="#sidebar-state"' in response.text
