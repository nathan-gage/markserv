from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias

from .paths import DIRECTORY_DEFAULT_BASENAMES, MARKDOWN_SUFFIXES

if TYPE_CHECKING:
    from .sources import WatchPathFilter


@dataclass(frozen=True, slots=True)
class ServeConfig:
    source: Path
    root_dir: Path
    mode: Literal["directory", "single"]
    default_doc: str | None


@dataclass(frozen=True, slots=True)
class MarkdownPage:
    rel_path: str
    label: str
    title: str | None = None
    nav_order: float | None = None
    hidden: bool = False


NavValue: TypeAlias = "NavTree | MarkdownPage"
NavTree: TypeAlias = dict[str, NavValue]


@dataclass(frozen=True, slots=True)
class NavFile:
    kind: Literal["file"] = "file"
    label: str = ""
    href: str = ""
    rel_path: str = ""


@dataclass(frozen=True, slots=True)
class NavDirectory:
    kind: Literal["dir"] = "dir"
    name: str = ""
    path: str = ""
    files: tuple[NavFile, ...] = field(default_factory=tuple)
    directories: tuple[NavDirectory, ...] = field(default_factory=tuple)


NavNode: TypeAlias = NavDirectory | NavFile


class SiteSource(Protocol):
    name: str
    root_label: str
    default_doc: str | None
    show_navigation: bool
    watch_root: Path | None
    watch_filter: WatchPathFilter | None

    def page_index(self) -> PageIndex: ...

    def read_markdown(self, rel_path: str) -> str | None: ...

    def resolve_asset(self, rel_path: str) -> Path | None: ...

    def is_directory(self, rel_path: str) -> bool: ...


@dataclass(frozen=True)
class PageIndex:
    pages: tuple[MarkdownPage, ...]
    _page_by_rel_path: dict[str, MarkdownPage] = field(init=False, repr=False, compare=False, hash=False)
    _pages_by_prefix: dict[str, tuple[MarkdownPage, ...]] = field(init=False, repr=False, compare=False, hash=False)
    _page_paths_by_prefix: dict[str, frozenset[str]] = field(init=False, repr=False, compare=False, hash=False)
    _default_doc_by_prefix: dict[str, str | None] = field(init=False, repr=False, compare=False, hash=False)
    _directory_paths: tuple[str, ...] = field(init=False, repr=False, compare=False, hash=False)
    _directory_path_set: frozenset[str] = field(init=False, repr=False, compare=False, hash=False)
    _nav_items: tuple[NavNode, ...] = field(init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        from .navigation import build_nav_items

        page_by_rel_path: dict[str, MarkdownPage] = {page.rel_path: page for page in self.pages}
        pages_by_prefix_lists: dict[str, list[MarkdownPage]] = {"": []}
        visible_directory_paths: set[str] = set()
        all_directory_paths: set[str] = set()
        visible_pages: list[MarkdownPage] = []

        for page in self.pages:
            pages_by_prefix_lists[""].append(page)
            if not page.hidden:
                visible_pages.append(page)

            parts = page.rel_path.split("/")
            for index in range(1, len(parts)):
                prefix = "/".join(parts[:index])
                pages_by_prefix_lists.setdefault(prefix, []).append(page)
                all_directory_paths.add(prefix)
                if not page.hidden:
                    visible_directory_paths.add(prefix)

        pages_by_prefix = {prefix: tuple(pages) for prefix, pages in pages_by_prefix_lists.items()}
        page_paths_by_prefix = {
            prefix: frozenset(page.rel_path for page in pages) for prefix, pages in pages_by_prefix.items()
        }
        default_doc_by_prefix = {
            prefix: _default_doc_from_candidate_pages(prefix, pages) for prefix, pages in pages_by_prefix.items()
        }

        object.__setattr__(self, "_page_by_rel_path", page_by_rel_path)
        object.__setattr__(self, "_pages_by_prefix", pages_by_prefix)
        object.__setattr__(self, "_page_paths_by_prefix", page_paths_by_prefix)
        object.__setattr__(self, "_default_doc_by_prefix", default_doc_by_prefix)
        object.__setattr__(
            self,
            "_directory_paths",
            tuple(sorted(visible_directory_paths, key=lambda path: (path.count("/"), path.casefold()))),
        )
        object.__setattr__(self, "_directory_path_set", frozenset(all_directory_paths))
        object.__setattr__(self, "_nav_items", build_nav_items(tuple(visible_pages)))

    def choose_default_doc(self, preferred: str | None = None, prefix: str = "") -> str | None:
        normalized_prefix = prefix.strip("/")
        candidate_paths = self._page_paths_by_prefix.get(normalized_prefix)
        if not candidate_paths:
            return None

        if preferred and preferred in candidate_paths:
            return preferred
        return self._default_doc_by_prefix[normalized_prefix]

    def nav_items(
        self,
        current_rel: str | None = None,
        open_paths: tuple[str, ...] = (),
        *,
        nav_state_explicit: bool = False,
    ) -> tuple[NavNode, ...]:
        del current_rel, open_paths, nav_state_explicit
        return self._nav_items

    def directory_paths(self) -> tuple[str, ...]:
        return self._directory_paths

    def has_directory(self, rel_path: str) -> bool:
        normalized_path = rel_path.strip("/")
        if not normalized_path:
            return bool(self.pages)
        return normalized_path in self._directory_path_set

    def page_for(self, rel_path: str) -> MarkdownPage | None:
        return self._page_by_rel_path.get(rel_path)

    def candidate_pages(self, prefix: str = "") -> tuple[MarkdownPage, ...]:
        return self._pages_by_prefix.get(prefix.strip("/"), ())


def _default_doc_from_candidate_pages(normalized_prefix: str, candidate_pages: tuple[MarkdownPage, ...]) -> str | None:
    if not candidate_pages:
        return None

    preferred_pages = [page for page in candidate_pages if not page.hidden] or list(candidate_pages)
    preferred_set = {page.rel_path for page in preferred_pages}

    for basename in DIRECTORY_DEFAULT_BASENAMES:
        for suffix in sorted(MARKDOWN_SUFFIXES):
            candidate = f"{normalized_prefix}/{basename}{suffix}" if normalized_prefix else f"{basename}{suffix}"
            if candidate in preferred_set:
                return candidate

    return sorted(preferred_pages, key=lambda page: (page.rel_path.count("/"), *sort_markdown_page(page)))[0].rel_path


def sort_markdown_page(page: MarkdownPage) -> tuple[bool, float, str, str]:
    return (
        page.nav_order is None,
        0.0 if page.nav_order is None else page.nav_order,
        page.label.lower(),
        page.rel_path.lower(),
    )
