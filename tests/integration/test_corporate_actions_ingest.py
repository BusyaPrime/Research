from __future__ import annotations

from alpha_research.common.io import read_parquet
from alpha_research.data.ingest.corporate_actions import CorporateActionsIngestionService
from alpha_research.data.providers.base import ProviderPage
from alpha_research.reference.security_master import SymbolMapper
from tests.helpers.fakes import PagedCorporateActionsProvider, sample_security_master


def _build_provider() -> PagedCorporateActionsProvider:
    page_0 = {
        "data": [
            {"symbol": "AAPL", "event_type": "split", "event_date": "2024-06-01", "effective_date": "2024-06-10", "split_ratio": 2.0},
            {"symbol": "MSFT", "event_type": "dividend", "event_date": "2024-06-02", "effective_date": "2024-06-15", "dividend_amount": 1.5},
            {"symbol": "GOOG", "event_type": "delisting", "event_date": "2024-06-03", "effective_date": "2024-06-20", "delisting_code": "MNA"},
        ]
    }
    page_1 = {
        "data": [
            {"old_symbol": "GOOG", "new_symbol": "GOOGL", "event_type": "symbol_change", "event_date": "2024-06-04", "effective_date": "2024-06-21"},
            {"symbol": "AAPL", "event_type": "merger", "event_date": "2024-06-05", "effective_date": "2024-06-22"},
        ]
    }
    return PagedCorporateActionsProvider(
        [
            ProviderPage(records=page_0["data"], original_payload=page_0, next_page_token="1"),
            ProviderPage(records=page_1["data"], original_payload=page_1),
        ]
    )


def test_corporate_actions_split_ratios_normalized(minimal_repo) -> None:
    mapper = SymbolMapper(sample_security_master())
    service = CorporateActionsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["AAPL", "MSFT", "GOOG"], "2024-06-01", "2024-06-30", mapper)
    bronze = read_parquet(artifacts.bronze_path)
    split = bronze.loc[bronze["event_type"] == "split"].iloc[0]
    assert float(split["split_ratio"]) == 2.0


def test_corporate_actions_dividend_attaches_security_id(minimal_repo) -> None:
    mapper = SymbolMapper(sample_security_master())
    service = CorporateActionsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["AAPL", "MSFT", "GOOG"], "2024-06-01", "2024-06-30", mapper)
    bronze = read_parquet(artifacts.bronze_path)
    dividend = bronze.loc[bronze["event_type"] == "dividend"].iloc[0]
    assert dividend["security_id"] == "SEC_MSFT"


def test_corporate_actions_delisting_reaches_canonical_layer(minimal_repo) -> None:
    mapper = SymbolMapper(sample_security_master())
    service = CorporateActionsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["AAPL", "MSFT", "GOOG"], "2024-06-01", "2024-06-30", mapper)
    bronze = read_parquet(artifacts.bronze_path)
    assert "delisting" in set(bronze["event_type"])


def test_corporate_actions_symbol_change_not_lost(minimal_repo) -> None:
    mapper = SymbolMapper(sample_security_master())
    service = CorporateActionsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["AAPL", "MSFT", "GOOG"], "2024-06-01", "2024-06-30", mapper)
    bronze = read_parquet(artifacts.bronze_path)
    symbol_change = bronze.loc[bronze["event_type"] == "symbol_change"].iloc[0]
    assert symbol_change["old_symbol"] == "GOOG"
    assert symbol_change["new_symbol"] == "GOOGL"


def test_corporate_actions_manifest_contains_row_counts(minimal_repo) -> None:
    mapper = SymbolMapper(sample_security_master())
    service = CorporateActionsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["AAPL", "MSFT", "GOOG"], "2024-06-01", "2024-06-30", mapper)
    manifest = service.load_manifest(artifacts.manifest_path)
    assert manifest["row_count_raw"] == 5
    assert manifest["row_count_valid"] == 4
    assert manifest["dataset_id"].startswith("bronze_corporate_actions__v1__")
    assert manifest["file_sha256"]


def test_corporate_actions_invalid_rows_written_to_failed_extract(minimal_repo) -> None:
    mapper = SymbolMapper(sample_security_master())
    service = CorporateActionsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["AAPL", "MSFT", "GOOG"], "2024-06-01", "2024-06-30", mapper)
    failed = read_parquet(artifacts.failed_extract_path)
    assert len(failed) == 1
    assert failed.iloc[0]["event_type"] == "merger"
