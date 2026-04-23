from __future__ import annotations

from markserv.site import MarkdownPage, PageIndex


def test_page_index_distinguishes_visible_navigation_from_hidden_only_directories() -> None:
    index = PageIndex(
        (
            MarkdownPage(rel_path="guide/README.md", label="Guide"),
            MarkdownPage(rel_path="guide/topic.md", label="Topic"),
            MarkdownPage(rel_path="secret/plan.md", label="Plan", hidden=True),
        )
    )

    assert index.page_for("guide/topic.md") == MarkdownPage(rel_path="guide/topic.md", label="Topic")
    assert index.choose_default_doc(prefix="guide") == "guide/README.md"
    assert index.choose_default_doc(prefix="secret") == "secret/plan.md"
    assert index.directory_paths() == ("guide",)
    assert index.has_directory("guide") is True
    assert index.has_directory("secret") is True
    assert index.has_directory("guide/topic.md") is False
