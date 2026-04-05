from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root by walking upward for `pyproject.toml` or `.git`."""

    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate

    raise FileNotFoundError("Could not locate repository root from the provided start path.")


@dataclass(frozen=True)
class RepositoryPaths:
    root: Path

    @classmethod
    def from_root(cls, root: Path | None = None) -> RepositoryPaths:
        return cls(root=find_repo_root(root))

    @property
    def config_dir(self) -> Path:
        return self.root / "configs"

    @property
    def schema_dir(self) -> Path:
        return self.root / "schemas"

    @property
    def spec_dir(self) -> Path:
        return self.root / "docs" / "specs"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"
