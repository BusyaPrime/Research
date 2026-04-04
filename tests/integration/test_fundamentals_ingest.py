from __future__ import annotations

import pandas as pd

from alpha_research.common.io import read_parquet
from alpha_research.data.ingest.fundamentals import FundamentalsIngestionService
from alpha_research.data.providers.base import ProviderPage
from alpha_research.data.schemas import validate_dataframe
from tests.helpers.fakes import PagedFundamentalsProvider


def _build_provider() -> PagedFundamentalsProvider:
    page_0 = {
        "data": [
            {
                "security_id": "SEC_AAPL",
                "source_company_id": "COMP_AAPL",
                "form_type": "10-Q",
                "filing_date": "2024-05-01",
                "acceptance_datetime": "2024-05-01T18:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "BookEquity",
                "metric_value": "1000",
                "metric_unit": "USD",
                "statement_type": "balance_sheet",
            },
            {
                "security_id": "SEC_AAPL",
                "source_company_id": "COMP_AAPL",
                "form_type": "10-Q",
                "filing_date": "2024-05-01",
                "acceptance_datetime": "2024-05-03T12:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "NetIncome",
                "metric_value": "250",
                "metric_unit": "USD",
                "statement_type": "income_statement",
            },
        ]
    }
    page_1 = {
        "data": [
            {
                "security_id": "SEC_AAPL",
                "source_company_id": "COMP_AAPL",
                "form_type": "10-Q/A",
                "filing_date": "2024-05-04",
                "acceptance_datetime": "2024-05-04T12:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "BookEquity",
                "metric_value": "1100",
                "metric_unit": "USD",
                "statement_type": "balance_sheet",
            },
            {
                "security_id": "SEC_AAPL",
                "source_company_id": "COMP_AAPL",
                "form_type": "10-Q",
                "filing_date": "2024-05-01",
                "acceptance_datetime": "2024-05-03T12:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "NetIncome",
                "metric_value": "250",
                "metric_unit": "USD",
                "statement_type": "income_statement",
            },
        ]
    }
    return PagedFundamentalsProvider(
        [
            ProviderPage(records=page_0["data"], original_payload=page_0, next_page_token="1"),
            ProviderPage(records=page_1["data"], original_payload=page_1),
        ]
    )


def test_fundamentals_available_from_uses_policy(minimal_repo) -> None:
    service = FundamentalsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["COMP_AAPL"], "2024-01-01", "2024-06-01")
    bronze = read_parquet(artifacts.bronze_path)
    first_row = bronze.loc[bronze["metric_name_canonical"] == "book_equity"].iloc[0]
    assert pd.Timestamp(first_row["available_from"]).isoformat() == "2024-05-02T03:59:59+00:00"


def test_fundamentals_fiscal_period_end_is_not_used_as_available_from(minimal_repo) -> None:
    service = FundamentalsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["COMP_AAPL"], "2024-01-01", "2024-06-01")
    bronze = read_parquet(artifacts.bronze_path)
    first_row = bronze.loc[bronze["metric_name_canonical"] == "book_equity"].iloc[0]
    assert pd.Timestamp(first_row["available_from"]).normalize() != pd.Timestamp(first_row["fiscal_period_end"]).tz_localize("UTC")


def test_fundamentals_restatement_flagged_separately(minimal_repo) -> None:
    service = FundamentalsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["COMP_AAPL"], "2024-01-01", "2024-06-01")
    bronze = read_parquet(artifacts.bronze_path)
    restated = bronze.loc[bronze["metric_name_canonical"] == "book_equity", "is_restatement"]
    assert restated.tolist() == [False, True]


def test_fundamentals_duplicate_facts_logged(minimal_repo) -> None:
    service = FundamentalsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["COMP_AAPL"], "2024-01-01", "2024-06-01")
    manifest = service.load_manifest(artifacts.manifest_path)
    assert manifest["duplicate_fact_count"] == 2


def test_fundamentals_metric_names_map_deterministically(minimal_repo) -> None:
    service = FundamentalsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["COMP_AAPL"], "2024-01-01", "2024-06-01")
    bronze = read_parquet(artifacts.bronze_path)
    assert set(bronze["metric_name_canonical"]) == {"book_equity", "net_income_ttm"}


def test_fundamentals_bronze_schema_validates(minimal_repo) -> None:
    service = FundamentalsIngestionService(root=minimal_repo)
    artifacts = service.ingest(_build_provider(), ["COMP_AAPL"], "2024-01-01", "2024-06-01")
    bronze = read_parquet(artifacts.bronze_path)
    validated = validate_dataframe(bronze, "bronze_fundamentals", root=minimal_repo)
    assert len(validated) == 4
