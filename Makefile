PYTHON ?= python

.PHONY: bootstrap validate-config dry-run test lint typecheck quality

bootstrap:
	$(PYTHON) -m alpha_research.cli.main bootstrap

validate-config:
	$(PYTHON) -m alpha_research.cli.main config-validate

dry-run:
	$(PYTHON) -m alpha_research.cli.main run-full-pipeline --dry-run

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests

typecheck:
	$(PYTHON) -m mypy src/alpha_research

quality: lint typecheck test
