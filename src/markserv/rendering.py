from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape as _html_escape
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

from htmy import Component, ComponentType, Fragment, SafeStr, html

from .markdown import render_markdown
from .site import NavDirectory, NavFile, NavNode, PageIndex, SiteSource, humanize_name, is_markdown_path

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .search import SearchResult

TITLE_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$", re.MULTILINE)
ANCHOR_TAG_RE = re.compile(r"<a(?P<attrs>\s[^>]*)>", re.IGNORECASE)
HREF_ATTR_RE = re.compile(r'\shref="([^"]+)"')
NAV_QUERY_PARAM = "nav"
NAV_STATE_QUERY_PARAM = "nav_state"
SIDEBAR_STATE_FORM_ID = "sidebar-state"
MAIN_SHELL_ID = "main-shell"
SIDEBAR_SHELL_ID = "sidebar-shell"


@dataclass(frozen=True)
class DocsPageView:
    title: str
    rel_path: str
    rendered_markdown: str
    with_sidebar: bool
    config_name: str
    root_dir: str
    home_href: str | None
    nav_open_paths: tuple[str, ...]
    nav_state_explicit: bool
    nav_items: tuple[NavNode, ...]
    dev_reload: bool = False


@dataclass(frozen=True)
class EmptyPageView:
    root_dir: str
    dev_reload: bool = False


def extract_title(markdown_text: str, fallback: str) -> str:
    match = TITLE_RE.search(markdown_text)
    if not match:
        return fallback
    title = match.group(1).strip().strip("#").strip()
    return title or fallback


def _encode_query_pairs(pairs: Sequence[tuple[str, str]]) -> str:
    return urlencode(pairs, doseq=True, safe="/", quote_via=quote)


def _with_nav_open_paths(
    href: str,
    nav_open_paths: Sequence[str],
    *,
    nav_state_explicit: bool = False,
) -> str:
    split = urlsplit(href)
    query_pairs = [
        (name, value)
        for name, value in parse_qsl(split.query, keep_blank_values=True)
        if name not in {NAV_QUERY_PARAM, NAV_STATE_QUERY_PARAM}
    ]
    if nav_state_explicit:
        query_pairs.append((NAV_STATE_QUERY_PARAM, "1"))
        if nav_open_paths:
            query_pairs.extend((NAV_QUERY_PARAM, path) for path in nav_open_paths)
        else:
            query_pairs.append((NAV_QUERY_PARAM, ""))
    return urlunsplit((split.scheme, split.netloc, split.path, _encode_query_pairs(query_pairs), split.fragment))


def docs_href(
    rel_path: str,
    nav_open_paths: Sequence[str] = (),
    *,
    nav_state_explicit: bool = False,
) -> str:
    return _with_nav_open_paths(
        f"/docs/{quote(rel_path, safe='/')}",
        nav_open_paths,
        nav_state_explicit=nav_state_explicit,
    )


def public_asset_href(rel_path: str) -> str:
    return f"/public/{quote(rel_path, safe='/')}"


def icon_href(rel_path: str) -> str:
    return f"/icons/docs/{quote(rel_path, safe='/')}"


def build_empty_view(site: SiteSource, *, dev_reload: bool = False) -> EmptyPageView:
    return EmptyPageView(root_dir=site.root_label, dev_reload=dev_reload)


def build_docs_view(
    site: SiteSource,
    page_index: PageIndex,
    rel_path: str,
    markdown_text: str,
    *,
    nav_open_paths: Sequence[str] = (),
    nav_state_explicit: bool = False,
    dev_reload: bool = False,
) -> DocsPageView:
    page = page_index.page_for(rel_path)
    fallback_title = humanize_name(rel_path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    title = (
        page.title
        if page is not None and page.title is not None
        else extract_title(markdown_text, fallback=fallback_title)
    )
    nav_open_paths = tuple(nav_open_paths)
    home_doc = page_index.choose_default_doc(preferred=site.default_doc)
    nav_items = page_index.nav_items(rel_path, open_paths=nav_open_paths, nav_state_explicit=nav_state_explicit)
    with_sidebar = site.show_navigation and bool(nav_items)

    rendered_markdown = _enhance_markdown_links(
        render_markdown(markdown_text),
        rel_path,
        nav_open_paths,
        nav_state_explicit=nav_state_explicit,
    )

    return DocsPageView(
        title=title,
        rel_path=rel_path,
        rendered_markdown=rendered_markdown,
        with_sidebar=with_sidebar,
        config_name=site.name,
        root_dir=site.root_label,
        home_href=None if home_doc is None else docs_href(home_doc),
        nav_open_paths=nav_open_paths,
        nav_state_explicit=nav_state_explicit,
        nav_items=nav_items,
        dev_reload=dev_reload,
    )


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

_NAV_TREE_BASE = 0.65  # rem – left padding for depth-0 items
_NAV_TREE_STEP = 1.2  # rem added per nesting depth


def _htmx_request_href(href: str) -> str | None:
    split = urlsplit(href)
    if not split.path.startswith("/docs/"):
        return None
    request_href = split.path
    if split.query:
        request_href = f"{request_href}?{split.query}"
    return request_href


def _htmx_nav_attrs(href: str) -> dict[str, str]:
    request_href = _htmx_request_href(href)
    if request_href is None:
        return {}
    return {
        "hx_get": request_href,
        "hx_target": f"#{MAIN_SHELL_ID}",
        "hx_select": f"#{MAIN_SHELL_ID}",
        "hx_swap": "outerHTML",
        "hx_push_url": href,
        "hx_include": f"#{SIDEBAR_STATE_FORM_ID}",
    }


def _htmx_sidebar_attrs(href: str) -> dict[str, str]:
    request_href = _htmx_request_href(href)
    if request_href is None:
        return {}
    return {
        "hx_get": request_href,
        "hx_target": f"#{SIDEBAR_SHELL_ID}",
        "hx_select": f"#{SIDEBAR_SHELL_ID}",
        "hx_swap": "outerHTML",
    }


def _htmx_nav_html_attrs(href: str) -> str:
    attrs = _htmx_nav_attrs(href)
    return "".join(f' {name.replace("_", "-")}="{_html_escape(value, quote=True)}"' for name, value in attrs.items())


def _resolve_markdown_docs_href(current_rel_path: str, href: str) -> str | None:
    split = urlsplit(href)
    if split.scheme or split.netloc or not split.path:
        return None

    resolved = urlsplit(urljoin(docs_href(current_rel_path), href))
    if not resolved.path.startswith("/docs/"):
        return None

    rel_target = unquote(resolved.path.removeprefix("/docs/"))
    if not rel_target or not is_markdown_path(Path(rel_target)):
        return None

    canonical_path = docs_href(rel_target)
    if canonical_path == docs_href(current_rel_path):
        return None

    return urlunsplit(("", "", canonical_path, resolved.query, resolved.fragment))


def _enhance_markdown_links(
    rendered_html: str,
    current_rel_path: str,
    nav_open_paths: Sequence[str],
    *,
    nav_state_explicit: bool = False,
) -> str:
    def replace(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        if "hx-get=" in attrs or "data-hx-get=" in attrs:
            return match.group(0)

        href_match = HREF_ATTR_RE.search(attrs)
        if href_match is None:
            return match.group(0)

        current_href = href_match.group(1)
        docs_target_href = _resolve_markdown_docs_href(current_rel_path, current_href)
        if docs_target_href is None:
            return match.group(0)

        updated_attrs = HREF_ATTR_RE.sub(
            f' href="{_html_escape(docs_target_href, quote=True)}"',
            attrs,
            count=1,
        )
        return f"<a{updated_attrs}{_htmx_nav_html_attrs(docs_target_href)}>"

    return ANCHOR_TAG_RE.sub(replace, rendered_html)


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
        html.a(nav_file.label, href=href, class_=cls, style=_nav_tree_pad(depth), **_htmx_nav_attrs(href)),
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
            **_htmx_sidebar_attrs(toggle_request_href),
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


_ICON_SYSTEM = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect width="20" height="14" x="2" y="3" rx="2"/>'
    '<line x1="8" x2="16" y1="21" y2="21"/>'
    '<line x1="12" x2="12" y1="17" y2="21"/></svg>'
)
_ICON_SUN = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2v2"/><path d="M12 20v2"/>'
    '<path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/>'
    '<path d="M2 12h2"/><path d="M20 12h2"/>'
    '<path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>'
)
_ICON_MOON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803'
    ' a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"/></svg>'
)
_ICON_SIDEBAR_CLOSE = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect width="18" height="18" x="3" y="3" rx="2"/>'
    '<path d="M9 3v18"/><path d="m16 15-3-3 3-3"/></svg>'
)
_ICON_SIDEBAR_OPEN = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect width="18" height="18" x="3" y="3" rx="2"/>'
    '<path d="M9 3v18"/><path d="m14 9 3 3-3 3"/></svg>'
)
_ICON_CLIPBOARD = (
    '<svg class="copy-icon copy-icon-default" width="14" height="14" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>'
    '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>'
)
_ICON_CLIPBOARD_CHECK = (
    '<svg class="copy-icon copy-icon-check" width="14" height="14" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>'
    '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
    '<path d="m9 14 2 2 4-4"/></svg>'
)
_ICON_SEARCH = (
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'
)


_THEME_BUTTONS = (
    ("system", "System", _ICON_SYSTEM),
    ("light", "Light", _ICON_SUN),
    ("dark", "Dark", _ICON_MOON),
)


def _theme_buttons() -> tuple[ComponentType, ...]:
    return tuple(
        html.button(
            SafeStr(icon),
            type="button",
            class_="theme-btn hit-area-1",
            data_theme_btn=value,
            aria_label=f"{label} theme",
            title=label,
        )
        for value, label, icon in _THEME_BUTTONS
    )


def theme_picker() -> ComponentType:
    return html.div(*_theme_buttons(), class_="theme-picker")


def floating_theme_picker() -> ComponentType:
    return html.div(
        *_theme_buttons(),
        html.span(class_="theme-label"),
        class_="floating-theme-picker",
    )


def _sidebar_toggle() -> ComponentType:
    return Fragment(
        html.input_(
            type="checkbox",
            id="sidebar-collapsed-toggle",
            class_="sidebar-collapse-toggle",
            hx_preserve="",
            aria_hidden="true",
            tabindex="-1",
        ),
        html.label(
            html.span(SafeStr(_ICON_SIDEBAR_CLOSE), class_="sidebar-icon-close"),
            html.span(SafeStr(_ICON_SIDEBAR_OPEN), class_="sidebar-icon-open"),
            for_="sidebar-collapsed-toggle",
            class_="sidebar-toggle hit-area-2",
            aria_label="Toggle sidebar",
            title="Toggle sidebar",
        ),
    )


def _sidebar_state_form(view: DocsPageView) -> ComponentType:
    inputs: list[ComponentType] = []
    if view.nav_state_explicit:
        inputs.append(html.input_(type="hidden", name=NAV_STATE_QUERY_PARAM, value="1"))
    for path in view.nav_open_paths:
        inputs.append(html.input_(type="hidden", name=NAV_QUERY_PARAM, value=path))
    return html.form(*inputs, id=SIDEBAR_STATE_FORM_ID, class_="sidebar-state")


def sidebar_shell(view: DocsPageView, *, oob: bool = False) -> ComponentType:
    title: ComponentType
    if view.home_href is not None:
        title = html.a(view.config_name, href=view.home_href, class_="sidebar-title", **_htmx_nav_attrs(view.home_href))
    else:
        title = html.span(view.config_name, class_="sidebar-title")

    attrs: dict[str, str] = {"id": SIDEBAR_SHELL_ID, "class_": "sidebar"}
    if oob:
        attrs["hx_swap_oob"] = "outerHTML"

    return html.aside(
        _sidebar_state_form(view),
        html.div(
            html.div(title, class_="sidebar-header"),
            html.div(
                html.div(
                    html.span(view.root_dir, class_="sidebar-path-text"),
                    html.button(
                        SafeStr(_ICON_CLIPBOARD),
                        SafeStr(_ICON_CLIPBOARD_CHECK),
                        type="button",
                        class_="copy-btn copy-btn-sm hit-area-1",
                        data_copy_text=view.root_dir,
                        aria_label="Copy path",
                        title="Copy path",
                    ),
                    class_="content-path-group",
                ),
                class_="sidebar-path",
            ),
            class_="sidebar-top",
        ),
        render_nav_items(
            view.nav_items,
            view.rel_path,
            view.nav_open_paths,
            nav_state_explicit=view.nav_state_explicit,
        ),
        html.div(
            theme_picker(),
            class_="sidebar-footer",
        ),
        **attrs,
    )


def main_shell(view: DocsPageView) -> ComponentType:
    return html.main(
        html.div(
            html.div(
                html.span(view.rel_path, class_="content-path"),
                html.button(
                    SafeStr(_ICON_CLIPBOARD),
                    SafeStr(_ICON_CLIPBOARD_CHECK),
                    type="button",
                    class_="copy-btn hit-area-1",
                    data_copy_text=view.rel_path,
                    aria_label="Copy file path",
                    title="Copy file path",
                ),
                class_="content-path-group",
            ),
            class_="content-header",
        ),
        html.div(
            html.article(SafeStr(view.rendered_markdown), class_="markdown-body"),
            class_="markdown-frame",
        ),
        id=MAIN_SHELL_ID,
        class_="main",
        data_icon=icon_href(view.rel_path),
    )


def docs_shell(view: DocsPageView) -> ComponentType:
    sidebar: ComponentType = Fragment()
    theme_float: ComponentType = Fragment()
    sidebar_toggle: ComponentType = Fragment()
    if not view.with_sidebar:
        theme_float = floating_theme_picker()
    if view.with_sidebar:
        sidebar_toggle = _sidebar_toggle()
        sidebar = html.div(
            sidebar_shell(view),
            html.div(class_="sidebar-resize hit-area-x-2", aria_hidden="true"),
            class_="sidebar-frame",
        )

    shell_class = "app-shell with-sidebar" if view.with_sidebar else "app-shell"
    return html.div(
        sidebar_toggle,
        sidebar,
        theme_float,
        main_shell(view),
        id="page-shell",
        class_=shell_class,
        data_icon=icon_href(view.rel_path),
        hx_history_elt="",
    )


def empty_shell(view: EmptyPageView) -> ComponentType:
    return html.main(
        floating_theme_picker(),
        html.div(
            html.h1("No markdown files found"),
            class_="empty-state-header",
        ),
        html.p(
            "markserv scanned ",
            html.code(view.root_dir),
            " and did not find any markdown files.",
        ),
        html.ul(
            html.li("Git-style ignore rules from ", html.code(".gitignore"), " are respected."),
            html.li(
                "Markdown files are expected to use common extensions like ",
                html.code(".md"),
                " or ",
                html.code(".markdown"),
                ".",
            ),
        ),
        id="page-shell",
        class_="empty-state",
        hx_history_elt="",
    )


def search_chrome() -> ComponentType:
    return Fragment(
        html.button(
            html.span(SafeStr(_ICON_SEARCH), class_="search-trigger-icon"),
            html.span("Cmd/Ctrl K", class_="search-trigger-shortcut", data_search_shortcut=""),
            type="button",
            class_="search-trigger",
            data_search_open="",
            aria_label="Open search",
            title="Search docs (Cmd/Ctrl+K)",
        ),
        html.dialog(
            html.div(
                html.div(
                    html.span(SafeStr(_ICON_SEARCH), class_="search-input-icon"),
                    html.input_(
                        type="search",
                        class_="search-input",
                        name="q",
                        placeholder="Search pages, headings, and content",
                        autocomplete="off",
                        autocapitalize="off",
                        spellcheck="false",
                        data_search_input="",
                        aria_label="Search docs",
                        hx_get="/_search",
                        hx_trigger="input changed delay:100ms, search",
                        hx_target="[data-search-results]",
                        hx_swap="innerHTML",
                        hx_sync="this:replace",
                        hx_indicator=".search-input-icon",
                        hx_include=f"#{SIDEBAR_STATE_FORM_ID}",
                    ),
                    html.button(
                        "Esc",
                        type="button",
                        class_="search-close hit-area-1",
                        data_search_close="",
                        aria_label="Close search",
                    ),
                    class_="search-modal-header",
                ),
                html.div(
                    html.div(
                        html.p(
                            "Start typing to search pages, headings, and content.",
                            class_="search-state",
                        ),
                        class_="search-results",
                        data_search_results="",
                        role="listbox",
                        aria_label="Search results",
                    ),
                    class_="search-modal-body",
                ),
                html.div(
                    html.span("Pages, headings, and body text", class_="search-footer-copy"),
                    html.div(
                        html.kbd("\u2191"),
                        html.kbd("\u2193"),
                        html.span("move"),
                        html.kbd("Enter"),
                        html.span("open"),
                        class_="search-footer-hints",
                    ),
                    class_="search-modal-footer",
                ),
                class_="search-modal",
            ),
            class_="search-dialog",
            data_search_dialog="",
            aria_label="Search docs",
        ),
    )


def render_search_results_fragment(
    results: Sequence[SearchResult],
    query: str,
    nav_open_paths: Sequence[str] = (),
    *,
    nav_state_explicit: bool = False,
) -> str:
    """Render search results as an HTML fragment for HTMX swap."""
    if not query.strip():
        return '<p class="search-state">Start typing to search pages, headings, and content.</p>'
    if not results:
        return '<p class="search-state">No matching docs found.</p>'
    parts: list[str] = []
    for r in results:
        href = r.href
        snippet = ""
        if r.snippet:
            snippet = f'<span class="search-result-snippet">{_html_escape(r.snippet)}</span>'
        parts.append(
            f'<a href="{_html_escape(href)}" class="search-result"{_htmx_nav_html_attrs(href)}>'
            f'<span class="search-result-header">'
            f'<span class="search-result-title">{_html_escape(r.title)}</span>'
            f'<span class="search-result-path">{_html_escape(r.rel_path)}</span>'
            f"</span>"
            f"{snippet}"
            f"</a>"
        )
    return "".join(parts)


def base_document(
    title: str, body_content: ComponentType, favicon_href: str | None = None, *, dev_reload: bool = False
) -> Component:
    favicon: ComponentType = Fragment()
    if favicon_href is not None:
        favicon = html.link(rel="icon", type="image/png", href=favicon_href, id="favicon")

    return (
        html.DOCTYPE.html,
        html.html(
            html.head(
                html.Meta.charset(),
                html.Meta.viewport(),
                html.meta(name="htmx-config", content='{"historyRestoreAsHxRequest":false}'),
                html.title(title),
                favicon,
                html.link(
                    rel="stylesheet",
                    href=public_asset_href("css/github-markdown-light.css"),
                    media="(prefers-color-scheme: light), (prefers-color-scheme: no-preference)",
                    id="github-markdown-light",
                ),
                html.link(
                    rel="stylesheet",
                    href=public_asset_href("css/github-markdown-dark.css"),
                    media="(prefers-color-scheme: dark)",
                    id="github-markdown-dark",
                ),
                html.link(
                    rel="stylesheet",
                    href=public_asset_href("css/pygments-light.css"),
                    media="(prefers-color-scheme: light), (prefers-color-scheme: no-preference)",
                    id="pygments-light",
                ),
                html.link(
                    rel="stylesheet",
                    href=public_asset_href("css/pygments-dark.css"),
                    media="(prefers-color-scheme: dark)",
                    id="pygments-dark",
                ),
                html.link(rel="stylesheet", href=public_asset_href("css/app.css")),
                html.script(src=public_asset_href("js/theme.js")),
                html.script(src=public_asset_href("js/sidebar.js")),
                html.script(src=public_asset_href("js/clipboard.js")),
                html.script(src=public_asset_href("js/favicon.js"), defer=True),
                html.script(src=public_asset_href("js/live-reload.js"), defer=True),
                html.script(src=public_asset_href("js/search.js"), defer=True),
                html.script(src=public_asset_href("js/dev-reload.js"), defer=True) if dev_reload else Fragment(),
            ),
            html.body(
                search_chrome(),
                body_content,
                html.script(src=public_asset_href("vendor/htmx.min.js")),
            ),
            lang="en",
            data_dev_reload="true" if dev_reload else None,
        ),
    )


def render_docs_page(view: DocsPageView) -> Component:
    return base_document(
        f"{view.title} · markserv",
        docs_shell(view),
        favicon_href=icon_href(view.rel_path),
        dev_reload=view.dev_reload,
    )


def render_empty_page(view: EmptyPageView) -> Component:
    return base_document("markserv", empty_shell(view), dev_reload=view.dev_reload)


def render_sidebar_fragment(view: DocsPageView) -> ComponentType:
    return sidebar_shell(view)


def render_docs_fragment(view: DocsPageView) -> ComponentType:
    return Fragment(
        html.title(f"{view.title} · markserv", hx_swap_oob="true"),
        html.link(rel="icon", type="image/png", href=icon_href(view.rel_path), id="favicon", hx_swap_oob="outerHTML"),
        sidebar_shell(view, oob=True),
        main_shell(view),
    )


def render_empty_fragment(view: EmptyPageView) -> ComponentType:
    return Fragment(
        html.title("markserv", hx_swap_oob="true"),
        empty_shell(view),
    )
