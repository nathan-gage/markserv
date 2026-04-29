from __future__ import annotations

from markserv.markdown import MarkdownFrontMatter, parse_markdown_document, render_markdown


def test_parse_markdown_document_extracts_supported_front_matter() -> None:
    document = parse_markdown_document(
        "---\ntitle: Project Overview\nnav_label: Start Here\nnav_order: 5\nhidden: true\n---\n# Hello\n"
    )

    assert document.body == "# Hello\n"
    assert document.front_matter == MarkdownFrontMatter(
        title="Project Overview",
        nav_label="Start Here",
        nav_order=5.0,
        hidden=True,
    )


def test_parse_markdown_document_supports_yaml_front_matter() -> None:
    document = parse_markdown_document(
        "---\n"
        'title: "Project Overview"\n'
        "nav_label: Start Here\n"
        "nav_order: 7.5\n"
        "hidden: false\n"
        "tags:\n"
        "  - docs\n"
        "  - guide\n"
        "nested:\n"
        "  owner: team-docs\n"
        "---\n"
        "# Hello\n"
    )

    assert document.body == "# Hello\n"
    assert document.front_matter == MarkdownFrontMatter(
        title="Project Overview",
        nav_label="Start Here",
        nav_order=7.5,
        hidden=False,
        extras={
            "tags": ("docs", "guide"),
            "nested": {"owner": "team-docs"},
        },
    )


def test_parse_markdown_document_freezes_extra_metadata() -> None:
    document = parse_markdown_document("---\ntags:\n  - docs\nmeta:\n  owner: docs\n---\n# Hello\n")

    extras = document.front_matter.extras
    assert extras == {"tags": ("docs",), "meta": {"owner": "docs"}}

    tags = extras["tags"]
    assert isinstance(tags, tuple)


def test_parse_markdown_document_leaves_non_front_matter_preamble_untouched() -> None:
    markdown_text = "---\nnot: quite\n- valid\n---\n# Hello\n"

    document = parse_markdown_document(markdown_text)

    assert document.body == markdown_text
    assert document.front_matter == MarkdownFrontMatter()


def test_render_markdown_adds_heading_anchors_with_unique_ids() -> None:
    rendered = render_markdown("# Hello\n\n## Details & Setup\n\n## Details & Setup\n")

    assert 'id="hello"' in rendered
    assert 'href="#hello"' in rendered
    assert 'id="details-setup"' in rendered
    assert 'id="details-setup-1"' in rendered
    assert 'class="anchor hit-area-1"' in rendered
    assert 'class="anchor-icon lucide lucide-link-icon lucide-link"' in rendered


def test_render_markdown_syntax_highlights_fenced_code_blocks() -> None:
    rendered = render_markdown("```python\ndef greet():\n    return 1\n```\n")

    assert '<pre class="highlight" data-language="python">' in rendered
    assert 'class="language-python"' in rendered
    assert '<span class="k">def</span>' in rendered


def test_render_markdown_preserves_mermaid_fences_for_client_rendering() -> None:
    rendered = render_markdown("```mermaid\ngraph TD\n  A[Start] --> B{Done?}\n```\n")

    assert '<pre class="mermaid">graph TD\n  A[Start] --&gt; B{Done?}\n</pre>' in rendered
    assert 'class="highlight"' not in rendered
    assert "<code" not in rendered
