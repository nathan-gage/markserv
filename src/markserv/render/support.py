from __future__ import annotations

import re
from collections.abc import Sequence
from html import escape as html_escape
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

from ..content import is_markdown_path

TITLE_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$", re.MULTILINE)
ANCHOR_TAG_RE = re.compile(r"<a(?P<attrs>\s[^>]*)>", re.IGNORECASE)
HREF_ATTR_RE = re.compile(r'\shref="([^"]+)"')
NAV_QUERY_PARAM = "nav"
NAV_STATE_QUERY_PARAM = "nav_state"
SIDEBAR_STATE_FORM_ID = "sidebar-state"
MAIN_SHELL_ID = "main-shell"
SIDEBAR_SHELL_ID = "sidebar-shell"


def extract_title(markdown_text: str, fallback: str) -> str:
    match = TITLE_RE.search(markdown_text)
    if not match:
        return fallback
    title = match.group(1).strip().strip("#").strip()
    return title or fallback


def _encode_query_pairs(pairs: Sequence[tuple[str, str]]) -> str:
    return urlencode(pairs, doseq=True, safe="/", quote_via=quote)


def with_nav_open_paths(
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
    return with_nav_open_paths(
        f"/docs/{quote(rel_path, safe='/')}",
        nav_open_paths,
        nav_state_explicit=nav_state_explicit,
    )


def public_asset_href(rel_path: str) -> str:
    return f"/public/{quote(rel_path, safe='/')}"


def icon_href(rel_path: str) -> str:
    return f"/icons/docs/{quote(rel_path, safe='/')}"


def htmx_request_href(href: str) -> str | None:
    split = urlsplit(href)
    if not split.path.startswith("/docs/"):
        return None
    request_href = split.path
    if split.query:
        request_href = f"{request_href}?{split.query}"
    return request_href


def htmx_nav_attrs(href: str) -> dict[str, str]:
    request_href = htmx_request_href(href)
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


def htmx_sidebar_attrs(href: str) -> dict[str, str]:
    request_href = htmx_request_href(href)
    if request_href is None:
        return {}
    return {
        "hx_get": request_href,
        "hx_target": f"#{SIDEBAR_SHELL_ID}",
        "hx_select": f"#{SIDEBAR_SHELL_ID}",
        "hx_swap": "outerHTML",
    }


def htmx_nav_html_attrs(href: str) -> str:
    attrs = htmx_nav_attrs(href)
    return "".join(f' {name.replace("_", "-")}="{html_escape(value, quote=True)}"' for name, value in attrs.items())


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


def enhance_markdown_links(
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
            f' href="{html_escape(docs_target_href, quote=True)}"',
            attrs,
            count=1,
        )
        return f"<a{updated_attrs}{htmx_nav_html_attrs(docs_target_href)}>"

    return ANCHOR_TAG_RE.sub(replace, rendered_html)
