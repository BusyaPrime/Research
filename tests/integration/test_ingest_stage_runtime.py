from __future__ import annotations

from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.pipeline.stages import run_stage_command


def test_ingest_stage_commands_run_with_runtime_stub_adapter(minimal_repo) -> None:
    loaded = load_resolved_config_bundle(minimal_repo)

    market = run_stage_command("ingest-market", minimal_repo, loaded)
    fundamentals = run_stage_command("ingest-fundamentals", minimal_repo, loaded)
    corporate_actions = run_stage_command("ingest-corporate-actions", minimal_repo, loaded)

    for payload in (market, fundamentals, corporate_actions):
        assert payload["status"] == "completed"
        assert payload["manifest_path"]
        assert payload["primary_artifact_path"]
        assert (minimal_repo / payload["manifest_path"]).exists()
        assert (minimal_repo / payload["primary_artifact_path"]).exists()
        assert payload["notes"]

    assert (minimal_repo / "data" / "reference" / "security_master.parquet").exists()
