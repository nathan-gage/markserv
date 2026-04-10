from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, TypeAlias
from urllib.parse import quote

from ignoretree import IgnoreResolver

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".mkdn"}
DEFAULT_IGNORE_PATTERNS = [".git/"]
DIRECTORY_DEFAULT_BASENAMES = ("README", "readme", "index", "INDEX")


class SitePathError(LookupError):
    pass


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


@dataclass(frozen=True)
class PageIndex:
    pages: tuple[MarkdownPage, ...]

    def choose_default_doc(self, preferred: str | None = None, prefix: str = "") -> str | None:
        normalized_prefix = prefix.strip("/")
        if normalized_prefix:
            base_prefix = f"{normalized_prefix}/"
            candidates = [page.rel_path for page in self.pages if page.rel_path.startswith(base_prefix)]
        else:
            candidates = [page.rel_path for page in self.pages]

        if not candidates:
            return None

        candidate_set = set(candidates)
        if preferred and preferred in candidate_set:
            return preferred

        for basename in DIRECTORY_DEFAULT_BASENAMES:
            for suffix in sorted(MARKDOWN_SUFFIXES):
                candidate = f"{normalized_prefix}/{basename}{suffix}" if normalized_prefix else f"{basename}{suffix}"
                if candidate in candidate_set:
                    return candidate

        return sorted(candidates, key=lambda value: (value.count("/"), value.lower()))[0]

    def nav_items(self, current_rel: str) -> tuple[NavNode, ...]:
        return _build_nav_nodes(_build_nav_tree(self.pages), current_rel)

    def has_directory(self, rel_path: str) -> bool:
        normalized_path = rel_path.strip("/")
        if not normalized_path:
            return bool(self.pages)
        base_prefix = f"{normalized_path}/"
        return any(page.rel_path.startswith(base_prefix) for page in self.pages)


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
        return path.read_text(encoding="utf-8", errors="replace")

    def resolve_asset(self, rel_path: str) -> Path | None:
        path = self._resolve_path(rel_path)
        if path is None or not path.exists() or not path.is_file() or is_markdown_path(path):
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


@dataclass(slots=True)
class SyntheticSite:
    name: str
    root_label: str
    documents: dict[str, str]
    default_doc: str | None = None
    show_navigation: bool = True
    watch_root: Path | None = field(init=False, default=None)
    watch_filter: WatchPathFilter | None = field(init=False, default=None)
    _page_index: PageIndex = field(init=False, repr=False)

    def __post_init__(self) -> None:
        normalized_documents: dict[str, str] = {}
        for raw_path, markdown_text in self.documents.items():
            rel_path = normalize_rel_path(raw_path)
            if not rel_path or not is_markdown_path(Path(rel_path)):
                raise ValueError(f"Synthetic document path must be markdown: {raw_path}")
            normalized_documents[rel_path] = markdown_text

        self.documents = normalized_documents
        if self.default_doc is not None:
            self.default_doc = normalize_rel_path(self.default_doc)

        self._page_index = PageIndex(
            tuple(
                MarkdownPage(rel_path=rel_path, label=humanize_name(Path(rel_path).stem) + Path(rel_path).suffix)
                for rel_path in sorted(self.documents, key=str.lower)
            )
        )

    def page_index(self) -> PageIndex:
        return self._page_index

    def read_markdown(self, rel_path: str) -> str | None:
        return self.documents.get(rel_path)

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


def choose_root_for_file(file_path: Path, cwd: Path) -> Path:
    if not file_path.is_relative_to(cwd):
        return file_path.parent

    chosen = file_path.parent
    current = file_path.parent
    while True:
        if (current / ".git").exists() or (current / ".gitignore").exists():
            chosen = current
        if current == cwd:
            return chosen
        current = current.parent


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
            pages.append(MarkdownPage(rel_path=rel_path, label=humanize_name(path.stem)))

    return pages


def humanize_name(stem: str) -> str:
    value = stem.replace("_", " ").replace("-", " ").strip()
    return value if value else stem


def is_markdown_path(path: Path) -> bool:
    return path.suffix.lower() in MARKDOWN_SUFFIXES


def normalize_rel_path(raw_path: str) -> str:
    cleaned = raw_path.replace("\\", "/").strip("/")
    parts = []
    for part in PurePosixPath(cleaned).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise SitePathError("Not found")
        parts.append(part)
    return "/".join(parts)


def resolve_rooted_path(root_dir: Path, rel_path: str) -> Path:
    root = root_dir.resolve()
    candidate = root.joinpath(*([part for part in rel_path.split("/") if part] or ["."]))
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SitePathError("Not found") from exc
    return resolved


def _build_nav_tree(pages: Iterable[MarkdownPage]) -> NavTree:
    root: NavTree = {}
    for page in pages:
        node: NavTree = root
        parts = page.rel_path.split("/")
        for part in parts[:-1]:
            existing = node.get(part)
            if isinstance(existing, MarkdownPage):
                break
            if existing is None:
                child: NavTree = {}
                node[part] = child
                node = child
                continue
            node = existing
        else:
            node[parts[-1]] = page
    return root


def _build_nav_nodes(tree: NavTree, current_rel: str, prefix: str = "") -> tuple[NavNode, ...]:
    directories: list[tuple[str, NavTree]] = []
    files_only: list[MarkdownPage] = []

    for name, child in tree.items():
        if isinstance(child, MarkdownPage):
            files_only.append(child)
        else:
            directories.append((name, child))

    items: list[NavNode] = []
    for directory_name, child_tree in sorted(directories, key=lambda item: item[0].lower()):
        rel_dir = f"{prefix}/{directory_name}" if prefix else directory_name
        items.append(
            NavDirectory(
                name=directory_name,
                open=current_rel.startswith(f"{rel_dir}/"),
                children=_build_nav_nodes(child_tree, current_rel, rel_dir),
            )
        )

    for page in sorted(files_only, key=lambda item: item.rel_path.lower()):
        items.append(
            NavFile(
                label=page.label,
                href=f"/docs/{quote(page.rel_path, safe='/')}",
                active=page.rel_path == current_rel,
            )
        )

    return tuple(items)
