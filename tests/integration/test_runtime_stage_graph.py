from __future__ import annotations

from alpha_research.pipeline.runtime_release import resolve_stage_plan, stage_contract_snapshot


def test_run_full_pipeline_stage_plan_is_explicit_and_ordered() -> None:
    plan = resolve_stage_plan("run-full-pipeline")
    assert [stage.stage_id for stage in plan] == [
        "S01",
        "S02",
        "S03",
        "S04",
        "S05",
        "S06",
        "S07",
        "S08",
        "S09",
        "S10",
        "S11",
        "S12",
        "S13",
        "S14",
        "S15",
    ]


def test_stage_contract_snapshot_exposes_inputs_outputs_and_failure_semantics() -> None:
    snapshot = stage_contract_snapshot("run-report")
    assert snapshot
    final_stage = snapshot[-1]
    assert final_stage["stage_id"] == "S15"
    assert "review_bundle" in final_stage["produced_artifacts"]
    assert final_stage["failure_semantics"]
    assert final_stage["eligibility_contract"]
