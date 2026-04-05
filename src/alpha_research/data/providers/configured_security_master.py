from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.config.models import AdapterConfig, ProviderConfig
from alpha_research.data.providers.configured_transport import (
    ConfiguredAdapterPermanentError,
    http_get_json,
    load_table_from_path,
    provider_headers,
    resolve_local_path,
)
from alpha_research.reference.security_master import SymbolMapper, build_security_master


def _map_exchange_label(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().upper()
    if text == "NASDAQ":
        return "NASDAQ"
    if text in {"NYSE", "NEW YORK STOCK EXCHANGE"}:
        return "NYSE"
    if text == "NYSE ARCA":
        return "NYSE"
    return text or None


def _infer_security_type(name: object) -> str:
    text = str(name or "").upper()
    if any(token in text for token in ("ADR", "DEPOSITARY")):
        return "adr"
    if any(token in text for token in ("ETF", "EXCHANGE TRADED FUND", "TRUST", "FUND", "PORTFOLIO")):
        return "etf"
    if "PREFERRED" in text:
        return "preferred"
    if "WARRANT" in text:
        return "warrant"
    if "UNIT" in text and "COMM" not in text:
        return "unit"
    return "common_stock"


@dataclass(frozen=True)
class ResolvedSecurityMaster:
    raw_frame: pd.DataFrame
    canonical_frame: pd.DataFrame
    symbol_mapper: SymbolMapper


def load_security_master_from_config(root: Path, provider: ProviderConfig, adapter: AdapterConfig) -> ResolvedSecurityMaster:
    if adapter.adapter_type == "local_file_security_master":
        path = resolve_local_path(adapter, root)
        raw = load_table_from_path(path)
    elif adapter.adapter_type == "sec_exchange_security_master":
        if not adapter.base_url:
            raise ConfiguredAdapterPermanentError(f"Для adapter `{adapter.adapter_name}` не задан base_url.")
        payload = http_get_json(adapter, adapter.base_url, headers=provider_headers(adapter), root=root)
        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        frame = pd.DataFrame(rows, columns=fields)
        if frame.empty:
            raise ConfiguredAdapterPermanentError(f"SEC exchange security master adapter `{adapter.adapter_name}` вернул пустой payload.")
        frame["cik"] = frame["cik"].astype("Int64").astype("string").str.zfill(10)
        frame["symbol"] = frame["ticker"].astype("string").str.upper()
        frame["exchange"] = frame["exchange"].map(_map_exchange_label).astype("string")
        frame["security_type"] = frame["name"].map(_infer_security_type).astype("string")
        frame["listing_date"] = pd.NaT
        frame["delisting_date"] = pd.NaT
        frame["sector"] = pd.NA
        frame["industry"] = pd.NA
        frame["country"] = "US"
        frame["currency"] = "USD"
        frame["is_common_stock"] = frame["security_type"].eq("common_stock")
        frame["source_company_id"] = frame["cik"]
        raw = frame.rename(columns={"cik": "security_id"})[
            [
                "security_id",
                "symbol",
                "security_type",
                "exchange",
                "listing_date",
                "delisting_date",
                "sector",
                "industry",
                "country",
                "currency",
                "is_common_stock",
                "source_company_id",
            ]
        ].copy()
    else:
        raise ConfiguredAdapterPermanentError(f"Неподдерживаемый security master adapter type: {adapter.adapter_type}")
    raw.attrs["adapter_name"] = adapter.adapter_name
    canonical = build_security_master(raw, root=root)
    return ResolvedSecurityMaster(raw_frame=raw, canonical_frame=canonical, symbol_mapper=SymbolMapper(canonical))
