from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def repo_copy(tmp_path: Path, repo_root: Path) -> Path:
    target = tmp_path / "repo"
    target.mkdir()

    for relative in ("configs", "docs", "schemas", "tests", "pseudocode", "backlog"):
        source = repo_root / relative
        destination = target / relative
        shutil.copytree(source, destination)

    for relative in ("artifacts", "logs"):
        (target / relative).mkdir(parents=True, exist_ok=True)

    (target / ".git").mkdir()
    (target / "pyproject.toml").write_text((repo_root / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture
def minimal_repo(tmp_path: Path, repo_root: Path) -> Path:
    target = tmp_path / "workspace"
    target.mkdir()

    for relative in ("configs", "docs", "schemas", "pseudocode", "backlog"):
        source = repo_root / relative
        destination = target / relative
        shutil.copytree(source, destination)

    for relative in ("data", "artifacts", "logs", "reports"):
        (target / relative).mkdir(parents=True, exist_ok=True)

    (target / ".git").mkdir()
    (target / "pyproject.toml").write_text((repo_root / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture
def workspace_repo_copy(repo_root: Path) -> Path:
    base = repo_root / ".pytest_tmp"
    base.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="repo_", dir=base))

    for relative in ("configs", "docs", "schemas", "tests", "pseudocode", "backlog", ".github"):
        source = repo_root / relative
        if source.exists():
            shutil.copytree(source, target / relative)

    for relative in ("artifacts", "logs", "reports"):
        (target / relative).mkdir(parents=True, exist_ok=True)

    (target / ".git").mkdir()
    (target / "pyproject.toml").write_text((repo_root / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8")
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)
