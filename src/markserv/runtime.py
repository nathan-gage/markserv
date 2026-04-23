from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fasthx.htmy import HTMY

from .content import PageIndex, SiteSource
from .search import SearchIndex, build_search_index


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

    def cached_icon(self, requested_path: str) -> bytes | None:
        return self._icon_cache.get(requested_path)

    def store_icon(self, requested_path: str, png_bytes: bytes) -> bytes:
        self._icon_cache[requested_path] = png_bytes
        return png_bytes
