from __future__ import annotations

from collections.abc import Sequence
from html import escape as html_escape

from htmy import ComponentType, Fragment, SafeStr

from ..content import NavDirectory, NavFile, NavNode, humanize_name
from .support import docs_href, htmx_nav_attrs, htmx_sidebar_attrs

_ICON_FOLDER = (
    '<svg class="nav-icon" width="14" height="14" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9'
    'A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>'
)
_ICON_FOLDER_OPEN = (
    '<svg class="nav-icon" width="14" height="14" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6'
    "a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9"
    'l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/></svg>'
)
_ICON_CHEVRON = (
    '<svg class="nav-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="m9 18 6-6-6-6"/></svg>'
)
_NAV_TREE_BASE = 0.65
_NAV_TREE_STEP = 1.2


def _nav_tree_pad(depth: int) -> str:
    return f"padding-left: {_NAV_TREE_BASE + depth * _NAV_TREE_STEP}rem"


def _html_attrs(attrs: dict[str, str]) -> str:
    return "".join(f' {name.replace("_", "-")}="{html_escape(value, quote=True)}"' for name, value in attrs.items())


def _sorted_nav_open_paths(paths: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(paths), key=lambda path: (path.count("/"), path.casefold())))


def _toggle_nav_open_paths(nav_open_paths: Sequence[str], directory_path: str) -> tuple[str, ...]:
    if directory_path in nav_open_paths:
        return _sorted_nav_open_paths(tuple(path for path in nav_open_paths if path != directory_path))
    return _sorted_nav_open_paths((*nav_open_paths, directory_path))


def _open_nav_open_paths(nav_open_paths: Sequence[str], directory_paths: Sequence[str]) -> tuple[str, ...]:
    return _sorted_nav_open_paths((*nav_open_paths, *directory_paths))


def _current_directory_paths(rel_path: str) -> frozenset[str]:
    parts = rel_path.split("/")
    return frozenset("/".join(parts[:index]) for index in range(1, len(parts)))


def _is_directory_open(
    directory_path: str,
    open_path_set: frozenset[str],
    current_directory_paths: frozenset[str],
    *,
    nav_state_explicit: bool,
) -> bool:
    return directory_path in open_path_set or (not nav_state_explicit and directory_path in current_directory_paths)


def _collapsed_nav_chain(directory: NavDirectory) -> tuple[NavDirectory, ...]:
    chain = [directory]
    current = directory
    while not current.files and len(current.directories) == 1:
        current = current.directories[0]
        chain.append(current)
    return tuple(chain)


def _nav_folder_label_html(chain: Sequence[NavDirectory]) -> str:
    head, *tail = [humanize_name(directory.name) for directory in chain]
    head_html = f'<span class="nav-folder-name">{html_escape(head)}</span>'
    if not tail:
        return head_html
    suffix = " / ".join(tail)
    return f'{head_html}<span class="nav-folder-suffix"> / {html_escape(suffix)}</span>'


def _nav_tree_item_html(nav_file: NavFile, depth: int, *, current_rel_path: str) -> str:
    cls = "nav-link is-active is-highlighted" if nav_file.rel_path == current_rel_path else "nav-link"
    return (
        '<div class="nav-row">'
        f'<a href="{html_escape(nav_file.href, quote=True)}"'
        f' class="{cls}"'
        f' style="{html_escape(_nav_tree_pad(depth), quote=True)}"'
        f"{_html_attrs(htmx_nav_attrs(nav_file.href))}>"
        f"{html_escape(nav_file.label)}"
        "</a>"
        "</div>"
    )


def _nav_tree_folder_html(
    directory: NavDirectory,
    depth: int,
    current_rel_path: str,
    nav_open_paths: Sequence[str],
    open_path_set: frozenset[str],
    current_directory_paths: frozenset[str],
    *,
    nav_state_explicit: bool = False,
) -> str:
    is_open = _is_directory_open(
        directory.path,
        open_path_set,
        current_directory_paths,
        nav_state_explicit=nav_state_explicit,
    )
    visible_chain = (directory,) if is_open else _collapsed_nav_chain(directory)

    if is_open:
        toggle_paths = (
            _toggle_nav_open_paths(nav_open_paths, directory.path)
            if directory.path in open_path_set
            else _sorted_nav_open_paths(nav_open_paths)
        )
    else:
        toggle_paths = _open_nav_open_paths(nav_open_paths, tuple(item.path for item in visible_chain))

    toggle_request_href = docs_href(current_rel_path, toggle_paths, nav_state_explicit=True)
    icon = _ICON_FOLDER_OPEN if is_open else _ICON_FOLDER

    children_html = ""
    if is_open:
        rendered_children: list[str] = []
        child_depth = depth + 1
        for file_child in directory.files:
            rendered_children.append(_nav_tree_item_html(file_child, child_depth, current_rel_path=current_rel_path))
        for directory_child in directory.directories:
            rendered_children.append(
                _nav_tree_folder_html(
                    directory_child,
                    child_depth,
                    current_rel_path,
                    nav_open_paths,
                    open_path_set,
                    current_directory_paths,
                    nav_state_explicit=nav_state_explicit,
                )
            )
        if rendered_children:
            children_html = f'<div class="nav-folder-children">{"".join(rendered_children)}</div>'

    header_cls = (
        "nav-folder-header is-active-branch is-highlighted"
        if directory.path in current_directory_paths
        else "nav-folder-header"
    )
    cls = "nav-folder is-open" if is_open else "nav-folder"
    return (
        f'<div class="{cls}">'
        f'<button type="button" class="{header_cls}"'
        f' style="{html_escape(_nav_tree_pad(depth), quote=True)}"'
        f' aria-expanded="{"true" if is_open else "false"}"'
        f"{_html_attrs(htmx_sidebar_attrs(toggle_request_href))}>"
        f"{_ICON_CHEVRON}{icon}{_nav_folder_label_html(visible_chain)}"
        "</button>"
        f"{children_html}"
        "</div>"
    )


def render_nav_items(
    items: tuple[NavNode, ...],
    current_rel_path: str,
    nav_open_paths: Sequence[str],
    *,
    nav_state_explicit: bool = False,
) -> ComponentType:
    if not items:
        return Fragment()

    current_directory_paths = _current_directory_paths(current_rel_path)
    open_path_set = frozenset(nav_open_paths)
    elements: list[str] = []

    for item in items:
        if not isinstance(item, NavDirectory):
            elements.append(_nav_tree_item_html(item, depth=0, current_rel_path=current_rel_path))
    for item in items:
        if isinstance(item, NavDirectory):
            elements.append(
                _nav_tree_folder_html(
                    item,
                    depth=0,
                    current_rel_path=current_rel_path,
                    nav_open_paths=nav_open_paths,
                    open_path_set=open_path_set,
                    current_directory_paths=current_directory_paths,
                    nav_state_explicit=nav_state_explicit,
                )
            )

    return SafeStr(f'<nav class="nav-list">{"".join(elements)}</nav>')
