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


def build_nav_nodes(
    tree: NavTree,
    current_rel: str,
    prefix: str = "",
    *,
    open_paths: frozenset[str] = frozenset(),
    nav_state_explicit: bool = False,
) -> tuple[NavNode, ...]:
    directories: list[tuple[str, NavTree]] = []
    files_only: list[MarkdownPage] = []

    for name, child in tree.items():
        if isinstance(child, MarkdownPage):
            files_only.append(child)
        else:
            directories.append((name, child))

    items: list[NavNode] = []
    for directory_name, child_tree in sorted(directories, key=lambda item: item[0].lower()):
        rel_dir = f"{prefix}/{directory_name}" if prefix else directory_name
        items.append(
            NavDirectory(
                name=directory_name,
                path=rel_dir,
                open=rel_dir in open_paths or (not nav_state_explicit and current_rel.startswith(f"{rel_dir}/")),
                children=build_nav_nodes(
                    child_tree,
                    current_rel,
                    rel_dir,
                    open_paths=open_paths,
                    nav_state_explicit=nav_state_explicit,
                ),
            )
        )

    for page in sorted(files_only, key=sort_markdown_page):
        items.append(
            NavFile(
                label=page.label,
                href=f"/docs/{quote(page.rel_path, safe='/')}",
                active=page.rel_path == current_rel,
            )
        )

    return tuple(items)
