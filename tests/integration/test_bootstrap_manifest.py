from __future__ import annotations

import json

from alpha_research.cli.main import main


def test_bootstrap_manifest_contains_required_fields(repo_copy) -> None:
    code = main(["bootstrap", "--root", str(repo_copy)])
    manifest_path = next((repo_copy / "artifacts" / "bootstrap").rglob("bootstrap_manifest.json"))
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert code == 0
    assert payload["config_hash"]
    assert payload["runtime_metadata"]["environment_fingerprint_hash"]
    assert payload["spec_hashes"]["master_spec"]
    assert payload["schema_paths"]
