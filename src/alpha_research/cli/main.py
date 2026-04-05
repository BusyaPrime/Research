from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from alpha_research.common.hashing import hash_file
from alpha_research.common.logging import configure_logging
from alpha_research.common.manifests import BootstrapManifest, write_model_document
from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import (
    build_config_snapshot,
    bundle_as_pretty_json,
    export_config_schemas,
    load_resolved_config_bundle,
)
from alpha_research.pipeline.stages import FULL_PIPELINE_ORDER, STAGE_COMMANDS, run_stage_command
from alpha_research.tracking.runtime import capture_runtime_metadata
from alpha_research.version import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alpha-research")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--root", type=Path, default=None)
    bootstrap.add_argument("--extra-policy", choices=("forbid", "warn"), default="forbid")

    config_validate = subparsers.add_parser("config-validate")
    config_validate.add_argument("--root", type=Path, default=None)
    config_validate.add_argument("--extra-policy", choices=("forbid", "warn"), default="forbid")

    config_dry_run = subparsers.add_parser("config-dry-run")
    config_dry_run.add_argument("--root", type=Path, default=None)
    config_dry_run.add_argument("--extra-policy", choices=("forbid", "warn"), default="forbid")

    for command in STAGE_COMMANDS:
        stage = subparsers.add_parser(command)
        stage.add_argument("--root", type=Path, default=None)
        stage.add_argument("--extra-policy", choices=("forbid", "warn"), default="forbid")
        stage.add_argument("--dry-run", action="store_true")

    return parser


def _resolve_root(root: Path | None) -> RepositoryPaths:
    return RepositoryPaths.from_root(root or Path.cwd())


def _collect_spec_hashes(paths: RepositoryPaths) -> dict[str, str]:
    candidates = {
        "master_spec": paths.spec_dir / "MASTER_SPEC.md",
        "machine_spec": paths.spec_dir / "machine_spec.yaml",
        "table_schemas": paths.schema_dir / "table_schemas.yaml",
        "feature_registry": paths.schema_dir / "feature_registry.yaml",
        "acceptance_tests": paths.root / "tests" / "acceptance" / "acceptance_tests.yaml",
        "pipeline_pseudocode": paths.root / "pseudocode" / "pipeline_pseudocode.md",
        "backlog": paths.root / "backlog" / "backlog.yaml",
    }
    return {name: hash_file(path) for name, path in candidates.items()}


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _run_bootstrap(args: argparse.Namespace) -> int:
    paths = _resolve_root(args.root)
    loaded = load_resolved_config_bundle(paths.root, extra_policy=args.extra_policy)
    run_id = f"bootstrap-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = paths.artifacts_dir / "bootstrap" / run_id
    logger = configure_logging(paths.logs_dir, run_id)

    config_snapshot = build_config_snapshot(paths.config_dir)
    config_snapshot_path = write_model_document(config_snapshot, run_dir / "config_snapshot.json")
    schema_paths = export_config_schemas(run_dir / "config_schemas")
    runtime_metadata = capture_runtime_metadata(paths.root)

    manifest = BootstrapManifest(
        run_id=run_id,
        config_hash=loaded.config_hash,
        config_snapshot_path=str(config_snapshot_path.relative_to(paths.root)),
        schema_paths=[str(path.relative_to(paths.root)) for path in schema_paths],
        spec_hashes=_collect_spec_hashes(paths),
        runtime_metadata=runtime_metadata,
        notes=[
            "Foundation bootstrap only.",
            "Часть stage-команд уже работает в operational path; незакрытый хвост остался в vendor ingest, model zoo и финальном release-hardening.",
        ],
    )
    manifest_path = write_model_document(manifest, run_dir / "bootstrap_manifest.json")
    logger.info("bootstrap manifest written")

    _print(
        {
            "status": "bootstrap_ok",
            "run_id": run_id,
            "config_hash": loaded.config_hash,
            "warnings": list(loaded.warnings),
            "manifest_path": str(manifest_path.relative_to(paths.root)),
        }
    )
    return 0


def _run_config_validate(args: argparse.Namespace) -> int:
    paths = _resolve_root(args.root)
    loaded = load_resolved_config_bundle(paths.root, extra_policy=args.extra_policy)
    _print(
        {
            "status": "config_valid",
            "config_hash": loaded.config_hash,
            "config_files": [str(path.relative_to(paths.root)) for path in loaded.file_paths],
            "warnings": list(loaded.warnings),
        }
    )
    return 0


def _run_config_dry_run(args: argparse.Namespace) -> int:
    paths = _resolve_root(args.root)
    loaded = load_resolved_config_bundle(paths.root, extra_policy=args.extra_policy)
    print(bundle_as_pretty_json(loaded))
    return 0


def _run_stage_command(args: argparse.Namespace) -> int:
    paths = _resolve_root(args.root)
    loaded = load_resolved_config_bundle(paths.root, extra_policy=args.extra_policy)

    if args.command == "run-full-pipeline" and args.dry_run:
        _print(
            {
                "status": "dry_run_only",
                "config_hash": loaded.config_hash,
                "pipeline_order": list(FULL_PIPELINE_ORDER),
                "warnings": list(loaded.warnings),
                "resolved_project": loaded.bundle.project.model_dump(mode="json"),
            }
        )
        return 0

    payload = run_stage_command(args.command, paths.root, loaded)
    _print(payload)
    return 0 if payload.get("status") == "completed" else 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "bootstrap":
        return _run_bootstrap(args)
    if args.command == "config-validate":
        return _run_config_validate(args)
    if args.command == "config-dry-run":
        return _run_config_dry_run(args)
    return _run_stage_command(args)


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
