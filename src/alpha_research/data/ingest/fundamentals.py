from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.common.hashing import hash_mapping
from alpha_research.common.io import read_json
from alpha_research.data.providers.base import FundamentalsProvider
from alpha_research.data.schemas import schema_field_names, validate_dataframe
from alpha_research.data.storage import (
    DatasetPaths,
    bronze_lineage_descriptor,
    build_request_key,
    maybe_load_manifest,
    persist_bronze_frame,
    persist_manifest,
    persist_payload,
    utc_now_iso,
)

CANONICAL_METRIC_MAP = {
    "bookequity": "book_equity",
    "book_equity": "book_equity",
    "stockholdersequity": "book_equity",
    "netincome": "net_income_ttm",
    "net_income": "net_income_ttm",
    "net_income_ttm": "net_income_ttm",
    "revenue": "revenue_ttm",
    "revenue_ttm": "revenue_ttm",
    "operatingcashflow": "operating_cashflow_ttm",
    "operating_cashflow_ttm": "operating_cashflow_ttm",
    "grossprofit": "gross_profit_ttm",
    "gross_profit_ttm": "gross_profit_ttm",
    "operatingincome": "operating_income_ttm",
    "operating_income_ttm": "operating_income_ttm",
    "totalassets": "total_assets",
    "total_assets": "total_assets",
    "totaldebt": "total_debt",
    "total_debt": "total_debt",
    "ebit": "ebit_ttm",
    "ebit_ttm": "ebit_ttm",
    "interestexpense": "interest_expense_ttm",
    "interest_expense_ttm": "interest_expense_ttm",
    "currentassets": "current_assets",
    "current_assets": "current_assets",
    "currentliabilities": "current_liabilities",
    "current_liabilities": "current_liabilities",
    "sharesoutstanding": "shares_outstanding",
    "shares_outstanding": "shares_outstanding",
}


def canonicalize_metric_name(metric_name_raw: str) -> str:
    normalized = "".join(ch for ch in str(metric_name_raw).lower() if ch.isalnum() or ch == "_").replace("__", "_")
    return CANONICAL_METRIC_MAP.get(normalized, normalized)


def compute_available_from(filing_date: object, acceptance_datetime: object, timezone: str = "America/New_York") -> pd.Timestamp:
    filing_ts = pd.Timestamp(filing_date) if pd.notna(filing_date) else pd.NaT
    acceptance_ts = pd.Timestamp(acceptance_datetime) if pd.notna(acceptance_datetime) else pd.NaT

    filing_eod_utc = pd.NaT
    if filing_ts is not pd.NaT and pd.notna(filing_ts):
        filing_eod_local = filing_ts.normalize().tz_localize(timezone) + pd.Timedelta(hours=23, minutes=59, seconds=59)
        filing_eod_utc = filing_eod_local.tz_convert("UTC")

    if acceptance_ts is not pd.NaT and pd.notna(acceptance_ts):
        if acceptance_ts.tzinfo is None:
            acceptance_ts = acceptance_ts.tz_localize("UTC")
        else:
            acceptance_ts = acceptance_ts.tz_convert("UTC")

    candidates = [value for value in (filing_eod_utc, acceptance_ts) if pd.notna(value)]
    if not candidates:
        return pd.NaT
    return max(candidates)


@dataclass(frozen=True)
class FundamentalsIngestArtifacts:
    request_key: str
    manifest_path: Path
    raw_payload_path: Path
    bronze_path: Path
    idempotent_hit: bool


class FundamentalsIngestionService:
    def __init__(self, root: Path | None = None, data_version: str = "v1", timezone: str = "America/New_York") -> None:
        self.paths = DatasetPaths.from_root(root)
        self.root = self.paths.root
        self.data_version = data_version
        self.timezone = timezone

    def ingest(self, provider: FundamentalsProvider, company_ids: list[str], start_date: str, end_date: str) -> FundamentalsIngestArtifacts:
        request_key = build_request_key(provider.name, provider.endpoint_name, company_ids, start_date, end_date)
        manifest_path = self.paths.raw_manifest_path("fundamentals", request_key)
        raw_path = self.paths.raw_payload_path("fundamentals", request_key)
        bronze_path = self.paths.bronze_path("fundamentals", request_key)

        if maybe_load_manifest(manifest_path):
            return FundamentalsIngestArtifacts(request_key, manifest_path, raw_path, bronze_path, True)

        page_token: str | None = None
        pages: list[dict[str, object]] = []
        records: list[dict[str, object]] = []
        while True:
            page = provider.fetch_fundamentals(company_ids, start_date, end_date, page_token=page_token)
            pages.append(page.original_payload)
            records.extend(page.records)
            page_token = page.next_page_token
            if page_token is None:
                break

        raw_package = {
            "provider_name": provider.name,
            "endpoint_name": provider.endpoint_name,
            "pages": pages,
        }
        persist_payload(raw_path, raw_package)

        bronze = pd.DataFrame.from_records(records)
        if bronze.empty:
            bronze = pd.DataFrame(
                columns=[
                    "security_id",
                    "source_company_id",
                    "form_type",
                    "filing_date",
                    "acceptance_datetime",
                    "fiscal_period_end",
                    "metric_name_raw",
                    "metric_name_canonical",
                    "metric_value",
                    "metric_unit",
                    "statement_type",
                    "available_from",
                    "is_restatement",
                    "data_version",
                ]
            )
        bronze["metric_name_raw"] = bronze["metric_name_raw"].astype("string")
        bronze["metric_name_canonical"] = bronze["metric_name_raw"].map(canonicalize_metric_name).astype("string")
        bronze["available_from"] = bronze.apply(
            lambda row: compute_available_from(row.get("filing_date"), row.get("acceptance_datetime"), timezone=self.timezone),
            axis=1,
        )
        bronze["metric_value"] = pd.to_numeric(bronze["metric_value"], errors="coerce")
        bronze["statement_type"] = bronze.get("statement_type", pd.Series("unknown", index=bronze.index))
        bronze["form_type"] = bronze.get("form_type", pd.Series(dtype="string"))
        bronze["metric_unit"] = bronze.get("metric_unit", pd.Series(dtype="string"))
        bronze["acceptance_datetime"] = pd.to_datetime(bronze.get("acceptance_datetime"), errors="coerce", utc=True)
        bronze["filing_date"] = pd.to_datetime(bronze.get("filing_date"), errors="coerce").dt.normalize()
        bronze["fiscal_period_end"] = pd.to_datetime(bronze.get("fiscal_period_end"), errors="coerce").dt.normalize()
        bronze["data_version"] = self.data_version

        sort_columns = ["source_company_id", "metric_name_canonical", "fiscal_period_end", "available_from"]
        bronze = bronze.sort_values(sort_columns, kind="stable").reset_index(drop=True)
        bronze["is_restatement"] = bronze.duplicated(["source_company_id", "metric_name_canonical", "fiscal_period_end"], keep="first")
        duplicate_exact_mask = bronze.duplicated(["source_company_id", "metric_name_canonical", "fiscal_period_end", "available_from"], keep=False)
        bronze = validate_dataframe(bronze[schema_field_names("bronze_fundamentals", root=self.root)], "bronze_fundamentals", root=self.root)
        persist_bronze_frame(bronze_path, bronze)
        lineage = bronze_lineage_descriptor(bronze, dataset="fundamentals", data_version=self.data_version, path=bronze_path)

        manifest = {
            "request_id": request_key,
            "provider_name": provider.name,
            "endpoint_name": provider.endpoint_name,
            "symbols_requested": sorted(company_ids),
            "start_date": start_date,
            "end_date": end_date,
            "fetched_at_utc": utc_now_iso(),
            "payload_path": str(raw_path.relative_to(self.root)),
            "row_count_raw": int(len(records)),
            "checksum": hash_mapping(raw_package),
            "row_count_bronze": int(len(bronze)),
            "bronze_path": str(bronze_path.relative_to(self.root)),
            "duplicate_fact_count": int(duplicate_exact_mask.sum()),
            "restatement_count": int(bronze["is_restatement"].sum()),
            **lineage,
        }
        persist_manifest(manifest_path, manifest)
        return FundamentalsIngestArtifacts(request_key, manifest_path, raw_path, bronze_path, False)

    def load_manifest(self, manifest_path: Path) -> dict[str, object]:
        return read_json(manifest_path)
