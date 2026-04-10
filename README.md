# markserv

[![PyPI](https://img.shields.io/pypi/v/markserv.svg)](https://pypi.org/project/markserv/)
[![Python Versions](https://img.shields.io/pypi/pyversions/markserv.svg)](https://pypi.org/project/markserv/)
[![CI](https://github.com/nathan-gage/markserv/actions/workflows/ci.yml/badge.svg)](https://github.com/nathan-gage/markserv/actions/workflows/ci.yml)

`markserv` is a small FastAPI-based Markdown preview server for local docs.

Point it at a Markdown file or docs folder and it gives you a clean, GitHub-style reading view with live reload, sidebar navigation, heading anchors, and syntax highlighting.

## Highlights

- GitHub-flavored Markdown rendering via [`cmarkgfm`](https://github.com/theacodes/cmarkgfm)
- Live reload while editing local docs
- Directory browsing with sidebar navigation
- Automatic heading anchors for deep-linking
- Syntax highlighting for fenced code blocks
- YAML front matter for titles and nav metadata
- Safer asset serving defaults for linked local files
- System, light, and dark theme support with saved preference

## Install

### Install from PyPI

With `uv`:

```bash
uv tool install markserv
```

With `pipx`:

```bash
pipx install markserv
```

### Install locally for development

```bash
uv tool install .
```

## Quickstart

Serve a docs directory:

```bash
markserv docs/
```

Serve a single file:

```bash
markserv README.md
```

Run the built-in demo site:

```bash
markserv.demo
```

A few useful variations:

```bash
markserv .
markserv --host localhost --port 4422 .
markserv --no-open README.md
markserv.demo --no-open --port 9001
```

## How it behaves

- Renders common Markdown extensions like `.md` and `.markdown`
- Watches Markdown files and reloads the browser when content changes
- Respects `.gitignore` while scanning so ignored trees like `.venv/` are skipped
- Serves linked local assets from the same file tree with safer defaults for hidden, executable, and sensitive files
- In directory mode, shows a sidebar for browsing multiple Markdown pages
- Adds heading anchors automatically for easy deep-linking
- Syntax-highlights fenced code blocks
- Supports YAML front matter for page titles and navigation labels/order
- Remembers your theme choice in browser storage

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

## Tech stack

`markserv` uses:

- [`cmarkgfm`](https://github.com/theacodes/cmarkgfm) for GitHub-flavored Markdown rendering
- [`FastAPI`](https://fastapi.tiangolo.com/) for the local web app
- [`FastHX`](https://github.com/volfpeter/fasthx) for HTMX-aware FastAPI rendering
- [`htmy`](https://github.com/volfpeter/htmy) for Python component-based HTML rendering
- [`github-markdown-css`](https://github.com/sindresorhus/github-markdown-css) for GitHub-like styling
- [`watchfiles`](https://github.com/samuelcolvin/watchfiles) for live reload
- [`ignoretree`](https://pypi.org/project/ignoretree/) to respect `.gitignore` rules while scanning

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

- This is intended for plain Markdown / GFM-style docs, not MDX.
- UI components are rendered with `htmy` from Python.
- Front-end assets live under `src/markserv/public/`.
- Bundled CSS comes from `github-markdown-css` and generated Pygments themes.
- Bundled HTMX assets are used for SSE-driven live updates.
- The upstream stylesheet license is included at `src/markserv/public/licenses/github-markdown-css.LICENSE`.
- The bundled HTMX license is included at `src/markserv/public/licenses/htmx.LICENSE`.
