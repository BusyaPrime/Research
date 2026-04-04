from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.time.calendar import ExchangeCalendarAdapter


@dataclass(frozen=True)
class ModelResearchBundle:
    calendar: ExchangeCalendarAdapter
    panel: pd.DataFrame
    feature_columns: list[str]
    label_column: str


def build_model_research_bundle() -> ModelResearchBundle:
    calendar = ExchangeCalendarAdapter("XNYS")
    dates = calendar.calendar.sessions_in_range("2021-01-04", "2024-12-31").tz_localize(None)
    securities = [f"SEC_{idx:02d}" for idx in range(10)]
    rng = np.random.default_rng(123)
    rows: list[dict[str, object]] = []
    day_index = np.arange(len(dates))
    for sec_idx, security_id in enumerate(securities):
        sec_noise = rng.normal(0.0, 0.02, size=len(dates))
        for i, date in enumerate(dates):
            ret_1 = 0.02 * np.sin((i + sec_idx) / 11.0) + sec_idx * 0.0005
            mom_21_ex1 = 0.04 * np.cos((i + sec_idx) / 19.0) + sec_idx * 0.001
            book_to_price = 0.3 + sec_idx * 0.05 + 0.05 * np.sin(i / 37.0)
            vol_21 = 0.15 + 0.01 * sec_idx + 0.02 * np.cos(i / 23.0)
            label = 0.7 * mom_21_ex1 - 0.25 * ret_1 + 0.15 * book_to_price - 0.1 * vol_21 + sec_noise[i]
            rows.append(
                {
                    "date": date,
                    "security_id": security_id,
                    "row_valid_flag": True,
                    "ret_1": ret_1,
                    "rev_1": -ret_1,
                    "mom_21_ex1": mom_21_ex1,
                    "book_to_price": book_to_price,
                    "vol_21": vol_21,
                    "label_excess_5d_oo": label,
                }
            )
    panel = pd.DataFrame(rows)
    return ModelResearchBundle(
        calendar=calendar,
        panel=panel,
        feature_columns=["ret_1", "rev_1", "mom_21_ex1", "book_to_price", "vol_21"],
        label_column="label_excess_5d_oo",
    )
