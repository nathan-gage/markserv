from __future__ import annotations

from collections.abc import Sequence

from htmy import ComponentType, Fragment, SafeStr, html

from ..content import NavDirectory, NavFile, NavNode, humanize_name
from .support import docs_href, htmx_nav_attrs, htmx_sidebar_attrs

_ICON_FOLDER = SafeStr(
    '<svg class="nav-icon" width="14" height="14" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9'
    'A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>'
)
_ICON_FOLDER_OPEN = SafeStr(
    '<svg class="nav-icon" width="14" height="14" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6'
    "a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9"
    'l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/></svg>'
)
_ICON_CHEVRON = SafeStr(
    '<svg class="nav-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="m9 18 6-6-6-6"/></svg>'
)
_NAV_TREE_BASE = 0.65
_NAV_TREE_STEP = 1.2


def _nav_tree_pad(depth: int) -> str:
    return f"padding-left: {_NAV_TREE_BASE + depth * _NAV_TREE_STEP}rem"


def _sorted_nav_open_paths(paths: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(paths), key=lambda path: (path.count("/"), path.casefold())))


def _toggle_nav_open_paths(nav_open_paths: Sequence[str], directory_path: str) -> tuple[str, ...]:
    if directory_path in nav_open_paths:
        return _sorted_nav_open_paths(tuple(path for path in nav_open_paths if path != directory_path))
    return _sorted_nav_open_paths((*nav_open_paths, directory_path))


def _open_nav_open_paths(nav_open_paths: Sequence[str], directory_paths: Sequence[str]) -> tuple[str, ...]:
    return _sorted_nav_open_paths((*nav_open_paths, *directory_paths))


def _nav_children(directory: NavDirectory) -> tuple[tuple[NavFile, ...], tuple[NavDirectory, ...]]:
    files = tuple(child for child in directory.children if not isinstance(child, NavDirectory))
    directories = tuple(child for child in directory.children if isinstance(child, NavDirectory))
    return files, directories


def _collapsed_nav_chain(directory: NavDirectory) -> tuple[NavDirectory, ...]:
    chain = [directory]
    current = directory
    while True:
        files, directories = _nav_children(current)
        if files or len(directories) != 1:
            return tuple(chain)
        current = directories[0]
        chain.append(current)


def _nav_folder_label(chain: Sequence[NavDirectory]) -> ComponentType:
    head, *tail = [humanize_name(directory.name) for directory in chain]
    if not tail:
        return html.span(head, class_="nav-folder-name")
    return Fragment(
        html.span(head, class_="nav-folder-name"),
        html.span(" / " + " / ".join(tail), class_="nav-folder-suffix"),
    )


def _nav_tree_item(
    nav_file: NavFile,
    depth: int,
    nav_open_paths: Sequence[str],
    *,
    nav_state_explicit: bool = False,
) -> ComponentType:
    cls = "nav-link is-active is-highlighted" if nav_file.active else "nav-link"
    href = nav_file.href
    return html.div(
        html.a(nav_file.label, href=href, class_=cls, style=_nav_tree_pad(depth), **htmx_nav_attrs(href)),
        class_="nav-row",
    )


def _nav_tree_folder(
    directory: NavDirectory,
    depth: int,
    current_rel_path: str,
    nav_open_paths: Sequence[str],
    *,
    nav_state_explicit: bool = False,
) -> ComponentType:
    visible_chain = (directory,) if directory.open else _collapsed_nav_chain(directory)
    toggle_paths = (
        _toggle_nav_open_paths(nav_open_paths, directory.path)
        if directory.open
        else _open_nav_open_paths(nav_open_paths, tuple(item.path for item in visible_chain))
    )
    toggle_request_href = docs_href(current_rel_path, toggle_paths, nav_state_explicit=True)
    icon = _ICON_FOLDER_OPEN if directory.open else _ICON_FOLDER

    files, directories = _nav_children(directory)
    children: list[ComponentType] = []
    child_depth = depth + 1
    if directory.open:
        for file_child in files:
            children.append(
                _nav_tree_item(file_child, child_depth, nav_open_paths, nav_state_explicit=nav_state_explicit)
            )
        for directory_child in directories:
            children.append(
                _nav_tree_folder(
                    directory_child,
                    child_depth,
                    current_rel_path,
                    nav_open_paths,
                    nav_state_explicit=nav_state_explicit,
                )
            )

    children_block: ComponentType = Fragment()
    if children:
        children_block = html.div(*children, class_="nav-folder-children")

    header_cls = (
        "nav-folder-header is-active-branch is-highlighted"
        if current_rel_path.startswith(f"{directory.path}/")
        else "nav-folder-header"
    )
    cls = "nav-folder is-open" if directory.open else "nav-folder"
    return html.div(
        html.button(
            _ICON_CHEVRON,
            icon,
            _nav_folder_label(visible_chain),
            type="button",
            class_=header_cls,
            style=_nav_tree_pad(depth),
            aria_expanded="true" if directory.open else "false",
            **htmx_sidebar_attrs(toggle_request_href),
        ),
        children_block,
        class_=cls,
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

    elements: list[ComponentType] = []
    for item in items:
        if not isinstance(item, NavDirectory):
            elements.append(
                _nav_tree_item(item, depth=0, nav_open_paths=nav_open_paths, nav_state_explicit=nav_state_explicit)
            )
    for item in items:
        if isinstance(item, NavDirectory):
            elements.append(
                _nav_tree_folder(
                    item,
                    depth=0,
                    current_rel_path=current_rel_path,
                    nav_open_paths=nav_open_paths,
                    nav_state_explicit=nav_state_explicit,
                )
            )

    return html.nav(*elements, class_="nav-list")
