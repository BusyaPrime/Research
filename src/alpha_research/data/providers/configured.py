from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from alpha_research.common.io import read_json, read_parquet
from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.config.models import AdapterConfig, ProviderConfig
from alpha_research.data.providers.base import CorporateActionsProvider, FundamentalsProvider, MarketDataProvider, ProviderPage
from alpha_research.reference.security_master import SymbolMapper, build_security_master


class ConfiguredAdapterError(RuntimeError):
    pass


def _http_get_bytes(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = 30) -> bytes:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _resolve_env(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _resolve_local_path(adapter: AdapterConfig, root: Path) -> Path:
    local_path = adapter.local_path or _resolve_env(adapter.local_path_env)
    if not local_path:
        raise ConfiguredAdapterError(
            f"Для adapter `{adapter.adapter_name}` не указан local_path и не задан env `{adapter.local_path_env}`."
        )
    candidate = Path(local_path)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    if not candidate.exists():
        raise ConfiguredAdapterError(f"Локальный файл для adapter `{adapter.adapter_name}` не найден: {candidate}")
    return candidate


def _load_table_from_path(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return read_parquet(path)
    if suffix == ".json":
        payload = read_json(path)
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict) and "records" in payload:
            return pd.DataFrame(payload["records"])
        return pd.DataFrame([payload])
    raise ConfiguredAdapterError(f"Неподдерживаемый формат локального файла: {path}")


def _provider_headers(adapter: AdapterConfig) -> dict[str, str]:
    headers = dict(adapter.default_headers or {})
    api_key = _resolve_env(adapter.api_key_env)
    if adapter.api_key_header and api_key:
        headers[adapter.api_key_header] = api_key
    user_agent = _resolve_env(adapter.user_agent_env)
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def _provider_url(adapter: AdapterConfig, path: str, query: dict[str, str | int | float | None] | None = None) -> str:
    if not adapter.base_url:
        raise ConfiguredAdapterError(f"Для adapter `{adapter.adapter_name}` не задан base_url.")
    base = adapter.base_url.rstrip("/")
    relative = path.lstrip("/")
    params = {key: value for key, value in (query or {}).items() if value is not None}
    api_key = _resolve_env(adapter.api_key_env)
    if adapter.api_key_query_param and api_key:
        params[adapter.api_key_query_param] = api_key
    encoded = urlencode(params)
    if encoded:
        return f"{base}/{relative}?{encoded}"
    return f"{base}/{relative}"


def _normalize_company_id(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        raise ConfiguredAdapterError(f"company_id `{value}` не похож на CIK/числовой идентификатор.")
    return digits.zfill(10)


def _coerce_date_column(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], errors="coerce").dt.normalize()


def _filter_by_date(frame: pd.DataFrame, column: str, start_date: str, end_date: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    output = frame.copy()
    output[column] = _coerce_date_column(output, column)
    return output.loc[output[column].between(start_ts, end_ts)].copy()


def _load_stooq_symbol_market_frame(adapter: AdapterConfig, request_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = _provider_url(adapter, "", {"s": request_symbol, "i": "d"})
    text = _http_get_bytes(url, headers=_provider_headers(adapter), timeout_seconds=adapter.timeout_seconds).decode("utf-8")
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


@dataclass(frozen=True)
class ResolvedSecurityMaster:
    raw_frame: pd.DataFrame
    canonical_frame: pd.DataFrame
    symbol_mapper: SymbolMapper


def _select_adapter(provider: ProviderConfig, *, expected_types: set[str]) -> AdapterConfig:
    adapters = provider.adapters or []
    if not adapters:
        raise ConfiguredAdapterError("В provider config не описан ни один adapter.")
    adapter_map = {adapter.adapter_name: adapter for adapter in adapters if adapter.enabled}
    for preferred in provider.priority or []:
        adapter = adapter_map.get(preferred)
        if adapter is not None and adapter.adapter_type in expected_types:
            return adapter
    for adapter in adapters:
        if adapter.enabled and adapter.adapter_type in expected_types:
            return adapter
    raise ConfiguredAdapterError(
        f"Не найден enabled adapter допустимого типа {sorted(expected_types)}."
    )


def load_security_master_from_config(root: Path, provider: ProviderConfig) -> ResolvedSecurityMaster:
    adapter = _select_adapter(provider, expected_types={"local_file_security_master"})
    path = _resolve_local_path(adapter, root)
    raw = _load_table_from_path(path)
    raw.attrs["adapter_name"] = adapter.adapter_name
    canonical = build_security_master(raw, root=root)
    return ResolvedSecurityMaster(raw_frame=raw, canonical_frame=canonical, symbol_mapper=SymbolMapper(canonical))


class StooqEodHttpMarketProvider(MarketDataProvider):
    def __init__(self, adapter: AdapterConfig) -> None:
        self.adapter = adapter

    @property
    def name(self) -> str:
        return self.adapter.adapter_name

    def fetch_market_data(self, symbols: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        if page_token is not None:
            return ProviderPage(records=[], original_payload={"records": [], "next_page_token": None}, next_page_token=None)

        all_records: list[dict[str, object]] = []
        payloads: list[dict[str, object]] = []
        missing_symbols: list[str] = []
        start_ts = pd.Timestamp(start_date).normalize()
        end_ts = pd.Timestamp(end_date).normalize()
        template = self.adapter.symbol_template or "{symbol}.us"

        for symbol in symbols:
            rendered_symbol = template.format(symbol=str(symbol).lower())
            frame = _load_stooq_symbol_market_frame(self.adapter, rendered_symbol, start_date, end_date)
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
        self.frame = _load_table_from_path(_resolve_local_path(adapter, root))

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
        frame = _filter_by_date(frame, "trade_date", start_date, end_date)
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


class SecCompanyFactsProvider(FundamentalsProvider):
    def __init__(self, adapter: AdapterConfig, raw_security_master: pd.DataFrame) -> None:
        self.adapter = adapter
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
            cik = _normalize_company_id(company_id)
            url = _provider_url(self.adapter, f"CIK{cik}.json")
            payload = json.loads(
                _http_get_bytes(url, headers=_provider_headers(self.adapter), timeout_seconds=self.adapter.timeout_seconds).decode("utf-8")
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
        self.frame = _load_table_from_path(_resolve_local_path(adapter, root))

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
        frame = _filter_by_date(frame, "filing_date", start_date, end_date)
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


class LocalFileCorporateActionsProvider(CorporateActionsProvider):
    def __init__(self, adapter: AdapterConfig, root: Path) -> None:
        self.adapter = adapter
        self.root = root
        self.frame = _load_table_from_path(_resolve_local_path(adapter, root))

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
        date_column = "effective_date" if "effective_date" in frame.columns else "event_date"
        frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce").dt.normalize()
        frame = frame.loc[frame[date_column].between(start_ts, end_ts)].copy()
        records = frame.to_dict(orient="records")
        return ProviderPage(records=records, original_payload={"records": records, "next_page_token": None}, next_page_token=None)


def load_benchmark_market_from_config(root: Path, provider: ProviderConfig, start_date: str, end_date: str) -> tuple[pd.DataFrame, str]:
    adapter = _select_adapter(
        provider,
        expected_types={"local_file_benchmark", "stooq_benchmark_http", "market_panel_proxy"},
    )
    if adapter.adapter_type == "market_panel_proxy":
        return pd.DataFrame(), adapter.adapter_name
    if adapter.adapter_type == "local_file_benchmark":
        frame = _load_table_from_path(_resolve_local_path(adapter, root))
        required = {"trade_date", "open", "high", "low", "close"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ConfiguredAdapterError(f"В benchmark adapter `{adapter.adapter_name}` не хватает колонок: {missing}")
        benchmark = _filter_by_date(frame, "trade_date", start_date, end_date)
        return benchmark.loc[:, ["trade_date", "open", "high", "low", "close"]].copy(), adapter.adapter_name
    if adapter.adapter_type == "stooq_benchmark_http":
        request_symbol = adapter.request_symbol or "spy.us"
        benchmark = _load_stooq_symbol_market_frame(adapter, request_symbol, start_date, end_date)
        return benchmark.loc[:, ["trade_date", "open", "high", "low", "close"]].copy(), adapter.adapter_name
    raise ConfiguredAdapterError(f"Неподдерживаемый benchmark adapter type: {adapter.adapter_type}")


@dataclass(frozen=True)
class ConfiguredIngestContext:
    security_master_raw: pd.DataFrame
    security_master: pd.DataFrame
    symbol_mapper: SymbolMapper
    market_provider: MarketDataProvider
    fundamentals_provider: FundamentalsProvider
    corporate_actions_provider: CorporateActionsProvider
    notes: list[str]


def build_configured_ingest_context(root: Path, loaded: LoadedConfigBundle) -> ConfiguredIngestContext:
    paths = RepositoryPaths.from_root(root)
    resolved_security_master = load_security_master_from_config(paths.root, loaded.bundle.data_sources.security_master_provider)

    market_adapter = _select_adapter(
        loaded.bundle.data_sources.market_provider,
        expected_types={"stooq_eod_http", "local_file_market_daily"},
    )
    fundamentals_adapter = _select_adapter(
        loaded.bundle.data_sources.fundamentals_provider,
        expected_types={"sec_companyfacts_http", "local_file_fundamentals"},
    )
    corporate_actions_adapter = _select_adapter(
        loaded.bundle.data_sources.corporate_actions_provider,
        expected_types={"local_file_corporate_actions"},
    )

    notes = [
        "Операционный ingest работает через configured adapters path.",
        f"security_master_adapter={resolved_security_master.raw_frame.attrs.get('adapter_name', 'local_file_security_master')}",
        f"market_adapter={market_adapter.adapter_name}",
        f"fundamentals_adapter={fundamentals_adapter.adapter_name}",
        f"corporate_actions_adapter={corporate_actions_adapter.adapter_name}",
    ]
    if market_adapter.adapter_type == "stooq_eod_http":
        market_provider: MarketDataProvider = StooqEodHttpMarketProvider(market_adapter)
    elif market_adapter.adapter_type == "local_file_market_daily":
        market_provider = LocalFileMarketProvider(market_adapter, paths.root)
    else:
        raise ConfiguredAdapterError(f"Неподдерживаемый market adapter type: {market_adapter.adapter_type}")

    if fundamentals_adapter.adapter_type == "sec_companyfacts_http":
        fundamentals_provider: FundamentalsProvider = SecCompanyFactsProvider(fundamentals_adapter, resolved_security_master.raw_frame)
    elif fundamentals_adapter.adapter_type == "local_file_fundamentals":
        fundamentals_provider = LocalFileFundamentalsProvider(fundamentals_adapter, paths.root)
    else:
        raise ConfiguredAdapterError(f"Неподдерживаемый fundamentals adapter type: {fundamentals_adapter.adapter_type}")

    return ConfiguredIngestContext(
        security_master_raw=resolved_security_master.raw_frame,
        security_master=resolved_security_master.canonical_frame,
        symbol_mapper=resolved_security_master.symbol_mapper,
        market_provider=market_provider,
        fundamentals_provider=fundamentals_provider,
        corporate_actions_provider=LocalFileCorporateActionsProvider(corporate_actions_adapter, paths.root),
        notes=notes,
    )
