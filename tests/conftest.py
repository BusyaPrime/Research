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


COPYTREE_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_tmp", ".pytest_cache")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=COPYTREE_IGNORE)


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def repo_copy(tmp_path: Path, repo_root: Path) -> Path:
    target = tmp_path / "repo"
    target.mkdir()

    _copy_tree(repo_root / "configs", target / "configs")
    _copy_tree(repo_root / "schemas", target / "schemas")
    _copy_tree(repo_root / "pseudocode", target / "pseudocode")
    _copy_file(repo_root / "backlog" / "backlog.yaml", target / "backlog" / "backlog.yaml")
    _copy_file(repo_root / "docs" / "specs" / "MASTER_SPEC.md", target / "docs" / "specs" / "MASTER_SPEC.md")
    _copy_file(repo_root / "docs" / "specs" / "machine_spec.yaml", target / "docs" / "specs" / "machine_spec.yaml")
    _copy_file(repo_root / "tests" / "acceptance" / "acceptance_tests.yaml", target / "tests" / "acceptance" / "acceptance_tests.yaml")

    for relative in ("artifacts", "logs"):
        (target / relative).mkdir(parents=True, exist_ok=True)

    (target / ".git").mkdir()
    (target / "pyproject.toml").write_text((repo_root / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture
def minimal_repo(tmp_path: Path, repo_root: Path) -> Path:
    target = tmp_path / "workspace"
    target.mkdir()

    _copy_tree(repo_root / "configs", target / "configs")
    _copy_tree(repo_root / "schemas", target / "schemas")

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

    _copy_tree(repo_root / "configs", target / "configs")
    _copy_tree(repo_root / "schemas", target / "schemas")
    _copy_file(repo_root / "docs" / "release_checklist.md", target / "docs" / "release_checklist.md")

    for relative in ("artifacts", "logs", "reports"):
        (target / relative).mkdir(parents=True, exist_ok=True)

    (target / ".git").mkdir()
    (target / "pyproject.toml").write_text((repo_root / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8")
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)
