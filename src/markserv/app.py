from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import os
import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, TypeAlias
from urllib.parse import quote

import cmarkgfm
from cmarkgfm.cmark import Options
from fastapi import FastAPI, HTTPException
from fastapi import Response as FastAPIResponse
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fasthx.htmy import HTMY
from htmy import Component, ComponentType, Fragment, SafeStr, html
from ignoretree import IgnoreResolver
from watchfiles import awatch

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".mkdn"}
DEFAULT_IGNORE_PATTERNS = [".git/"]
DIRECTORY_DEFAULT_BASENAMES = ("README", "readme", "index", "INDEX")
CMARK_OPTIONS = Options.CMARK_OPT_GITHUB_PRE_LANG | Options.CMARK_OPT_SMART
NO_CACHE_HEADERS = {"Cache-Control": "no-store"}
TITLE_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$", re.MULTILINE)
PACKAGE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = PACKAGE_DIR / "public"


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


class ReloadBroker:
    def __init__(self) -> None:
        self._version = 0
        self._condition = asyncio.Condition()

    @property
    def version(self) -> int:
        return self._version

    async def publish(self) -> None:
        async with self._condition:
            self._version += 1
            self._condition.notify_all()

    async def wait_for_update(self, version: int, timeout: float = 15.0) -> tuple[int, bool]:
        async with self._condition:
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(lambda: self._version > version),
                    timeout=timeout,
                )
            except TimeoutError:
                return version, False
            return self._version, True


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
        return not (
            self.resolver.is_ignored(rel_path, auto_enter=True)
            or self.resolver.is_dir_ignored(rel_path, auto_enter=True)
        )


def build_ignore_resolver(root_dir: Path) -> IgnoreResolver:
    return IgnoreResolver(root_dir, default_patterns=DEFAULT_IGNORE_PATTERNS)


def is_markdown_path(path: Path) -> bool:
    return path.suffix.lower() in MARKDOWN_SUFFIXES


def humanize_name(stem: str) -> str:
    value = stem.replace("_", " ").replace("-", " ").strip()
    return value if value else stem


def extract_title(markdown_text: str, fallback: str) -> str:
    match = TITLE_RE.search(markdown_text)
    if not match:
        return fallback
    title = match.group(1).strip().strip("#").strip()
    return title or fallback


def docs_href(rel_path: str) -> str:
    return f"/docs/{quote(rel_path, safe='/')}"


def public_asset_href(rel_path: str) -> str:
    return f"/public/{quote(rel_path, safe='/')}"


def docs_fragment_href(rel_path: str) -> str:
    return f"/_live/docs/{quote(rel_path, safe='/')}"


def root_fragment_href() -> str:
    return "/_live/root"


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


def choose_default_doc(pages: Iterable[MarkdownPage], preferred: str | None = None, prefix: str = "") -> str | None:
    normalized_prefix = prefix.strip("/")
    if normalized_prefix:
        base_prefix = f"{normalized_prefix}/"
        candidates = [page.rel_path for page in pages if page.rel_path.startswith(base_prefix)]
    else:
        candidates = [page.rel_path for page in pages]

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


def normalize_rel_path(raw_path: str) -> str:
    cleaned = raw_path.replace("\\", "/").strip("/")
    parts = []
    for part in PurePosixPath(cleaned).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise HTTPException(status_code=404, detail="Not found")
        parts.append(part)
    return "/".join(parts)


def resolve_site_path(root_dir: Path, rel_path: str) -> Path:
    root = root_dir.resolve()
    candidate = root.joinpath(*([part for part in rel_path.split("/") if part] or ["."]))
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    return resolved


def public_asset_response(asset_path: str) -> Response:
    normalized_path = normalize_rel_path(asset_path)
    if not normalized_path:
        raise HTTPException(status_code=404, detail="Asset not found")

    target = resolve_site_path(PUBLIC_DIR, normalized_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    media_type, _encoding = mimetypes.guess_type(target.name)
    return Response(
        target.read_bytes(),
        media_type=media_type or "application/octet-stream",
        headers=NO_CACHE_HEADERS,
    )


def render_markdown(markdown_text: str) -> str:
    return cmarkgfm.github_flavored_markdown_to_html(markdown_text, options=CMARK_OPTIONS)


def build_nav_tree(pages: Iterable[MarkdownPage]) -> NavTree:
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


def build_nav_nodes(tree: NavTree, current_rel: str, prefix: str = "") -> tuple[NavNode, ...]:
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
                children=build_nav_nodes(child_tree, current_rel, rel_dir),
            )
        )

    for page in sorted(files_only, key=lambda item: item.rel_path.lower()):
        items.append(
            NavFile(
                label=page.label,
                href=docs_href(page.rel_path),
                active=page.rel_path == current_rel,
            )
        )

    return tuple(items)


def redirect_response(location: str, *, htmx: bool = False) -> Response:
    if htmx:
        return Response(status_code=204, headers={**NO_CACHE_HEADERS, "HX-Redirect": location})
    return RedirectResponse(location, status_code=307, headers=NO_CACHE_HEADERS)


def build_empty_view(config: ServeConfig) -> EmptyPageView:
    return EmptyPageView(root_dir=str(config.root_dir), live_fragment_href=root_fragment_href())


def build_docs_view(config: ServeConfig, rel_path: str) -> DocsPageView:
    markdown_path = resolve_site_path(config.root_dir, rel_path)
    markdown_text = markdown_path.read_text(encoding="utf-8", errors="replace")
    title = extract_title(markdown_text, fallback=humanize_name(markdown_path.stem))
    pages = discover_pages(config.root_dir) if config.mode == "directory" else []
    home_doc = choose_default_doc(pages, preferred=config.default_doc) if pages else config.default_doc
    with_sidebar = config.mode == "directory" and bool(pages)

    return DocsPageView(
        title=title,
        rel_path=rel_path,
        rendered_markdown=render_markdown(markdown_text),
        with_sidebar=with_sidebar,
        config_name=config.source.name,
        root_dir=str(config.root_dir),
        home_href=None if home_doc is None else docs_href(home_doc),
        nav_items=build_nav_nodes(build_nav_tree(pages), rel_path),
        live_fragment_href=docs_fragment_href(rel_path),
    )


def resolve_docs_response(config: ServeConfig, requested_path: str, *, htmx: bool = False) -> Response | DocsPageView:
    rel_path = normalize_rel_path(requested_path)
    target = resolve_site_path(config.root_dir, rel_path)
    resolver = build_ignore_resolver(config.root_dir)

    if rel_path:
        is_ignored = (
            resolver.is_dir_ignored(rel_path, auto_enter=True)
            if target.is_dir()
            else resolver.is_ignored(rel_path, auto_enter=True)
        )
        if is_ignored:
            raise HTTPException(status_code=404, detail="Not found")

    if target.is_dir():
        pages = discover_pages(config.root_dir)
        default_doc = choose_default_doc(pages, prefix=rel_path)
        if default_doc is None:
            raise HTTPException(status_code=404, detail="Directory contains no markdown files")
        return redirect_response(docs_href(default_doc), htmx=htmx)

    if not target.exists() or not target.is_file():
        if htmx:
            pages = discover_pages(config.root_dir)
            fallback = choose_default_doc(pages, preferred=config.default_doc)
            return redirect_response(docs_href(fallback) if fallback is not None else "/", htmx=True)
        raise HTTPException(status_code=404, detail="Not found")

    if is_markdown_path(target):
        return build_docs_view(config, rel_path)

    return FileResponse(target, headers=NO_CACHE_HEADERS)


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
            html.div(view.rel_path, class_="content-header"),
            html.div(
                html.article(SafeStr(view.rendered_markdown), class_="markdown-body"),
                class_="markdown-frame",
            ),
            class_="main",
        ),
        id="page-shell",
        class_=shell_class,
    )


def empty_shell(view: EmptyPageView) -> ComponentType:
    return html.main(
        sse_reload_listener(view.live_fragment_href),
        html.h1("No markdown files found"),
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


def base_document(title: str, body_content: ComponentType) -> Component:
    return (
        html.DOCTYPE.html,
        html.html(
            html.head(
                html.Meta.charset(),
                html.Meta.viewport(),
                html.title(title),
                html.link(
                    rel="stylesheet",
                    href=public_asset_href("css/github-markdown-light.css"),
                    media="(prefers-color-scheme: light), (prefers-color-scheme: no-preference)",
                ),
                html.link(
                    rel="stylesheet",
                    href=public_asset_href("css/github-markdown-dark.css"),
                    media="(prefers-color-scheme: dark)",
                ),
                html.link(rel="stylesheet", href=public_asset_href("css/app.css")),
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
    return base_document(f"{view.title} · markserv", docs_shell(view))


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


async def watch_for_changes(root_dir: Path, path_filter: WatchPathFilter, broker: ReloadBroker) -> None:
    async for changes in awatch(
        root_dir,
        watch_filter=path_filter,
        debounce=250,
        step=50,
        ignore_permission_denied=True,
    ):
        if any(Path(path).name == ".gitignore" for _change, path in changes):
            path_filter.refresh()
        await broker.publish()


def create_app(config: ServeConfig) -> FastAPI:
    broker = ReloadBroker()
    path_filter = WatchPathFilter(config.root_dir)
    htmy = HTMY(stream=False)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(watch_for_changes(config.root_dir, path_filter, broker))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/public/{asset_path:path}")
    async def public_asset(asset_path: str) -> Response:
        return public_asset_response(asset_path)

    @app.get("/_events")
    async def events() -> StreamingResponse:
        async def event_stream() -> AsyncIterator[str]:
            version = broker.version
            yield "retry: 1000\n\n"
            while True:
                version, changed = await broker.wait_for_update(version)
                if changed:
                    yield "event: reload\ndata: now\n\n"
                else:
                    yield "event: ping\ndata: keepalive\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/", response_model=None)
    @app.get("/docs", response_model=None)
    @htmy.page(render_empty_page)
    async def root(response: FastAPIResponse) -> Response | EmptyPageView:
        response.headers.update(NO_CACHE_HEADERS)
        if config.mode == "single" and config.default_doc is not None:
            return redirect_response(docs_href(config.default_doc))

        pages = discover_pages(config.root_dir)
        home_doc = choose_default_doc(pages, preferred=config.default_doc)
        if home_doc is not None:
            return redirect_response(docs_href(home_doc))

        return build_empty_view(config)

    @app.get("/_live/root", response_model=None)
    @htmy.hx(render_empty_fragment, no_data=True)
    async def root_fragment(response: FastAPIResponse) -> Response | EmptyPageView:
        response.headers.update(NO_CACHE_HEADERS)
        pages = discover_pages(config.root_dir)
        home_doc = choose_default_doc(pages, preferred=config.default_doc)
        if home_doc is not None:
            return redirect_response(docs_href(home_doc), htmx=True)

        return build_empty_view(config)

    @app.get("/docs/{requested_path:path}", response_model=None)
    @htmy.page(render_docs_page)
    async def docs(requested_path: str, response: FastAPIResponse) -> Response | DocsPageView:
        response.headers.update(NO_CACHE_HEADERS)
        return resolve_docs_response(config, requested_path)

    @app.get("/_live/docs/{requested_path:path}", response_model=None)
    @htmy.hx(render_docs_fragment, no_data=True)
    async def docs_fragment(requested_path: str, response: FastAPIResponse) -> Response | DocsPageView:
        response.headers.update(NO_CACHE_HEADERS)
        return resolve_docs_response(config, requested_path, htmx=True)

    return app
