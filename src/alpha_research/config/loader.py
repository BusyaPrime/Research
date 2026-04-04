from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args, get_origin

import yaml
from pydantic import BaseModel, ValidationError

from alpha_research.common.hashing import hash_file, hash_paths
from alpha_research.common.manifests import ConfigSnapshot, ConfigSnapshotEntry, write_json_document
from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.models import (
    CalendarConfig,
    CapacityConfig,
    CostsConfig,
    DataSourcesConfig,
    ExperimentConfig,
    FeaturesConfig,
    LabelsConfig,
    ModelsConfig,
    PortfolioConfig,
    PreprocessingConfig,
    ProjectConfig,
    ReportingConfig,
    ResolvedConfigBundle,
    SplitsConfig,
    UniverseConfig,
)


class ConfigValidationError(RuntimeError):
    """Raised when a config file fails validation."""


@dataclass(frozen=True)
class LoadedConfigBundle:
    bundle: ResolvedConfigBundle
    config_hash: str
    warnings: tuple[str, ...]
    file_paths: tuple[Path, ...]


CONFIG_FILE_MODELS: dict[str, type[BaseModel]] = {
    "project.yaml": ProjectConfig,
    "data_sources.yaml": DataSourcesConfig,
    "calendar.yaml": CalendarConfig,
    "universe.yaml": UniverseConfig,
    "labels.yaml": LabelsConfig,
    "features.yaml": FeaturesConfig,
    "preprocessing.yaml": PreprocessingConfig,
    "models.yaml": ModelsConfig,
    "splits.yaml": SplitsConfig,
    "portfolio.yaml": PortfolioConfig,
    "costs.yaml": CostsConfig,
    "capacity.yaml": CapacityConfig,
    "reporting.yaml": ReportingConfig,
}


def load_yaml_file(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def iter_yaml_files(config_dir: Path) -> list[Path]:
    files = [config_dir / name for name in CONFIG_FILE_MODELS]
    experiments_dir = config_dir / "experiments"
    if experiments_dir.exists():
        files.extend(sorted(experiments_dir.glob("*.yaml")))
    return files


def _unwrap_annotation(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    if origin in (list, dict):
        return annotation
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    return args[0] if args else annotation


def _find_unknown_fields(model_cls: type[BaseModel], payload: Any, prefix: str = "") -> list[str]:
    if not isinstance(payload, dict):
        return []

    warnings: list[str] = []
    for key, value in payload.items():
        current_path = f"{prefix}.{key}" if prefix else key
        field_info = model_cls.model_fields.get(key)
        if field_info is None:
            warnings.append(current_path)
            continue

        annotation = _unwrap_annotation(field_info.annotation)
        origin = get_origin(annotation)

        if origin is list:
            args = get_args(annotation)
            item_type = args[0] if args else Any
            inner = _unwrap_annotation(item_type)
            if isinstance(value, list) and isinstance(inner, type) and issubclass(inner, BaseModel):
                for index, item in enumerate(value):
                    warnings.extend(_find_unknown_fields(inner, item, f"{current_path}[{index}]"))
        elif origin is dict:
            args = get_args(annotation)
            value_type = args[1] if len(args) == 2 else Any
            inner = _unwrap_annotation(value_type)
            if isinstance(value, dict) and isinstance(inner, type) and issubclass(inner, BaseModel):
                for dict_key, item in value.items():
                    warnings.extend(_find_unknown_fields(inner, item, f"{current_path}.{dict_key}"))
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            warnings.extend(_find_unknown_fields(annotation, value, current_path))

    return warnings


def validate_model(
    model_cls: type[BaseModel],
    payload: Any,
    path: Path,
    extra_policy: str = "forbid",
) -> tuple[BaseModel, list[str]]:
    try:
        if extra_policy == "warn":
            warnings = _find_unknown_fields(model_cls, payload)
            model = model_cls.model_validate(payload, extra="ignore")
            return model, warnings
        model = model_cls.model_validate(payload)
        return model, []
    except ValidationError as exc:
        raise ConfigValidationError(f"Validation failed for {path}: {exc}") from exc


def export_config_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "project.schema.json": ProjectConfig.model_json_schema(),
        "data_sources.schema.json": DataSourcesConfig.model_json_schema(),
        "experiment.schema.json": ExperimentConfig.model_json_schema(),
    }

    output_paths: list[Path] = []
    for name, schema in schemas.items():
        path = output_dir / name
        write_json_document(schema, path)
        output_paths.append(path)
    return output_paths


def build_config_snapshot(config_dir: Path) -> ConfigSnapshot:
    file_paths = iter_yaml_files(config_dir)
    entries = [
        ConfigSnapshotEntry(
            relative_path=path.relative_to(config_dir).as_posix(),
            sha256=hash_file(path),
            content=load_yaml_file(path),
        )
        for path in file_paths
    ]
    return ConfigSnapshot(config_hash=hash_paths(file_paths, config_dir), entries=entries)


def load_resolved_config_bundle(root: Path | None = None, extra_policy: str = "forbid") -> LoadedConfigBundle:
    paths = RepositoryPaths.from_root(root)
    file_paths = tuple(iter_yaml_files(paths.config_dir))

    loaded: dict[str, Any] = {}
    warnings: list[str] = []

    for file_name, model_cls in CONFIG_FILE_MODELS.items():
        path = paths.config_dir / file_name
        payload = load_yaml_file(path)
        model, model_warnings = validate_model(model_cls, payload, path, extra_policy=extra_policy)
        loaded[path.stem] = model
        warnings.extend(f"{path.name}: {warning}" for warning in model_warnings)

    experiments: dict[str, ExperimentConfig] = {}
    for path in sorted((paths.config_dir / "experiments").glob("*.yaml")):
        payload = load_yaml_file(path)
        model, model_warnings = validate_model(ExperimentConfig, payload, path, extra_policy=extra_policy)
        experiments[path.stem] = model
        warnings.extend(f"{path.name}: {warning}" for warning in model_warnings)

    bundle = ResolvedConfigBundle(experiments=experiments, **loaded)
    config_hash = hash_paths(list(file_paths), paths.config_dir)
    return LoadedConfigBundle(
        bundle=bundle,
        config_hash=config_hash,
        warnings=tuple(sorted(warnings)),
        file_paths=file_paths,
    )


def bundle_as_pretty_json(bundle: LoadedConfigBundle) -> str:
    payload = {
        "config_hash": bundle.config_hash,
        "warnings": list(bundle.warnings),
        "bundle": bundle.bundle.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
