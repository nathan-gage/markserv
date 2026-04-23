from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import quote

from .models import MarkdownPage, NavDirectory, NavFile, NavNode, NavTree, sort_markdown_page


def build_nav_tree(pages: Iterable[MarkdownPage]) -> NavTree:
    root: NavTree = {}
    for page in pages:
        node: NavTree = root
        parts = page.rel_path.split("/")
        for part in parts[:-1]:
            existing = node.get(part)
            if isinstance(existing, MarkdownPage):
                break
            if existing is None:
                child: NavTree = {}
                node[part] = child
                node = child
                continue
            node = existing
        else:
            node[parts[-1]] = page
    return root


def build_nav_items(pages: tuple[MarkdownPage, ...]) -> tuple[NavNode, ...]:
    return _build_nav_items(build_nav_tree(pages))


def _build_nav_items(tree: NavTree, prefix: str = "") -> tuple[NavNode, ...]:
    directories: list[tuple[str, NavTree]] = []
    files: list[MarkdownPage] = []

    for name, child in tree.items():
        if isinstance(child, MarkdownPage):
            files.append(child)
        else:
            directories.append((name, child))

    directory_items = tuple(
        _build_nav_directory(directory_name, child_tree, prefix)
        for directory_name, child_tree in sorted(directories, key=lambda item: item[0].lower())
    )
    file_items = tuple(
        NavFile(label=page.label, href=f"/docs/{quote(page.rel_path, safe='/')}", rel_path=page.rel_path)
        for page in sorted(files, key=sort_markdown_page)
    )
    return (*directory_items, *file_items)


def _build_nav_directory(directory_name: str, child_tree: NavTree, prefix: str) -> NavDirectory:
    rel_dir = f"{prefix}/{directory_name}" if prefix else directory_name
    directories: list[tuple[str, NavTree]] = []
    files: list[MarkdownPage] = []

    for name, child in child_tree.items():
        if isinstance(child, MarkdownPage):
            files.append(child)
        else:
            directories.append((name, child))

    return NavDirectory(
        name=directory_name,
        path=rel_dir,
        files=tuple(
            NavFile(label=page.label, href=f"/docs/{quote(page.rel_path, safe='/')}", rel_path=page.rel_path)
            for page in sorted(files, key=sort_markdown_page)
        ),
        directories=tuple(
            _build_nav_directory(name, tree, rel_dir)
            for name, tree in sorted(directories, key=lambda item: item[0].lower())
        ),
    )
