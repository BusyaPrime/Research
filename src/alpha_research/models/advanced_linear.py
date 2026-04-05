from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.models.baselines import ModelArtifact, RidgeRegressionModel


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


def _rank_target(labels: pd.Series, dates: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"date": pd.to_datetime(dates, errors="coerce").dt.normalize(), "label": pd.to_numeric(labels, errors="coerce")})
    ranked = frame.groupby("date", dropna=False)["label"].transform(lambda values: values.rank(method="average", pct=True) - 0.5)
    return pd.to_numeric(ranked, errors="coerce")


class ElasticNetRegressionModel:
    name = "elastic_net_regression"

    def __init__(self, alpha: float = 1.0, l1_ratio: float = 0.5, max_iter: int = 800, tolerance: float = 1e-6) -> None:
        self.alpha = float(alpha)
        self.l1_ratio = float(l1_ratio)
        self.max_iter = int(max_iter)
        self.tolerance = float(tolerance)
        self.feature_columns_: list[str] = []
        self.coefficients_: np.ndarray | None = None
        self.intercept_: float = 0.0

    def fit(self, frame: pd.DataFrame, feature_columns: list[str], label_column: str) -> ElasticNetRegressionModel:
        clean = frame[feature_columns + [label_column]].dropna().copy()
        self.feature_columns_ = list(feature_columns)
        if clean.empty:
            self.coefficients_ = np.zeros(len(feature_columns), dtype="float64")
            self.intercept_ = 0.0
            return self

        X = clean[feature_columns].to_numpy(dtype="float64")
        y = clean[label_column].to_numpy(dtype="float64")
        x_mean = X.mean(axis=0)
        y_mean = float(y.mean())
        Xc = X - x_mean
        yc = y - y_mean
        beta = np.zeros(X.shape[1], dtype="float64")

        l1_penalty = self.alpha * self.l1_ratio
        l2_penalty = self.alpha * (1.0 - self.l1_ratio)

        for _ in range(self.max_iter):
            previous = beta.copy()
            for idx in range(X.shape[1]):
                residual = yc - Xc @ beta + Xc[:, idx] * beta[idx]
                rho = float((Xc[:, idx] * residual).mean())
                z = float((Xc[:, idx] ** 2).mean()) + l2_penalty
                if z <= 1e-12:
                    beta[idx] = 0.0
                    continue
                beta[idx] = np.sign(rho) * max(abs(rho) - l1_penalty, 0.0) / z
            if np.max(np.abs(beta - previous)) < self.tolerance:
                break

        self.coefficients_ = beta
        self.intercept_ = float(y_mean - x_mean @ beta)
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        X = frame[self.feature_columns_].fillna(0.0).to_numpy(dtype="float64")
        coefficients = self.coefficients_ if self.coefficients_ is not None else np.zeros(len(self.feature_columns_), dtype="float64")
        return X @ coefficients + self.intercept_

    def to_artifact(self) -> ModelArtifact:
        coefficients = None if self.coefficients_ is None else self.coefficients_.tolist()
        return ModelArtifact(
            model_name=self.name,
            params={
                "alpha": self.alpha,
                "l1_ratio": self.l1_ratio,
                "feature_columns": self.feature_columns_,
                "max_iter": self.max_iter,
                "tolerance": self.tolerance,
            },
            coefficients=coefficients,
            intercept=self.intercept_,
        )


class RankRidgeRegressionModel:
    name = "rank_ridge_regression"

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = float(alpha)
        self.model_ = RidgeRegressionModel(alpha=alpha)

    def fit(self, frame: pd.DataFrame, feature_columns: list[str], label_column: str) -> RankRidgeRegressionModel:
        clean = frame.copy()
        clean["date"] = pd.to_datetime(clean["date"], errors="coerce").dt.normalize()
        clean["_rank_target"] = _rank_target(clean[label_column], clean["date"])
        self.model_.fit(clean, feature_columns, "_rank_target")
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.model_.predict(frame)

    def to_artifact(self) -> ModelArtifact:
        artifact = self.model_.to_artifact()
        return ModelArtifact(
            model_name=self.name,
            params={"alpha": self.alpha, "feature_columns": artifact.params.get("feature_columns", [])},
            coefficients=artifact.coefficients,
            intercept=artifact.intercept,
        )


@dataclass(frozen=True)
class TunedLinearModelResult:
    best_params: dict[str, float]
    diagnostics: pd.DataFrame


def tune_elastic_net_model(
    *,
    alpha_grid: list[float],
    l1_ratio_grid: list[float],
    train_frame: pd.DataFrame,
    valid_frame: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
) -> TunedLinearModelResult:
    rows: list[dict[str, float]] = []
    best_params = {"alpha": float(alpha_grid[0]), "l1_ratio": float(l1_ratio_grid[0])}
    best_score = -np.inf
    for alpha in alpha_grid:
        for l1_ratio in l1_ratio_grid:
            model = ElasticNetRegressionModel(alpha=float(alpha), l1_ratio=float(l1_ratio))
            model.fit(train_frame, feature_columns, label_column)
            scored = valid_frame[["date", label_column]].copy()
            scored["prediction"] = model.predict(valid_frame)
            metric = _rank_ic_by_date(scored, "prediction", label_column)
            rows.append({"alpha": float(alpha), "l1_ratio": float(l1_ratio), "validation_rank_ic_mean": metric})
            if pd.notna(metric) and metric > best_score:
                best_score = metric
                best_params = {"alpha": float(alpha), "l1_ratio": float(l1_ratio)}
    return TunedLinearModelResult(best_params=best_params, diagnostics=pd.DataFrame(rows))


def tune_rank_ridge_model(
    *,
    alpha_grid: list[float],
    train_frame: pd.DataFrame,
    valid_frame: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
) -> TunedLinearModelResult:
    rows: list[dict[str, float]] = []
    best_params = {"alpha": float(alpha_grid[0])}
    best_score = -np.inf
    for alpha in alpha_grid:
        model = RankRidgeRegressionModel(alpha=float(alpha))
        model.fit(train_frame, feature_columns, label_column)
        scored = valid_frame[["date", label_column]].copy()
        scored["prediction"] = model.predict(valid_frame)
        metric = _rank_ic_by_date(scored, "prediction", label_column)
        rows.append({"alpha": float(alpha), "validation_rank_ic_mean": metric})
        if pd.notna(metric) and metric > best_score:
            best_score = metric
            best_params = {"alpha": float(alpha)}
    return TunedLinearModelResult(best_params=best_params, diagnostics=pd.DataFrame(rows))
