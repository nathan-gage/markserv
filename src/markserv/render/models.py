from __future__ import annotations

from dataclasses import dataclass

from ..content import NavNode


@dataclass(frozen=True)
class NavigationState:
    open_paths: tuple[str, ...] = ()
    explicit: bool = False


@dataclass(frozen=True)
class SidebarView:
    config_name: str
    root_dir: str
    home_href: str | None
    navigation: NavigationState
    items: tuple[NavNode, ...]


EMPTY_NAVIGATION_STATE = NavigationState()


@dataclass(frozen=True)
class DocsPageView:
    title: str
    rel_path: str
    rendered_markdown: str
    sidebar: SidebarView | None
    dev_reload: bool = False


@dataclass(frozen=True)
class EmptyPageView:
    root_dir: str
    dev_reload: bool = False
