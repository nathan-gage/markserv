from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from .site import MarkdownPage, PageIndex, SiteSource, humanize_name

ATX_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
IMAGE_LINK_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
AUTOLINK_RE = re.compile(r"<((?:https?|mailto):[^>]+)>")
INLINE_CODE_RE = re.compile(r"`+")
BLOCK_PREFIX_RE = re.compile(r"^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+\.\s+)", re.MULTILINE)
TABLE_PIPE_RE = re.compile(r"\|")
WHITESPACE_RE = re.compile(r"\s+")
BOUNDARY_CHARS = " /._-#:([]"


@dataclass(frozen=True)
class SearchResult:
    title: str
    rel_path: str
    href: str
    snippet: str | None

    def to_payload(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "rel_path": self.rel_path,
            "href": self.href,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class IndexedPage:
    rel_path: str
    title: str
    label: str
    headings: tuple[str, ...]
    plain_text: str
    plain_text_folded: str
    path_folded: str
    title_folded: str
    label_folded: str
    headings_folded: tuple[str, ...]


class SearchIndex:
    def __init__(self, pages: tuple[IndexedPage, ...]) -> None:
        self.pages = pages

    def search(self, query: str, limit: int = 12) -> list[SearchResult]:
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return []

        terms = tuple(dict.fromkeys(normalized_query.split()))
        limit = max(1, min(limit, 50))
        ranked: list[tuple[int, SearchResult]] = []

        for page in self.pages:
            combined = " ".join(
                [
                    page.path_folded,
                    page.title_folded,
                    page.label_folded,
                    *page.headings_folded,
                    page.plain_text_folded,
                ]
            )
            if any(term not in combined for term in terms):
                continue

            heading_match = _best_heading_match(page.headings, page.headings_folded, normalized_query, terms)
            snippet = heading_match or _make_excerpt(page.plain_text, page.plain_text_folded, normalized_query, terms)

            score = 0
            score += _score_field(
                page.path_folded, normalized_query, terms, exact=220, prefix=150, phrase_score=110, term=50
            )
            score += _score_field(
                page.title_folded, normalized_query, terms, exact=210, prefix=140, phrase_score=100, term=46
            )
            score += _score_field(
                page.label_folded, normalized_query, terms, exact=180, prefix=120, phrase_score=85, term=38
            )
            score += _score_headings(page.headings_folded, normalized_query, terms)
            score += _score_field(
                page.plain_text_folded, normalized_query, terms, exact=0, prefix=0, phrase_score=36, term=11
            )

            if heading_match is not None:
                score += 18
            if snippet is not None:
                score += 4

            ranked.append(
                (
                    score,
                    SearchResult(
                        title=page.title,
                        rel_path=page.rel_path,
                        href=_docs_href(page.rel_path),
                        snippet=snippet,
                    ),
                )
            )

        ranked.sort(key=lambda item: (-item[0], item[1].rel_path.lower(), item[1].title.lower()))
        return [result for _score, result in ranked[:limit]]


def build_search_index(site: SiteSource, page_index: PageIndex) -> SearchIndex:
    indexed_pages: list[IndexedPage] = []

    for page in page_index.pages:
        markdown_text = site.read_markdown(page.rel_path)
        if markdown_text is None:
            continue

        headings = extract_markdown_headings(markdown_text)
        title = _page_title(page, headings)
        plain_text = markdown_to_plain_text(markdown_text)
        indexed_pages.append(
            IndexedPage(
                rel_path=page.rel_path,
                title=title,
                label=page.label,
                headings=headings,
                plain_text=plain_text,
                plain_text_folded=_normalize_text(plain_text),
                path_folded=_normalize_text(page.rel_path),
                title_folded=_normalize_text(title),
                label_folded=_normalize_text(page.label),
                headings_folded=tuple(_normalize_text(heading) for heading in headings),
            )
        )

    return SearchIndex(tuple(indexed_pages))


def extract_markdown_headings(markdown_text: str) -> tuple[str, ...]:
    headings: list[str] = []
    in_fence = False
    fence_marker = ""

    for line in markdown_text.splitlines():
        fence_match = FENCE_RE.match(line)
        if fence_match is not None:
            marker = fence_match.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue

        if in_fence:
            continue

        heading_match = ATX_HEADING_RE.match(line)
        if heading_match is None:
            continue

        heading = _clean_inline_markdown(heading_match.group(2))
        if heading:
            headings.append(heading)

    return tuple(headings)


def markdown_to_plain_text(markdown_text: str) -> str:
    text = IMAGE_LINK_RE.sub(r"\1", markdown_text)
    text = INLINE_LINK_RE.sub(r"\1", text)
    text = AUTOLINK_RE.sub(r"\1", text)
    text = INLINE_CODE_RE.sub(" ", text)
    text = BLOCK_PREFIX_RE.sub("", text)
    text = TABLE_PIPE_RE.sub(" ", text)
    text = text.replace("---", " ")
    text = text.replace("***", " ")
    text = text.replace("___", " ")
    return WHITESPACE_RE.sub(" ", text).strip()


def _page_title(page: MarkdownPage, headings: tuple[str, ...]) -> str:
    fallback_label = humanize_name(page.rel_path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    if page.title is not None:
        return page.title
    if page.label and page.label != fallback_label:
        return page.label
    if headings:
        return headings[0]
    return page.label or fallback_label


def _docs_href(rel_path: str) -> str:
    return f"/docs/{quote(rel_path, safe='/')}"


def _normalize_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value.casefold()).strip()


def _clean_inline_markdown(value: str) -> str:
    cleaned = IMAGE_LINK_RE.sub(r"\1", value)
    cleaned = INLINE_LINK_RE.sub(r"\1", cleaned)
    cleaned = AUTOLINK_RE.sub(r"\1", cleaned)
    cleaned = INLINE_CODE_RE.sub("", cleaned)
    cleaned = cleaned.replace("*", "")
    cleaned = cleaned.replace("_", "")
    cleaned = cleaned.replace("~", "")
    cleaned = cleaned.replace("[", "")
    cleaned = cleaned.replace("]", "")
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def _score_headings(headings: tuple[str, ...], phrase: str, terms: tuple[str, ...]) -> int:
    if not headings:
        return 0
    return max(
        _score_field(heading, phrase, terms, exact=160, prefix=110, phrase_score=78, term=30) for heading in headings
    )


def _score_field(
    field: str,
    phrase: str,
    terms: tuple[str, ...],
    *,
    exact: int,
    prefix: int,
    phrase_score: int,
    term: int,
) -> int:
    if not field:
        return 0

    score = 0
    if exact and field == phrase:
        score += exact
    elif prefix and field.startswith(phrase):
        score += prefix
    elif phrase_score and phrase in field:
        score += phrase_score

    for search_term in terms:
        position = field.find(search_term)
        if position < 0:
            continue
        score += term
        if position == 0 or field[position - 1] in BOUNDARY_CHARS:
            score += max(4, term // 3)

    return score


def _best_heading_match(
    headings: tuple[str, ...], headings_folded: tuple[str, ...], phrase: str, terms: tuple[str, ...]
) -> str | None:
    scored: list[tuple[int, str]] = []
    for heading, heading_folded in zip(headings, headings_folded, strict=False):
        if phrase not in heading_folded and any(term not in heading_folded for term in terms):
            continue
        scored.append(
            (-_score_field(heading_folded, phrase, terms, exact=10, prefix=8, phrase_score=6, term=3), heading)
        )
    if not scored:
        return None
    scored.sort()
    return scored[0][1]


def _make_excerpt(body_text: str, body_text_folded: str, phrase: str, terms: tuple[str, ...]) -> str | None:
    if not body_text:
        return None

    index = body_text_folded.find(phrase)
    if index < 0:
        positions = [body_text_folded.find(term) for term in terms if term]
        positions = [position for position in positions if position >= 0]
        if not positions:
            return None
        index = min(positions)

    start = max(0, index - 48)
    end = min(len(body_text), index + max(len(phrase), 24) + 88)
    excerpt = body_text[start:end].strip()
    if not excerpt:
        return None
    if start > 0:
        excerpt = f"…{excerpt}"
    if end < len(body_text):
        excerpt = f"{excerpt}…"
    return excerpt
