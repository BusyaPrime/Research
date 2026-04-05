from __future__ import annotations

from pathlib import Path

import yaml


def test_spec_coverage_map_references_existing_repo_paths(repo_root: Path) -> None:
    coverage_path = repo_root / "docs" / "status" / "spec_coverage_map.yaml"
    payload = yaml.safe_load(coverage_path.read_text(encoding="utf-8"))
    assert payload["clauses"]

    for clause in payload["clauses"]:
        assert clause["status"] in {"enforced", "partial", "planned"}
        for bucket_name in ("implemented_in", "tested_by", "surfaced_in"):
            assert clause[bucket_name]
            for relative_path in clause[bucket_name]:
                if relative_path.startswith(("manifests/", "diagnostics/")):
                    continue
                assert (repo_root / relative_path).exists(), f"{clause['clause_id']} -> missing path {relative_path}"
