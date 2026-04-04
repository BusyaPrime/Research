from __future__ import annotations

import pandas as pd

from alpha_research.common.io import read_json, read_parquet
from alpha_research.data.ingest.market import MarketIngestionService
from alpha_research.data.providers.base import ProviderPage
from alpha_research.data.schemas import validate_dataframe
from alpha_research.reference.security_master import SymbolMapper
from tests.helpers.fakes import PagedMarketProvider, sample_security_master


def _build_provider() -> PagedMarketProvider:
    page_0_payload = {
        "data": [
            {"symbol": "AAPL", "trade_date": "2024-01-02", "open": 100, "high": 101, "low": 99, "close": 100.5, "adj_close": 100.5, "volume": 1000, "currency": "USD"},
            {"symbol": "MSFT", "trade_date": "2024-01-02", "open": 200, "high": 201, "low": 199, "close": 200.5, "adj_close": 200.5, "volume": 2000, "currency": "USD"},
        ],
        "next_page_token": "1",
    }
    page_1_payload = {
        "data": [
            {"symbol": "AAPL", "trade_date": "2024-01-03", "open": 101, "high": 102, "low": 100, "close": 101.5, "adj_close": 101.5, "volume": 1100, "currency": "USD"},
        ]
    }
    return PagedMarketProvider(
        [
            ProviderPage(records=page_0_payload["data"], original_payload=page_0_payload, next_page_token="1", missing_symbols=["ZZZZ"]),
            ProviderPage(records=page_1_payload["data"], original_payload=page_1_payload),
        ]
    )


def test_market_raw_payload_is_preserved_without_mutation(minimal_repo) -> None:
    provider = _build_provider()
    mapper = SymbolMapper(sample_security_master())
    service = MarketIngestionService(root=minimal_repo)
    artifacts = service.ingest(provider, ["AAPL", "MSFT", "ZZZZ"], "2024-01-01", "2024-01-03", mapper)

    raw_payload = read_json(artifacts.raw_payload_path)
    assert raw_payload["pages"][0]["data"][0]["symbol"] == "AAPL"
    assert raw_payload["pages"][1]["data"][0]["trade_date"] == "2024-01-03"


def test_market_request_manifest_created_for_batch(minimal_repo) -> None:
    provider = _build_provider()
    mapper = SymbolMapper(sample_security_master())
    service = MarketIngestionService(root=minimal_repo)
    artifacts = service.ingest(provider, ["AAPL", "MSFT"], "2024-01-01", "2024-01-03", mapper)

    manifest = service.load_manifest(artifacts.manifest_path)
    assert manifest["request_id"]
    assert manifest["row_count_raw"] == 3


def test_market_repeated_ingest_is_idempotent(minimal_repo) -> None:
    provider = _build_provider()
    mapper = SymbolMapper(sample_security_master())
    service = MarketIngestionService(root=minimal_repo)

    first = service.ingest(provider, ["AAPL", "MSFT"], "2024-01-01", "2024-01-03", mapper)
    second = service.ingest(provider, ["AAPL", "MSFT"], "2024-01-01", "2024-01-03", mapper)

    assert not first.idempotent_hit
    assert second.idempotent_hit
    assert provider.calls == 2


def test_market_pagination_keeps_all_rows(minimal_repo) -> None:
    provider = _build_provider()
    mapper = SymbolMapper(sample_security_master())
    service = MarketIngestionService(root=minimal_repo)
    artifacts = service.ingest(provider, ["AAPL", "MSFT"], "2024-01-01", "2024-01-03", mapper)

    bronze = read_parquet(artifacts.bronze_path)
    assert len(bronze) == 3
    assert set(bronze["security_id"]) == {"SEC_AAPL", "SEC_MSFT"}


def test_market_provider_missing_symbols_logged_separately(minimal_repo) -> None:
    provider = _build_provider()
    mapper = SymbolMapper(sample_security_master())
    service = MarketIngestionService(root=minimal_repo)
    artifacts = service.ingest(provider, ["AAPL", "MSFT", "ZZZZ"], "2024-01-01", "2024-01-03", mapper)

    manifest = service.load_manifest(artifacts.manifest_path)
    assert "ZZZZ" in manifest["missing_symbols"]


def test_market_bronze_schema_validates_after_ingest(minimal_repo) -> None:
    provider = _build_provider()
    mapper = SymbolMapper(sample_security_master())
    service = MarketIngestionService(root=minimal_repo)
    artifacts = service.ingest(provider, ["AAPL", "MSFT"], "2024-01-01", "2024-01-03", mapper)

    bronze = read_parquet(artifacts.bronze_path)
    validated = validate_dataframe(bronze, "bronze_market_daily", root=minimal_repo)
    assert len(validated) == 3
