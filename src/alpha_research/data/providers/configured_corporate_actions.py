from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from alpha_research.config.models import AdapterConfig
from alpha_research.data.providers.base import CorporateActionsProvider, ProviderPage
from alpha_research.data.providers.configured_market import load_yahoo_chart_payload
from alpha_research.data.providers.configured_transport import (
    ConfiguredAdapterError,
    load_table_from_path,
    resolve_local_path,
)


def yahoo_chart_events_to_corporate_actions(chart: dict[str, Any], symbol: str) -> list[dict[str, object]]:
    events = chart.get("events") or {}
    rows: list[dict[str, object]] = []
    for payload in (events.get("dividends") or {}).values():
        event_ts = pd.to_datetime(payload.get("date"), unit="s", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
        rows.append(
            {
                "symbol": symbol.upper(),
                "event_type": "dividend",
                "event_date": str(event_ts.date()),
                "effective_date": str(event_ts.date()),
                "split_ratio": None,
                "dividend_amount": float(payload.get("amount")) if payload.get("amount") is not None else None,
                "delisting_code": None,
                "old_symbol": None,
                "new_symbol": None,
            }
        )
    for payload in (events.get("splits") or {}).values():
        event_ts = pd.to_datetime(payload.get("date"), unit="s", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
        numerator = float(payload.get("numerator", 1.0) or 1.0)
        denominator = float(payload.get("denominator", 1.0) or 1.0)
        rows.append(
            {
                "symbol": symbol.upper(),
                "event_type": "split",
                "event_date": str(event_ts.date()),
                "effective_date": str(event_ts.date()),
                "split_ratio": numerator / denominator if denominator else None,
                "dividend_amount": None,
                "delisting_code": None,
                "old_symbol": None,
                "new_symbol": None,
            }
        )
    return rows


class LocalFileCorporateActionsProvider(CorporateActionsProvider):
    def __init__(self, adapter: AdapterConfig, root: Path) -> None:
        self.adapter = adapter
        self.root = root
        self.frame = load_table_from_path(resolve_local_path(adapter, root))

    @property
    def name(self) -> str:
        return self.adapter.adapter_name

    def fetch_corporate_actions(self, securities: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        if page_token is not None:
            return ProviderPage(records=[], original_payload={"records": [], "next_page_token": None}, next_page_token=None)

        frame = self.frame.copy()
        start_ts = pd.Timestamp(start_date).normalize()
        end_ts = pd.Timestamp(end_date).normalize()
        if "symbol" in frame.columns:
            frame["symbol"] = frame["symbol"].astype("string").str.upper()
            frame = frame.loc[frame["symbol"].isin([str(item).upper() for item in securities])].copy()
        elif "security_id" in frame.columns:
            frame["security_id"] = frame["security_id"].astype("string")
            frame = frame.loc[frame["security_id"].isin([str(item) for item in securities])].copy()
        else:
            raise ConfiguredAdapterError("Локальный corporate actions adapter ожидает колонку `symbol` или `security_id`.")

        date_column = "effective_date" if "effective_date" in frame.columns else "event_date"
        frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce").dt.normalize()
        frame = frame.loc[frame[date_column].between(start_ts, end_ts)].copy()
        records = frame.where(pd.notna(frame), None).to_dict(orient="records")
        return ProviderPage(records=records, original_payload={"records": records, "next_page_token": None}, next_page_token=None)


class YahooChartCorporateActionsProvider(CorporateActionsProvider):
    def __init__(self, adapter: AdapterConfig, *, root: Path | None = None) -> None:
        self.adapter = adapter
        self.root = root

    @property
    def name(self) -> str:
        return self.adapter.adapter_name

    def fetch_corporate_actions(self, securities: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        if page_token is not None:
            return ProviderPage(records=[], original_payload={"records": [], "next_page_token": None}, next_page_token=None)

        records: list[dict[str, object]] = []
        payloads: list[dict[str, object]] = []
        for symbol in securities:
            chart = load_yahoo_chart_payload(self.adapter, str(symbol).upper(), start_date, end_date, root=self.root)
            rows = yahoo_chart_events_to_corporate_actions(chart, str(symbol).upper())
            payloads.append({"symbol": str(symbol).upper(), "event_count": len(rows)})
            records.extend(rows)
        return ProviderPage(records=records, original_payload={"pages": payloads, "next_page_token": None}, next_page_token=None)
