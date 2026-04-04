PYTHON ?= python

.PHONY: bootstrap validate-config dry-run test

bootstrap:
	$(PYTHON) -m alpha_research.cli.main bootstrap

validate-config:
	$(PYTHON) -m alpha_research.cli.main config-validate

dry-run:
	$(PYTHON) -m alpha_research.cli.main run-full-pipeline --dry-run

test:
	$(PYTHON) -m pytest
