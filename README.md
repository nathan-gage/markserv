# markserv

`markserv` is a small FastAPI-based markdown preview server for local docs.

It uses:

- [`cmarkgfm`](https://github.com/theacodes/cmarkgfm) for GitHub-flavored markdown rendering
- [`FastAPI`](https://fastapi.tiangolo.com/) for the local web app
- [`FastHX`](https://github.com/volfpeter/fasthx) for HTMX-aware FastAPI rendering
- [`htmy`](https://github.com/volfpeter/htmy) for Python component-based HTML rendering
- [`github-markdown-css`](https://github.com/sindresorhus/github-markdown-css) for GitHub-like styling
- [`watchfiles`](https://github.com/samuelcolvin/watchfiles) for live reload
- [`ignoretree`](https://pypi.org/project/ignoretree/) to respect `.gitignore` rules while scanning

## Install

Once published:

```bash
uv tool install markserv
```

For local development:

```bash
uv tool install .
```

## Usage

Serve a directory of markdown files:

```bash
markserv docs/
```

Serve a single markdown file:

```bash
markserv README.md
```

Run the built-in synthetic demo site:

```bash
markserv.demo
```

Options:

```bash
markserv .
markserv --host localhost --port 4422 .
markserv --no-open README.md
markserv.demo --no-open --port 9001
```

## Behavior

- Renders common markdown extensions like `.md` and `.markdown`
- Adds heading anchors automatically for easy deep-linking
- Syntax-highlights fenced code blocks
- Watches markdown files and reloads the browser when content changes
- Respects `.gitignore` while scanning so ignored trees like `.venv/` are skipped
- Serves linked local assets from the same file tree with safer defaults for hidden, executable, and sensitive files
- In directory mode, shows a sidebar for browsing multiple markdown pages
- Supports YAML front matter for page titles and navigation labels/order
- Includes a system/light/dark theme control that remembers your choice in browser storage

## Front matter

`markserv` supports YAML front matter for navigation metadata:

```md
---
title: Overview
nav_label: Start Here
nav_order: 10
hidden: false
---

# Overview
```

Supported top-level keys:

- `title`: browser/page title fallback
- `nav_label`: sidebar label override
- `nav_order`: numeric sort order in the sidebar
- `hidden`: hide the page from sidebar navigation while keeping it routable

## Development

Install dev tooling:

```bash
make install
```

Common commands:

```bash
make format
make format-check
make lint
make typecheck
make test
make all-ci
```

## Notes

- This is intended for plain markdown / GFM-style docs, not MDX.
- UI components are rendered with `htmy` from Python.
- Front-end assets live under `src/markserv/public/`.
- Bundled CSS comes from `github-markdown-css`.
- Bundled HTMX assets are used for SSE-driven live updates.
- The upstream stylesheet license is included at `src/markserv/public/licenses/github-markdown-css.LICENSE`.
- The bundled HTMX license is included at `src/markserv/public/licenses/htmx.LICENSE`.
