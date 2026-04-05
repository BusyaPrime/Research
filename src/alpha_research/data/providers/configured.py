from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.config.models import AdapterConfig, ProviderConfig
from alpha_research.data.providers import configured_transport as _transport
from alpha_research.data.providers.base import CorporateActionsProvider, FundamentalsProvider, MarketDataProvider
from alpha_research.data.providers.configured_corporate_actions import (
    LocalFileCorporateActionsProvider,
    YahooChartCorporateActionsProvider,
)
from alpha_research.data.providers.configured_fundamentals import (
    LocalFileFundamentalsProvider,
    SecCompanyFactsProvider,
)
from alpha_research.data.providers.configured_market import (
    LocalFileMarketProvider,
    StooqEodHttpMarketProvider,
    YahooChartMarketProvider,
)
from alpha_research.data.providers.configured_market import (
    load_benchmark_market_from_config as _load_benchmark_market_from_config,
)
from alpha_research.data.providers.configured_security_master import (
    ResolvedSecurityMaster,
    load_security_master_from_config,
)
from alpha_research.reference.security_master import SymbolMapper

ConfiguredAdapterError = _transport.ConfiguredAdapterError
ConfiguredAdapterTransientError = _transport.ConfiguredAdapterTransientError
ConfiguredAdapterPermanentError = _transport.ConfiguredAdapterPermanentError

# Compatibility bridge: integration tests and local tooling patch the transport
# entrypoint on the facade module. Before building providers we mirror that
# override into the extracted transport layer.
_http_get_bytes = _transport._raw_http_get_bytes


def _sync_transport_overrides() -> None:
    _transport._raw_http_get_bytes = _http_get_bytes


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
    raise ConfiguredAdapterError(f"Не найден enabled adapter допустимого типа {sorted(expected_types)}.")


@dataclass(frozen=True)
class ConfiguredIngestContext:
    security_master_raw: pd.DataFrame
    security_master: pd.DataFrame
    symbol_mapper: SymbolMapper
    market_provider: MarketDataProvider
    fundamentals_provider: FundamentalsProvider
    corporate_actions_provider: CorporateActionsProvider
    notes: list[str]


def _build_market_provider(adapter: AdapterConfig, root: Path) -> MarketDataProvider:
    if adapter.adapter_type == "stooq_eod_http":
        return StooqEodHttpMarketProvider(adapter, root=root)
    if adapter.adapter_type == "yahoo_chart_http":
        return YahooChartMarketProvider(adapter, root=root)
    if adapter.adapter_type == "local_file_market_daily":
        return LocalFileMarketProvider(adapter, root)
    raise ConfiguredAdapterError(f"Неподдерживаемый market adapter type: {adapter.adapter_type}")


def _build_fundamentals_provider(
    adapter: AdapterConfig,
    raw_security_master: pd.DataFrame,
    root: Path,
) -> FundamentalsProvider:
    if adapter.adapter_type == "sec_companyfacts_http":
        return SecCompanyFactsProvider(adapter, raw_security_master, root=root)
    if adapter.adapter_type == "local_file_fundamentals":
        return LocalFileFundamentalsProvider(adapter, root)
    raise ConfiguredAdapterError(f"Неподдерживаемый fundamentals adapter type: {adapter.adapter_type}")


def _build_corporate_actions_provider(adapter: AdapterConfig, root: Path) -> CorporateActionsProvider:
    if adapter.adapter_type == "local_file_corporate_actions":
        return LocalFileCorporateActionsProvider(adapter, root)
    if adapter.adapter_type == "yahoo_chart_corporate_actions_http":
        return YahooChartCorporateActionsProvider(adapter, root=root)
    raise ConfiguredAdapterError(f"Неподдерживаемый corporate actions adapter type: {adapter.adapter_type}")


def load_benchmark_market_from_config(root: Path, provider: ProviderConfig, start_date: str, end_date: str) -> tuple[pd.DataFrame, str]:
    _sync_transport_overrides()
    adapter = _select_adapter(
        provider,
        expected_types={"local_file_benchmark", "stooq_benchmark_http", "yahoo_chart_benchmark_http", "market_panel_proxy"},
    )
    return _load_benchmark_market_from_config(root, provider, start_date, end_date, adapter)


def build_configured_ingest_context(root: Path, loaded: LoadedConfigBundle) -> ConfiguredIngestContext:
    _sync_transport_overrides()
    paths = RepositoryPaths.from_root(root)

    security_master_adapter = _select_adapter(
        loaded.bundle.data_sources.security_master_provider,
        expected_types={"local_file_security_master", "sec_exchange_security_master"},
    )
    resolved_security_master: ResolvedSecurityMaster = load_security_master_from_config(
        paths.root,
        loaded.bundle.data_sources.security_master_provider,
        security_master_adapter,
    )

    market_adapter = _select_adapter(
        loaded.bundle.data_sources.market_provider,
        expected_types={"stooq_eod_http", "local_file_market_daily", "yahoo_chart_http"},
    )
    fundamentals_adapter = _select_adapter(
        loaded.bundle.data_sources.fundamentals_provider,
        expected_types={"sec_companyfacts_http", "local_file_fundamentals"},
    )
    corporate_actions_adapter = _select_adapter(
        loaded.bundle.data_sources.corporate_actions_provider,
        expected_types={"local_file_corporate_actions", "yahoo_chart_corporate_actions_http"},
    )

    notes = [
        "Операционный ingest работает через configured adapters path.",
        f"security_master_adapter={resolved_security_master.raw_frame.attrs.get('adapter_name', security_master_adapter.adapter_name)}",
        f"market_adapter={market_adapter.adapter_name}",
        f"fundamentals_adapter={fundamentals_adapter.adapter_name}",
        f"corporate_actions_adapter={corporate_actions_adapter.adapter_name}",
    ]
    return ConfiguredIngestContext(
        security_master_raw=resolved_security_master.raw_frame,
        security_master=resolved_security_master.canonical_frame,
        symbol_mapper=resolved_security_master.symbol_mapper,
        market_provider=_build_market_provider(market_adapter, paths.root),
        fundamentals_provider=_build_fundamentals_provider(fundamentals_adapter, resolved_security_master.raw_frame, paths.root),
        corporate_actions_provider=_build_corporate_actions_provider(corporate_actions_adapter, paths.root),
        notes=notes,
    )


__all__ = [
    "ConfiguredAdapterError",
    "ConfiguredAdapterPermanentError",
    "ConfiguredAdapterTransientError",
    "ConfiguredIngestContext",
    "_http_get_bytes",
    "build_configured_ingest_context",
    "load_benchmark_market_from_config",
]
