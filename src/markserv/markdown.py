from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape, unescape
from typing import cast

import cmarkgfm
import yaml
from cmarkgfm.cmark import Options
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexer import Lexer
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

CMARK_OPTIONS = Options.CMARK_OPT_GITHUB_PRE_LANG | Options.CMARK_OPT_SMART
FRONT_MATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<block>.*?)(?:\r?\n)(?:---|\.\.\.)[ \t]*(?:\r?\n|$)",
    re.DOTALL,
)
HEADING_RE = re.compile(r"<h(?P<level>[1-6])(?P<attrs>[^>]*)>(?P<content>.*?)</h(?P=level)>", re.DOTALL)
CODE_BLOCK_RE = re.compile(r"<pre(?P<attrs>[^>]*)><code>(?P<code>.*?)</code></pre>", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
ID_ATTR_RE = re.compile(r'\bid="([^"]+)"')
CLASS_ATTR_RE = re.compile(r'class="([^"]*)"')
LANG_ATTR_RE = re.compile(r'\slang="([^"]+)"')
WORD_BREAK_RE = re.compile(r"[\s_]+")
NON_SLUG_RE = re.compile(r"[^\w\- ]+", re.UNICODE)
PYGMENTS_HTML_FORMATTER = HtmlFormatter(nowrap=True)
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
ANCHOR_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'class="anchor-icon lucide lucide-link-icon lucide-link" aria-hidden="true">'
    '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
    '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'
    "</svg>"
)


@dataclass(frozen=True)
class MarkdownFrontMatter:
    title: str | None = None
    nav_label: str | None = None
    nav_order: float | None = None
    hidden: bool = False


@dataclass(frozen=True)
class MarkdownDocument:
    body: str
    front_matter: MarkdownFrontMatter = MarkdownFrontMatter()


def parse_markdown_document(markdown_text: str) -> MarkdownDocument:
    match = FRONT_MATTER_RE.match(markdown_text)
    if match is None:
        return MarkdownDocument(body=markdown_text)

    mapping = _parse_front_matter_mapping(match.group("block"))
    if mapping is None:
        return MarkdownDocument(body=markdown_text)

    return MarkdownDocument(
        body=markdown_text[match.end() :],
        front_matter=_front_matter_from_mapping(mapping),
    )


def render_markdown(markdown_text: str) -> str:
    rendered_html = cmarkgfm.github_flavored_markdown_to_html(markdown_text, options=CMARK_OPTIONS)
    rendered_html = _highlight_code_blocks(rendered_html)
    return _add_heading_anchors(rendered_html)


def _parse_front_matter_mapping(block: str) -> dict[str, object] | None:
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        return None

    if loaded is None:
        return {} if _is_empty_yaml_block(block) else None
    if not isinstance(loaded, dict):
        return None

    data: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            continue
        data[key.strip().lower()] = value
    return data


def _is_empty_yaml_block(block: str) -> bool:
    return all(not line.strip() or line.lstrip().startswith("#") for line in block.splitlines())


def _front_matter_from_mapping(data: dict[str, object]) -> MarkdownFrontMatter:
    nav_label_value = data.get("nav_label", data.get("sidebar_label", data.get("label")))
    nav_order_value = data.get("nav_order", data.get("order"))
    hidden_value = data["hidden"] if "hidden" in data else data.get("nav_hidden")

    return MarkdownFrontMatter(
        title=_string_value(data.get("title")),
        nav_label=_string_value(nav_label_value),
        nav_order=_float_value(nav_order_value),
        hidden=_bool_value(hidden_value),
    )


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _float_value(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUE_VALUES:
            return True
        if lowered in FALSE_VALUES:
            return False
    return False


def _highlight_code_blocks(rendered_html: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_pre_attrs = match.group("attrs")
        language = _extract_language(raw_pre_attrs)
        pre_attrs = _append_class_attr(_strip_language_attr(raw_pre_attrs), "highlight")
        if language is not None:
            pre_attrs = _set_attr(pre_attrs, "data-language", language)

        code_text = unescape(match.group("code"))
        lexer = _lexer_for_language(language)
        highlighted = highlight(code_text, lexer, PYGMENTS_HTML_FORMATTER)

        code_attrs = ""
        if language is not None:
            language_class = escape(_language_class_name(language), quote=True)
            code_attrs = f' class="{language_class}"'

        return f"<pre{pre_attrs}><code{code_attrs}>{highlighted}</code></pre>"

    return CODE_BLOCK_RE.sub(replace, rendered_html)


def _extract_language(attrs: str) -> str | None:
    match = LANG_ATTR_RE.search(attrs)
    if match is None:
        return None

    language = match.group(1).strip().split(maxsplit=1)[0]
    return language or None


def _strip_language_attr(attrs: str) -> str:
    return LANG_ATTR_RE.sub("", attrs)


def _lexer_for_language(language: str | None) -> Lexer:
    if language is None:
        return cast(Lexer, TextLexer())
    try:
        return get_lexer_by_name(language)
    except ClassNotFound:
        return cast(Lexer, TextLexer())


def _language_class_name(language: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_+-]+", "-", language.strip().lower()).strip("-")
    return f"language-{normalized or 'text'}"


def _add_heading_anchors(rendered_html: str) -> str:
    slug_counts: dict[str, int] = {}

    def replace(match: re.Match[str]) -> str:
        level = match.group("level")
        attrs = match.group("attrs")
        content = match.group("content")
        if '<a class="anchor' in content:
            return match.group(0)

        heading_text = _heading_text(content)
        heading_id = _get_or_create_heading_id(attrs, heading_text, slug_counts)
        attrs_with_id = _set_attr(attrs, "id", heading_id)
        attrs_with_id = _append_class_attr(attrs_with_id, "heading-element")
        escaped_id = escape(heading_id, quote=True)
        escaped_label = escape(f"Permalink: {heading_text}", quote=True)
        anchor = f'<a class="anchor hit-area-1" href="#{escaped_id}" aria-label="{escaped_label}">{ANCHOR_ICON_SVG}</a>'
        return f"<h{level}{attrs_with_id}>{anchor}{content}</h{level}>"

    return HEADING_RE.sub(replace, rendered_html)


def _heading_text(content: str) -> str:
    text = unescape(TAG_RE.sub("", content))
    text = WORD_BREAK_RE.sub(" ", text).strip()
    return text or "Section"


def _get_or_create_heading_id(attrs: str, heading_text: str, slug_counts: dict[str, int]) -> str:
    existing_id = _attr_value(attrs, ID_ATTR_RE)
    if existing_id is not None:
        return existing_id

    base_slug = _slugify(heading_text)
    count = slug_counts.get(base_slug, 0)
    slug_counts[base_slug] = count + 1
    return base_slug if count == 0 else f"{base_slug}-{count}"


def _slugify(value: str) -> str:
    normalized = unescape(value).strip().lower()
    normalized = NON_SLUG_RE.sub("", normalized)
    normalized = WORD_BREAK_RE.sub("-", normalized)
    normalized = normalized.strip("-")
    return normalized or "section"


def _attr_value(attrs: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(attrs)
    if match is None:
        return None
    value = match.group(1).strip()
    return value or None


def _append_class_attr(attrs: str, class_name: str) -> str:
    match = CLASS_ATTR_RE.search(attrs)
    if match is None:
        return f'{attrs} class="{class_name}"'

    classes = match.group(1).split()
    if class_name in classes:
        return attrs

    updated = " ".join([*classes, class_name])
    return f"{attrs[: match.start(1)]}{updated}{attrs[match.end(1) :]}"


def _set_attr(attrs: str, name: str, value: str) -> str:
    attr_re = re.compile(rf'{name}="[^"]*"')
    escaped_value = escape(value, quote=True)
    replacement = f'{name}="{escaped_value}"'
    if attr_re.search(attrs) is not None:
        return attr_re.sub(replacement, attrs, count=1)
    return f"{attrs} {replacement}"
