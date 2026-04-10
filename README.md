# markserv

[![PyPI](https://img.shields.io/pypi/v/markserv.svg)](https://pypi.org/project/markserv/)
[![Python Versions](https://img.shields.io/pypi/pyversions/markserv.svg)](https://pypi.org/project/markserv/)
[![CI](https://github.com/nathan-gage/markserv/actions/workflows/ci.yml/badge.svg)](https://github.com/nathan-gage/markserv/actions/workflows/ci.yml)

`markserv` opens local Markdown files and docs folders in your browser as a lightweight live-preview web app.

Point it at a README, notes directory, or docs tree and you get a clean GitHub-style reading view with live reload, sidebar navigation, heading anchors, syntax highlighting, and theme switching.

![markserv screenshot](https://raw.githubusercontent.com/nathan-gage/markserv/main/.github/assets/readme-screenshot.png)

## Why markserv?

- GitHub-flavored Markdown rendering via [`cmarkgfm`](https://github.com/theacodes/cmarkgfm)
- Live reload while editing local docs
- Cmd/Ctrl+K quick search across pages, headings, and body text
- Sidebar navigation for directory-based docs
- Automatic heading anchors for deep-linking
- Syntax highlighting for fenced code blocks
- YAML front matter for titles and nav metadata
- Safer asset serving defaults for linked local files
- System, light, and dark theme support with saved preference

## Install

> Requires Python 3.11+

| Use case | Command |
| --- | --- |
| Install from PyPI with `uv` | `uv tool install markserv` |
| Install from PyPI with `pipx` | `pipx install markserv` |
| Install a local checkout for development | `uv tool install .` |

## Quick start

### Serve a docs directory

```bash
markserv docs/
```

### Serve a single Markdown file

```bash
markserv README.md
```

### Run the built-in demo site

```bash
markserv.demo
```

### Common variations

| Command | What it does |
| --- | --- |
| `markserv .` | Serve the current directory |
| `markserv --host localhost --port 4422 .` | Bind to a custom host/port |
| `markserv --no-open README.md` | Start without opening a browser |
| `markserv.demo --no-open --port 9001` | Run the demo on a custom port |

## What it does

- Renders common Markdown extensions like `.md` and `.markdown`
- Watches Markdown files and reloads the browser when content changes
- Supports Cmd/Ctrl+K quick search across page titles, headings, paths, and body text
- Respects `.gitignore` while scanning, so ignored trees like `.venv/` are skipped
- Serves linked local assets from the same file tree with safer defaults for hidden, executable, and sensitive files
- In directory mode, shows a sidebar for browsing multiple Markdown pages
- Adds heading anchors automatically for easy deep-linking
- Syntax-highlights fenced code blocks
- Supports YAML front matter for page titles and navigation labels/order
- Remembers your theme choice in browser storage

## Front matter

`markserv` supports YAML front matter for page and navigation metadata:

```md
---
title: Overview
nav_label: Start Here
nav_order: 10
hidden: false
---

# Overview
```

| Key | Purpose |
| --- | --- |
| `title` | Browser/page title fallback |
| `nav_label` | Sidebar label override |
| `nav_order` | Numeric sort order in the sidebar |
| `hidden` | Hide the page from sidebar navigation while keeping it routable |

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

| Task | Command |
| --- | --- |
| Format | `make format` |
| Check formatting | `make format-check` |
| Lint | `make lint` |
| Type-check | `make typecheck` |
| Test | `make test` |
| Run the full local CI suite | `make all-ci` |

## Notes

- `markserv` is intended for plain Markdown / GFM-style docs, not MDX.
- UI components are rendered with `htmy` from Python.
- Front-end assets live under `src/markserv/public/`.
- Bundled CSS comes from `github-markdown-css` and generated Pygments themes.
- Bundled HTMX assets are used for SSE-driven live updates.
- The upstream stylesheet license is included at `src/markserv/public/licenses/github-markdown-css.LICENSE`.
- The bundled HTMX license is included at `src/markserv/public/licenses/htmx.LICENSE`.
