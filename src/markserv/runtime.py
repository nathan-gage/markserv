from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fasthx.htmy import HTMY

from .content import PageIndex, SiteSource
from .render import DocsPageView, NavigationState
from .search import SearchIndex, build_search_index

_DOCS_VIEW_CACHE_LIMIT = 128
_SIDEBAR_FRAGMENT_CACHE_LIMIT = 256


def _docs_view_cache_key(view: DocsPageView) -> tuple[str, tuple[str, ...], bool]:
    sidebar = view.sidebar
    return (
        view.rel_path,
        (() if sidebar is None else sidebar.navigation.open_paths),
        False if sidebar is None else sidebar.navigation.explicit,
    )


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


@dataclass(slots=True)
class SiteRuntime:
    site: SiteSource
    dev_reload: bool
    broker: ReloadBroker = field(default_factory=ReloadBroker)
    dev_reload_broker: ReloadBroker = field(default_factory=ReloadBroker)
    renderer: HTMY = field(default_factory=lambda: HTMY(stream=False))
    _page_index_cache: PageIndex | None = field(default=None, init=False, repr=False)
    _search_index_cache: SearchIndex | None = field(default=None, init=False, repr=False)
    _icon_cache: dict[str, bytes] = field(default_factory=dict, init=False, repr=False)
    _docs_view_cache: dict[tuple[str, tuple[str, ...], bool], DocsPageView] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _sidebar_fragment_cache: dict[tuple[str, tuple[str, ...], bool], str] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _page_index_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _search_index_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def get_page_index(self) -> PageIndex:
        cached = self._page_index_cache
        if cached is not None:
            return cached

        async with self._page_index_lock:
            cached = self._page_index_cache
            if cached is None:
                cached = await asyncio.to_thread(self.site.page_index)
                self._page_index_cache = cached
        return cached

    async def get_search_index(self) -> SearchIndex:
        cached = self._search_index_cache
        if cached is not None:
            return cached

        page_index = await self.get_page_index()
        async with self._search_index_lock:
            cached = self._search_index_cache
            if cached is None:
                cached = await asyncio.to_thread(build_search_index, self.site, page_index)
                self._search_index_cache = cached
        return cached

    async def invalidate(self) -> None:
        async with self._page_index_lock:
            self._page_index_cache = None
        async with self._search_index_lock:
            self._search_index_cache = None
        self._icon_cache.clear()
        self._docs_view_cache.clear()
        self._sidebar_fragment_cache.clear()

    def cached_docs_view(self, rel_path: str, navigation: NavigationState) -> DocsPageView | None:
        cache_key = (rel_path, navigation.open_paths, navigation.explicit)
        cached = self._docs_view_cache.get(cache_key)
        if cached is None:
            return None

        self._docs_view_cache.pop(cache_key)
        self._docs_view_cache[cache_key] = cached
        return cached

    def store_docs_view(self, view: DocsPageView) -> DocsPageView:
        cache_key = _docs_view_cache_key(view)
        self._docs_view_cache[cache_key] = view
        while len(self._docs_view_cache) > _DOCS_VIEW_CACHE_LIMIT:
            oldest_key = next(iter(self._docs_view_cache))
            self._docs_view_cache.pop(oldest_key)
        return view

    def cached_sidebar_fragment(self, view: DocsPageView) -> str | None:
        cache_key = _docs_view_cache_key(view)
        cached = self._sidebar_fragment_cache.get(cache_key)
        if cached is None:
            return None

        self._sidebar_fragment_cache.pop(cache_key)
        self._sidebar_fragment_cache[cache_key] = cached
        return cached

    def store_sidebar_fragment(self, view: DocsPageView, html: str) -> str:
        cache_key = _docs_view_cache_key(view)
        self._sidebar_fragment_cache[cache_key] = html
        while len(self._sidebar_fragment_cache) > _SIDEBAR_FRAGMENT_CACHE_LIMIT:
            oldest_key = next(iter(self._sidebar_fragment_cache))
            self._sidebar_fragment_cache.pop(oldest_key)
        return html

    def cached_icon(self, requested_path: str) -> bytes | None:
        return self._icon_cache.get(requested_path)

    def store_icon(self, requested_path: str, png_bytes: bytes) -> bytes:
        self._icon_cache[requested_path] = png_bytes
        return png_bytes
