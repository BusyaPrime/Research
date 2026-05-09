# Local setup

The project targets Python 3.12 and keeps runtime and developer dependencies in
lock files. Prefer a dedicated virtual environment so release smoke artifacts and
cache files do not mix with other projects.

## Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock -r requirements-dev.lock
```

## macOS and Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock -r requirements-dev.lock
```

## Editable install

Use an editable install when changing package code or CLI entry points:

```bash
python -m pip install -e ".[dev,research]"
```

The lock-file install is better for release reproduction. The editable install is
better for local feature work.

## Smoke check

After installation, run:

```bash
python -m alpha_research config-validate
python -m alpha_research run-full-pipeline --dry-run
python -m pytest tests/unit
```

These commands should complete without network access. Network-backed adapter
checks belong in explicit live-public smoke runs.
