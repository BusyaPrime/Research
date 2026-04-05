from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pandas as pd

from alpha_research.config.models import AdapterConfig, ProviderConfig
from alpha_research.data.providers.base import MarketDataProvider, ProviderPage
from alpha_research.data.providers.configured_transport import (
    ConfiguredAdapterError,
    http_get_bytes,
    http_get_json,
    load_table_from_path,
    provider_headers,
    provider_url,
    resolve_local_path,
)


def coerce_date_column(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], errors="coerce").dt.normalize()


def filter_by_date(frame: pd.DataFrame, column: str, start_date: str, end_date: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    output = frame.copy()
    output[column] = coerce_date_column(output, column)
    return output.loc[output[column].between(start_ts, end_ts)].copy()


def load_stooq_symbol_market_frame(adapter: AdapterConfig, request_symbol: str, start_date: str, end_date: str, *, root: Path | None = None) -> pd.DataFrame:
    url = provider_url(adapter, "", {"s": request_symbol, "i": "d"})
    text = http_get_bytes(adapter, url, headers=provider_headers(adapter), root=root, cache_key=url).decode("utf-8")
    frame = pd.read_csv(io.StringIO(text))
    if frame.empty or "Date" not in frame.columns:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "adj_close", "volume"])
    frame["trade_date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame = frame.loc[frame["trade_date"].between(pd.Timestamp(start_date).normalize(), pd.Timestamp(end_date).normalize())].copy()
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "adj_close", "volume"])
    return frame.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    ).assign(adj_close=lambda item: item["close"])[["trade_date", "open", "high", "low", "close", "adj_close", "volume"]]


def load_yahoo_chart_payload(adapter: AdapterConfig, request_symbol: str, start_date: str, end_date: str, *, root: Path | None = None) -> dict[str, Any]:
    start_ts = int(pd.Timestamp(start_date).timestamp())
    end_ts = int((pd.Timestamp(end_date) + pd.Timedelta(days=1)).timestamp())
    url = provider_url(
        adapter,
        request_symbol,
        {
            "period1": start_ts,
            "period2": end_ts,
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        },
    )
    try:
        payload = http_get_json(adapter, url, headers=provider_headers(adapter), root=root, cache_key=url)
    except HTTPError as exc:
        if exc.code in {400, 404}:
            return {}
        raise
    chart = payload.get("chart", {})
    error = chart.get("error")
    if error:
        raise ConfiguredAdapterError(f"Yahoo chart adapter `{adapter.adapter_name}` вернул ошибку для `{request_symbol}`: {error}")
    results = chart.get("result") or []
    return results[0] if results else {}


def yahoo_chart_to_market_frame(chart: dict[str, Any]) -> pd.DataFrame:
    timestamps = chart.get("timestamp") or []
    if not timestamps:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "adj_close", "volume"])
    quote_items = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    adjclose_items = ((chart.get("indicators") or {}).get("adjclose") or [{}])[0]
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(pd.Series(timestamps), unit="s", utc=True).dt.tz_convert("America/New_York").dt.normalize(),
            "open": pd.to_numeric(pd.Series(quote_items.get("open")), errors="coerce"),
            "high": pd.to_numeric(pd.Series(quote_items.get("high")), errors="coerce"),
            "low": pd.to_numeric(pd.Series(quote_items.get("low")), errors="coerce"),
            "close": pd.to_numeric(pd.Series(quote_items.get("close")), errors="coerce"),
            "adj_close": pd.to_numeric(pd.Series(adjclose_items.get("adjclose")), errors="coerce"),
            "volume": pd.to_numeric(pd.Series(quote_items.get("volume")), errors="coerce"),
        }
    )
    frame["trade_date"] = frame["trade_date"].dt.tz_localize(None)
    frame = frame.dropna(subset=["trade_date", "open", "high", "low", "close"]).copy()
    if frame["adj_close"].isna().all():
        frame["adj_close"] = frame["close"]
    frame["volume"] = frame["volume"].fillna(0).astype("int64")
    return frame


class StooqEodHttpMarketProvider(MarketDataProvider):
    def __init__(self, adapter: AdapterConfig, *, root: Path | None = None) -> None:
        self.adapter = adapter
        self.root = root

    @property
    def name(self) -> str:
        return self.adapter.adapter_name

    def fetch_market_data(self, symbols: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        if page_token is not None:
            return ProviderPage(records=[], original_payload={"records": [], "next_page_token": None}, next_page_token=None)

        all_records: list[dict[str, object]] = []
        payloads: list[dict[str, object]] = []
        missing_symbols: list[str] = []
        template = self.adapter.symbol_template or "{symbol}.us"

        for symbol in symbols:
            rendered_symbol = template.format(symbol=str(symbol).lower())
            frame = load_stooq_symbol_market_frame(self.adapter, rendered_symbol, start_date, end_date, root=self.root)
            payloads.append({"symbol": str(symbol).upper(), "request_symbol": rendered_symbol, "row_count": int(len(frame))})
            if frame.empty:
                missing_symbols.append(str(symbol).upper())
                continue
            for row in frame.itertuples(index=False):
                all_records.append(
                    {
                        "provider_symbol": str(symbol).upper(),
                        "symbol": str(symbol).upper(),
                        "trade_date": str(pd.Timestamp(row.trade_date).date()),
                        "open": float(row.open),
                        "high": float(row.high),
                        "low": float(row.low),
                        "close": float(row.close),
                        "adj_close": float(row.adj_close),
                        "volume": int(row.volume),
                        "currency": "USD",
                        "raw_payload_version": "stooq_csv_v1",
                    }
                )
        return ProviderPage(records=all_records, original_payload={"pages": payloads, "next_page_token": None}, next_page_token=None, missing_symbols=missing_symbols)


class LocalFileMarketProvider(MarketDataProvider):
    def __init__(self, adapter: AdapterConfig, root: Path) -> None:
        self.adapter = adapter
        self.root = root
        self.frame = load_table_from_path(resolve_local_path(adapter, root))

    @property
    def name(self) -> str:
        return self.adapter.adapter_name

    def fetch_market_data(self, symbols: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        if page_token is not None:
            return ProviderPage(records=[], original_payload={"records": [], "next_page_token": None}, next_page_token=None)

        frame = self.frame.copy()
        if "provider_symbol" not in frame.columns and "symbol" not in frame.columns:
            raise ConfiguredAdapterError("Локальный market adapter ожидает колонку `provider_symbol` или `symbol`.")
        if "provider_symbol" not in frame.columns:
            frame["provider_symbol"] = frame["symbol"]
        frame["provider_symbol"] = frame["provider_symbol"].astype("string").str.upper()
        frame = frame.loc[frame["provider_symbol"].isin([str(symbol).upper() for symbol in symbols])].copy()
        frame = filter_by_date(frame, "trade_date", start_date, end_date)
        if "currency" not in frame.columns:
            frame["currency"] = "USD"
        if "raw_payload_version" not in frame.columns:
            frame["raw_payload_version"] = "local_file_v1"
        required = [
            "provider_symbol",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "currency",
            "raw_payload_version",
        ]
        missing = sorted(set(symbol.upper() for symbol in symbols) - set(frame["provider_symbol"].dropna().astype(str).str.upper().unique().tolist()))
        records = frame.loc[:, required].assign(trade_date=lambda item: item["trade_date"].dt.date.astype(str)).to_dict(orient="records")
        return ProviderPage(records=records, original_payload={"records": records, "next_page_token": None}, next_page_token=None, missing_symbols=missing)


class YahooChartMarketProvider(MarketDataProvider):
    def __init__(self, adapter: AdapterConfig, *, root: Path | None = None) -> None:
        self.adapter = adapter
        self.root = root

    @property
    def name(self) -> str:
        return self.adapter.adapter_name

    def fetch_market_data(self, symbols: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        if page_token is not None:
            return ProviderPage(records=[], original_payload={"records": [], "next_page_token": None}, next_page_token=None)

        all_records: list[dict[str, object]] = []
        payloads: list[dict[str, object]] = []
        missing_symbols: list[str] = []
        for symbol in symbols:
            chart = load_yahoo_chart_payload(self.adapter, str(symbol).upper(), start_date, end_date, root=self.root)
            frame = yahoo_chart_to_market_frame(chart)
            payloads.append({"symbol": str(symbol).upper(), "row_count": int(len(frame))})
            if frame.empty:
                missing_symbols.append(str(symbol).upper())
                continue
            for row in frame.itertuples(index=False):
                all_records.append(
                    {
                        "provider_symbol": str(symbol).upper(),
                        "symbol": str(symbol).upper(),
                        "trade_date": str(pd.Timestamp(row.trade_date).date()),
                        "open": float(row.open),
                        "high": float(row.high),
                        "low": float(row.low),
                        "close": float(row.close),
                        "adj_close": float(row.adj_close),
                        "volume": int(row.volume),
                        "currency": "USD",
                        "raw_payload_version": "yahoo_chart_v1",
                    }
                )
        return ProviderPage(records=all_records, original_payload={"pages": payloads, "next_page_token": None}, next_page_token=None, missing_symbols=missing_symbols)


def load_benchmark_market_from_config(root: Path, provider: ProviderConfig, start_date: str, end_date: str, adapter: AdapterConfig) -> tuple[pd.DataFrame, str]:
    if adapter.adapter_type == "market_panel_proxy":
        return pd.DataFrame(), adapter.adapter_name
    if adapter.adapter_type == "local_file_benchmark":
        frame = load_table_from_path(resolve_local_path(adapter, root))
        required = {"trade_date", "open", "high", "low", "close"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ConfiguredAdapterError(f"В benchmark adapter `{adapter.adapter_name}` не хватает колонок: {missing}")
        benchmark = filter_by_date(frame, "trade_date", start_date, end_date)
        return benchmark.loc[:, ["trade_date", "open", "high", "low", "close"]].copy(), adapter.adapter_name
    if adapter.adapter_type == "stooq_benchmark_http":
        request_symbol = adapter.request_symbol or "spy.us"
        benchmark = load_stooq_symbol_market_frame(adapter, request_symbol, start_date, end_date, root=root)
        return benchmark.loc[:, ["trade_date", "open", "high", "low", "close"]].copy(), adapter.adapter_name
    if adapter.adapter_type == "yahoo_chart_benchmark_http":
        request_symbol = adapter.request_symbol or "SPY"
        benchmark = yahoo_chart_to_market_frame(load_yahoo_chart_payload(adapter, request_symbol, start_date, end_date, root=root))
        return benchmark.loc[:, ["trade_date", "open", "high", "low", "close"]].copy(), adapter.adapter_name
    raise ConfiguredAdapterError(f"Неподдерживаемый benchmark adapter type: {adapter.adapter_type}")
