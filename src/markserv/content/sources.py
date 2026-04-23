from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ignoretree import IgnoreResolver

from ..markdown import MarkdownDocument, MarkdownFrontMatter, parse_markdown_document
from .models import MarkdownPage, PageIndex, ServeConfig
from .paths import (
    DEFAULT_IGNORE_PATTERNS,
    SitePathError,
    choose_root_for_file,
    humanize_name,
    is_markdown_path,
    is_safe_asset_path,
    normalize_rel_path,
    resolve_rooted_path,
)


class WatchPathFilter:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.refresh()

    def refresh(self) -> None:
        self.resolver = build_ignore_resolver(self.root_dir)
        self.resolver.load_all()

    def _to_rel_path(self, path: str) -> str | None:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root_dir / candidate

        try:
            resolved = candidate.resolve(strict=False)
            relative = resolved.relative_to(self.root_dir)
        except ValueError:
            return None

        rel_path = relative.as_posix()
        return rel_path or None

    def __call__(self, _change: object, path: str) -> bool:
        rel_path = self._to_rel_path(path)
        if rel_path is None:
            return False
        if rel_path == ".git" or rel_path.startswith(".git/"):
            return False
        if rel_path.endswith("/.gitignore") or rel_path == ".gitignore":
            return True
        if self.resolver.is_ignored(rel_path, auto_enter=True) or self.resolver.is_dir_ignored(
            rel_path, auto_enter=True
        ):
            return False
        return is_markdown_path(Path(rel_path))


@dataclass(slots=True)
class FileSite:
    config: ServeConfig
    name: str = field(init=False)
    root_label: str = field(init=False)
    default_doc: str | None = field(init=False)
    show_navigation: bool = field(init=False)
    watch_root: Path | None = field(init=False)
    watch_filter: WatchPathFilter | None = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.config.source.name
        self.root_label = str(self.config.root_dir)
        self.default_doc = self.config.default_doc
        self.show_navigation = self.config.mode == "directory"
        self.watch_root = self.config.root_dir
        self.watch_filter = WatchPathFilter(self.config.root_dir)

    def page_index(self) -> PageIndex:
        return PageIndex(tuple(discover_pages(self.config.root_dir)))

    def read_markdown(self, rel_path: str) -> str | None:
        path = self._resolve_path(rel_path)
        if path is None or not path.exists() or not path.is_file() or not is_markdown_path(path):
            return None
        return self._read_document(path).body

    def resolve_asset(self, rel_path: str) -> Path | None:
        path = self._resolve_path(rel_path)
        if path is None or not path.exists() or not path.is_file() or is_markdown_path(path):
            return None
        if not is_safe_asset_path(rel_path):
            return None
        return path

    def is_directory(self, rel_path: str) -> bool:
        path = self._resolve_path(rel_path, allow_directory=True)
        return path is not None and path.exists() and path.is_dir()

    def _resolve_path(self, rel_path: str, *, allow_directory: bool = False) -> Path | None:
        try:
            normalized_path = normalize_rel_path(rel_path)
            path = resolve_rooted_path(self.config.root_dir, normalized_path)
        except SitePathError:
            return None

        if normalized_path and self._is_ignored(normalized_path, is_dir=path.is_dir()):
            return None
        if path.is_dir() and not allow_directory:
            return None
        return path

    def _is_ignored(self, rel_path: str, *, is_dir: bool) -> bool:
        resolver = build_ignore_resolver(self.config.root_dir)
        if is_dir:
            return resolver.is_dir_ignored(rel_path, auto_enter=True)
        return resolver.is_ignored(rel_path, auto_enter=True)

    def _read_document(self, path: Path) -> MarkdownDocument:
        return parse_markdown_document(path.read_text(encoding="utf-8", errors="replace"))


@dataclass(slots=True)
class SyntheticSite:
    name: str
    root_label: str
    documents: dict[str, str]
    default_doc: str | None = None
    show_navigation: bool = True
    watch_root: Path | None = field(init=False, default=None)
    watch_filter: WatchPathFilter | None = field(init=False, default=None)
    _parsed_documents: dict[str, MarkdownDocument] = field(init=False, repr=False)
    _document_bodies: dict[str, str] = field(init=False, repr=False)
    _page_index: PageIndex = field(init=False, repr=False)

    def __post_init__(self) -> None:
        normalized_sources: dict[str, str] = {}
        normalized_documents: dict[str, MarkdownDocument] = {}
        for raw_path, markdown_text in self.documents.items():
            rel_path = normalize_rel_path(raw_path)
            if not rel_path or not is_markdown_path(Path(rel_path)):
                raise ValueError(f"Synthetic document path must be markdown: {raw_path}")
            normalized_sources[rel_path] = markdown_text
            normalized_documents[rel_path] = parse_markdown_document(markdown_text)

        self.documents = normalized_sources
        self._parsed_documents = normalized_documents
        self._document_bodies = {rel_path: document.body for rel_path, document in normalized_documents.items()}
        if self.default_doc is not None:
            self.default_doc = normalize_rel_path(self.default_doc)

        self._page_index = PageIndex(
            tuple(
                build_markdown_page(rel_path, Path(rel_path).stem, document.front_matter)
                for rel_path, document in sorted(self._parsed_documents.items(), key=lambda item: item[0].lower())
            )
        )

    @property
    def document_bodies(self) -> dict[str, str]:
        return dict(self._document_bodies)

    def page_index(self) -> PageIndex:
        return self._page_index

    def read_markdown(self, rel_path: str) -> str | None:
        return self._document_bodies.get(rel_path)

    def resolve_asset(self, rel_path: str) -> Path | None:
        return None

    def is_directory(self, rel_path: str) -> bool:
        return self._page_index.has_directory(rel_path)


def build_config(target: Path, cwd: Path | None = None) -> ServeConfig:
    source = target.expanduser().resolve()
    if not source.exists():
        raise ValueError(f"Path does not exist: {target}")

    if source.is_dir():
        return ServeConfig(source=source, root_dir=source, mode="directory", default_doc=None)

    if not source.is_file() or not is_markdown_path(source):
        raise ValueError(f"Path is not a markdown file: {target}")

    working_dir = (cwd or Path.cwd()).resolve()
    root_dir = choose_root_for_file(source, working_dir)
    default_doc = source.relative_to(root_dir).as_posix()
    return ServeConfig(source=source, root_dir=root_dir, mode="single", default_doc=default_doc)


def build_file_site(config: ServeConfig) -> FileSite:
    return FileSite(config)


def build_ignore_resolver(root_dir: Path) -> IgnoreResolver:
    return IgnoreResolver(root_dir, default_patterns=DEFAULT_IGNORE_PATTERNS)


def discover_pages(root_dir: Path) -> list[MarkdownPage]:
    resolver = build_ignore_resolver(root_dir)
    pages: list[MarkdownPage] = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        current_dir = Path(dirpath)
        rel_dir = os.path.relpath(current_dir, root_dir).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""

        resolver.enter_directory(rel_dir)
        dirnames[:] = [
            directory
            for directory in sorted(dirnames, key=str.lower)
            if not resolver.is_dir_ignored(f"{rel_dir}/{directory}" if rel_dir else directory)
        ]

        for filename in sorted(filenames, key=str.lower):
            rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
            if resolver.is_ignored(rel_path):
                continue
            path = current_dir / filename
            if not is_markdown_path(path):
                continue
            pages.append(
                build_markdown_page(
                    rel_path,
                    path.stem,
                    parse_markdown_document(path.read_text(encoding="utf-8", errors="replace")).front_matter,
                )
            )

    return pages


def build_markdown_page(rel_path: str, fallback_stem: str, front_matter: MarkdownFrontMatter) -> MarkdownPage:
    label = front_matter.nav_label or front_matter.title or humanize_name(fallback_stem)
    return MarkdownPage(
        rel_path=rel_path,
        label=label,
        title=front_matter.title,
        nav_order=front_matter.nav_order,
        hidden=front_matter.hidden,
    )
