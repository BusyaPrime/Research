from __future__ import annotations

from pathlib import Path


def test_governance_artifacts_exist_and_cover_core_review_needs(repo_root: Path) -> None:
    expected_files = [
        repo_root / "docs" / "governance" / "README.md",
        repo_root / "docs" / "governance" / "goals_and_business_questions.md",
        repo_root / "docs" / "governance" / "unresolved_risks.md",
        repo_root / "docs" / "governance" / "raci.md",
        repo_root / "docs" / "governance" / "phase_definition_of_done.md",
        repo_root / "docs" / "governance" / "naming_and_versioning.md",
        repo_root / "docs" / "governance" / "experiment_and_rollback_policy.md",
        repo_root / "docs" / "governance" / "raw_data_immutability.md",
        repo_root / "docs" / "governance" / "anti_leakage_review_checklist.md",
        repo_root / "docs" / "governance" / "demo_plan.md",
        repo_root / "docs" / "governance" / "glossary.md",
    ]

    for path in expected_files:
        assert path.exists(), path


def test_anti_leakage_checklist_covers_time_pit_splits_and_execution(repo_root: Path) -> None:
    content = (repo_root / "docs" / "governance" / "anti_leakage_review_checklist.md").read_text(encoding="utf-8")
    assert "Time semantics" in content
    assert "PIT и fundamentals" in content
    assert "Splits и preprocessing" in content
    assert "Portfolio и execution" in content


def test_phase_definition_of_done_covers_all_delivery_phases(repo_root: Path) -> None:
    content = (repo_root / "docs" / "governance" / "phase_definition_of_done.md").read_text(encoding="utf-8")
    for marker in (
        "Фаза 1. Analyze and map",
        "Фаза 2. Foundation",
        "Фаза 3. Data layer",
        "Фаза 4. PIT & universe",
        "Фаза 5. Labels & features",
        "Фаза 6. Splits & models",
        "Фаза 7. Portfolio/backtest",
        "Фаза 8. Capacity/robustness/regimes/decay",
        "Фаза 9. Reporting & hardening",
    ):
        assert marker in content
