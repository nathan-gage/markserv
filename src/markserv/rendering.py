from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

import cmarkgfm
from cmarkgfm.cmark import Options
from htmy import Component, ComponentType, Fragment, SafeStr, html

from .site import NavDirectory, NavNode, PageIndex, SiteSource, humanize_name

CMARK_OPTIONS = Options.CMARK_OPT_GITHUB_PRE_LANG | Options.CMARK_OPT_SMART
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
    live_fragment_href: str


@dataclass(frozen=True)
class EmptyPageView:
    root_dir: str
    live_fragment_href: str


def extract_title(markdown_text: str, fallback: str) -> str:
    match = TITLE_RE.search(markdown_text)
    if not match:
        return fallback
    title = match.group(1).strip().strip("#").strip()
    return title or fallback


def render_markdown(markdown_text: str) -> str:
    return cmarkgfm.github_flavored_markdown_to_html(markdown_text, options=CMARK_OPTIONS)


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


def build_empty_view(site: SiteSource) -> EmptyPageView:
    return EmptyPageView(root_dir=site.root_label, live_fragment_href=root_fragment_href())


def build_docs_view(site: SiteSource, page_index: PageIndex, rel_path: str, markdown_text: str) -> DocsPageView:
    title = extract_title(markdown_text, fallback=humanize_name(rel_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]))
    home_doc = page_index.choose_default_doc(preferred=site.default_doc)
    with_sidebar = site.show_navigation and bool(page_index.pages)

    return DocsPageView(
        title=title,
        rel_path=rel_path,
        rendered_markdown=render_markdown(markdown_text),
        with_sidebar=with_sidebar,
        config_name=site.name,
        root_dir=site.root_label,
        home_href=None if home_doc is None else docs_href(home_doc),
        nav_items=page_index.nav_items(rel_path),
        live_fragment_href=docs_fragment_href(rel_path),
    )


def sse_reload_listener(live_fragment_href: str) -> ComponentType:
    return html.div(
        html.div(
            hx_get=live_fragment_href,
            hx_trigger="sse:reload",
            hx_target="#page-shell",
            hx_swap="outerHTML",
        ),
        hidden=True,
        hx_ext="sse",
        sse_connect="/_events",
    )


def render_nav_items(items: tuple[NavNode, ...]) -> ComponentType:
    if not items:
        return Fragment()

    return html.ul(
        *(
            html.li(
                html.details(
                    html.summary(item.name),
                    render_nav_items(item.children),
                    open=True if item.open else None,
                ),
                class_="nav-dir",
            )
            if isinstance(item, NavDirectory)
            else html.li(
                html.a(
                    item.label,
                    href=item.href,
                    class_="nav-link is-active" if item.active else "nav-link",
                ),
                class_="nav-file",
            )
            for item in items
        ),
        class_="nav-tree",
    )


_ICON_SYSTEM = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="2" y="3" width="20" height="14" rx="2"/>'
    '<line x1="8" y1="21" x2="16" y2="21"/>'
    '<line x1="12" y1="17" x2="12" y2="21"/></svg>'
)
_ICON_SUN = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="5"/>'
    '<line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>'
    '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>'
    '<line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
    '<line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>'
    '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>'
    '<line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
)
_ICON_MOON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
)


def theme_picker() -> ComponentType:
    return html.div(
        html.span("Theme", class_="theme-picker-label"),
        *(
            html.button(
                SafeStr(icon),
                type="button",
                class_="theme-btn",
                data_theme_btn=value,
                aria_label=f"{label} theme",
                title=label,
            )
            for value, label, icon in (
                ("system", "System", _ICON_SYSTEM),
                ("light", "Light", _ICON_SUN),
                ("dark", "Dark", _ICON_MOON),
            )
        ),
        class_="theme-picker",
    )


def docs_shell(view: DocsPageView) -> ComponentType:
    sidebar: ComponentType = Fragment()
    if view.with_sidebar:
        home_link: ComponentType = Fragment()
        if view.home_href is not None:
            home_link = html.a("Home", href=view.home_href, class_="home-link")

        sidebar = html.aside(
            html.div(
                html.p(view.config_name, class_="sidebar-title"),
                html.p(f"Watching {view.root_dir}", class_="sidebar-subtitle"),
                home_link,
                class_="sidebar-header",
            ),
            render_nav_items(view.nav_items),
            class_="sidebar",
        )

    shell_class = "app-shell with-sidebar" if view.with_sidebar else "app-shell"
    return html.div(
        sse_reload_listener(view.live_fragment_href),
        sidebar,
        html.main(
            html.div(
                html.span(view.rel_path, class_="content-path"),
                theme_picker(),
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
    )


def empty_shell(view: EmptyPageView) -> ComponentType:
    return html.main(
        sse_reload_listener(view.live_fragment_href),
        html.div(
            html.h1("No markdown files found"),
            theme_picker(),
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
    )


def base_document(title: str, body_content: ComponentType, favicon_href: str | None = None) -> Component:
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
                html.link(rel="stylesheet", href=public_asset_href("css/app.css")),
                html.script(src=public_asset_href("js/theme.js")),
                html.script(src=public_asset_href("js/favicon.js"), defer=True),
            ),
            html.body(
                body_content,
                html.script(src=public_asset_href("vendor/htmx.min.js")),
                html.script(src=public_asset_href("vendor/sse.js")),
            ),
            lang="en",
        ),
    )


def render_docs_page(view: DocsPageView) -> Component:
    return base_document(f"{view.title} · markserv", docs_shell(view), favicon_href=icon_href(view.rel_path))


def render_empty_page(view: EmptyPageView) -> Component:
    return base_document("markserv", empty_shell(view))


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
