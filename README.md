# markserv

`markserv` is a small FastAPI-based markdown preview server for local docs.

It uses:

- [`cmarkgfm`](https://github.com/theacodes/cmarkgfm) for GitHub-flavored markdown rendering
- [`FastAPI`](https://fastapi.tiangolo.com/) for the local web app
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

Options:

```bash
markserv --host 127.0.0.1 --port 8000 --open docs/
```

## Behavior

- Renders common markdown extensions like `.md` and `.markdown`
- Watches files and reloads the browser when content changes
- Respects `.gitignore` while scanning so ignored trees like `.venv/` are skipped
- Serves linked local assets like images from the same file tree
- In directory mode, shows a sidebar for browsing multiple markdown pages

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
- Bundled CSS comes from `github-markdown-css`.
- Front-end assets live under `src/markserv/public/`.
- The upstream stylesheet license is included at `src/markserv/public/licenses/github-markdown-css.LICENSE`.
