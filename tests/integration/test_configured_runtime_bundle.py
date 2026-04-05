from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.pipeline.bundle_loader import resolve_operational_bundle


def _write_csv(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def _enable_configured_adapter_mode(root: Path, security_master_path: Path, corporate_actions_path: Path, benchmark_path: Path) -> None:
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

    for adapter in data_sources["benchmark_provider"]["adapters"]:
        adapter["enabled"] = adapter["adapter_name"] == "local_file_benchmark"
        if adapter["adapter_name"] == "local_file_benchmark":
            adapter["local_path"] = str(benchmark_path.relative_to(root))

    data_sources_path.write_text(yaml.safe_dump(data_sources, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_configured_runtime_bundle_resolves_from_external_adapters(minimal_repo, monkeypatch) -> None:
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
    benchmark_path = _write_csv(
        minimal_repo / "fixtures" / "benchmark_market.csv",
        pd.DataFrame(
            [
                {"trade_date": "2024-06-03", "open": 500.0, "high": 501.0, "low": 499.0, "close": 500.5},
                {"trade_date": "2024-06-04", "open": 501.0, "high": 502.0, "low": 500.0, "close": 501.5},
            ]
        ),
    )
    _enable_configured_adapter_mode(minimal_repo, security_master_path, corporate_actions_path, benchmark_path)

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
    bundle = resolve_operational_bundle(
        RepositoryPaths.from_root(minimal_repo),
        loaded,
        start_date="2024-04-01",
        end_date="2024-06-04",
        n_securities=2,
    )

    assert len(bundle.security_master) == 2
    assert not bundle.silver_market.empty
    assert not bundle.silver_fundamentals.empty
    assert not bundle.benchmark_market.empty
    assert any("configured adapters" in note for note in bundle.notes)
    assert any("benchmark_adapter=local_file_benchmark" in note for note in bundle.notes)
