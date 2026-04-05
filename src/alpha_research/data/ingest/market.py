from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.common.hashing import hash_mapping
from alpha_research.common.io import read_json
from alpha_research.data.providers.base import MarketDataProvider
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


@dataclass(frozen=True)
class MarketIngestArtifacts:
    request_key: str
    manifest_path: Path
    raw_payload_path: Path
    bronze_path: Path
    idempotent_hit: bool


class MarketIngestionService:
    def __init__(self, root: Path | None = None, data_version: str = "v1") -> None:
        self.paths = DatasetPaths.from_root(root)
        self.root = self.paths.root
        self.data_version = data_version

    def ingest(self, provider: MarketDataProvider, symbols: list[str], start_date: str, end_date: str, symbol_mapper: SymbolMapper) -> MarketIngestArtifacts:
        request_key = build_request_key(provider.name, provider.endpoint_name, symbols, start_date, end_date)
        manifest_path = self.paths.raw_manifest_path("market", request_key)
        raw_path = self.paths.raw_payload_path("market", request_key)
        bronze_path = self.paths.bronze_path("market_daily", request_key)

        if manifest := maybe_load_manifest(manifest_path):
            return MarketIngestArtifacts(request_key=request_key, manifest_path=manifest_path, raw_payload_path=raw_path, bronze_path=bronze_path, idempotent_hit=True)

        page_token: str | None = None
        pages: list[dict[str, object]] = []
        records: list[dict[str, object]] = []
        provider_missing: set[str] = set()
        while True:
            page = provider.fetch_market_data(symbols, start_date, end_date, page_token=page_token)
            pages.append(page.original_payload)
            records.extend(page.records)
            provider_missing.update(page.missing_symbols)
            page_token = page.next_page_token
            if page_token is None:
                break

        raw_package = {
            "provider_name": provider.name,
            "endpoint_name": provider.endpoint_name,
            "pages": pages,
            "missing_symbols": sorted(provider_missing),
        }
        persist_payload(raw_path, raw_package)

        raw_frame = pd.DataFrame.from_records(records)
        if raw_frame.empty:
            raw_frame = pd.DataFrame(columns=["provider_symbol", "trade_date", "open", "high", "low", "close", "adj_close", "volume", "currency", "raw_payload_version"])
        raw_frame["provider_symbol"] = raw_frame.get("provider_symbol", raw_frame.get("symbol", pd.Series(index=raw_frame.index, dtype="string"))).astype("string").str.upper()
        raw_frame["raw_payload_version"] = raw_frame.get("raw_payload_version", "as_received")
        raw_frame = validate_dataframe(raw_frame[schema_field_names("raw_market_payload", root=self.root)], "raw_market_payload", root=self.root)

        mapping = symbol_mapper.map_symbols(raw_frame["provider_symbol"].dropna().astype(str).str.upper().unique().tolist())
        bronze = raw_frame.rename(columns={"provider_symbol": "symbol"}).copy()
        bronze["symbol"] = bronze["symbol"].astype("string").str.upper()
        bronze["security_id"] = bronze["symbol"].map(mapping.mapped)
        bronze = bronze[bronze["security_id"].notna()].copy()
        bronze["provider_name"] = provider.name
        bronze["data_version"] = self.data_version
        bronze = validate_dataframe(bronze[schema_field_names("bronze_market_daily", root=self.root)], "bronze_market_daily", root=self.root)
        persist_bronze_frame(bronze_path, bronze)
        lineage = bronze_lineage_descriptor(bronze, dataset="market_daily", data_version=self.data_version, path=bronze_path)

        manifest = {
            "request_id": request_key,
            "provider_name": provider.name,
            "endpoint_name": provider.endpoint_name,
            "symbols_requested": sorted(symbol.upper() for symbol in symbols),
            "start_date": start_date,
            "end_date": end_date,
            "fetched_at_utc": utc_now_iso(),
            "payload_path": str(raw_path.relative_to(self.root)),
            "row_count_raw": int(len(raw_frame)),
            "checksum": hash_mapping(raw_package),
            "row_count_bronze": int(len(bronze)),
            "bronze_path": str(bronze_path.relative_to(self.root)),
            "missing_symbols": sorted(set(provider_missing) | set(mapping.missing_symbols)),
            **lineage,
        }
        persist_manifest(manifest_path, manifest)
        return MarketIngestArtifacts(request_key=request_key, manifest_path=manifest_path, raw_payload_path=raw_path, bronze_path=bronze_path, idempotent_hit=False)

    def load_manifest(self, manifest_path: Path) -> dict[str, object]:
        return read_json(manifest_path)
