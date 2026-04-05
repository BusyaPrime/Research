from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

import yaml


def test_acceptance_items_have_test_coverage_rules(repo_root: Path) -> None:
    acceptance_items = yaml.safe_load((repo_root / "tests" / "acceptance" / "acceptance_tests.yaml").read_text(encoding="utf-8"))
    coverage_payload = yaml.safe_load((repo_root / "docs" / "status" / "acceptance_coverage_map.yaml").read_text(encoding="utf-8"))
    rules = coverage_payload["coverage_rules"]

    for item in acceptance_items:
        matching_rules = [rule for rule in rules if fnmatch(item["test_id"], rule["acceptance_pattern"])]
        assert matching_rules, f"Нет coverage rule для {item['test_id']}"
        mapped_tests = []
        for rule in matching_rules:
            mapped_tests.extend(rule["tests"])
        assert mapped_tests, f"Coverage rule для {item['test_id']} не содержит тестовых файлов"
        for test_path in mapped_tests:
            assert (repo_root / test_path).exists(), f"{item['test_id']} -> отсутствует тестовый файл {test_path}"
