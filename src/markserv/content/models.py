from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias

from .paths import DIRECTORY_DEFAULT_BASENAMES, MARKDOWN_SUFFIXES

if TYPE_CHECKING:
    from .sources import WatchPathFilter


@dataclass(frozen=True)
class ServeConfig:
    source: Path
    root_dir: Path
    mode: Literal["directory", "single"]
    default_doc: str | None


@dataclass(frozen=True)
class MarkdownPage:
    rel_path: str
    label: str
    title: str | None = None
    nav_order: float | None = None
    hidden: bool = False


NavValue: TypeAlias = "NavTree | MarkdownPage"
NavTree: TypeAlias = dict[str, NavValue]


@dataclass(frozen=True)
class NavFile:
    kind: Literal["file"] = "file"
    label: str = ""
    href: str = ""
    active: bool = False


@dataclass(frozen=True)
class NavDirectory:
    kind: Literal["dir"] = "dir"
    name: str = ""
    path: str = ""
    open: bool = False
    children: tuple[NavNode, ...] = field(default_factory=tuple)


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

    def choose_default_doc(self, preferred: str | None = None, prefix: str = "") -> str | None:
        normalized_prefix = prefix.strip("/")
        candidate_pages = self._candidate_pages(normalized_prefix)
        if not candidate_pages:
            return None

        candidate_set = {page.rel_path for page in candidate_pages}
        if preferred and preferred in candidate_set:
            return preferred

        preferred_pages = [page for page in candidate_pages if not page.hidden] or candidate_pages
        preferred_set = {page.rel_path for page in preferred_pages}

        for basename in DIRECTORY_DEFAULT_BASENAMES:
            for suffix in sorted(MARKDOWN_SUFFIXES):
                candidate = f"{normalized_prefix}/{basename}{suffix}" if normalized_prefix else f"{basename}{suffix}"
                if candidate in preferred_set:
                    return candidate

        return sorted(preferred_pages, key=lambda page: (page.rel_path.count("/"), *sort_markdown_page(page)))[
            0
        ].rel_path

    def nav_items(
        self,
        current_rel: str,
        open_paths: tuple[str, ...] = (),
        *,
        nav_state_explicit: bool = False,
    ) -> tuple[NavNode, ...]:
        from .navigation import build_nav_nodes, build_nav_tree

        visible_pages = tuple(page for page in self.pages if not page.hidden)
        return build_nav_nodes(
            build_nav_tree(visible_pages),
            current_rel,
            open_paths=frozenset(open_paths),
            nav_state_explicit=nav_state_explicit,
        )

    def directory_paths(self) -> tuple[str, ...]:
        directories: set[str] = set()
        for page in self.pages:
            if page.hidden:
                continue
            parts = page.rel_path.split("/")
            for index in range(1, len(parts)):
                directories.add("/".join(parts[:index]))
        return tuple(sorted(directories, key=lambda path: (path.count("/"), path.casefold())))

    def has_directory(self, rel_path: str) -> bool:
        normalized_path = rel_path.strip("/")
        if not normalized_path:
            return bool(self.pages)
        base_prefix = f"{normalized_path}/"
        return any(page.rel_path.startswith(base_prefix) for page in self.pages)

    def page_for(self, rel_path: str) -> MarkdownPage | None:
        for page in self.pages:
            if page.rel_path == rel_path:
                return page
        return None

    def _candidate_pages(self, normalized_prefix: str) -> tuple[MarkdownPage, ...]:
        if not normalized_prefix:
            return self.pages

        base_prefix = f"{normalized_prefix}/"
        return tuple(page for page in self.pages if page.rel_path.startswith(base_prefix))


def sort_markdown_page(page: MarkdownPage) -> tuple[bool, float, str, str]:
    return (
        page.nav_order is None,
        0.0 if page.nav_order is None else page.nav_order,
        page.label.lower(),
        page.rel_path.lower(),
    )
