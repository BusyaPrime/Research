from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.data.schemas import validate_dataframe


def build_security_master(raw_frame: pd.DataFrame, root: Path | None = None) -> pd.DataFrame:
    frame = raw_frame.copy()
    frame["exchange"] = frame["exchange"].astype("string").str.upper()
    frame["security_type"] = frame["security_type"].astype("string").str.lower()
    frame["symbol"] = frame["symbol"].astype("string").str.upper()
    frame["is_common_stock"] = frame["is_common_stock"].astype("boolean")
    validated = validate_dataframe(frame, "security_master", root=root)

    listing_dates = pd.to_datetime(validated["listing_date"], errors="coerce")
    delisting_dates = pd.to_datetime(validated["delisting_date"], errors="coerce")
    invalid_interval = delisting_dates.notna() & listing_dates.notna() & (delisting_dates < listing_dates)
    if invalid_interval.any():
        raise ValueError("security_master contains listing intervals with delisting_date < listing_date")

    return validated.sort_values(["security_id", "symbol"], kind="stable").reset_index(drop=True)


@dataclass(frozen=True)
class SymbolMappingResult:
    mapped: dict[str, str]
    missing_symbols: list[str]


class SymbolMapper:
    def __init__(self, security_master: pd.DataFrame) -> None:
        self.security_master = build_security_master(security_master)

    def resolve(self, symbol: str, as_of_date: str | pd.Timestamp | None = None) -> str | None:
        symbol_normalized = str(symbol).upper()
        candidates = self.security_master[self.security_master["symbol"] == symbol_normalized]
        if as_of_date is not None and not candidates.empty:
            as_of_ts = pd.Timestamp(as_of_date).normalize()
            listing = pd.to_datetime(candidates["listing_date"], errors="coerce")
            delisting = pd.to_datetime(candidates["delisting_date"], errors="coerce")
            active_mask = (listing.isna() | (listing <= as_of_ts)) & (delisting.isna() | (delisting >= as_of_ts))
            candidates = candidates[active_mask]
        if candidates.empty:
            return None
        security_ids = candidates["security_id"].dropna().unique().tolist()
        if len(security_ids) != 1:
            raise ValueError(f"Ambiguous symbol mapping for {symbol_normalized}: {security_ids}")
        return security_ids[0]

    def map_symbols(self, symbols: list[str], as_of_date: str | pd.Timestamp | None = None) -> SymbolMappingResult:
        mapped: dict[str, str] = {}
        missing: list[str] = []
        for symbol in symbols:
            security_id = self.resolve(symbol, as_of_date=as_of_date)
            if security_id is None:
                missing.append(str(symbol).upper())
            else:
                mapped[str(symbol).upper()] = security_id
        return SymbolMappingResult(mapped=mapped, missing_symbols=sorted(set(missing)))
