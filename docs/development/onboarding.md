# Developer onboarding

This guide is the short path from a fresh clone to a reviewable local run of the
Alpha Research Platform. The canonical product and research contracts still live
in `docs/specs/MASTER_SPEC.md`, but this document explains the engineering
sequence a contributor should follow before opening a pull request.

## First read

Read these files in order:

1. `README.md` for the platform intent and current capability map.
2. `docs/specs/MASTER_SPEC.md` for the research and operational invariants.
3. `docs/specs/machine_spec.yaml` for machine-readable stage contracts.
4. `docs/runbooks/reproducible_local_runbook.md` for deterministic local runs.
5. `docs/status/spec_coverage_map.yaml` for the implementation-to-spec map.

## Local confidence path

The lightweight local confidence path is:

```bash
python -m pip install -r requirements.lock -r requirements-dev.lock
python -m alpha_research config-validate
python -m pytest tests/unit
python -m pytest tests/integration/test_config_loader.py
python .\scripts\run_release_smoke.py --root . --mode configured-local
```

Use the full CI-equivalent path before merging changes that affect the pipeline,
release bundle, point-in-time joins, OOF training, or reporting outputs.

## Review posture

Every change should preserve these invariants:

- no same-bar execution in backtests;
- no future fundamentals in point-in-time joins;
- preprocessing is fit only on train folds;
- release-grade runs do not silently fall back to fixture-only data;
- reports identify uncertainty, stability, and FDR evidence.

If a change intentionally relaxes one of these rules, document the reason in the
pull request and update the relevant spec/status artifact in the same branch.
