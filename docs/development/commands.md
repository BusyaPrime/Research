# Command reference

Use this page as the local command index. The Makefile exposes the shortest
aliases, while the Python module commands are useful when debugging from a shell
or CI step.

## Make targets

| Command | Purpose |
| --- | --- |
| `make bootstrap` | Create local bootstrap artifacts through the CLI. |
| `make validate-config` | Validate the default configuration contract. |
| `make dry-run` | Execute the pipeline dispatcher without material side effects. |
| `make test` | Run the default pytest suite. |

## Python commands

| Command | Purpose |
| --- | --- |
| `python -m alpha_research config-validate` | Validate config files and adapter contracts. |
| `python -m alpha_research bootstrap` | Prepare local runtime directories and manifests. |
| `python -m alpha_research run-full-pipeline --dry-run` | Check the orchestration graph without running the full research workload. |
| `python .\scripts\verify_release_bundle.py --root .` | Verify release evidence artifacts. |
| `python .\scripts\run_release_smoke.py --root . --mode configured-local` | Run deterministic configured-local smoke. |
| `python .\scripts\run_release_smoke.py --root . --mode live-public` | Run live-public smoke against external providers. |

## Quality gates

```bash
python -m ruff check src tests
python -m mypy src/alpha_research
python -m pytest
```

Run the smaller unit/integration slices while developing. Run the full set before
opening a pull request that touches shared pipeline behavior.
