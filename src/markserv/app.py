from __future__ import annotations

import asyncio
import contextlib
import html
import os
import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Literal, TypeAlias
from urllib.parse import quote

import cmarkgfm
from cmarkgfm.cmark import Options
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from ignoretree import IgnoreResolver
from watchfiles import awatch

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".mkdn"}
DEFAULT_IGNORE_PATTERNS = [".git/"]
DIRECTORY_DEFAULT_BASENAMES = ("README", "readme", "index", "INDEX")
CMARK_OPTIONS = Options.CMARK_OPT_GITHUB_PRE_LANG | Options.CMARK_OPT_SMART
NO_CACHE_HEADERS = {"Cache-Control": "no-store"}
TITLE_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$", re.MULTILINE)
SHELL_CSS = """
:root {
  color-scheme: light dark;
  --bg: #ffffff;
  --panel: #f6f8fa;
  --panel-border: #d0d7de;
  --text: #24292f;
  --muted: #57606a;
  --link: #0969da;
  --active-bg: rgba(9, 105, 218, 0.10);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117;
    --panel: #161b22;
    --panel-border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --link: #58a6ff;
    --active-bg: rgba(88, 166, 255, 0.14);
  }
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  min-height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  min-height: 100vh;
}

.app-shell {
  display: grid;
  min-height: 100vh;
}

.app-shell.with-sidebar {
  grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
}

.sidebar {
  position: sticky;
  top: 0;
  align-self: start;
  height: 100vh;
  overflow-y: auto;
  border-right: 1px solid var(--panel-border);
  background: var(--panel);
  padding: 1rem;
}

.sidebar-header {
  margin-bottom: 1rem;
}

.sidebar-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
}

.sidebar-subtitle {
  margin: 0.35rem 0 0;
  color: var(--muted);
  font-size: 0.8rem;
  word-break: break-word;
}

.home-link {
  display: inline-flex;
  margin-top: 0.75rem;
  color: var(--link);
  text-decoration: none;
  font-size: 0.85rem;
}

.nav-tree,
.nav-tree ul {
  list-style: none;
  margin: 0;
  padding-left: 0.9rem;
}

.nav-tree {
  padding-left: 0;
}

.nav-dir {
  margin: 0.2rem 0;
}

.nav-dir > details > summary {
  cursor: pointer;
  color: var(--muted);
  font-size: 0.9rem;
  user-select: none;
}

.nav-link {
  display: block;
  margin: 0.15rem 0;
  padding: 0.35rem 0.55rem;
  border-radius: 0.45rem;
  color: inherit;
  text-decoration: none;
  font-size: 0.92rem;
}

.nav-link:hover {
  background: rgba(127, 127, 127, 0.08);
}

.nav-link.is-active {
  background: var(--active-bg);
  color: var(--link);
  font-weight: 600;
}

.main {
  min-width: 0;
}

.content-header {
  padding: 1rem 1.25rem 0;
  color: var(--muted);
  font-size: 0.85rem;
}

.markdown-frame {
  padding: 0 1.25rem 2rem;
}

.markdown-body {
  box-sizing: border-box;
  min-width: 200px;
  max-width: 980px;
  margin: 0 auto;
  padding: 2rem 2.25rem 3rem;
}

.empty-state {
  max-width: 720px;
  margin: 4rem auto;
  padding: 0 1.25rem;
}

.empty-state h1 {
  margin-bottom: 0.5rem;
}

.empty-state p,
.empty-state li {
  color: var(--muted);
  line-height: 1.6;
}

@media (max-width: 900px) {
  .app-shell.with-sidebar {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: relative;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--panel-border);
  }
}

@media (max-width: 767px) {
  .markdown-frame {
    padding: 0 0 1.5rem;
  }

  .markdown-body {
    padding: 1rem 1rem 2rem;
  }
}
""".strip()


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


def asset_text(name: str) -> str:
    if name not in {"github-markdown-light.css", "github-markdown-dark.css"}:
        raise HTTPException(status_code=404, detail="Asset not found")
    return files("markserv").joinpath("static").joinpath(name).read_text(encoding="utf-8")


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


def render_nav_tree(tree: NavTree, current_rel: str, prefix: str = "") -> str:
    directories: list[tuple[str, NavTree]] = []
    files_only: list[MarkdownPage] = []

    for name, child in tree.items():
        if isinstance(child, MarkdownPage):
            files_only.append(child)
        else:
            directories.append((name, child))

    items: list[str] = []
    for directory_name, child_tree in sorted(directories, key=lambda item: item[0].lower()):
        rel_dir = f"{prefix}/{directory_name}" if prefix else directory_name
        open_attr = " open" if current_rel.startswith(f"{rel_dir}/") else ""
        items.append(
            "<li class='nav-dir'>"
            f"<details{open_attr}><summary>{html.escape(directory_name)}</summary>"
            f"{render_nav_tree(child_tree, current_rel, rel_dir)}"
            "</details></li>"
        )

    for page in sorted(files_only, key=lambda item: item.rel_path.lower()):
        active_class = " is-active" if page.rel_path == current_rel else ""
        items.append(
            "<li class='nav-file'>"
            f"<a class='nav-link{active_class}' href='{docs_href(page.rel_path)}'>{html.escape(page.label)}</a>"
            "</li>"
        )

    return f"<ul class='nav-tree'>{''.join(items)}</ul>" if items else ""


def render_sidebar(config: ServeConfig, pages: Iterable[MarkdownPage], current_rel: str, home_doc: str | None) -> str:
    home_link = f"<a class='home-link' href='{docs_href(home_doc)}'>Home</a>" if home_doc is not None else ""
    return (
        "<aside class='sidebar'>"
        "<div class='sidebar-header'>"
        f"<p class='sidebar-title'>{html.escape(config.source.name)}</p>"
        f"<p class='sidebar-subtitle'>Watching {html.escape(str(config.root_dir))}</p>"
        f"{home_link}"
        "</div>"
        f"{render_nav_tree(build_nav_tree(pages), current_rel)}"
        "</aside>"
    )


def render_page_html(
    *,
    config: ServeConfig,
    rel_path: str,
    title: str,
    rendered_markdown: str,
    pages: list[MarkdownPage],
    home_doc: str | None,
) -> str:
    with_sidebar = config.mode == "directory" and bool(pages)
    sidebar_html = render_sidebar(config, pages, rel_path, home_doc) if with_sidebar else ""
    shell_class = "app-shell with-sidebar" if with_sidebar else "app-shell"
    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>{html.escape(title)} · markserv</title>
    <link rel=\"stylesheet\" href=\"/_static/github-markdown-light.css\" media=\"(prefers-color-scheme: light), (prefers-color-scheme: no-preference)\">
    <link rel=\"stylesheet\" href=\"/_static/github-markdown-dark.css\" media=\"(prefers-color-scheme: dark)\">
    <style>{SHELL_CSS}</style>
  </head>
  <body>
    <div class=\"{shell_class}\">
      {sidebar_html}
      <main class=\"main\">
        <div class=\"content-header\">{html.escape(rel_path)}</div>
        <div class=\"markdown-frame\">
          <article class=\"markdown-body\">{rendered_markdown}</article>
        </div>
      </main>
    </div>
    <script>
      const stream = new EventSource('/_events');
      const reload = () => window.location.reload();
      stream.addEventListener('reload', reload);
      stream.onmessage = reload;
    </script>
  </body>
</html>
"""


def render_empty_html(config: ServeConfig) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>markserv</title>
    <style>{SHELL_CSS}</style>
  </head>
  <body>
    <main class=\"empty-state\">
      <h1>No markdown files found</h1>
      <p>markserv scanned <code>{html.escape(str(config.root_dir))}</code> and did not find any markdown files.</p>
      <ul>
        <li>Git-style ignore rules from <code>.gitignore</code> are respected.</li>
        <li>Markdown files are expected to use common extensions like <code>.md</code> or <code>.markdown</code>.</li>
      </ul>
    </main>
    <script>
      const stream = new EventSource('/_events');
      const reload = () => window.location.reload();
      stream.addEventListener('reload', reload);
      stream.onmessage = reload;
    </script>
  </body>
</html>
"""


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

    @app.get("/_static/{name}")
    async def static_asset(name: str) -> Response:
        return Response(asset_text(name), media_type="text/css", headers=NO_CACHE_HEADERS)

    @app.get("/_events")
    async def events() -> StreamingResponse:
        async def event_stream() -> AsyncIterator[str]:
            version = broker.version
            yield "retry: 1000\n\n"
            while True:
                version, changed = await broker.wait_for_update(version)
                if changed:
                    yield "event: reload\ndata: reload\n\n"
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

    @app.get("/")
    async def root() -> Response:
        if config.mode == "single" and config.default_doc is not None:
            return RedirectResponse(docs_href(config.default_doc), status_code=307)

        pages = discover_pages(config.root_dir)
        home_doc = choose_default_doc(pages, preferred=config.default_doc)
        if home_doc is None:
            return HTMLResponse(render_empty_html(config), headers=NO_CACHE_HEADERS)
        return RedirectResponse(docs_href(home_doc), status_code=307)

    @app.get("/docs")
    async def docs_root() -> Response:
        return await root()

    @app.get("/docs/{requested_path:path}")
    async def docs(requested_path: str) -> Response:
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
            return RedirectResponse(docs_href(default_doc), status_code=307)

        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="Not found")

        if is_markdown_path(target):
            markdown_text = target.read_text(encoding="utf-8", errors="replace")
            title = extract_title(markdown_text, fallback=humanize_name(target.stem))
            pages = discover_pages(config.root_dir) if config.mode == "directory" else []
            home_doc = choose_default_doc(pages, preferred=config.default_doc) if pages else config.default_doc
            html_page = render_page_html(
                config=config,
                rel_path=rel_path,
                title=title,
                rendered_markdown=render_markdown(markdown_text),
                pages=pages,
                home_doc=home_doc,
            )
            return HTMLResponse(html_page, headers=NO_CACHE_HEADERS)

        return FileResponse(target, headers=NO_CACHE_HEADERS)

    return app
