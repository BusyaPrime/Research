from __future__ import annotations

import pandas as pd


def assert_no_future_available_from(joined_panel: pd.DataFrame, metrics: list[str], as_of_column: str = "as_of_timestamp") -> None:
    for metric in metrics:
        source_column = f"source_available_from__{metric}"
        if source_column not in joined_panel.columns:
            continue
        source_ts = pd.to_datetime(joined_panel[source_column], errors="coerce", utc=True)
        as_of_ts = pd.to_datetime(joined_panel[as_of_column], errors="coerce", utc=True)
        invalid = source_ts.notna() & (source_ts > as_of_ts)
        if invalid.any():
            raise ValueError(f"Future data leakage detected for metric {metric}.")
