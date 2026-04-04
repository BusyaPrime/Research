from __future__ import annotations

from pathlib import Path

from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.pipeline.runtime import OPERATIONAL_COMMANDS, execute_operational_command
from alpha_research.common.paths import RepositoryPaths


STAGE_COMMANDS = (
    "ingest-market",
    "ingest-fundamentals",
    "ingest-corporate-actions",
    "build-reference",
    "build-silver",
    "build-universe",
    "build-features",
    "build-labels",
    "build-gold",
    "run-train",
    "run-predict-oof",
    "run-backtest",
    "run-capacity",
    "run-report",
    "run-full-pipeline",
)

FULL_PIPELINE_ORDER = (
    "bootstrap",
    "reference_data",
    "market_ingest",
    "fundamentals_ingest",
    "corporate_actions",
    "qa",
    "pit",
    "universe",
    "features_labels",
    "gold_panel",
    "splits",
    "training",
    "portfolio",
    "execution_backtest",
    "capacity",
    "evaluation_reporting",
)


def build_stub_response(command_name: str, root: Path, loaded: LoadedConfigBundle) -> dict[str, object]:
    return {
        "command": command_name,
        "status": "stub",
        "root": str(root),
        "config_hash": loaded.config_hash,
        "temporary_simplification": True,
        "impact_on_research_validity": "Command surface exists, but stage logic is intentionally not implemented in foundation phase.",
        "next_dependency": "Implement the corresponding modules from backlog/ and MASTER_SPEC section 14 before using this command operationally.",
    }


def run_stage_command(command_name: str, root: Path, loaded: LoadedConfigBundle) -> dict[str, object]:
    if command_name not in OPERATIONAL_COMMANDS:
        return build_stub_response(command_name, root, loaded)

    result = execute_operational_command(command_name, RepositoryPaths.from_root(root), loaded)
    return {
        "command": command_name,
        "status": "completed",
        "root": str(root),
        "config_hash": loaded.config_hash,
        "run_id": result.run_id,
        "dataset_version": result.dataset_version,
        "manifest_path": str(result.manifest_path.relative_to(root)),
        "report_path": str(result.report_path.relative_to(root)),
        "review_bundle_path": str(result.review_bundle_path.relative_to(root)),
        "primary_artifact_path": str(result.primary_artifact_path.relative_to(root)),
        "notes": result.notes,
    }
