from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape as _html_escape
from typing import TYPE_CHECKING
from urllib.parse import quote

from htmy import Component, ComponentType, Fragment, SafeStr, html

from .markdown import render_markdown
from .site import NavDirectory, NavFile, NavNode, PageIndex, SiteSource, humanize_name

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .search import SearchResult

TITLE_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class DocsPageView:
    title: str
    rel_path: str
    rendered_markdown: str
    with_sidebar: bool
    config_name: str
    root_dir: str
    home_href: str | None
    nav_items: tuple[NavNode, ...]
    live_fragment_href: str | None
    dev_reload: bool = False


@dataclass(frozen=True)
class EmptyPageView:
    root_dir: str
    live_fragment_href: str | None
    dev_reload: bool = False


def extract_title(markdown_text: str, fallback: str) -> str:
    match = TITLE_RE.search(markdown_text)
    if not match:
        return fallback
    title = match.group(1).strip().strip("#").strip()
    return title or fallback


def docs_href(rel_path: str) -> str:
    return f"/docs/{quote(rel_path, safe='/')}"


def public_asset_href(rel_path: str) -> str:
    return f"/public/{quote(rel_path, safe='/')}"


def icon_href(rel_path: str) -> str:
    return f"/icons/docs/{quote(rel_path, safe='/')}"


def docs_fragment_href(rel_path: str) -> str:
    return f"/_live/docs/{quote(rel_path, safe='/')}"


def root_fragment_href() -> str:
    return "/_live/root"


def build_empty_view(site: SiteSource, *, dev_reload: bool = False) -> EmptyPageView:
    live_fragment_href = root_fragment_href() if site.watch_root is not None and site.watch_filter is not None else None
    return EmptyPageView(root_dir=site.root_label, live_fragment_href=live_fragment_href, dev_reload=dev_reload)


def build_docs_view(
    site: SiteSource, page_index: PageIndex, rel_path: str, markdown_text: str, *, dev_reload: bool = False
) -> DocsPageView:
    page = page_index.page_for(rel_path)
    fallback_title = humanize_name(rel_path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    title = (
        page.title
        if page is not None and page.title is not None
        else extract_title(markdown_text, fallback=fallback_title)
    )
    home_doc = page_index.choose_default_doc(preferred=site.default_doc)
    nav_items = page_index.nav_items(rel_path)
    with_sidebar = site.show_navigation and bool(nav_items)

    live_fragment_href = None
    if site.watch_root is not None and site.watch_filter is not None:
        live_fragment_href = docs_fragment_href(rel_path)

    return DocsPageView(
        title=title,
        rel_path=rel_path,
        rendered_markdown=render_markdown(markdown_text),
        with_sidebar=with_sidebar,
        config_name=site.name,
        root_dir=site.root_label,
        home_href=None if home_doc is None else docs_href(home_doc),
        nav_items=nav_items,
        live_fragment_href=live_fragment_href,
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


def _flatten_nav(items: tuple[NavNode, ...]) -> list[NavFile]:
    """Recursively collect all files from a nav tree."""
    result: list[NavFile] = []
    for item in items:
        if isinstance(item, NavDirectory):
            result.extend(_flatten_nav(item.children))
        else:
            result.append(item)
    return result


def _live_fragment_href_for_docs_href(href: str) -> str | None:
    prefix = "/docs/"
    if not href.startswith(prefix):
        return None
    return f"/_live/docs/{href.removeprefix(prefix)}"


def _live_nav_attrs(href: str) -> dict[str, str]:
    live_href = _live_fragment_href_for_docs_href(href)
    if live_href is None:
        return {}
    return {
        "hx_get": live_href,
        "hx_target": "#page-shell",
        "hx_swap": "outerHTML",
        "hx_push_url": "true",
    }


def _nav_link(nav_file: NavFile) -> ComponentType:
    cls = "nav-link is-active" if nav_file.active else "nav-link"
    return html.a(nav_file.label, href=nav_file.href, class_=cls, **_live_nav_attrs(nav_file.href))


def _render_section_children(children: tuple[NavNode, ...], group: list[ComponentType]) -> None:
    """Render a section's children: direct files first, then sub-dirs as sub-sections."""
    for child in children:
        if not isinstance(child, NavDirectory):
            group.append(_nav_link(child))
    for child in children:
        if isinstance(child, NavDirectory):
            sub_icon = _ICON_FOLDER_OPEN if child.open else _ICON_FOLDER
            sub: list[ComponentType] = [
                html.div(
                    sub_icon,
                    html.span(humanize_name(child.name), class_="nav-subsection-label"),
                    class_="nav-subsection",
                ),
            ]
            for f in _flatten_nav(child.children):
                sub.append(_nav_link(f))
            group.append(html.div(*sub, class_="nav-subgroup"))


def render_nav_items(items: tuple[NavNode, ...]) -> ComponentType:
    if not items:
        return Fragment()

    elements: list[ComponentType] = []
    root_links = [_nav_link(item) for item in items if not isinstance(item, NavDirectory)]
    if root_links:
        elements.append(html.div(*root_links, class_="nav-group"))
    for item in items:
        if not isinstance(item, NavDirectory):
            continue
        icon = _ICON_FOLDER_OPEN if item.open else _ICON_FOLDER
        group: list[ComponentType] = [
            html.div(icon, html.span(humanize_name(item.name), class_="nav-section-label"), class_="nav-section"),
        ]
        _render_section_children(item.children, group)
        elements.append(html.div(*group, class_="nav-group"))

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


def _sidebar_toggle_btn() -> ComponentType:
    return html.button(
        html.span(SafeStr(_ICON_SIDEBAR_CLOSE), class_="sidebar-icon-close"),
        html.span(SafeStr(_ICON_SIDEBAR_OPEN), class_="sidebar-icon-open"),
        type="button",
        class_="sidebar-toggle hit-area-2",
        data_sidebar_toggle="",
        aria_label="Toggle sidebar",
        title="Toggle sidebar",
    )


def docs_shell(view: DocsPageView) -> ComponentType:
    sidebar: ComponentType = Fragment()
    toggle_btn: ComponentType = Fragment()
    theme_float: ComponentType = Fragment()
    if not view.with_sidebar:
        theme_float = floating_theme_picker()
    if view.with_sidebar:
        title: ComponentType
        if view.home_href is not None:
            title = html.a(
                view.config_name, href=view.home_href, class_="sidebar-title", **_live_nav_attrs(view.home_href)
            )
        else:
            title = html.span(view.config_name, class_="sidebar-title")

        toggle_btn = _sidebar_toggle_btn()
        sidebar = Fragment(
            html.aside(
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
                render_nav_items(view.nav_items),
                html.div(
                    theme_picker(),
                    class_="sidebar-footer",
                ),
                class_="sidebar",
            ),
            html.div(class_="sidebar-resize hit-area-x-2"),
        )

    shell_class = "app-shell with-sidebar" if view.with_sidebar else "app-shell"
    return html.div(
        toggle_btn,
        sidebar,
        theme_float,
        html.main(
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
            class_="main",
        ),
        id="page-shell",
        class_=shell_class,
        data_icon=icon_href(view.rel_path),
        data_live_fragment=view.live_fragment_href,
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
        data_live_fragment=view.live_fragment_href,
    )


def search_chrome() -> ComponentType:
    return Fragment(
        html.button(
            SafeStr(_ICON_SEARCH),
            html.span("Search", class_="search-trigger-label"),
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
                        hx_trigger="input delay:100ms, search",
                        hx_target="[data-search-results]",
                        hx_swap="innerHTML",
                    ),
                    html.form(
                        html.button(
                            "Esc",
                            type="submit",
                            class_="search-close hit-area-1",
                            aria_label="Close search",
                        ),
                        method="dialog",
                        class_="search-close-form",
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


def render_search_results_fragment(results: Sequence[SearchResult], query: str) -> str:
    """Render search results as an HTML fragment for HTMX swap."""
    if not query.strip():
        return '<p class="search-state">Start typing to search pages, headings, and content.</p>'
    if not results:
        return '<p class="search-state">No matching docs found.</p>'
    parts: list[str] = []
    for r in results:
        snippet = ""
        if r.snippet:
            snippet = f'<span class="search-result-snippet">{_html_escape(r.snippet)}</span>'
        parts.append(
            f'<a href="{_html_escape(r.href)}" class="search-result">'
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


def render_docs_fragment(view: DocsPageView) -> ComponentType:
    return Fragment(
        html.title(f"{view.title} · markserv", hx_swap_oob="true"),
        docs_shell(view),
    )


def render_empty_fragment(view: EmptyPageView) -> ComponentType:
    return Fragment(
        html.title("markserv", hx_swap_oob="true"),
        empty_shell(view),
    )
