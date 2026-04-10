from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi import Response as FastAPIResponse
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fasthx.htmy import HTMY
from watchfiles import awatch

from .icons import generate_favicon
from .rendering import (
    DocsPageView,
    EmptyPageView,
    build_docs_view,
    build_empty_view,
    docs_href,
    render_docs_fragment,
    render_docs_page,
    render_empty_fragment,
    render_empty_page,
)
from .search import SearchIndex, build_search_index
from .site import (
    PageIndex,
    ServeConfig,
    SitePathError,
    SiteSource,
    WatchPathFilter,
    build_file_site,
    normalize_rel_path,
)

NO_CACHE_HEADERS = {"Cache-Control": "no-store"}
NO_SNIFF_HEADERS = {**NO_CACHE_HEADERS, "X-Content-Type-Options": "nosniff"}
SVG_CONTENT_SECURITY_POLICY = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
PACKAGE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = PACKAGE_DIR / "public"
PYTHON_RELOAD_ENV_VAR = "MARKSERV_PYTHON_RELOAD"
DEV_RELOAD_ASSET_EXTENSIONS = {".css", ".js"}


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
    try:
        normalized_path = normalize_rel_path(asset_path)
    except SitePathError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc
    if not normalized_path:
        raise HTTPException(status_code=404, detail="Asset not found")

    target = resolve_site_path(PUBLIC_DIR, normalized_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    media_type, _encoding = mimetypes.guess_type(target.name)
    headers = dict(NO_SNIFF_HEADERS)
    if target.suffix.lower() == ".svg":
        headers["Content-Security-Policy"] = SVG_CONTENT_SECURITY_POLICY
    return Response(
        target.read_bytes(),
        media_type=media_type or "application/octet-stream",
        headers=headers,
    )


def asset_file_response(asset_path: Path) -> Response:
    media_type, _encoding = mimetypes.guess_type(asset_path.name)
    headers = dict(NO_SNIFF_HEADERS)
    if asset_path.suffix.lower() == ".svg":
        headers["Content-Security-Policy"] = SVG_CONTENT_SECURITY_POLICY
    return FileResponse(
        asset_path,
        media_type=media_type or "application/octet-stream",
        headers=headers,
    )


def redirect_response(location: str, *, htmx: bool = False) -> Response:
    if htmx:
        return Response(status_code=204, headers={**NO_CACHE_HEADERS, "HX-Redirect": location})
    return RedirectResponse(location, status_code=307, headers=NO_CACHE_HEADERS)


async def resolve_docs_response(
    site: SiteSource,
    page_index: PageIndex,
    requested_path: str,
    *,
    htmx: bool = False,
    dev_reload: bool = False,
) -> Response | DocsPageView:
    try:
        rel_path = normalize_rel_path(requested_path)
    except SitePathError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc

    if await asyncio.to_thread(site.is_directory, rel_path):
        default_doc = page_index.choose_default_doc(prefix=rel_path)
        if default_doc is None:
            raise HTTPException(status_code=404, detail="Directory contains no markdown files")
        return redirect_response(docs_href(default_doc), htmx=htmx)

    markdown_text = await asyncio.to_thread(site.read_markdown, rel_path)
    if markdown_text is not None:
        return await asyncio.to_thread(
            build_docs_view, site, page_index, rel_path, markdown_text, dev_reload=dev_reload
        )

    asset_path = await asyncio.to_thread(site.resolve_asset, rel_path)
    if asset_path is not None:
        return asset_file_response(asset_path)

    if htmx:
        fallback = page_index.choose_default_doc(preferred=site.default_doc)
        return redirect_response(docs_href(fallback) if fallback is not None else "/", htmx=True)

    raise HTTPException(status_code=404, detail="Not found")


def python_reload_enabled() -> bool:
    value = os.environ.get(PYTHON_RELOAD_ENV_VAR, "")
    return value.lower() in {"1", "true", "yes", "on"}


def is_dev_reload_asset(path: str) -> bool:
    return Path(path).suffix.lower() in DEV_RELOAD_ASSET_EXTENSIONS


async def watch_for_changes(
    root_dir: Path,
    path_filter: WatchPathFilter,
    broker: ReloadBroker,
    *,
    on_change: Callable[[], Awaitable[None]] | None = None,
) -> None:
    async for changes in awatch(
        root_dir,
        watch_filter=path_filter,
        debounce=250,
        step=50,
        ignore_permission_denied=True,
    ):
        if any(Path(path).name == ".gitignore" for _change, path in changes):
            path_filter.refresh()
        if on_change is not None:
            await on_change()
        await broker.publish()


async def watch_for_dev_reload_assets(public_dir: Path, broker: ReloadBroker) -> None:
    async for _changes in awatch(
        public_dir,
        watch_filter=lambda _change, path: is_dev_reload_asset(path),
        debounce=150,
        step=50,
        ignore_permission_denied=True,
    ):
        await broker.publish()


def create_app(config_or_site: ServeConfig | SiteSource) -> FastAPI:
    site: SiteSource = build_file_site(config_or_site) if isinstance(config_or_site, ServeConfig) else config_or_site
    broker = ReloadBroker()
    dev_reload_broker = ReloadBroker()
    dev_reload = python_reload_enabled()
    htmy = HTMY(stream=False)
    page_index_cache: PageIndex | None = None
    search_index_cache: SearchIndex | None = None
    page_index_lock = asyncio.Lock()
    search_index_lock = asyncio.Lock()

    async def get_page_index() -> PageIndex:
        nonlocal page_index_cache

        cached = page_index_cache
        if cached is not None:
            return cached

        async with page_index_lock:
            cached = page_index_cache
            if cached is None:
                cached = await asyncio.to_thread(site.page_index)
                page_index_cache = cached
        return cached

    async def get_search_index() -> SearchIndex:
        nonlocal search_index_cache

        cached = search_index_cache
        if cached is not None:
            return cached

        page_index = await get_page_index()
        async with search_index_lock:
            cached = search_index_cache
            if cached is None:
                cached = await asyncio.to_thread(build_search_index, site, page_index)
                search_index_cache = cached
        return cached

    async def invalidate_site_caches() -> None:
        nonlocal page_index_cache, search_index_cache
        async with page_index_lock:
            page_index_cache = None
        async with search_index_lock:
            search_index_cache = None
        icon_cache.clear()

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        tasks: list[asyncio.Task[None]] = []

        if site.watch_root is not None and site.watch_filter is not None:
            tasks.append(
                asyncio.create_task(
                    watch_for_changes(
                        site.watch_root,
                        site.watch_filter,
                        broker,
                        on_change=invalidate_site_caches,
                    )
                )
            )

        if dev_reload:
            tasks.append(asyncio.create_task(watch_for_dev_reload_assets(PUBLIC_DIR, dev_reload_broker)))

        if not tasks:
            yield
            return

        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    icon_cache: dict[str, bytes] = {}

    @app.get("/public/{asset_path:path}")
    async def public_asset(asset_path: str) -> Response:
        return public_asset_response(asset_path)

    @app.get("/icons/docs/{requested_path:path}")
    def page_icon(requested_path: str) -> Response:
        """Generate a per-page favicon. Sync def so FastAPI runs it in a threadpool."""
        if requested_path in icon_cache:
            return Response(content=icon_cache[requested_path], media_type="image/png")

        try:
            rel_path = normalize_rel_path(requested_path)
        except SitePathError as exc:
            raise HTTPException(status_code=404, detail="Not found") from exc

        markdown_text = site.read_markdown(rel_path)
        if markdown_text is None:
            raise HTTPException(status_code=404, detail="Not found")

        png_bytes = generate_favicon(markdown_text)
        icon_cache[requested_path] = png_bytes
        return Response(content=png_bytes, media_type="image/png")

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

    @app.get("/_search")
    async def search_docs(q: str = "", limit: int = 12) -> dict[str, object]:
        query = q.strip()
        if not query:
            return {"results": []}
        results = await asyncio.to_thread((await get_search_index()).search, query, limit)
        return {"results": [result.to_payload() for result in results]}

    if dev_reload:

        @app.get("/_dev/reload")
        async def dev_reload_events() -> StreamingResponse:
            async def event_stream() -> AsyncIterator[str]:
                version = dev_reload_broker.version
                yield "retry: 250\n\n"
                while True:
                    version, changed = await dev_reload_broker.wait_for_update(version)
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
        if site.default_doc is not None:
            return redirect_response(docs_href(site.default_doc))

        home_doc = (await get_page_index()).choose_default_doc()
        if home_doc is not None:
            return redirect_response(docs_href(home_doc))

        return build_empty_view(site, dev_reload=dev_reload)

    @app.get("/_live/root", response_model=None)
    @htmy.hx(render_empty_fragment, no_data=True)
    async def root_fragment(response: FastAPIResponse) -> Response | EmptyPageView:
        response.headers.update(NO_CACHE_HEADERS)
        if site.default_doc is not None:
            return redirect_response(docs_href(site.default_doc), htmx=True)

        home_doc = (await get_page_index()).choose_default_doc()
        if home_doc is not None:
            return redirect_response(docs_href(home_doc), htmx=True)

        return build_empty_view(site, dev_reload=dev_reload)

    @app.get("/docs/{requested_path:path}", response_model=None)
    @htmy.page(render_docs_page)
    async def docs(requested_path: str, response: FastAPIResponse) -> Response | DocsPageView:
        response.headers.update(NO_CACHE_HEADERS)
        return await resolve_docs_response(site, await get_page_index(), requested_path, dev_reload=dev_reload)

    @app.get("/_live/docs/{requested_path:path}", response_model=None)
    @htmy.hx(render_docs_fragment, no_data=True)
    async def docs_fragment(requested_path: str, response: FastAPIResponse) -> Response | DocsPageView:
        response.headers.update(NO_CACHE_HEADERS)
        return await resolve_docs_response(
            site,
            await get_page_index(),
            requested_path,
            htmx=True,
            dev_reload=dev_reload,
        )

    return app
