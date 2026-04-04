from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from alpha_research.common.paths import RepositoryPaths


@dataclass(frozen=True)
class FeatureMetadata:
    name: str
    family: str
    formula: str
    inputs: tuple[str, ...]
    notes: str
    lag_policy: str
    missing_policy: str
    normalization_policy: str
    pit_semantics: str


def _default_pit_semantics(family: str) -> str:
    if family in {"fundamentals", "staleness_flags"}:
        return "latest_available_from_leq_decision_timestamp"
    return "uses_data_available_by_close_t"


@lru_cache(maxsize=1)
def load_feature_registry(root: str | None = None) -> dict[str, FeatureMetadata]:
    paths = RepositoryPaths.from_root(Path(root) if root else None)
    raw = yaml.safe_load((paths.schema_dir / "feature_registry.yaml").read_text(encoding="utf-8"))

    registry: dict[str, FeatureMetadata] = {}
    for name, spec in raw.items():
        family = spec["family"]
        registry[name] = FeatureMetadata(
            name=name,
            family=family,
            formula=spec["formula"],
            inputs=tuple(spec.get("inputs", [])),
            notes=str(spec.get("notes", "")),
            lag_policy="close_t_decision_safe" if family not in {"fundamentals", "staleness_flags"} else "pit_available_from_safe",
            missing_policy="config_default_missing_policy",
            normalization_policy="config_default_cross_section_normalization",
            pit_semantics=_default_pit_semantics(family),
        )
    return registry


def feature_names_by_family(family: str, root: str | None = None) -> list[str]:
    registry = load_feature_registry(root)
    return [name for name, meta in registry.items() if meta.family == family]
