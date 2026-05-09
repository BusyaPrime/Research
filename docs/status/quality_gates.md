# Quality gates

The repository has two CI paths:

- `ci.yml` runs the broad lint, type, test, integration, leakage, and configured
  local smoke matrix.
- `release_verification.yml` is the focused pull request path for release
  evidence: install, lint, typecheck, unit tests, release bundle verification,
  and configured-local smoke.

## Local equivalents

| CI step | Local command |
| --- | --- |
| Ruff lint | `make lint` |
| Mypy typecheck | `make typecheck` |
| Unit/default tests | `make test` |
| Release bundle verification | `make release-verify` |
| Configured local smoke | `make configured-local-smoke` |

## Review expectations

Run the focused path for changes touching pipeline orchestration, configured
adapters, release manifests, reporting, or status artifacts. For docs-only
changes, a markdown review is enough when no command contract changes.
