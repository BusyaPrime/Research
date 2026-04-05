from __future__ import annotations

import pandas as pd

from alpha_research.data.providers.base import CorporateActionsProvider, FundamentalsProvider, MarketDataProvider, ProviderPage


class PagedMarketProvider(MarketDataProvider):
    def __init__(self, pages: list[ProviderPage], name: str = "fake_market") -> None:
        self._pages = pages
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def fetch_market_data(self, symbols: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        self.calls += 1
        index = int(page_token) if page_token is not None else 0
        return self._pages[index]


class PagedFundamentalsProvider(FundamentalsProvider):
    def __init__(self, pages: list[ProviderPage], name: str = "fake_fundamentals") -> None:
        self._pages = pages
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def fetch_fundamentals(self, company_ids: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        self.calls += 1
        index = int(page_token) if page_token is not None else 0
        return self._pages[index]


class PagedCorporateActionsProvider(CorporateActionsProvider):
    def __init__(self, pages: list[ProviderPage], name: str = "fake_ca") -> None:
        self._pages = pages
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def fetch_corporate_actions(self, securities: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        self.calls += 1
        index = int(page_token) if page_token is not None else 0
        return self._pages[index]


def sample_security_master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "security_id": "SEC_AAPL",
                "symbol": "AAPL",
                "security_type": "common_stock",
                "exchange": "NASDAQ",
                "listing_date": "1980-12-12",
                "delisting_date": None,
                "sector": "Technology",
                "industry": "Hardware",
                "country": "US",
                "currency": "USD",
                "is_common_stock": True,
            },
            {
                "security_id": "SEC_MSFT",
                "symbol": "MSFT",
                "security_type": "common_stock",
                "exchange": "NASDAQ",
                "listing_date": "1986-03-13",
                "delisting_date": None,
                "sector": "Technology",
                "industry": "Software",
                "country": "US",
                "currency": "USD",
                "is_common_stock": True,
            },
            {
                "security_id": "SEC_GOOG",
                "symbol": "GOOG",
                "security_type": "common_stock",
                "exchange": "NASDAQ",
                "listing_date": "2004-08-19",
                "delisting_date": None,
                "sector": "Technology",
                "industry": "Internet",
                "country": "US",
                "currency": "USD",
                "is_common_stock": True,
            },
        ]
    )
