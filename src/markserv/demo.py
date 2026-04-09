from __future__ import annotations

from typing import Annotated

from cyclopts import App, Parameter
from cyclopts.help import PlainFormatter

from .app import create_app
from .cli import DEFAULT_HOST, DEFAULT_PORT, serve_application
from .site import SyntheticSite

DEMO_DOCUMENTS = {
    "README.md": """# markserv demo

Welcome to the built-in demo site.

This sample tree exists so you can quickly try the renderer, sidebar navigation, live reload, and theme control.

## Try these pages

- [Quickstart](guides/quickstart.md)
- [GitHub-flavored markdown examples](guides/features/gfm.md)
- [Nested navigation](guides/nested/deep-dive.md)
- [Reference notes](reference/notes.md)

## What to try

- Toggle between **system**, **light**, and **dark** themes.
- Follow links between nested folders.
- Resize the window to see the responsive layout.

> markserv is meant to feel nice for local docs, READMEs, and note collections.
""",
    "guides/quickstart.md": """# Quickstart

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

Continue to the [feature examples](features/gfm.md).
""",
    "guides/features/gfm.md": """# GitHub-flavored markdown examples

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
    "guides/nested/deep-dive.md": """# Deep dive

This file lives in a nested folder so you can inspect sidebar behavior.

## Notes

Nested folders are shown as expandable sections in the sidebar.

### Another level

The current page should stay highlighted while its parent folders remain open.

See the [reference notes](../../reference/notes.md) for a simple cross-link.
""",
    "reference/notes.md": """# Reference notes

A small page for cross-link testing.

## Relative links

- [Back home](../README.md)
- [Quickstart](../guides/quickstart.md)
- [Deep dive](../guides/nested/deep-dive.md)

## Inline HTML

GitHub-flavored markdown rendering should also tolerate small inline HTML snippets like <kbd>Ctrl</kbd> + <kbd>C</kbd>.
""",
}

__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "build_demo_site", "main", "serve_demo"]

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


def serve_demo(*, host: str, port: int, open_browser: bool) -> None:
    site = build_demo_site()
    serve_application(
        create_app(site),
        source="markserv demo",
        root_dir=site.root_label,
        host=host,
        port=port,
        open_browser=open_browser,
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
