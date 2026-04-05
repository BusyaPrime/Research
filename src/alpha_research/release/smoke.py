from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import warnings

from alpha_research.common.manifests import write_json_document
from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import LoadedConfigBundle, load_resolved_config_bundle
from alpha_research.common.hashing import hash_mapping
from alpha_research.pipeline.runtime import execute_operational_command
from alpha_research.pipeline.stages import run_stage_command
from alpha_research.release.local_fixtures import prepare_local_configured_smoke_bundle
from alpha_research.release.verification import ReleaseVerificationResult, verify_release_bundle
from alpha_research.tracking.runtime import capture_runtime_metadata


@dataclass(frozen=True)
class ReleaseSmokeResult:
    summary_path: Path
    run_id: str
    verification: ReleaseVerificationResult
    ingest_commands_run: tuple[str, ...]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_smoke_loaded(loaded: LoadedConfigBundle) -> LoadedConfigBundle:
    smoke = loaded.bundle.runtime.release_smoke
    if smoke.experiment_key not in loaded.bundle.experiments:
        raise KeyError(f"В configs/runtime.yaml указан неизвестный experiment_key: {smoke.experiment_key}")

    experiment = loaded.bundle.experiments[smoke.experiment_key]
    model = experiment.model
    updated_model = model.model_copy(
        update={
            "n_trials": min(model.n_trials or smoke.max_model_trials, smoke.max_model_trials),
            "use_best_previous_params": False,
        }
    )
    smoke_experiment = experiment.model_copy(update={"model": updated_model})
    runtime_bundle = loaded.bundle.runtime
    if smoke.provider_mode_override is not None:
        runtime_bundle = runtime_bundle.model_copy(
            update={"ingest": runtime_bundle.ingest.model_copy(update={"provider_mode": smoke.provider_mode_override})}
        )
    if smoke.preferred_symbols is not None and not smoke.prepare_local_configured_fixtures:
        runtime_bundle = runtime_bundle.model_copy(
            update={"ingest": runtime_bundle.ingest.model_copy(update={"symbol_allowlist": list(smoke.preferred_symbols)})}
        )
    runtime_bundle = runtime_bundle.model_copy(update={"operational_experiment_key": smoke.experiment_key})
    smoke_bundle = loaded.bundle.model_copy(update={"experiments": {smoke.experiment_key: smoke_experiment}, "runtime": runtime_bundle})
    return replace(loaded, bundle=smoke_bundle, config_hash=hash_mapping(smoke_bundle.model_dump(mode="json")))


def run_release_smoke(
    root: Path | None = None,
    *,
    extra_policy: str = "forbid",
    provider_mode_override: str | None = None,
    prepare_local_configured_fixtures_override: bool | None = None,
) -> ReleaseSmokeResult:
    paths = RepositoryPaths.from_root(root)
    loaded = load_resolved_config_bundle(paths.root, extra_policy=extra_policy)
    smoke = loaded.bundle.runtime.release_smoke
    if not smoke.enabled:
        raise RuntimeError("Release smoke profile отключен в configs/runtime.yaml.")

    if provider_mode_override is not None or prepare_local_configured_fixtures_override is not None:
        smoke_override = smoke.model_copy(
            update={
                "provider_mode_override": provider_mode_override if provider_mode_override is not None else smoke.provider_mode_override,
                "prepare_local_configured_fixtures": (
                    prepare_local_configured_fixtures_override
                    if prepare_local_configured_fixtures_override is not None
                    else smoke.prepare_local_configured_fixtures
                ),
            }
        )
        loaded = replace(loaded, bundle=loaded.bundle.model_copy(update={"runtime": loaded.bundle.runtime.model_copy(update={"release_smoke": smoke_override})}))
        smoke = smoke_override

    smoke_loaded = _build_smoke_loaded(loaded)
    synthetic_bundle = None
    prepared_fixture_dir: Path | None = None
    if smoke.prepare_local_configured_fixtures:
        smoke_loaded, prepared_fixture_dir = prepare_local_configured_smoke_bundle(
            paths.root,
            smoke_loaded,
            start_date=smoke.start_date,
            end_date=smoke.end_date,
            n_securities=smoke.n_securities,
        )
    elif smoke_loaded.bundle.runtime.ingest.provider_mode == "synthetic_vendor_stub":
        from alpha_research.pipeline.fixture_data import build_synthetic_research_bundle

        synthetic_bundle = build_synthetic_research_bundle(
            start_date=smoke.start_date,
            end_date=smoke.end_date,
            n_securities=smoke.n_securities,
            seed=loaded.bundle.project.default_random_seed,
        )

    ingest_results: list[dict[str, object]] = []
    ingest_commands_run: list[str] = []
    if smoke.run_ingest_commands:
        for command_name in ("build-reference", "ingest-market", "ingest-fundamentals", "ingest-corporate-actions"):
            payload = run_stage_command(command_name, paths.root, smoke_loaded)
            ingest_results.append(payload)
            ingest_commands_run.append(command_name)

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always", RuntimeWarning)
        operational = execute_operational_command(
            "run-report",
            paths,
            smoke_loaded,
            synthetic_bundle=synthetic_bundle,
            split_config=smoke.splits,
            capacity_config=smoke.capacity,
            universe_config=smoke.universe,
            cost_scenarios=smoke.cost_scenarios,
            bundle_start_date=smoke.start_date,
            bundle_end_date=smoke.end_date,
            bundle_n_securities=smoke.n_securities,
            ablation_max_feature_family_scenarios=smoke.ablation_max_feature_family_scenarios,
            ablation_max_preprocessing_scenarios=smoke.ablation_max_preprocessing_scenarios,
        )
        verification = verify_release_bundle(paths.root, operational.review_bundle_path)

    warning_messages = sorted({str(item.message) for item in caught_warnings if str(item.message)})

    started_at = _now_utc()
    summary_dir = paths.artifacts_dir / "release_smoke"
    summary_path = summary_dir / f"release_smoke_{started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    write_json_document(
        {
            "status": "completed",
            "profile": smoke.model_dump(mode="json"),
            "config_hash": smoke_loaded.config_hash,
            "runtime_metadata": capture_runtime_metadata(paths.root).model_dump(mode="json"),
            "prepared_fixture_dir": None if prepared_fixture_dir is None else str(prepared_fixture_dir.relative_to(paths.root)),
            "ingest_commands_run": ingest_commands_run,
            "ingest_results": ingest_results,
            "operational_run": {
                "run_id": operational.run_id,
                "manifest_path": str(operational.manifest_path.relative_to(paths.root)),
                "report_path": str(operational.report_path.relative_to(paths.root)),
                "review_bundle_path": str(operational.review_bundle_path.relative_to(paths.root)),
                "primary_artifact_path": str(operational.primary_artifact_path.relative_to(paths.root)),
                "dataset_version": operational.dataset_version,
                "notes": operational.notes,
            },
            "verification": {
                "ok": verification.ok,
                "review_bundle_path": str(verification.review_bundle_path.relative_to(paths.root)),
                "manifest_count": verification.manifest_count,
                "report_count": verification.report_count,
                "section_count": verification.section_count,
                "figure_count": verification.figure_count,
                "pending_output_count": verification.pending_output_count,
                "notes": verification.notes,
            },
            "runtime_warnings": warning_messages,
        },
        summary_path,
    )
    return ReleaseSmokeResult(
        summary_path=summary_path,
        run_id=operational.run_id,
        verification=verification,
        ingest_commands_run=tuple(ingest_commands_run),
    )
