from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from htmy import Component
from watchfiles import awatch

from .content import (
    PageIndex,
    ServeConfig,
    SitePathError,
    SiteSource,
    WatchPathFilter,
    build_file_site,
    normalize_rel_path,
    resolve_rooted_path,
)
from .icons import generate_favicon
from .render import (
    EMPTY_NAVIGATION_STATE,
    DocsPageView,
    EmptyPageView,
    NavigationState,
    build_docs_view,
    build_empty_view,
    docs_href,
    render_docs_fragment,
    render_docs_page,
    render_empty_fragment,
    render_empty_page,
    render_search_results_fragment,
    render_sidebar_fragment,
)
from .runtime import ReloadBroker, SiteRuntime
from .settings import python_reload_enabled

NO_CACHE_HEADERS = {"Cache-Control": "no-store"}
NO_SNIFF_HEADERS = {**NO_CACHE_HEADERS, "X-Content-Type-Options": "nosniff"}
SVG_CONTENT_SECURITY_POLICY = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
PACKAGE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = PACKAGE_DIR / "public"
DEV_RELOAD_ASSET_EXTENSIONS = {".css", ".js"}
V = TypeVar("V", DocsPageView, EmptyPageView)


def _response_headers_for_file(path: Path) -> dict[str, str]:
    headers = dict(NO_SNIFF_HEADERS)
    if path.suffix.lower() == ".svg":
        headers["Content-Security-Policy"] = SVG_CONTENT_SECURITY_POLICY
    return headers


def file_response(path: Path) -> Response:
    media_type, _encoding = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        headers=_response_headers_for_file(path),
    )


def public_asset_response(asset_path: str) -> Response:
    try:
        normalized_path = normalize_rel_path(asset_path)
        if not normalized_path:
            raise SitePathError("Asset not found")
        target = resolve_rooted_path(PUBLIC_DIR, normalized_path)
    except SitePathError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return file_response(target)


def _htmx_location_value(location: str) -> str:
    if not location.startswith("/"):
        return location
    return json.dumps(
        {
            "path": location,
            "target": "#main-shell",
            "swap": "outerHTML",
            "select": "#main-shell",
        },
        separators=(",", ":"),
    )


def redirect_response(location: str, *, htmx: bool = False) -> Response:
    if htmx:
        header_name = "HX-Location" if location.startswith("/") else "HX-Redirect"
        return Response(status_code=204, headers={**NO_CACHE_HEADERS, header_name: _htmx_location_value(location)})
    return RedirectResponse(location, status_code=307, headers=NO_CACHE_HEADERS)


def _nav_open_paths(
    raw_paths: list[str],
    page_index: PageIndex,
    *,
    default_to_all: bool = False,
) -> tuple[str, ...]:
    if not raw_paths:
        return page_index.directory_paths() if default_to_all else ()

    paths: list[str] = []
    seen: set[str] = set()

    for raw_path in raw_paths:
        try:
            normalized = normalize_rel_path(raw_path)
        except SitePathError:
            continue
        if not normalized or normalized in seen or not page_index.has_directory(normalized):
            continue
        seen.add(normalized)
        paths.append(normalized)

    return tuple(sorted(paths, key=lambda path: (path.count("/"), path.casefold())))


def nav_state_from_request(
    request: Request,
    page_index: PageIndex,
    *,
    default_to_all: bool = False,
) -> NavigationState:
    return NavigationState(
        open_paths=_nav_open_paths(
            list(request.query_params.getlist("nav")), page_index, default_to_all=default_to_all
        ),
        explicit="nav_state" in request.query_params,
    )


async def resolve_docs_response(
    site: SiteSource,
    page_index: PageIndex,
    requested_path: str,
    *,
    htmx: bool = False,
    navigation: NavigationState = EMPTY_NAVIGATION_STATE,
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
            build_docs_view,
            site,
            page_index,
            rel_path,
            markdown_text,
            navigation=navigation,
            dev_reload=dev_reload,
        )

    asset_path = await asyncio.to_thread(site.resolve_asset, rel_path)
    if asset_path is not None:
        return file_response(asset_path)

    if htmx:
        fallback = page_index.choose_default_doc(preferred=site.default_doc)
        return redirect_response(docs_href(fallback) if fallback is not None else "/", htmx=True)

    raise HTTPException(status_code=404, detail="Not found")


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


def event_stream_response(broker: ReloadBroker, *, retry_ms: int) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        version = broker.version
        yield f"retry: {retry_ms}\n\n"
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


def is_htmx_request(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def create_app(config_or_site: ServeConfig | SiteSource) -> FastAPI:
    site: SiteSource = build_file_site(config_or_site) if isinstance(config_or_site, ServeConfig) else config_or_site
    runtime = SiteRuntime(site=site, dev_reload=python_reload_enabled())

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        tasks: list[asyncio.Task[None]] = []

        if site.watch_root is not None and site.watch_filter is not None:
            tasks.append(
                asyncio.create_task(
                    watch_for_changes(
                        site.watch_root,
                        site.watch_filter,
                        runtime.broker,
                        on_change=runtime.invalidate,
                    )
                )
            )

        if runtime.dev_reload:
            tasks.append(asyncio.create_task(watch_for_dev_reload_assets(PUBLIC_DIR, runtime.dev_reload_broker)))

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

    @app.get("/public/{asset_path:path}")
    async def public_asset(asset_path: str) -> Response:
        return public_asset_response(asset_path)

    @app.get("/icons/docs/{requested_path:path}")
    def page_icon(requested_path: str) -> Response:
        """Generate a per-page favicon. Sync def so FastAPI runs it in a threadpool."""
        cached = runtime.cached_icon(requested_path)
        if cached is not None:
            return Response(content=cached, media_type="image/png")

        try:
            rel_path = normalize_rel_path(requested_path)
        except SitePathError as exc:
            raise HTTPException(status_code=404, detail="Not found") from exc

        markdown_text = site.read_markdown(rel_path)
        if markdown_text is None:
            raise HTTPException(status_code=404, detail="Not found")

        png_bytes = runtime.store_icon(requested_path, generate_favicon(markdown_text))
        return Response(content=png_bytes, media_type="image/png")

    @app.get("/_events")
    async def events() -> StreamingResponse:
        return event_stream_response(runtime.broker, retry_ms=1000)

    @app.get("/_search", response_model=None)
    async def search_docs(request: Request, q: str = "", limit: int = 12) -> Response | dict[str, object]:
        query = q.strip()
        if not query:
            if is_htmx_request(request):
                return HTMLResponse(render_search_results_fragment([], ""))
            return {"results": []}

        results = await asyncio.to_thread((await runtime.get_search_index()).search, query, limit)
        if is_htmx_request(request):
            return HTMLResponse(render_search_results_fragment(results, query))
        return {"results": [result.to_payload() for result in results]}

    if runtime.dev_reload:

        @app.get("/_dev/reload")
        async def dev_reload_events() -> StreamingResponse:
            return event_stream_response(runtime.dev_reload_broker, retry_ms=250)

    async def render_view_response(
        request: Request,
        view: V,
        *,
        page_renderer: Callable[[V], Component],
        fragment_renderer: Callable[[V], Component],
    ) -> HTMLResponse:
        component = fragment_renderer(view) if is_htmx_request(request) else page_renderer(view)
        return HTMLResponse(await runtime.renderer.render_component(component, request), headers=NO_CACHE_HEADERS)

    @app.get("/", response_model=None)
    @app.get("/docs", response_model=None)
    async def root(request: Request) -> Response:
        page_index = await runtime.get_page_index()
        if site.default_doc is not None:
            return redirect_response(docs_href(site.default_doc), htmx=is_htmx_request(request))

        home_doc = page_index.choose_default_doc()
        if home_doc is not None:
            return redirect_response(docs_href(home_doc), htmx=is_htmx_request(request))

        return await render_view_response(
            request,
            build_empty_view(site, dev_reload=runtime.dev_reload),
            page_renderer=render_empty_page,
            fragment_renderer=render_empty_fragment,
        )

    @app.get("/docs/{requested_path:path}", response_model=None)
    async def docs(request: Request, requested_path: str) -> Response:
        page_index = await runtime.get_page_index()
        resolved = await resolve_docs_response(
            site,
            page_index,
            requested_path,
            htmx=is_htmx_request(request),
            navigation=nav_state_from_request(request, page_index, default_to_all=True),
            dev_reload=runtime.dev_reload,
        )
        if isinstance(resolved, Response):
            return resolved

        if is_htmx_request(request) and request.headers.get("hx-target") == "sidebar-shell":
            return HTMLResponse(
                await runtime.renderer.render_component(render_sidebar_fragment(resolved), request),
                headers=NO_CACHE_HEADERS,
            )

        return await render_view_response(
            request,
            resolved,
            page_renderer=render_docs_page,
            fragment_renderer=render_docs_fragment,
        )

    return app
