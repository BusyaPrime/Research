from __future__ import annotations

import json
from urllib.error import HTTPError

import pandas as pd

from alpha_research.config.models import AdapterConfig
from alpha_research.data.providers.configured_corporate_actions import YahooChartCorporateActionsProvider
from alpha_research.data.providers.configured_fundamentals import SecCompanyFactsProvider
from alpha_research.data.providers.configured_market import LocalFileMarketProvider
from alpha_research.data.providers.configured_transport import http_get_bytes


def test_configured_transport_retries_http_429(minimal_repo, monkeypatch) -> None:
    adapter = AdapterConfig(
        adapter_name="test_http",
        adapter_type="test_http",
        base_url="https://example.com",
        timeout_seconds=1,
        max_retries=2,
        backoff_seconds=0.0,
    )
    calls = {"count": 0}

    def _flaky_fetch(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = 30) -> bytes:
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(url, 429, "too many requests", hdrs=None, fp=None)
        return b'{"status":"ok"}'

    monkeypatch.setattr("alpha_research.data.providers.configured_transport._raw_http_get_bytes", _flaky_fetch)
    payload = http_get_bytes(adapter, "https://example.com/data", root=minimal_repo)
    assert payload == b'{"status":"ok"}'
    assert calls["count"] == 2


def test_configured_transport_cache_reuses_response(minimal_repo, monkeypatch) -> None:
    adapter = AdapterConfig(
        adapter_name="cached_http",
        adapter_type="test_http",
        base_url="https://example.com",
        cache_enabled=True,
        cache_subdir="contract_tests",
        backoff_seconds=0.0,
    )
    calls = {"count": 0}

    def _once(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = 30) -> bytes:
        calls["count"] += 1
        return b"cached-payload"

    monkeypatch.setattr("alpha_research.data.providers.configured_transport._raw_http_get_bytes", _once)
    first = http_get_bytes(adapter, "https://example.com/data", root=minimal_repo, cache_key="market::AAPL")
    second = http_get_bytes(adapter, "https://example.com/data", root=minimal_repo, cache_key="market::AAPL")
    assert first == b"cached-payload"
    assert second == b"cached-payload"
    assert calls["count"] == 1


def test_local_market_provider_contract_returns_provider_page(tmp_path) -> None:
    csv_path = tmp_path / "market.csv"
    pd.DataFrame(
        [
            {
                "provider_symbol": "AAPL",
                "trade_date": "2024-06-03",
                "open": 190.0,
                "high": 191.0,
                "low": 189.0,
                "close": 190.5,
                "adj_close": 190.5,
                "volume": 1_000_000,
                "currency": "USD",
                "raw_payload_version": "fixture_v1",
            }
        ]
    ).to_csv(csv_path, index=False)
    adapter = AdapterConfig(adapter_name="local_market", adapter_type="local_file_market_daily", local_path=str(csv_path))
    provider = LocalFileMarketProvider(adapter, tmp_path)
    page = provider.fetch_market_data(["AAPL", "MSFT"], "2024-06-01", "2024-06-05")
    assert provider.name == "local_market"
    assert page.next_page_token is None
    assert len(page.records) == 1
    assert page.missing_symbols == ["MSFT"]
    assert page.records[0]["provider_symbol"] == "AAPL"


def test_sec_companyfacts_provider_contract_maps_security_ids(minimal_repo, monkeypatch) -> None:
    adapter = AdapterConfig(
        adapter_name="sec_companyfacts_http",
        adapter_type="sec_companyfacts_http",
        base_url="https://data.sec.gov/api/xbrl/companyfacts",
        timeout_seconds=1,
        backoff_seconds=0.0,
    )
    raw_security_master = pd.DataFrame(
        [
            {"security_id": "SEC_1001", "source_company_id": "1001"},
        ]
    )

    def _fake_http(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = 30) -> bytes:
        assert "CIK0000001001.json" in url
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

    monkeypatch.setattr("alpha_research.data.providers.configured_transport._raw_http_get_bytes", _fake_http)
    provider = SecCompanyFactsProvider(adapter, raw_security_master, root=minimal_repo)
    page = provider.fetch_fundamentals(["1001"], "2024-04-01", "2024-06-30")
    assert provider.name == "sec_companyfacts_http"
    assert len(page.records) == 1
    assert page.records[0]["security_id"] == "SEC_1001"
    assert page.records[0]["metric_name_raw"] == "Assets"


def test_yahoo_corporate_actions_provider_contract_extracts_events(minimal_repo, monkeypatch) -> None:
    adapter = AdapterConfig(
        adapter_name="yahoo_chart_corporate_actions_http",
        adapter_type="yahoo_chart_corporate_actions_http",
        base_url="https://query1.finance.yahoo.com/v8/finance/chart",
        timeout_seconds=1,
        backoff_seconds=0.0,
    )

    def _fake_http(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = 30) -> bytes:
        assert "AAPL" in url
        return json.dumps(
            {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1717977600],
                            "indicators": {"quote": [{}], "adjclose": [{}]},
                            "events": {
                                "dividends": {
                                    "1717977600": {"date": 1717977600, "amount": 0.25}
                                },
                                "splits": {
                                    "1717977600": {"date": 1717977600, "numerator": 2, "denominator": 1}
                                },
                            },
                        }
                    ],
                    "error": None,
                }
            }
        ).encode("utf-8")

    monkeypatch.setattr("alpha_research.data.providers.configured_transport._raw_http_get_bytes", _fake_http)
    provider = YahooChartCorporateActionsProvider(adapter, root=minimal_repo)
    page = provider.fetch_corporate_actions(["AAPL"], "2024-06-01", "2024-06-30")
    event_types = {record["event_type"] for record in page.records}
    assert provider.name == "yahoo_chart_corporate_actions_http"
    assert event_types == {"dividend", "split"}
