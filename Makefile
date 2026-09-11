.PHONY: help install sync test test-fast lint format type cov cov-html check clean pre-commit-install pre-commit-run docs-build

help:
	@echo "P1 核心库常用命令："
	@echo "  make install         - 安装基础依赖与 dev 依赖（uv sync --extra dev）"
	@echo "  make test            - 跑全部测试 + 覆盖率报告（CI 等价）"
	@echo "  make test-fast       - 跑测试，跳过覆盖率统计"
	@echo "  make lint            - ruff check（lint）"
	@echo "  make format          - ruff format（自动修复 + 格式化）"
	@echo "  make type            - mypy --strict src"
	@echo "  make cov             - 仅生成覆盖率报告"
	@echo "  make cov-html        - 生成 HTML 覆盖率报告（htmlcov/）"
	@echo "  make check           - lint + format 检查 + type check + 测试"
	@echo "  make pre-commit-install - 安装 pre-commit 钩子"
	@echo "  make pre-commit-run  - 对全仓库执行 pre-commit"
	@echo "  make clean           - 清理构建产物与缓存"

install:
	uv sync --extra dev

sync:
	uv sync --extra dev

test:
	uv run pytest

test-fast:
	uv run pytest --no-cov

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

type:
	uv run mypy --strict src

cov:
	uv run pytest --cov-report=term-missing --no-cov-term-missing=skip-covered

cov-html:
	uv run pytest --cov-report=html

check: lint type test
	@echo "✓ lint + type + test 全部通过"

pre-commit-install:
	uv run pre-commit install

pre-commit-run:
	uv run pre-commit run --all-files

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage*
	find . -type d -name "__pycache__" -exec rm -rf {} +