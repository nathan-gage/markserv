from __future__ import annotations

from html import escape as html_escape
from typing import TYPE_CHECKING

from htmy import Component, ComponentType, Fragment, SafeStr, html

from .models import DocsPageView, EmptyPageView, SidebarView
from .nav import render_nav_items
from .support import (
    MAIN_SHELL_ID,
    NAV_QUERY_PARAM,
    NAV_STATE_QUERY_PARAM,
    SIDEBAR_STATE_FORM_ID,
    htmx_nav_attrs,
    htmx_nav_html_attrs,
    icon_href,
    public_asset_href,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..search import SearchResult


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
    return html.div(*_theme_buttons(), html.span(class_="theme-label"), class_="floating-theme-picker")


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


def _sidebar_state_form(sidebar: SidebarView) -> ComponentType:
    inputs: list[ComponentType] = []
    if sidebar.navigation.explicit:
        inputs.append(html.input_(type="hidden", name=NAV_STATE_QUERY_PARAM, value="1"))
    for path in sidebar.navigation.open_paths:
        inputs.append(html.input_(type="hidden", name=NAV_QUERY_PARAM, value=path))
    return html.form(*inputs, id=SIDEBAR_STATE_FORM_ID, class_="sidebar-state")


def sidebar_shell(view: DocsPageView, *, oob: bool = False) -> ComponentType:
    sidebar = view.sidebar
    if sidebar is None:
        return Fragment()

    title: ComponentType
    if sidebar.home_href is not None:
        title = html.a(
            sidebar.config_name, href=sidebar.home_href, class_="sidebar-title", **htmx_nav_attrs(sidebar.home_href)
        )
    else:
        title = html.span(sidebar.config_name, class_="sidebar-title")

    attrs: dict[str, str] = {"id": "sidebar-shell", "class_": "sidebar"}
    if oob:
        attrs["hx_swap_oob"] = "outerHTML"

    return html.aside(
        _sidebar_state_form(sidebar),
        html.div(
            html.div(title, class_="sidebar-header"),
            html.div(
                html.div(
                    html.span(sidebar.root_dir, class_="sidebar-path-text"),
                    html.button(
                        SafeStr(_ICON_CLIPBOARD),
                        SafeStr(_ICON_CLIPBOARD_CHECK),
                        type="button",
                        class_="copy-btn copy-btn-sm hit-area-1",
                        data_copy_text=sidebar.root_dir,
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
            sidebar.items,
            view.rel_path,
            sidebar.navigation.open_paths,
            nav_state_explicit=sidebar.navigation.explicit,
        ),
        html.div(theme_picker(), class_="sidebar-footer"),
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
        html.div(html.article(SafeStr(view.rendered_markdown), class_="markdown-body"), class_="markdown-frame"),
        id=MAIN_SHELL_ID,
        class_="main",
        data_icon=icon_href(view.rel_path),
    )


def docs_shell(view: DocsPageView) -> ComponentType:
    sidebar_frame: ComponentType = Fragment()
    theme_float: ComponentType = Fragment()
    sidebar_toggle: ComponentType = Fragment()
    has_sidebar = view.sidebar is not None
    if not has_sidebar:
        theme_float = floating_theme_picker()
    if has_sidebar:
        sidebar_toggle = _sidebar_toggle()
        sidebar_frame = html.div(
            sidebar_shell(view),
            html.div(class_="sidebar-resize hit-area-x-2", aria_hidden="true"),
            class_="sidebar-frame",
        )

    shell_class = "app-shell with-sidebar" if has_sidebar else "app-shell"
    return html.div(
        sidebar_toggle,
        sidebar_frame,
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
        html.div(html.h1("No markdown files found"), class_="empty-state-header"),
        html.p("markserv scanned ", html.code(view.root_dir), " and did not find any markdown files."),
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
                        html.p("Start typing to search pages, headings, and content.", class_="search-state"),
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
    if not query.strip():
        return '<p class="search-state">Start typing to search pages, headings, and content.</p>'
    if not results:
        return '<p class="search-state">No matching docs found.</p>'

    parts: list[str] = []
    for result in results:
        snippet = ""
        if result.snippet:
            snippet = f'<span class="search-result-snippet">{html_escape(result.snippet)}</span>'
        parts.append(
            f'<a href="{html_escape(result.href)}" class="search-result"{htmx_nav_html_attrs(result.href)}>'
            f'<span class="search-result-header">'
            f'<span class="search-result-title">{html_escape(result.title)}</span>'
            f'<span class="search-result-path">{html_escape(result.rel_path)}</span>'
            f"</span>"
            f"{snippet}"
            f"</a>"
        )
    return "".join(parts)


def base_document(
    title: str,
    body_content: ComponentType,
    favicon_href: str | None = None,
    *,
    dev_reload: bool = False,
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
            html.body(search_chrome(), body_content, html.script(src=public_asset_href("vendor/htmx.min.js"))),
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
    sidebar_fragment: ComponentType = Fragment()
    if view.sidebar is not None:
        sidebar_fragment = sidebar_shell(view, oob=True)
    return Fragment(
        html.title(f"{view.title} · markserv", hx_swap_oob="true"),
        html.link(rel="icon", type="image/png", href=icon_href(view.rel_path), id="favicon", hx_swap_oob="outerHTML"),
        sidebar_fragment,
        main_shell(view),
    )


def render_empty_fragment(view: EmptyPageView) -> ComponentType:
    return Fragment(html.title("markserv", hx_swap_oob="true"), empty_shell(view))
