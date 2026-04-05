from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.pipeline import runtime_research
from alpha_research.pipeline.runtime_ingest import INGEST_COMMANDS, execute_ingest_stage_command
from alpha_research.pipeline.runtime_verification import (
    strict_failure_semantics,
)


@dataclass(frozen=True)
class StageDefinition:
    stage_id: str
    name: str
    required_inputs: tuple[str, ...]
    produced_artifacts: tuple[str, ...]
    failure_semantics: str
    eligibility_contract: str
    predecessors: tuple[str, ...] = ()


STAGE_GRAPH: tuple[StageDefinition, ...] = (
    StageDefinition(
        stage_id="S01",
        name="reference_data",
        required_inputs=("security_master_raw",),
        produced_artifacts=("security_master",),
        failure_semantics=strict_failure_semantics(rationale="Reference layer задает идентичность бумаг для всех downstream joins.").rationale,
        eligibility_contract="release_grade_allowed=true; capability in {fixture_only, local_repro, public_adapter, release_candidate}",
    ),
    StageDefinition(
        stage_id="S02",
        name="market_ingest",
        required_inputs=("provider_market_api", "security_master"),
        produced_artifacts=("raw_market", "bronze_market"),
        failure_semantics=strict_failure_semantics(rationale="Потеря market ingest ломает prices, ADV, labels и execution path.").rationale,
        eligibility_contract="release_grade_allowed=true; provider contract must persist raw payload and manifest",
        predecessors=("S01",),
    ),
    StageDefinition(
        stage_id="S03",
        name="fundamentals_ingest",
        required_inputs=("provider_fundamentals_api", "security_master"),
        produced_artifacts=("raw_fundamentals", "bronze_fundamentals"),
        failure_semantics=strict_failure_semantics(rationale="Fundamentals ingest обязан сохранить PIT-совместимую availability chronology.").rationale,
        eligibility_contract="release_grade_allowed=true; available_from policy and raw manifest required",
        predecessors=("S01",),
    ),
    StageDefinition(
        stage_id="S04",
        name="corporate_actions",
        required_inputs=("provider_corporate_actions_api", "security_master"),
        produced_artifacts=("bronze_corporate_actions",),
        failure_semantics=strict_failure_semantics(rationale="Corporate actions влияют на continuity prices, listings и symbol mapping.").rationale,
        eligibility_contract="release_grade_allowed=true; failed extracts must be surfaced",
        predecessors=("S01",),
    ),
    StageDefinition(
        stage_id="S05",
        name="qa",
        required_inputs=("bronze_market", "bronze_fundamentals", "bronze_corporate_actions"),
        produced_artifacts=("qa_reports",),
        failure_semantics=strict_failure_semantics(rationale="QA должен fail-fast на сломанных source contracts до PIT и features.").rationale,
        eligibility_contract="release_grade_allowed=true; QA diagnostics required",
        predecessors=("S02", "S03", "S04"),
    ),
    StageDefinition(
        stage_id="S06",
        name="pit",
        required_inputs=("security_master", "bronze_market", "bronze_fundamentals", "bronze_corporate_actions"),
        produced_artifacts=("silver_market", "silver_fundamentals"),
        failure_semantics=strict_failure_semantics(rationale="PIT semantics нельзя деградировать без потери исследовательской валидности.").rationale,
        eligibility_contract="release_grade_allowed=true; future data forbidden",
        predecessors=("S01", "S02", "S03", "S04", "S05"),
    ),
    StageDefinition(
        stage_id="S07",
        name="universe",
        required_inputs=("silver_market", "security_master"),
        produced_artifacts=("universe_snapshot",),
        failure_semantics=strict_failure_semantics(rationale="Universe должен быть point-in-time и reproducible.").rationale,
        eligibility_contract="release_grade_allowed=true; exclusion reasons and diagnostics required",
        predecessors=("S06",),
    ),
    StageDefinition(
        stage_id="S08",
        name="features_labels",
        required_inputs=("silver_market", "silver_fundamentals", "universe_snapshot"),
        produced_artifacts=("feature_panel", "label_panel"),
        failure_semantics=strict_failure_semantics(rationale="Features/labels задают temporal correctness и leakage boundary.").rationale,
        eligibility_contract="release_grade_allowed=true; label alignment and registry-driven features required",
        predecessors=("S06", "S07"),
    ),
    StageDefinition(
        stage_id="S09",
        name="gold_panel",
        required_inputs=("feature_panel", "label_panel"),
        produced_artifacts=("gold_panel", "dataset_manifest"),
        failure_semantics=strict_failure_semantics(rationale="Gold panel фиксирует modeling dataset contract и lineage.").rationale,
        eligibility_contract="release_grade_allowed=true; immutable dataset manifest required",
        predecessors=("S08",),
    ),
    StageDefinition(
        stage_id="S10",
        name="splits",
        required_inputs=("gold_panel",),
        produced_artifacts=("fold_metadata", "validation_protocol"),
        failure_semantics=strict_failure_semantics(rationale="Split protocol ломает OOF purity при любой мягкой деградации.").rationale,
        eligibility_contract="release_grade_allowed=true; purge/embargo invariants required",
        predecessors=("S09",),
    ),
    StageDefinition(
        stage_id="S11",
        name="training",
        required_inputs=("gold_panel", "fold_metadata"),
        produced_artifacts=("oof_predictions", "oof_manifest", "evaluation_manifest"),
        failure_semantics=strict_failure_semantics(rationale="Training обязан сохранять OOF-only discipline и data-usage trace.").rationale,
        eligibility_contract="release_grade_allowed=true; evaluation protocol and purity checks required",
        predecessors=("S10",),
    ),
    StageDefinition(
        stage_id="S12",
        name="portfolio",
        required_inputs=("oof_predictions", "universe_snapshot"),
        produced_artifacts=("target_weights", "trades"),
        failure_semantics=strict_failure_semantics(rationale="Portfolio construction не должен маскировать broken constraints и participation caps.").rationale,
        eligibility_contract="release_grade_allowed=true; constraints and rejections required",
        predecessors=("S11", "S07"),
    ),
    StageDefinition(
        stage_id="S13",
        name="execution_backtest",
        required_inputs=("trades", "silver_market"),
        produced_artifacts=("portfolio_daily_state", "holdings_snapshots", "backtest_manifest"),
        failure_semantics=strict_failure_semantics(rationale="Execution/backtest формирует реальный gross/net accounting и cost path.").rationale,
        eligibility_contract="release_grade_allowed=true; gross/net, turnover and costs required",
        predecessors=("S12", "S06"),
    ),
    StageDefinition(
        stage_id="S14",
        name="capacity",
        required_inputs=("portfolio_daily_state", "trades"),
        produced_artifacts=("capacity_results", "capacity_manifest"),
        failure_semantics=strict_failure_semantics(rationale="Capacity stage нужен, чтобы слабые идеи умирали до красивого отчета.").rationale,
        eligibility_contract="release_grade_allowed=true; clipped/untradable diagnostics required",
        predecessors=("S13",),
    ),
    StageDefinition(
        stage_id="S15",
        name="evaluation_reporting",
        required_inputs=("oof_predictions", "portfolio_daily_state", "capacity_results"),
        produced_artifacts=("predictive_metrics", "portfolio_metrics", "report_bundle", "review_bundle"),
        failure_semantics=strict_failure_semantics(rationale="Reporting/release path обязан быть complete-or-fail и audit-ready.").rationale,
        eligibility_contract=(
            "release_grade_allowed=true; zero pending outputs; release_eligible bundle; "
            "capability in {release_candidate}"
        ),
        predecessors=("S11", "S13", "S14"),
    ),
)

STAGE_BY_ID = {stage.stage_id: stage for stage in STAGE_GRAPH}

COMMAND_TO_STAGE_IDS: dict[str, tuple[str, ...]] = {
    "build-reference": ("S01",),
    "ingest-market": ("S01", "S02"),
    "ingest-fundamentals": ("S01", "S03"),
    "ingest-corporate-actions": ("S01", "S04"),
    "build-silver": ("S01", "S02", "S03", "S04", "S05", "S06"),
    "build-universe": ("S01", "S02", "S03", "S04", "S05", "S06", "S07"),
    "build-features": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08"),
    "build-labels": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08"),
    "build-gold": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09"),
    "run-train": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11"),
    "run-predict-oof": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11"),
    "run-backtest": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13"),
    "run-capacity": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13", "S14"),
    "run-report": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13", "S14", "S15"),
    "run-full-pipeline": ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13", "S14", "S15"),
}


def resolve_stage_plan(command_name: str) -> list[StageDefinition]:
    if command_name not in COMMAND_TO_STAGE_IDS:
        raise KeyError(f"Unknown stage command: {command_name}")
    return [STAGE_BY_ID[stage_id] for stage_id in COMMAND_TO_STAGE_IDS[command_name]]


def stage_contract_snapshot(command_name: str) -> list[dict[str, object]]:
    return [
        {
            "stage_id": stage.stage_id,
            "name": stage.name,
            "required_inputs": list(stage.required_inputs),
            "produced_artifacts": list(stage.produced_artifacts),
            "failure_semantics": stage.failure_semantics,
            "eligibility_contract": stage.eligibility_contract,
            "predecessors": list(stage.predecessors),
        }
        for stage in resolve_stage_plan(command_name)
    ]


def execute_stage_command(command_name: str, root: Path, loaded: LoadedConfigBundle) -> dict[str, object]:
    stage_plan = resolve_stage_plan(command_name)
    stage_ids = [stage.stage_id for stage in stage_plan]
    if command_name == "build-reference" or command_name in INGEST_COMMANDS:
        payload = execute_ingest_stage_command(command_name, root, loaded, stage_ids=stage_ids)
    else:
        result = execute_operational_command(command_name, RepositoryPaths.from_root(root), loaded)
        payload = {
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
            "stage_ids": stage_ids,
        }
    payload["stage_contracts"] = stage_contract_snapshot(command_name)
    return payload


def execute_operational_command(
    command_name: str,
    paths: RepositoryPaths,
    loaded: LoadedConfigBundle,
    **kwargs: object,
) -> runtime_research.OperationalRunResult:
    return runtime_research.execute_operational_command(command_name, paths, loaded, **kwargs)
