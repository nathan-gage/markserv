.DEFAULT_GOAL := all

TOML_FILES := pyproject.toml
TAPLO := uv run taplo
YAMLFIX := uv run yamlfix
YAML_PATHS := .github

.PHONY: .uv
.uv: ## Check that uv is installed
	@uv --version || echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'

.PHONY: install-python
install-python: .uv ## Install development and lint dependencies
	uv sync --frozen

.PHONY: install
install: install-python ## Install local development dependencies

.PHONY: install-assets
install-assets: ## Install optional Node dependencies for refreshing vendored browser assets
	npm ci

.PHONY: install-all-python
install-all-python: .uv ## Install and sync an environment for every supported Python version
	UV_PROJECT_ENVIRONMENT=.venv311 uv sync --python 3.11 --frozen
	UV_PROJECT_ENVIRONMENT=.venv312 uv sync --python 3.12 --frozen
	UV_PROJECT_ENVIRONMENT=.venv313 uv sync --python 3.13 --frozen
	UV_PROJECT_ENVIRONMENT=.venv314 uv sync --python 3.14 --frozen

.PHONY: setup
setup: install ## Backward-compatible alias for install

.PHONY: sync
sync: .uv ## Update local packages and uv.lock
	uv sync

.PHONY: vendor-assets
vendor-assets: ## Refresh vendored browser assets from installed Node packages
	npm run vendor

.PHONY: update-mermaid
update-mermaid: ## Update Mermaid and refresh its vendored browser assets
	npm run update:mermaid

.PHONY: clean
clean: ## Remove generated build and tool artifacts
	rm -rf .coverage .mypy_cache .pytest_cache .ruff_cache .pyright dist build htmlcov .venv311 .venv312 .venv313 .venv314

.PHONY: format-python
format-python: ## Format Python code
	uv run ruff format src tests
	uv run ruff check --fix --fix-only src tests

.PHONY: format-toml
format-toml: ## Format TOML files
	$(TAPLO) format $(TOML_FILES)

.PHONY: format-yaml
format-yaml: ## Format YAML files with yamlfix
	$(YAMLFIX) $(YAML_PATHS)

.PHONY: format
format: format-python format-toml format-yaml ## Format the codebase

.PHONY: format-check-python
format-check-python: ## Check Python formatting without modifying files
	uv run ruff format --check src tests

.PHONY: format-check-toml
format-check-toml: ## Check TOML formatting without modifying files
	$(TAPLO) format --check $(TOML_FILES)

.PHONY: format-check-yaml
format-check-yaml: ## Check YAML formatting without modifying files
	$(YAMLFIX) --check $(YAML_PATHS)

.PHONY: format-check
format-check: format-check-python format-check-toml format-check-yaml ## Check formatting without modifying files

.PHONY: lint
lint: ## Lint the code
	uv run ruff check src tests

.PHONY: typecheck-pyright
typecheck-pyright: ## Run static type checking with Pyright
	PYRIGHT_PYTHON_IGNORE_WARNINGS=1 uv run pyright

.PHONY: typecheck-mypy
typecheck-mypy: ## Run static type checking with Mypy
	uv run mypy

.PHONY: typecheck
typecheck: typecheck-pyright typecheck-mypy ## Run static type checking

.PHONY: test
test: ## Run tests (set PYTEST_PYTHON=3.14 to choose an interpreter)
	@# To test using a specific Python version, run 'make install-all-python' then set PYTEST_PYTHON=3.11 or similar
	COLUMNS=120 $(if $(PYTEST_PYTHON),UV_PROJECT_ENVIRONMENT=.venv$(subst .,,$(PYTEST_PYTHON))) uv run $(if $(PYTEST_PYTHON),--python $(PYTEST_PYTHON)) pytest

.PHONY: test-all-python
test-all-python: ## Run tests on Python 3.11 to 3.14
	COLUMNS=120 UV_PROJECT_ENVIRONMENT=.venv311 uv run --python 3.11 pytest
	COLUMNS=120 UV_PROJECT_ENVIRONMENT=.venv312 uv run --python 3.12 pytest
	COLUMNS=120 UV_PROJECT_ENVIRONMENT=.venv313 uv run --python 3.13 pytest
	COLUMNS=120 UV_PROJECT_ENVIRONMENT=.venv314 uv run --python 3.14 pytest

.PHONY: all
all: format lint typecheck test ## Run the standard local development checks

.PHONY: all-ci
all-ci: format-check lint typecheck test ## Run the CI check suite

.PHONY: help
help: ## Show this help (usage: make help)
	@echo "Usage: make [recipe]"
	@echo "Recipes:"
	@awk '/^[a-zA-Z0-9_-]+:.*?##/ { \
		helpMessage = match($$0, /## (.*)/); \
		if (helpMessage) { \
			recipe = $$1; \
			sub(/:/, "", recipe); \
			printf "  \033[36m%-20s\033[0m %s\n", recipe, substr($$0, RSTART + 3, RLENGTH); \
		} \
	}' $(MAKEFILE_LIST)
