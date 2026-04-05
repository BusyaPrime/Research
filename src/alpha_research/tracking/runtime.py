from __future__ import annotations

import importlib.metadata
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from alpha_research.common.hashing import hash_mapping


class RuntimeMetadata(BaseModel):
    captured_at_utc: str
    git_commit_hash: str | None
    git_branch: str | None
    python_version: str
    python_executable: str
    platform: str
    environment_fingerprint_hash: str


def _run_git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def build_environment_fingerprint() -> str:
    packages = {
        dist.metadata["Name"]: dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    }
    payload = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "packages": dict(sorted(packages.items())),
    }
    return hash_mapping(payload)


def capture_runtime_metadata(root: Path) -> RuntimeMetadata:
    return RuntimeMetadata(
        captured_at_utc=datetime.now(UTC).isoformat(),
        git_commit_hash=_run_git(root, "rev-parse", "HEAD"),
        git_branch=_run_git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        python_version=platform.python_version(),
        python_executable=sys.executable,
        platform=platform.platform(),
        environment_fingerprint_hash=build_environment_fingerprint(),
    )
