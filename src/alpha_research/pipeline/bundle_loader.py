from __future__ import annotations

from pathlib import Path

import pandas as pd

from alpha_research.common.io import read_parquet
from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.data.ingest.corporate_actions import CorporateActionsIngestionService
from alpha_research.data.ingest.fundamentals import FundamentalsIngestionService
from alpha_research.data.ingest.market import MarketIngestionService
from alpha_research.data.providers.configured import ConfiguredAdapterError, build_configured_ingest_context, load_benchmark_market_from_config
from alpha_research.pipeline.fixture_data import SyntheticResearchBundle, build_synthetic_research_bundle
from alpha_research.pit.builders import build_silver_fundamentals_pit, build_silver_market
from alpha_research.reference.security_master import SymbolMapper
from alpha_research.time.calendar import ExchangeCalendarAdapter


def _selected_security_master(security_master: pd.DataFrame, n_securities: int | None) -> pd.DataFrame:
    frame = security_master.copy()
    allowlist = []
    if "symbol_allowlist" in frame.attrs and frame.attrs["symbol_allowlist"]:
        allowlist = [str(symbol).upper() for symbol in frame.attrs["symbol_allowlist"]]
    if allowlist:
        frame = frame.loc[frame["symbol"].astype("string").str.upper().isin(allowlist)].copy()
    symbol_series = frame["symbol"].astype("string")
    frame["_priority_common_stock"] = frame.get("is_common_stock", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    frame["_priority_exchange"] = frame.get("exchange", pd.Series(index=frame.index, dtype="string")).astype("string").isin(["NYSE", "NASDAQ"])
    frame["_priority_symbol"] = symbol_series.str.fullmatch(r"[A-Z]{1,5}", na=False)
    if n_securities is None or n_securities <= 0 or len(frame) <= n_securities:
        return frame.sort_values(["_priority_common_stock", "_priority_exchange", "_priority_symbol", "symbol", "security_id"], ascending=[False, False, False, True, True], kind="stable").drop(columns=["_priority_common_stock", "_priority_exchange", "_priority_symbol"], errors="ignore").reset_index(drop=True)
    return (
        frame.sort_values(
            ["_priority_common_stock", "_priority_exchange", "_priority_symbol", "symbol", "security_id"],
            ascending=[False, False, False, True, True],
            kind="stable",
        )
        .head(n_securities)
        .drop(columns=["_priority_common_stock", "_priority_exchange", "_priority_symbol"], errors="ignore")
        .reset_index(drop=True)
    )


def _company_ids_from_security_master(raw_security_master: pd.DataFrame, security_ids: set[str]) -> list[str]:
    if "source_company_id" not in raw_security_master.columns or "security_id" not in raw_security_master.columns:
        return []
    filtered = raw_security_master.loc[
        raw_security_master["security_id"].astype("string").isin(security_ids),
        "source_company_id",
    ]
    return filtered.dropna().astype("string").str.upper().drop_duplicates().tolist()


def _build_proxy_benchmark_market(silver_market: pd.DataFrame) -> pd.DataFrame:
    required = ["trade_date", "open", "high", "low", "close"]
    frame = silver_market.loc[:, required].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.normalize()
    benchmark = (
        frame.groupby("trade_date", as_index=False, sort=True)
        .agg(
            open=("open", "mean"),
            high=("high", "mean"),
            low=("low", "mean"),
            close=("close", "mean"),
        )
        .sort_values("trade_date", kind="stable")
        .reset_index(drop=True)
    )
    return benchmark


def _resolve_benchmark_market(
    root: Path,
    loaded: LoadedConfigBundle,
    silver_market: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, str]:
    benchmark, benchmark_adapter = load_benchmark_market_from_config(
        root,
        loaded.bundle.data_sources.benchmark_provider,
        start_date,
        end_date,
    )
    if benchmark_adapter == "market_panel_proxy" or benchmark.empty:
        return _build_proxy_benchmark_market(silver_market), "market_panel_proxy"
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], errors="coerce").dt.normalize()
    return benchmark.sort_values("trade_date", kind="stable").reset_index(drop=True), benchmark_adapter


def build_configured_research_bundle(
    root: Path,
    loaded: LoadedConfigBundle,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    n_securities: int | None = None,
) -> SyntheticResearchBundle:
    paths = RepositoryPaths.from_root(root)
    runtime_ingest = loaded.bundle.runtime.ingest
    effective_start = start_date or runtime_ingest.default_start_date
    effective_end = end_date or runtime_ingest.default_end_date

    try:
        context = build_configured_ingest_context(paths.root, loaded)
    except ConfiguredAdapterError as exc:
        raise KeyError(f"Configured bundle adapters error: {exc}") from exc

    security_master_candidate = context.security_master.copy()
    security_master_candidate.attrs["symbol_allowlist"] = runtime_ingest.symbol_allowlist
    security_master = _selected_security_master(security_master_candidate, n_securities)
    security_ids = set(security_master["security_id"].dropna().astype("string").tolist())
    symbol_mapper = SymbolMapper(security_master)
    symbols = security_master["symbol"].dropna().astype("string").str.upper().tolist()
    company_ids = _company_ids_from_security_master(context.security_master_raw, security_ids)

    market_service = MarketIngestionService(root=paths.root)
    market_artifacts = market_service.ingest(context.market_provider, symbols, effective_start, effective_end, symbol_mapper)
    bronze_market = read_parquet(market_artifacts.bronze_path)
    bronze_market = bronze_market.loc[bronze_market["security_id"].astype("string").isin(security_ids)].copy()
    silver_market = build_silver_market(bronze_market, root=paths.root)

    fundamentals_service = FundamentalsIngestionService(root=paths.root)
    fundamentals_artifacts = fundamentals_service.ingest(context.fundamentals_provider, company_ids, effective_start, effective_end)
    bronze_fundamentals = read_parquet(fundamentals_artifacts.bronze_path)
    bronze_fundamentals = bronze_fundamentals.loc[
        bronze_fundamentals["security_id"].astype("string").isin(security_ids)
    ].copy()
    silver_fundamentals = build_silver_fundamentals_pit(bronze_fundamentals, root=paths.root)

    corporate_actions_service = CorporateActionsIngestionService(root=paths.root)
    corporate_actions_service.ingest(
        context.corporate_actions_provider,
        symbols,
        effective_start,
        effective_end,
        symbol_mapper,
    )

    benchmark_market, benchmark_adapter = _resolve_benchmark_market(
        paths.root,
        loaded,
        silver_market,
        start_date=effective_start,
        end_date=effective_end,
    )
    notes = [
        *context.notes,
        "Research bundle собран из configured adapters и сохраненных bronze artifacts.",
        f"benchmark_adapter={benchmark_adapter}",
    ]
    if benchmark_adapter == "market_panel_proxy":
        notes.append("Benchmark path использует равновзвешенный proxy по market panel; labels config это допускает как proxy_or_index_return.")
    return SyntheticResearchBundle(
        calendar=ExchangeCalendarAdapter("XNYS"),
        security_master=security_master,
        silver_market=silver_market,
        bronze_fundamentals=bronze_fundamentals,
        silver_fundamentals=silver_fundamentals,
        benchmark_market=benchmark_market,
        notes=notes,
    )


def resolve_operational_bundle(
    paths: RepositoryPaths,
    loaded: LoadedConfigBundle,
    *,
    synthetic_bundle: SyntheticResearchBundle | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    n_securities: int | None = None,
) -> SyntheticResearchBundle:
    if synthetic_bundle is not None:
        return synthetic_bundle

    runtime_ingest = loaded.bundle.runtime.ingest
    if runtime_ingest.provider_mode == "configured_adapters":
        return build_configured_research_bundle(
            paths.root,
            loaded,
            start_date=start_date,
            end_date=end_date,
            n_securities=n_securities,
        )

    return build_synthetic_research_bundle(
        start_date=start_date or runtime_ingest.default_start_date,
        end_date=end_date or runtime_ingest.default_end_date,
        n_securities=n_securities or runtime_ingest.default_n_securities,
        seed=loaded.bundle.project.default_random_seed,
    )
