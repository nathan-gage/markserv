.DEFAULT_GOAL := all

TOML_FILES := pyproject.toml
TAPLO := uv run taplo

.PHONY: .uv
.uv: ## Check that uv is installed
	@uv --version || echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'

.PHONY: install-python
install-python: .uv ## Install development and lint dependencies
	uv sync --frozen

.PHONY: install
install: install-python ## Install local development dependencies

.PHONY: setup
setup: install ## Backward-compatible alias for install

.PHONY: sync
sync: .uv ## Update local packages and uv.lock
	uv sync

.PHONY: clean
clean: ## Remove generated build and tool artifacts
	rm -rf .coverage .mypy_cache .pytest_cache .ruff_cache .pyright dist build htmlcov

.PHONY: format-python
format-python: ## Format Python code
	uv run ruff format src tests
	uv run ruff check --fix --fix-only src tests

.PHONY: format-toml
format-toml: ## Format TOML files
	$(TAPLO) format $(TOML_FILES)

.PHONY: format
format: format-python format-toml ## Format the codebase

.PHONY: format-check-python
format-check-python: ## Check Python formatting without modifying files
	uv run ruff format --check src tests

.PHONY: format-check-toml
format-check-toml: ## Check TOML formatting without modifying files
	$(TAPLO) format --check $(TOML_FILES)

.PHONY: format-check
format-check: format-check-python format-check-toml ## Check formatting without modifying files

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
test: ## Run the test suite
	COLUMNS=120 uv run pytest

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
