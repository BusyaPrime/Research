from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.pipeline.stages import run_stage_command


def _write_csv(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def _enable_configured_adapter_mode(root: Path, security_master_path: Path, corporate_actions_path: Path) -> None:
    runtime_path = root / "configs" / "runtime.yaml"
    runtime_payload = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime_payload["ingest"]["provider_mode"] = "configured_adapters"
    runtime_path.write_text(yaml.safe_dump(runtime_payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    data_sources_path = root / "configs" / "data_sources.yaml"
    data_sources = yaml.safe_load(data_sources_path.read_text(encoding="utf-8"))

    for adapter in data_sources["market_provider"]["adapters"]:
        adapter["enabled"] = adapter["adapter_name"] == "stooq_eod_http"

    for adapter in data_sources["fundamentals_provider"]["adapters"]:
        adapter["enabled"] = adapter["adapter_name"] == "sec_companyfacts_http"

    for adapter in data_sources["security_master_provider"]["adapters"]:
        adapter["enabled"] = adapter["adapter_name"] == "local_file_security_master"
        if adapter["adapter_name"] == "local_file_security_master":
            adapter["local_path"] = str(security_master_path.relative_to(root))

    for adapter in data_sources["corporate_actions_provider"]["adapters"]:
        adapter["enabled"] = adapter["adapter_name"] == "local_file_corporate_actions"
        if adapter["adapter_name"] == "local_file_corporate_actions":
            adapter["local_path"] = str(corporate_actions_path.relative_to(root))

    data_sources_path.write_text(yaml.safe_dump(data_sources, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_configured_adapter_mode_runs_external_market_and_fundamentals(minimal_repo, monkeypatch) -> None:
    security_master_path = _write_csv(
        minimal_repo / "fixtures" / "external_security_master.csv",
        pd.DataFrame(
            [
                {
                    "security_id": "SEC_1001",
                    "symbol": "AAPL",
                    "security_type": "common_stock",
                    "exchange": "NASDAQ",
                    "listing_date": "1980-12-12",
                    "delisting_date": None,
                    "sector": "Technology",
                    "industry": "Consumer Electronics",
                    "country": "US",
                    "currency": "USD",
                    "is_common_stock": True,
                    "source_company_id": "1001",
                },
                {
                    "security_id": "SEC_1002",
                    "symbol": "MSFT",
                    "security_type": "common_stock",
                    "exchange": "NASDAQ",
                    "listing_date": "1986-03-13",
                    "delisting_date": None,
                    "sector": "Technology",
                    "industry": "Software",
                    "country": "US",
                    "currency": "USD",
                    "is_common_stock": True,
                    "source_company_id": "1002",
                },
            ]
        ),
    )
    corporate_actions_path = _write_csv(
        minimal_repo / "fixtures" / "corporate_actions.csv",
        pd.DataFrame(
            [
                {
                    "security_id": "SEC_1001",
                    "symbol": "AAPL",
                    "event_type": "split",
                    "event_date": "2024-06-10",
                    "effective_date": "2024-06-10",
                    "split_ratio": 2.0,
                    "dividend_amount": None,
                    "delisting_code": None,
                    "old_symbol": None,
                    "new_symbol": None,
                }
            ]
        ),
    )
    _enable_configured_adapter_mode(minimal_repo, security_master_path, corporate_actions_path)

    def _fake_http_get_bytes(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = 30) -> bytes:
        if "stooq.com" in url:
            if "aapl.us" in url:
                return b"Date,Open,High,Low,Close,Volume\n2024-06-03,190,191,189,190.5,1000000\n2024-06-04,191,192,190,191.5,1100000\n"
            if "msft.us" in url:
                return b"Date,Open,High,Low,Close,Volume\n2024-06-03,420,422,419,421.0,900000\n2024-06-04,421,423,420,422.5,950000\n"
        if "CIK0000001001.json" in url:
            return json.dumps(
                {
                    "facts": {
                        "us-gaap": {
                            "Assets": {
                                "units": {
                                    "USD": [
                                        {"end": "2024-03-31", "val": 352000000000, "filed": "2024-05-02", "form": "10-Q"}
                                    ]
                                }
                            }
                        }
                    }
                }
            ).encode("utf-8")
        if "CIK0000001002.json" in url:
            return json.dumps(
                {
                    "facts": {
                        "us-gaap": {
                            "Assets": {
                                "units": {
                                    "USD": [
                                        {"end": "2024-03-31", "val": 512000000000, "filed": "2024-04-25", "form": "10-Q"}
                                    ]
                                }
                            }
                        }
                    }
                }
            ).encode("utf-8")
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("alpha_research.data.providers.configured._http_get_bytes", _fake_http_get_bytes)

    loaded = load_resolved_config_bundle(minimal_repo)
    reference = run_stage_command("build-reference", minimal_repo, loaded)
    market = run_stage_command("ingest-market", minimal_repo, loaded)
    fundamentals = run_stage_command("ingest-fundamentals", minimal_repo, loaded)
    corporate_actions = run_stage_command("ingest-corporate-actions", minimal_repo, loaded)

    for payload in (reference, market, fundamentals, corporate_actions):
        assert payload["status"] == "completed"
        assert (minimal_repo / payload["manifest_path"]).exists()
        assert (minimal_repo / payload["primary_artifact_path"]).exists()
        assert any("configured adapters path" in note for note in payload["notes"])

    market_manifest = json.loads((minimal_repo / market["manifest_path"]).read_text(encoding="utf-8"))
    fundamentals_manifest = json.loads((minimal_repo / fundamentals["manifest_path"]).read_text(encoding="utf-8"))
    assert market_manifest["provider_name"] == "stooq_eod_http"
    assert fundamentals_manifest["provider_name"] == "sec_companyfacts_http"
    assert (minimal_repo / "data" / "reference" / "security_master.parquet").exists()
