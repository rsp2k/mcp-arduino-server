# MCP Arduino Server - Makefile
# ==============================

# Load environment variables from .env if exists
-include .env
export

# Color output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

# Get package version from pyproject.toml
VERSION := $(shell grep '^version' pyproject.toml | cut -d'"' -f2)

.PHONY: help
help: ## Show this help message
	@echo "$(GREEN)MCP Arduino Server - v$(VERSION)$(NC)"
	@echo "$(YELLOW)Usage:$(NC)"
	@echo "  make [target]"
	@echo ""
	@echo "$(YELLOW)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

.PHONY: install
install: ## Install dependencies with uv
	@echo "$(YELLOW)Installing dependencies...$(NC)"
	uv pip install -e ".[dev]"
	@echo "$(GREEN)Installation complete!$(NC)"

.PHONY: dev
dev: ## Run development server with debug logging
	@echo "$(GREEN)Starting development server...$(NC)"
	LOG_LEVEL=DEBUG uv run mcp-arduino-server

.PHONY: run
run: ## Run the MCP server
	@echo "$(GREEN)Starting MCP Arduino Server...$(NC)"
	uv run mcp-arduino-server

.PHONY: test
test: ## Run tests
	@echo "$(YELLOW)Running tests...$(NC)"
	uv run pytest tests/ -v --cov=mcp_arduino_server --cov-report=html

.PHONY: lint
lint: ## Run linting
	@echo "$(YELLOW)Running ruff...$(NC)"
	uv run ruff check src/
	uv run ruff format --check src/

.PHONY: format
format: ## Format code
	@echo "$(YELLOW)Formatting code...$(NC)"
	uv run ruff check --fix src/
	uv run ruff format src/

.PHONY: typecheck
typecheck: ## Run type checking
	@echo "$(YELLOW)Running mypy...$(NC)"
	uv run mypy src/

.PHONY: clean
clean: ## Clean up temporary files and caches
	@echo "$(YELLOW)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	rm -rf src/*.egg-info build dist
	rm -rf uv.lock
	@echo "$(GREEN)Cleanup complete$(NC)"

.PHONY: arduino-install-core
arduino-install-core: ## Install Arduino core (e.g., make arduino-install-core CORE=arduino:avr)
	@echo "$(YELLOW)Installing Arduino core: $(CORE)$(NC)"
	arduino-cli core install $(CORE)

.PHONY: arduino-list-boards
arduino-list-boards: ## List connected Arduino boards
	@echo "$(YELLOW)Listing connected boards...$(NC)"
	arduino-cli board list

.PHONY: arduino-init
arduino-init: ## Initialize Arduino CLI
	@echo "$(YELLOW)Initializing Arduino CLI...$(NC)"
	arduino-cli config init
	arduino-cli core install arduino:avr
	@echo "$(GREEN)Arduino CLI initialized$(NC)"

.PHONY: publish
publish: clean ## Build and publish to PyPI
	@echo "$(YELLOW)Building package...$(NC)"
	uv build
	@echo "$(GREEN)Package built. To publish, run:$(NC)"
	@echo "  uv publish"

.PHONY: install-hooks
install-hooks: ## Install git hooks
	@echo "$(YELLOW)Installing git hooks...$(NC)"
	@echo '#!/bin/bash' > .git/hooks/pre-commit
	@echo 'make lint' >> .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "$(GREEN)Git hooks installed$(NC)"

.PHONY: setup
setup: install arduino-init ## Complete setup (install deps + Arduino)
	@echo "$(GREEN)Setup complete!$(NC)"
	@echo ""
	@echo "Next steps:"
	@echo "1. Set your OpenAI API key in .env"
	@echo "2. Run 'make dev' to start the server"
	@echo "3. Or add to Claude Code: claude mcp add arduino \"uvx mcp-arduino-server\""

# Default target
.DEFAULT_GOAL := help