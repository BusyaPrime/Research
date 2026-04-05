from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.common.hashing import hash_mapping
from alpha_research.common.io import read_json
from alpha_research.data.providers.base import CorporateActionsProvider
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
from alpha_research.reference.security_master import SymbolMapper

VALID_EVENT_TYPES = {"split", "dividend", "delisting", "symbol_change"}


@dataclass(frozen=True)
class CorporateActionsIngestArtifacts:
    request_key: str
    manifest_path: Path
    raw_payload_path: Path
    bronze_path: Path
    failed_extract_path: Path
    idempotent_hit: bool


class CorporateActionsIngestionService:
    def __init__(self, root: Path | None = None, data_version: str = "v1") -> None:
        self.paths = DatasetPaths.from_root(root)
        self.root = self.paths.root
        self.data_version = data_version

    def ingest(self, provider: CorporateActionsProvider, securities: list[str], start_date: str, end_date: str, symbol_mapper: SymbolMapper) -> CorporateActionsIngestArtifacts:
        request_key = build_request_key(provider.name, provider.endpoint_name, securities, start_date, end_date)
        manifest_path = self.paths.raw_manifest_path("corporate_actions", request_key)
        raw_path = self.paths.raw_payload_path("corporate_actions", request_key)
        bronze_path = self.paths.bronze_path("corporate_actions", request_key)
        failed_path = self.paths.failed_extract_path("corporate_actions", request_key)

        if maybe_load_manifest(manifest_path):
            return CorporateActionsIngestArtifacts(request_key, manifest_path, raw_path, bronze_path, failed_path, True)

        page_token: str | None = None
        pages: list[dict[str, object]] = []
        records: list[dict[str, object]] = []
        while True:
            page = provider.fetch_corporate_actions(securities, start_date, end_date, page_token=page_token)
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

        frame = pd.DataFrame.from_records(records)
        if frame.empty:
            frame = pd.DataFrame(columns=["security_id", "event_type", "event_date", "effective_date", "split_ratio", "dividend_amount", "delisting_code", "old_symbol", "new_symbol", "data_version"])
        frame["event_type"] = frame["event_type"].astype("string").str.lower()
        frame["old_symbol"] = frame.get("old_symbol", pd.Series(index=frame.index, dtype="string")).astype("string").str.upper()
        frame["new_symbol"] = frame.get("new_symbol", pd.Series(index=frame.index, dtype="string")).astype("string").str.upper()
        symbol_series = frame.get("symbol", pd.Series(index=frame.index, dtype="string")).astype("string").str.upper()
        base_symbol = symbol_series.fillna(frame["old_symbol"])
        if "security_id" in frame.columns:
            frame["security_id"] = frame["security_id"].fillna(base_symbol.map(lambda value: symbol_mapper.resolve(value) if pd.notna(value) else None))
        else:
            frame["security_id"] = base_symbol.map(lambda value: symbol_mapper.resolve(value) if pd.notna(value) else None)
        frame["event_date"] = pd.to_datetime(frame.get("event_date"), errors="coerce").dt.normalize()
        frame["effective_date"] = pd.to_datetime(frame.get("effective_date"), errors="coerce").dt.normalize()
        frame["split_ratio"] = pd.to_numeric(frame.get("split_ratio"), errors="coerce")
        frame["dividend_amount"] = pd.to_numeric(frame.get("dividend_amount"), errors="coerce")
        frame["data_version"] = self.data_version

        invalid_mask = ~frame["event_type"].isin(VALID_EVENT_TYPES) | frame["security_id"].isna()
        failed = frame[invalid_mask].copy()
        valid = frame[~invalid_mask].copy()
        if not failed.empty:
            persist_bronze_frame(failed_path, failed)
        if not valid.empty:
            valid = validate_dataframe(valid[schema_field_names("bronze_corporate_actions", root=self.root)], "bronze_corporate_actions", root=self.root)
            persist_bronze_frame(bronze_path, valid)
        else:
            valid = validate_dataframe(pd.DataFrame(columns=schema_field_names("bronze_corporate_actions", root=self.root)), "bronze_corporate_actions", root=self.root)
        lineage = bronze_lineage_descriptor(valid, dataset="corporate_actions", data_version=self.data_version, path=bronze_path)

        manifest = {
            "request_id": request_key,
            "provider_name": provider.name,
            "endpoint_name": provider.endpoint_name,
            "symbols_requested": sorted(securities),
            "start_date": start_date,
            "end_date": end_date,
            "fetched_at_utc": utc_now_iso(),
            "payload_path": str(raw_path.relative_to(self.root)),
            "row_count_raw": int(len(records)),
            "checksum": hash_mapping(raw_package),
            "row_count_valid": int(len(valid)),
            "row_count_failed": int(len(failed)),
            "bronze_path": str(bronze_path.relative_to(self.root)),
            "failed_extract_path": str(failed_path.relative_to(self.root)) if not failed.empty else None,
            **lineage,
        }
        persist_manifest(manifest_path, manifest)
        return CorporateActionsIngestArtifacts(request_key, manifest_path, raw_path, bronze_path, failed_path, False)

    def load_manifest(self, manifest_path: Path) -> dict[str, object]:
        return read_json(manifest_path)
