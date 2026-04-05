from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alpha_research.config.models import AdapterConfig
from alpha_research.data.providers.base import FundamentalsProvider, ProviderPage
from alpha_research.data.providers.configured_transport import (
    ConfiguredAdapterError,
    http_get_bytes,
    load_table_from_path,
    provider_headers,
    provider_url,
    resolve_local_path,
)


def normalize_company_id(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        raise ConfiguredAdapterError(f"company_id `{value}` не похож на CIK/числовой идентификатор.")
    return digits.zfill(10)


class SecCompanyFactsProvider(FundamentalsProvider):
    def __init__(self, adapter: AdapterConfig, raw_security_master: pd.DataFrame, *, root: Path | None = None) -> None:
        self.adapter = adapter
        self.root = root
        self.raw_security_master = raw_security_master.copy()
        source_column = adapter.source_company_id_column or "source_company_id"
        if source_column not in self.raw_security_master.columns:
            raise ConfiguredAdapterError(
                f"В security master отсутствует колонка `{source_column}` для SEC fundamentals adapter."
            )
        self.source_company_id_column = source_column
        source_ids = self.raw_security_master[source_column].astype("string")
        security_ids = self.raw_security_master["security_id"].astype("string")
        self.company_to_security = {
            str(company_id): str(security_id)
            for company_id, security_id in zip(source_ids, security_ids, strict=False)
            if pd.notna(company_id) and pd.notna(security_id)
        }

    @property
    def name(self) -> str:
        return self.adapter.adapter_name

    def fetch_fundamentals(self, company_ids: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        if page_token is not None:
            return ProviderPage(records=[], original_payload={"records": [], "next_page_token": None}, next_page_token=None)

        start_ts = pd.Timestamp(start_date).normalize()
        end_ts = pd.Timestamp(end_date).normalize()
        records: list[dict[str, object]] = []
        payloads: list[dict[str, object]] = []

        for company_id in company_ids:
            cik = normalize_company_id(company_id)
            url = provider_url(self.adapter, f"CIK{cik}.json")
            payload = json.loads(
                http_get_bytes(self.adapter, url, headers=provider_headers(self.adapter), root=self.root, cache_key=url).decode("utf-8")
            )
            payloads.append({"company_id": company_id, "url": url})
            facts = payload.get("facts", {})
            security_id = self.company_to_security.get(str(company_id))
            if not security_id:
                continue
            for taxonomy_name, taxonomy_payload in facts.items():
                if not isinstance(taxonomy_payload, dict):
                    continue
                for metric_name_raw, metric_payload in taxonomy_payload.items():
                    units_payload = metric_payload.get("units", {})
                    if not isinstance(units_payload, dict):
                        continue
                    for metric_unit, unit_rows in units_payload.items():
                        if not isinstance(unit_rows, list):
                            continue
                        for row in unit_rows:
                            filing_date = pd.to_datetime(row.get("filed"), errors="coerce").normalize()
                            if pd.isna(filing_date) or filing_date < start_ts or filing_date > end_ts:
                                continue
                            fiscal_end = pd.to_datetime(row.get("end"), errors="coerce").normalize()
                            metric_value = row.get("val")
                            if metric_value is None:
                                continue
                            records.append(
                                {
                                    "security_id": security_id,
                                    "source_company_id": str(company_id),
                                    "form_type": row.get("form"),
                                    "filing_date": str(filing_date.date()) if pd.notna(filing_date) else None,
                                    "acceptance_datetime": None,
                                    "fiscal_period_end": str(fiscal_end.date()) if pd.notna(fiscal_end) else None,
                                    "metric_name_raw": metric_name_raw,
                                    "metric_value": metric_value,
                                    "metric_unit": metric_unit,
                                    "statement_type": taxonomy_name,
                                }
                            )
        return ProviderPage(records=records, original_payload={"pages": payloads, "next_page_token": None}, next_page_token=None)


class LocalFileFundamentalsProvider(FundamentalsProvider):
    def __init__(self, adapter: AdapterConfig, root: Path) -> None:
        self.adapter = adapter
        self.root = root
        self.frame = load_table_from_path(resolve_local_path(adapter, root))

    @property
    def name(self) -> str:
        return self.adapter.adapter_name

    def fetch_fundamentals(self, company_ids: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        if page_token is not None:
            return ProviderPage(records=[], original_payload={"records": [], "next_page_token": None}, next_page_token=None)

        frame = self.frame.copy()
        if "source_company_id" not in frame.columns:
            raise ConfiguredAdapterError("Локальный fundamentals adapter ожидает колонку `source_company_id`.")
        frame["source_company_id"] = frame["source_company_id"].astype("string").str.upper()
        frame = frame.loc[frame["source_company_id"].isin([str(company_id).upper() for company_id in company_ids])].copy()
        frame["filing_date"] = pd.to_datetime(frame["filing_date"], errors="coerce").dt.normalize()
        frame = frame.loc[frame["filing_date"].between(pd.Timestamp(start_date).normalize(), pd.Timestamp(end_date).normalize())].copy()
        if "statement_type" not in frame.columns:
            frame["statement_type"] = "fundamentals"
        required_columns = [
            "security_id",
            "source_company_id",
            "form_type",
            "filing_date",
            "acceptance_datetime",
            "fiscal_period_end",
            "metric_name_raw",
            "metric_value",
            "metric_unit",
            "statement_type",
        ]
        for column in required_columns:
            if column not in frame.columns:
                frame[column] = None
        records = frame.loc[:, required_columns].copy()
        records["filing_date"] = pd.to_datetime(records["filing_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        records["fiscal_period_end"] = pd.to_datetime(records["fiscal_period_end"], errors="coerce").dt.strftime("%Y-%m-%d")
        acceptance = pd.to_datetime(records["acceptance_datetime"], errors="coerce", utc=True)
        records["acceptance_datetime"] = acceptance.map(lambda value: value.isoformat() if pd.notna(value) else None)
        payload_records = records.where(pd.notna(records), None).to_dict(orient="records")
        return ProviderPage(records=payload_records, original_payload={"records": payload_records, "next_page_token": None}, next_page_token=None)
