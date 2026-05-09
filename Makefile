PYTHON ?= python

.PHONY: bootstrap validate-config dry-run test lint typecheck quality release-verify configured-local-smoke

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

release-verify:
	$(PYTHON) ./scripts/verify_release_bundle.py --root .

configured-local-smoke:
	$(PYTHON) ./scripts/run_release_smoke.py --root . --mode configured-local
