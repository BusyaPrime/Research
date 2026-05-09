# Troubleshooting

This page lists common local failures and the shortest useful recovery path.

## Import errors after cloning

Install the package in editable mode:

```bash
python -m pip install -e ".[dev,research]"
```

If the error only appears in an IDE, make sure the IDE interpreter points to the
same virtual environment used by the shell.

## Config validation fails

Run:

```bash
python -m alpha_research config-validate
```

Then inspect the failing config path and field name. Unknown fields are treated
as contract drift, not harmless extras.

## Configured adapter cannot find local data

Check whether the adapter uses `local_path` or `local_path_env`. Relative paths
are resolved from the repository root during local runs.

## Release smoke fails in live-public mode

Live-public mode can fail because of provider availability, rate limits, or
missing external configuration. Reproduce with configured-local mode first:

```bash
python .\scripts\run_release_smoke.py --root . --mode configured-local
```

Only debug external transport after the configured-local path is clean.

## Leakage tests fail

Treat leakage failures as correctness failures. Re-run the targeted test, then
inspect timestamp joins, fold boundaries, preprocessing fit points, and any
shortcut that may have pulled future data into the decision timestamp.
