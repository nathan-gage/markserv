from __future__ import annotations

from typing import Annotated

from cyclopts import App, Parameter
from cyclopts.help import PlainFormatter
from fastapi import FastAPI

from .app import create_app
from .cli import DEFAULT_HOST, DEFAULT_PORT, serve_application
from .content import SyntheticSite
from .settings import python_reload_enabled

DEMO_DOCUMENTS = {
    "README.md": """---
title: Demo Home
nav_label: Welcome
nav_order: 1
---

# markserv demo

Welcome to the built-in demo site.

This sample tree exists so you can quickly try the renderer, sidebar navigation, live reload, Cmd/Ctrl+K search, theme control, and YAML front matter support.

## Try these pages

- [Project overview](guides/project-overview.md)
- [Quickstart](guides/quickstart.md)
- [YAML front matter demo](guides/features/front-matter.md)
- [GitHub-flavored markdown examples](guides/features/gfm.md)
- [Nested navigation](guides/nested/deep-dive.md)
- [Reference notes](reference/notes.md)

## What to try

- Start with the [project overview](guides/project-overview.md).
- Notice that sidebar labels and ordering come from YAML front matter.
- Open the [front matter demo](guides/features/front-matter.md).
- Follow a link to the [hidden page](reference/hidden-page.md), which is routable but omitted from the sidebar.
- Press **Cmd/Ctrl+K** to search across pages and headings.
- Toggle between **system**, **light**, and **dark** themes.
- Resize the window to see the responsive layout.

> markserv is meant to feel nice for local docs, READMEs, and note collections.
""",
    "guides/project-overview.md": """
# Project overview

markserv turns a Markdown file or docs folder into a clean local site for READMEs, notes, and lightweight project docs.

It supports GitHub-flavored markdown, syntax highlighting, heading anchors, live reload, sidebar navigation, and theme switching out of the box.

## Included

- [x] GitHub-flavored Markdown
- [x] Syntax-highlighted fenced code blocks
- [x] Automatic heading anchors
- [x] Sidebar navigation for docs folders
- [x] System, light, and dark themes

## Quick start

```bash
uv tool install markserv
markserv README.md
markserv docs/
```

## Front matter

```yaml
---
title: Deployment guide
nav_order: 10
hidden: false
---
```

## Good fit

| Use case | Why it fits |
| --- | --- |
| Project README | Open a polished local view in one command |
| Team notes | Keep docs in plain Markdown |
| Docs folder | Browse nested pages from a generated sidebar |
""",
    "guides/quickstart.md": """---
title: Quickstart Guide
nav_label: Start Here
nav_order: 5
---

# Quickstart

This page gives you a quick way to verify the basics.

## Checklist

- [x] Markdown is rendered with GitHub-style formatting
- [x] Sidebar navigation is generated from nested folders
- [x] Theme choice is stored in browser storage
- [x] Synthetic demo content renders without touching the filesystem

## Code block

```python
from pathlib import Path

root = Path("docs")
print(root.resolve())
```

## Table

| Feature | Status |
| --- | --- |
| Live preview | Ready |
| Sidebar nav | Ready |
| Theme picker | Ready |

Continue to the [front matter demo](features/front-matter.md).
""",
    "guides/features/front-matter.md": """---
title: YAML front matter
nav_label: Front matter
nav_order: 10
---

# YAML front matter

This page uses YAML front matter to customize its browser title, sidebar label, and position in the nav.

## Example

```yaml
---
title: YAML front matter
nav_label: Front matter
nav_order: 10
hidden: false
---
```

## What it powers

- **title** sets the browser title fallback
- **nav_label** overrides the sidebar label
- **nav_order** controls sidebar ordering
- **hidden** keeps a page routable while removing it from the sidebar

You can also open the [hidden page](../../reference/hidden-page.md) to see that last behavior in action.
""",
    "guides/features/gfm.md": """---
nav_label: GFM examples
nav_order: 20
---

# GitHub-flavored markdown examples

This page exercises a few GFM features.

## Formatting

You can render **bold text**, *italic text*, ~~strikethrough~~, and `inline code`.

## Blockquote

> Markdown previews should be quick to open and pleasant to read.
>
> — local docs enjoyer

## Task list

- [x] Tables
- [x] Fenced code blocks
- [x] Blockquotes
- [x] Nested navigation

## Ordered list

1. Open the demo.
2. Change the selected page.
3. Explore the nested tree.

Back to the [demo home](../../README.md).
""",
    "guides/nested/deep-dive.md": """---
nav_order: 15
---

# Deep dive

This file lives in a nested folder so you can inspect sidebar behavior.

## Notes

Nested folders are shown as expandable sections in the sidebar.

### Another level

The current page should stay highlighted while its parent folders remain open.

See the [reference notes](../../reference/notes.md) for a simple cross-link.
""",
    "reference/notes.md": """---
nav_order: 30
---

# Reference notes

A small page for cross-link testing.

## Relative links

- [Back home](../README.md)
- [Quickstart](../guides/quickstart.md)
- [Project overview](../guides/project-overview.md)
- [Deep dive](../guides/nested/deep-dive.md)
- [Hidden page](hidden-page.md)

## Inline HTML

GitHub-flavored markdown rendering should also tolerate small inline HTML snippets like <kbd>Ctrl</kbd> + <kbd>C</kbd>.
""",
    "reference/hidden-page.md": """---
title: Hidden page
hidden: true
---

# Hidden page

This page is still routable, but it is intentionally omitted from the sidebar because `hidden: true` is set in front matter.

Head back to the [reference notes](notes.md) or the [demo home](../README.md).
""",
}

__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "build_demo_site", "create_demo_app", "main", "serve_demo"]

app = App(
    name="markserv.demo",
    help="Serve the built-in synthetic markdown demo.",
    help_formatter=PlainFormatter(),
    result_action="return_value",
)


def build_demo_site() -> SyntheticSite:
    return SyntheticSite(
        name="markserv demo",
        root_label="built-in demo",
        documents=DEMO_DOCUMENTS,
        default_doc="README.md",
    )


def create_demo_app() -> FastAPI:
    return create_app(build_demo_site())


def serve_demo(*, host: str, port: int, open_browser: bool) -> None:
    site = build_demo_site()
    serve_application(
        None if python_reload_enabled() else create_app(site),
        source="markserv demo",
        root_dir=site.root_label,
        host=host,
        port=port,
        open_browser=open_browser,
        app_factory_import="markserv.demo:create_demo_app",
    )


@app.default
def serve(
    *,
    host: Annotated[str, Parameter(help="Host interface to bind.")] = DEFAULT_HOST,
    port: Annotated[int, Parameter(help="Port to listen on.")] = DEFAULT_PORT,
    open_browser: Annotated[
        bool,
        Parameter(name="--open", help="Open the app in your default browser after the server starts."),
    ] = True,
) -> None:
    """Serve the built-in synthetic markdown demo."""
    serve_demo(host=host, port=port, open_browser=open_browser)


def main(argv: list[str] | None = None) -> None:
    app(tokens=argv)


if __name__ == "__main__":
    main()
