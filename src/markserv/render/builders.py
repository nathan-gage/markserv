from __future__ import annotations

from ..content import PageIndex, SiteSource, humanize_name
from ..markdown import render_markdown
from .models import EMPTY_NAVIGATION_STATE, DocsPageView, EmptyPageView, NavigationState, SidebarView
from .support import docs_href, enhance_markdown_links, extract_title


def build_empty_view(site: SiteSource, *, dev_reload: bool = False) -> EmptyPageView:
    return EmptyPageView(root_dir=site.root_label, dev_reload=dev_reload)


def build_docs_view(
    site: SiteSource,
    page_index: PageIndex,
    rel_path: str,
    markdown_text: str,
    *,
    navigation: NavigationState = EMPTY_NAVIGATION_STATE,
    dev_reload: bool = False,
) -> DocsPageView:
    page = page_index.page_for(rel_path)
    fallback_title = humanize_name(rel_path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    title = (
        page.title
        if page is not None and page.title is not None
        else extract_title(markdown_text, fallback=fallback_title)
    )
    home_doc = page_index.choose_default_doc(preferred=site.default_doc)
    nav_items = page_index.nav_items(rel_path, open_paths=navigation.open_paths, nav_state_explicit=navigation.explicit)

    sidebar = None
    if site.show_navigation and nav_items:
        sidebar = SidebarView(
            config_name=site.name,
            root_dir=site.root_label,
            home_href=None if home_doc is None else docs_href(home_doc),
            navigation=navigation,
            items=nav_items,
        )

    rendered_markdown = enhance_markdown_links(
        render_markdown(markdown_text),
        rel_path,
        navigation.open_paths,
        nav_state_explicit=navigation.explicit,
    )

    return DocsPageView(
        title=title,
        rel_path=rel_path,
        rendered_markdown=rendered_markdown,
        sidebar=sidebar,
        dev_reload=dev_reload,
    )
