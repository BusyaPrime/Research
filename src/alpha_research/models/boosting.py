from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd


def _safe_rank_corr(left: pd.Series, right: pd.Series) -> float:
    ranked = pd.concat(
        [
            pd.to_numeric(left, errors="coerce").rank(method="average").rename("left"),
            pd.to_numeric(right, errors="coerce").rank(method="average").rename("right"),
        ],
        axis=1,
    ).dropna()
    if len(ranked) < 2:
        return float("nan")
    if ranked["left"].std(ddof=0) <= 1e-12 or ranked["right"].std(ddof=0) <= 1e-12:
        return float("nan")
    return float(ranked["left"].corr(ranked["right"]))


def _rank_ic_by_date(frame: pd.DataFrame, prediction_column: str, label_column: str) -> float:
    scores: list[float] = []
    for _, group in frame.groupby("date", sort=False):
        subset = group[[prediction_column, label_column]].dropna()
        if len(subset) < 2:
            continue
        corr = _safe_rank_corr(subset[prediction_column], subset[label_column])
        if pd.notna(corr):
            scores.append(float(corr))
    return float(np.mean(scores)) if scores else float("nan")


@dataclass(frozen=True)
class DecisionStump:
    feature_name: str
    threshold: float
    left_value: float
    right_value: float

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        feature = pd.to_numeric(frame[self.feature_name], errors="coerce").to_numpy(dtype="float64")
        return np.where(feature <= self.threshold, self.left_value, self.right_value)


def _candidate_thresholds(values: np.ndarray, max_bins: int) -> list[float]:
    clean = values[np.isfinite(values)]
    if len(clean) < 4:
        return []
    quantiles = np.linspace(0.1, 0.9, max(2, max_bins))
    thresholds = np.unique(np.quantile(clean, quantiles))
    return [float(value) for value in thresholds if np.isfinite(value)]


def _rank_target(values: pd.Series, dates: pd.Series | None) -> pd.Series:
    if dates is None:
        return values.rank(method="average", pct=True) - 0.5

    frame = pd.DataFrame({"date": dates, "value": values})
    ranked = frame.groupby("date", dropna=False)["value"].transform(lambda column: column.rank(method="average", pct=True))
    return pd.to_numeric(ranked, errors="coerce") - 0.5


class _GradientBoostingBase:
    name = "gradient_boosting_base"
    max_feature_candidates = 16

    def __init__(
        self,
        *,
        n_estimators: int = 24,
        learning_rate: float = 0.05,
        max_bins: int = 12,
        min_leaf_size: int = 16,
        random_seed: int = 42,
    ) -> None:
        self.n_estimators = int(n_estimators)
        self.learning_rate = float(learning_rate)
        self.max_bins = int(max_bins)
        self.min_leaf_size = int(min_leaf_size)
        self.random_seed = int(random_seed)
        self.feature_columns_: list[str] = []
        self.feature_medians_: dict[str, float] = {}
        self.base_value_: float = 0.0
        self.stumps_: list[DecisionStump] = []

    def _prepare_features(self, frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
        output = pd.DataFrame(index=frame.index)
        for column in feature_columns:
            output[column] = pd.to_numeric(frame[column], errors="coerce")
        medians = output.median(axis=0, skipna=True).fillna(0.0)
        output = output.fillna(medians.to_dict())
        self.feature_medians_ = {column: float(value) for column, value in medians.to_dict().items()}
        return output.astype("float64")

    def _build_target(self, labels: pd.Series, dates: pd.Series | None) -> pd.Series:
        return pd.to_numeric(labels, errors="coerce")

    def _fit_stump(self, frame: pd.DataFrame, residual: np.ndarray) -> tuple[DecisionStump | None, float]:
        baseline_loss = float(np.mean(np.square(residual))) if len(residual) else 0.0
        best_loss = baseline_loss
        best_stump: DecisionStump | None = None

        for feature_name in self.feature_columns_:
            feature = frame[feature_name].to_numpy(dtype="float64")
            for threshold in _candidate_thresholds(feature, self.max_bins):
                left_mask = feature <= threshold
                left_count = int(left_mask.sum())
                right_count = int(len(feature) - left_count)
                if left_count < self.min_leaf_size or right_count < self.min_leaf_size:
                    continue
                left_value = float(residual[left_mask].mean())
                right_value = float(residual[~left_mask].mean())
                update = np.where(left_mask, left_value, right_value)
                loss = float(np.mean(np.square(residual - update)))
                if loss + 1e-12 < best_loss:
                    best_loss = loss
                    best_stump = DecisionStump(
                        feature_name=feature_name,
                        threshold=float(threshold),
                        left_value=left_value,
                        right_value=right_value,
                    )
        return best_stump, baseline_loss - best_loss

    def fit(self, frame: pd.DataFrame, feature_columns: list[str], label_column: str) -> "_GradientBoostingBase":
        clean = frame[feature_columns + [label_column]].copy()
        if "date" in frame.columns:
            clean["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
        clean = clean.dropna(subset=[label_column]).reset_index(drop=True)
        self.feature_columns_ = list(feature_columns)
        if clean.empty:
            self.base_value_ = 0.0
            self.stumps_ = []
            self.feature_medians_ = {column: 0.0 for column in feature_columns}
            return self

        features = self._prepare_features(clean, feature_columns)
        target = self._build_target(
            pd.to_numeric(clean[label_column], errors="coerce"),
            clean.get("date"),
        )
        mask = target.notna()
        features = features.loc[mask].reset_index(drop=True)
        target = target.loc[mask].reset_index(drop=True)
        if target.empty:
            self.base_value_ = 0.0
            self.stumps_ = []
            return self

        correlation_rows: list[tuple[str, float]] = []
        target_array = target.to_numpy(dtype="float64")
        for column in self.feature_columns_:
            values = features[column].to_numpy(dtype="float64")
            if np.std(values) <= 1e-12:
                continue
            corr = np.corrcoef(values, target_array)[0, 1]
            if np.isfinite(corr):
                correlation_rows.append((column, abs(float(corr))))
        if correlation_rows:
            selected = [column for column, _ in sorted(correlation_rows, key=lambda item: item[1], reverse=True)[: self.max_feature_candidates]]
            features = features.loc[:, selected].copy()
            self.feature_columns_ = selected

        prediction = np.full(len(target), float(target.mean()), dtype="float64")
        self.base_value_ = float(target.mean())
        self.stumps_ = []
        residual = target.to_numpy(dtype="float64") - prediction
        for _ in range(self.n_estimators):
            stump, gain = self._fit_stump(features, residual)
            if stump is None or gain <= 1e-12:
                break
            update = stump.predict(features)
            prediction = prediction + self.learning_rate * update
            residual = target.to_numpy(dtype="float64") - prediction
            self.stumps_.append(stump)
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        if not self.feature_columns_:
            return np.zeros(len(frame), dtype="float64")
        features = pd.DataFrame(index=frame.index)
        for column in self.feature_columns_:
            features[column] = pd.to_numeric(frame[column], errors="coerce").fillna(self.feature_medians_.get(column, 0.0))
        prediction = np.full(len(features), self.base_value_, dtype="float64")
        for stump in self.stumps_:
            prediction = prediction + self.learning_rate * stump.predict(features)
        return prediction


class GradientBoostingRegressorModel(_GradientBoostingBase):
    name = "gradient_boosting_regressor"


class GradientBoostingRankerModel(_GradientBoostingBase):
    name = "gradient_boosting_ranker"

    def _build_target(self, labels: pd.Series, dates: pd.Series | None) -> pd.Series:
        return _rank_target(labels, dates)


def tune_boosting_model(
    model_name: str,
    *,
    n_trials: int,
    train_frame: pd.DataFrame,
    valid_frame: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
    seed: int = 42,
) -> tuple[dict[str, float | int], pd.DataFrame]:
    if model_name == GradientBoostingRankerModel.name:
        model_cls = GradientBoostingRankerModel
    elif model_name == GradientBoostingRegressorModel.name:
        model_cls = GradientBoostingRegressorModel
    else:
        raise KeyError(f"Unsupported boosting model for tuning: {model_name}")

    search_space = [
        {
            "n_estimators": int(n_estimators),
            "learning_rate": float(learning_rate),
            "max_bins": int(max_bins),
            "min_leaf_size": int(min_leaf_size),
        }
        for n_estimators, learning_rate, max_bins, min_leaf_size in product(
            (12, 24),
            (0.05, 0.1),
            (8, 12, 16),
            (12, 24),
        )
    ]
    rng = np.random.default_rng(seed)
    candidate_order = rng.permutation(len(search_space)).tolist()
    rows: list[dict[str, float | int]] = []
    best_params = search_space[0]
    best_score = -np.inf

    for candidate_idx in candidate_order[: max(1, min(n_trials, len(search_space)))]:
        params = search_space[candidate_idx]
        model = model_cls(**params, random_seed=seed)
        model.fit(train_frame, feature_columns, label_column)
        scored = valid_frame[["date", label_column]].copy()
        scored["prediction"] = model.predict(valid_frame)
        metric = _rank_ic_by_date(scored, "prediction", label_column)
        rows.append(
            {
                **params,
                "validation_rank_ic_mean": metric,
            }
        )
        if pd.notna(metric) and metric > best_score:
            best_score = metric
            best_params = params

    return best_params, pd.DataFrame(rows)
