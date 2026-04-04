from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderPage:
    records: list[dict[str, Any]]
    original_payload: Any
    next_page_token: str | None = None
    missing_symbols: list[str] = field(default_factory=list)


class MarketDataProvider(ABC):
    endpoint_name = "market_daily"

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch_market_data(self, symbols: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        raise NotImplementedError


class FundamentalsProvider(ABC):
    endpoint_name = "fundamentals"

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch_fundamentals(self, company_ids: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        raise NotImplementedError


class CorporateActionsProvider(ABC):
    endpoint_name = "corporate_actions"

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch_corporate_actions(self, securities: list[str], start_date: str, end_date: str, page_token: str | None = None) -> ProviderPage:
        raise NotImplementedError
