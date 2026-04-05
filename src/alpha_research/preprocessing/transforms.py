from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd


class Winsorizer:
    def __init__(self, lower_pct: float = 0.5, upper_pct: float = 99.5) -> None:
        self.lower_pct = lower_pct / 100.0 if lower_pct > 1 else lower_pct
        self.upper_pct = upper_pct / 100.0 if upper_pct > 1 else upper_pct
        self.bounds_: dict[str, tuple[float, float]] = {}

    def fit(self, frame: pd.DataFrame, feature_columns: list[str]) -> Winsorizer:
        self.bounds_ = {}
        for column in feature_columns:
            series = pd.to_numeric(frame[column], errors="coerce")
            self.bounds_[column] = (float(series.quantile(self.lower_pct)), float(series.quantile(self.upper_pct)))
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        for column, (lower, upper) in self.bounds_.items():
            output[column] = pd.to_numeric(output[column], errors="coerce").astype("float64").clip(lower=lower, upper=upper)
        return output


def zscore_by_date(frame: pd.DataFrame, feature_columns: list[str], date_column: str = "date") -> pd.DataFrame:
    output = frame.copy()
    for column in feature_columns:
        def _transform(values: pd.Series) -> pd.Series:
            std = values.std(ddof=0)
            if pd.isna(std) or std == 0:
                return values * 0.0
            return (values - values.mean()) / std

        output[column] = output.groupby(date_column, dropna=False)[column].transform(_transform)
    return output


def robust_zscore_by_date(frame: pd.DataFrame, feature_columns: list[str], date_column: str = "date") -> pd.DataFrame:
    output = frame.copy()
    for column in feature_columns:
        def _transform(values: pd.Series) -> pd.Series:
            median = values.median()
            mad = (values - median).abs().median()
            scale = 1.4826 * mad if not pd.isna(mad) and mad != 0 else np.nan
            if pd.isna(scale) or scale == 0:
                return values * 0.0
            return (values - median) / scale
        output[column] = output.groupby(date_column, dropna=False)[column].transform(_transform)
    return output


def percentile_rank_by_date(frame: pd.DataFrame, feature_columns: list[str], date_column: str = "date") -> pd.DataFrame:
    output = frame.copy()
    for column in feature_columns:
        output[column] = output.groupby(date_column, dropna=False)[column].transform(lambda values: values.rank(method="average", pct=True))
    return output


def sector_neutralize(frame: pd.DataFrame, feature_columns: list[str], sector_column: str = "sector", date_column: str = "date") -> pd.DataFrame:
    output = frame.copy()
    original_index = output.index
    for column in feature_columns:
        output[column] = output[column] - output.groupby([date_column, sector_column], dropna=False)[column].transform("mean")
    output.index = original_index
    return output


def beta_neutralize(frame: pd.DataFrame, feature_columns: list[str], beta_column: str = "beta_estimate", date_column: str = "date") -> pd.DataFrame:
    output = frame.copy()
    original_index = output.index
    for column in feature_columns:
        residuals = pd.Series(np.nan, index=output.index, dtype="float64")
        for date, group in output.groupby(date_column, sort=False):
            valid = group[[column, beta_column]].dropna()
            if len(valid) < 2:
                residuals.loc[group.index] = group[column]
                continue
            X = np.column_stack([np.ones(len(valid)), valid[beta_column].to_numpy(dtype=float)])
            y = valid[column].to_numpy(dtype=float)
            coeffs, *_ = np.linalg.lstsq(X, y, rcond=None)
            fitted = X @ coeffs
            residuals.loc[valid.index] = y - fitted
            residuals.loc[group.index.difference(valid.index)] = group.loc[group.index.difference(valid.index), column]
        output[column] = residuals
    output.index = original_index
    return output


@dataclass(frozen=True)
class PreprocessingSpec:
    winsor_lower: float | None = None
    winsor_upper: float | None = None
    scaler: str | None = None
    neutralizer: str | None = None


@dataclass(frozen=True)
class PreprocessorFitMetadata:
    row_count: int
    unique_dates: int
    date_min: pd.Timestamp | None
    date_max: pd.Timestamp | None
    feature_signature: str


class FoldSafePreprocessor:
    def __init__(self, spec: PreprocessingSpec, feature_columns: list[str]) -> None:
        self.spec = spec
        self.feature_columns = feature_columns
        self.winsorizer_: Winsorizer | None = None
        self.fit_metadata_: PreprocessorFitMetadata | None = None

    def _build_fit_metadata(self, frame: pd.DataFrame) -> PreprocessorFitMetadata:
        working = frame.copy()
        if "date" in working.columns:
            dates = pd.to_datetime(working["date"], errors="coerce").dt.normalize()
            date_min = None if dates.dropna().empty else pd.Timestamp(dates.min())
            date_max = None if dates.dropna().empty else pd.Timestamp(dates.max())
            unique_dates = int(dates.nunique(dropna=True))
        else:
            date_min = None
            date_max = None
            unique_dates = 0

        feature_frame = working.reindex(columns=self.feature_columns).copy()
        hashed = pd.util.hash_pandas_object(feature_frame, index=True, categorize=False).values.tobytes()
        signature = hashlib.sha256(hashed).hexdigest()
        return PreprocessorFitMetadata(
            row_count=int(len(working)),
            unique_dates=unique_dates,
            date_min=date_min,
            date_max=date_max,
            feature_signature=signature,
        )

    def fit(self, train_frame: pd.DataFrame) -> FoldSafePreprocessor:
        self.fit_metadata_ = self._build_fit_metadata(train_frame)
        if self.spec.winsor_lower is not None and self.spec.winsor_upper is not None:
            self.winsorizer_ = Winsorizer(self.spec.winsor_lower, self.spec.winsor_upper).fit(train_frame, self.feature_columns)
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        if self.winsorizer_ is not None:
            output = self.winsorizer_.transform(output)

        if self.spec.scaler == "zscore_by_date":
            output = zscore_by_date(output, self.feature_columns)
        elif self.spec.scaler == "robust_zscore_by_date":
            output = robust_zscore_by_date(output, self.feature_columns)
        elif self.spec.scaler == "percentile_rank_by_date":
            output = percentile_rank_by_date(output, self.feature_columns)

        if self.spec.neutralizer == "sector":
            output = sector_neutralize(output, self.feature_columns)
        elif self.spec.neutralizer == "beta":
            output = beta_neutralize(output, self.feature_columns)
        elif self.spec.neutralizer == "sector_plus_beta":
            output = sector_neutralize(output, self.feature_columns)
            output = beta_neutralize(output, self.feature_columns)
        return output
