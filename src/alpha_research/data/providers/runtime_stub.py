from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from alpha_research.data.providers.base import CorporateActionsProvider, FundamentalsProvider, MarketDataProvider, ProviderPage
from alpha_research.pipeline.fixture_data import SyntheticResearchBundle


def _slice_page(records: list[dict[str, object]], page_size: int, page_token: str | None) -> ProviderPage:
    start = int(page_token or 0)
    end = start + page_size
    page_records = records[start:end]
    next_page_token = None if end >= len(records) else str(end)
    return ProviderPage(records=page_records, original_payload={"records": page_records, "next_page_token": next_page_token}, next_page_token=next_page_token)


@dataclass(frozen=True)
class RuntimeSecurityMasterFixture:
    frame: pd.DataFrame

    @property
    def symbols(self) -> list[str]:
        return self.frame["symbol"].dropna().astype("string").str.upper().tolist()

    @property
    def company_ids(self) -> list[str]:
        return [security_id.replace("SEC_", "COMP_") for security_id in self.frame["security_id"].dropna().astype("string").tolist()]


class SyntheticMarketDataProvider(MarketDataProvider):
    def __init__(self, bundle: SyntheticResearchBundle, page_size: int = 500) -> None:
        self.bundle = bundle
        self.page_size = page_size
        self._name = "synthetic_vendor_stub_market"

    @property
    def name(self) -> str:
        return self._name

    def fetch_market_data(self, symbols: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        market = self.bundle.silver_market.copy()
        security_master = self.bundle.security_master[["security_id", "symbol"]].copy()
        market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce").dt.normalize()
        market = market.merge(security_master, on="security_id", how="left")
        symbol_set = {str(symbol).upper() for symbol in symbols}
        start_ts = pd.Timestamp(start_date).normalize()
        end_ts = pd.Timestamp(end_date).normalize()
        filtered = market.loc[
            market["symbol"].astype("string").str.upper().isin(symbol_set)
            & market["trade_date"].between(start_ts, end_ts),
            ["symbol", "trade_date", "open", "high", "low", "close", "adj_close", "volume"],
        ].copy()
        records = [
            {
                "symbol": row.symbol,
                "trade_date": str(pd.Timestamp(row.trade_date).date()),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "adj_close": float(row.adj_close),
                "volume": int(row.volume),
                "currency": "USD",
            }
            for row in filtered.sort_values(["symbol", "trade_date"], kind="stable").itertuples(index=False)
        ]
        page = _slice_page(records, self.page_size, page_token)
        page.missing_symbols.extend(sorted(symbol_set - set(filtered["symbol"].astype("string").str.upper().unique().tolist())))
        return page


class SyntheticFundamentalsProvider(FundamentalsProvider):
    def __init__(self, bundle: SyntheticResearchBundle, page_size: int = 500) -> None:
        self.bundle = bundle
        self.page_size = page_size
        self._name = "synthetic_vendor_stub_fundamentals"

    @property
    def name(self) -> str:
        return self._name

    def fetch_fundamentals(self, company_ids: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        frame = self.bundle.bronze_fundamentals.copy()
        frame["filing_date"] = pd.to_datetime(frame["filing_date"], errors="coerce").dt.normalize()
        company_set = {str(company_id).upper() for company_id in company_ids}
        start_ts = pd.Timestamp(start_date).normalize()
        end_ts = pd.Timestamp(end_date).normalize()
        filtered = frame.loc[
            frame["source_company_id"].astype("string").str.upper().isin(company_set)
            & frame["filing_date"].between(start_ts, end_ts),
            [
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
            ],
        ].copy()
        records = [
            {
                "security_id": row.security_id,
                "source_company_id": row.source_company_id,
                "form_type": row.form_type,
                "filing_date": str(pd.Timestamp(row.filing_date).date()),
                "acceptance_datetime": str(pd.Timestamp(row.acceptance_datetime)),
                "fiscal_period_end": str(pd.Timestamp(row.fiscal_period_end).date()),
                "metric_name_raw": row.metric_name_raw,
                "metric_value": float(row.metric_value),
                "metric_unit": row.metric_unit,
                "statement_type": row.statement_type,
            }
            for row in filtered.sort_values(["source_company_id", "filing_date", "metric_name_raw"], kind="stable").itertuples(index=False)
        ]
        return _slice_page(records, self.page_size, page_token)


class SyntheticCorporateActionsProvider(CorporateActionsProvider):
    def __init__(self, bundle: SyntheticResearchBundle, page_size: int = 500) -> None:
        self.bundle = bundle
        self.page_size = page_size
        self._name = "synthetic_vendor_stub_corporate_actions"

    @property
    def name(self) -> str:
        return self._name

    def fetch_corporate_actions(self, securities: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        security_master = self.bundle.security_master.reset_index(drop=True)
        symbols = {str(item).upper() for item in securities}
        start_ts = pd.Timestamp(start_date).normalize()
        end_ts = pd.Timestamp(end_date).normalize()
        midpoint = start_ts + (end_ts - start_ts) / 2
        candidate_rows: list[dict[str, object]] = []
        if not security_master.empty:
            first = security_master.iloc[0]
            if str(first["symbol"]).upper() in symbols:
                candidate_rows.append(
                    {
                        "security_id": first["security_id"],
                        "symbol": first["symbol"],
                        "event_type": "split",
                        "event_date": str(pd.Timestamp(midpoint).normalize().date()),
                        "effective_date": str(pd.Timestamp(midpoint).normalize().date()),
                        "split_ratio": 2.0,
                        "dividend_amount": None,
                        "delisting_code": None,
                        "old_symbol": None,
                        "new_symbol": None,
                    }
                )
        if len(security_master) > 1:
            second = security_master.iloc[1]
            if str(second["symbol"]).upper() in symbols:
                candidate_rows.append(
                    {
                        "security_id": second["security_id"],
                        "symbol": second["symbol"],
                        "event_type": "dividend",
                        "event_date": str(pd.Timestamp(midpoint + pd.Timedelta(days=5)).normalize().date()),
                        "effective_date": str(pd.Timestamp(midpoint + pd.Timedelta(days=5)).normalize().date()),
                        "split_ratio": None,
                        "dividend_amount": 0.12,
                        "delisting_code": None,
                        "old_symbol": None,
                        "new_symbol": None,
                    }
                )
        if len(security_master) > 2:
            third = security_master.iloc[2]
            if str(third["symbol"]).upper() in symbols:
                candidate_rows.append(
                    {
                        "security_id": third["security_id"],
                        "symbol": third["symbol"],
                        "event_type": "symbol_change",
                        "event_date": str(pd.Timestamp(midpoint + pd.Timedelta(days=10)).normalize().date()),
                        "effective_date": str(pd.Timestamp(midpoint + pd.Timedelta(days=10)).normalize().date()),
                        "split_ratio": None,
                        "dividend_amount": None,
                        "delisting_code": None,
                        "old_symbol": third["symbol"],
                        "new_symbol": f"{third['symbol']}X",
                    }
                )
        return _slice_page(candidate_rows, self.page_size, page_token)
