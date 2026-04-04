from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import numpy as np
import pandas as pd


def _weighted_mean(values: np.ndarray, weights: np.ndarray | None) -> float:
    if weights is None:
        return float(values.mean()) if len(values) else 0.0
    denom = float(weights.sum())
    return float((values * weights).sum() / denom) if denom else 0.0


def _rank_ic_by_date(frame: pd.DataFrame, prediction_column: str, label_column: str) -> float:
    scores: list[float] = []
    for _, group in frame.groupby("date", sort=False):
        subset = group[[prediction_column, label_column]].dropna()
        if len(subset) < 2:
            continue
        corr = subset[prediction_column].rank(method="average").corr(subset[label_column].rank(method="average"))
        if pd.notna(corr):
            scores.append(float(corr))
    return float(np.mean(scores)) if scores else float("nan")


@dataclass(frozen=True)
class ModelArtifact:
    model_name: str
    params: dict[str, object]
    coefficients: list[float] | None = None
    intercept: float | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "model_name": self.model_name,
                "params": self.params,
                "coefficients": self.coefficients,
                "intercept": self.intercept,
            },
            sort_keys=True,
        )


class RandomScoreModel:
    name = "random_score"

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def fit(self, frame: pd.DataFrame, feature_columns: list[str], label_column: str) -> "RandomScoreModel":
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        scores = []
        for _, row in frame[["date", "security_id"]].iterrows():
            key = f"{self.seed}|{pd.Timestamp(row['date']).date()}|{row['security_id']}"
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
            scores.append(int(digest, 16) / float(16**16 - 1))
        return np.asarray(scores, dtype="float64")

    def to_artifact(self) -> ModelArtifact:
        return ModelArtifact(model_name=self.name, params={"seed": self.seed})


class HeuristicReversalScoreModel:
    name = "heuristic_reversal_score"

    def fit(self, frame: pd.DataFrame, feature_columns: list[str], label_column: str) -> "HeuristicReversalScoreModel":
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return pd.to_numeric(frame["rev_1"], errors="coerce").to_numpy(dtype="float64")

    def to_artifact(self) -> ModelArtifact:
        return ModelArtifact(model_name=self.name, params={})


class HeuristicMomentumScoreModel:
    name = "heuristic_momentum_score"

    def fit(self, frame: pd.DataFrame, feature_columns: list[str], label_column: str) -> "HeuristicMomentumScoreModel":
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return pd.to_numeric(frame["mom_21_ex1"], errors="coerce").to_numpy(dtype="float64")

    def to_artifact(self) -> ModelArtifact:
        return ModelArtifact(model_name=self.name, params={})


class HeuristicBlendScoreModel:
    name = "heuristic_blend_score"

    def fit(self, frame: pd.DataFrame, feature_columns: list[str], label_column: str) -> "HeuristicBlendScoreModel":
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        momentum = pd.to_numeric(frame["mom_21_ex1"], errors="coerce").fillna(0.0)
        value = pd.to_numeric(frame.get("book_to_price", 0.0), errors="coerce").fillna(0.0)
        reversal = pd.to_numeric(frame.get("rev_1", 0.0), errors="coerce").fillna(0.0)
        return (0.5 * momentum + 0.3 * value + 0.2 * reversal).to_numpy(dtype="float64")

    def to_artifact(self) -> ModelArtifact:
        return ModelArtifact(model_name=self.name, params={})


class RidgeRegressionModel:
    name = "ridge_regression"

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = float(alpha)
        self.feature_columns_: list[str] = []
        self.coefficients_: np.ndarray | None = None
        self.intercept_: float = 0.0

    def fit(
        self,
        frame: pd.DataFrame,
        feature_columns: list[str],
        label_column: str,
        sample_weight: np.ndarray | None = None,
    ) -> "RidgeRegressionModel":
        clean = frame[feature_columns + [label_column]].dropna()
        self.feature_columns_ = list(feature_columns)
        if clean.empty:
            self.coefficients_ = np.zeros(len(feature_columns), dtype="float64")
            self.intercept_ = 0.0
            return self

        X = clean[feature_columns].to_numpy(dtype="float64")
        y = clean[label_column].to_numpy(dtype="float64")
        weights = None if sample_weight is None else np.asarray(sample_weight[: len(clean)], dtype="float64")
        x_mean = np.asarray([_weighted_mean(X[:, idx], weights) for idx in range(X.shape[1])], dtype="float64")
        y_mean = _weighted_mean(y, weights)
        Xc = X - x_mean
        yc = y - y_mean
        if weights is not None:
            sqrt_w = np.sqrt(weights)[:, None]
            Xc = Xc * sqrt_w
            yc = yc * sqrt_w.ravel()
        penalty = np.eye(X.shape[1], dtype="float64") * self.alpha
        self.coefficients_ = np.linalg.solve(Xc.T @ Xc + penalty, Xc.T @ yc)
        self.intercept_ = float(y_mean - x_mean @ self.coefficients_)
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        X = frame[self.feature_columns_].fillna(0.0).to_numpy(dtype="float64")
        coefficients = self.coefficients_ if self.coefficients_ is not None else np.zeros(len(self.feature_columns_), dtype="float64")
        return X @ coefficients + self.intercept_

    def to_artifact(self) -> ModelArtifact:
        coefficients = None if self.coefficients_ is None else self.coefficients_.tolist()
        return ModelArtifact(model_name=self.name, params={"alpha": self.alpha, "feature_columns": self.feature_columns_}, coefficients=coefficients, intercept=self.intercept_)


class LassoRegressionModel:
    name = "lasso_regression"

    def __init__(self, alpha: float = 1.0, max_iter: int = 500, tolerance: float = 1e-6) -> None:
        self.alpha = float(alpha)
        self.max_iter = int(max_iter)
        self.tolerance = float(tolerance)
        self.feature_columns_: list[str] = []
        self.coefficients_: np.ndarray | None = None
        self.intercept_: float = 0.0

    def fit(self, frame: pd.DataFrame, feature_columns: list[str], label_column: str) -> "LassoRegressionModel":
        clean = frame[feature_columns + [label_column]].dropna()
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

        for _ in range(self.max_iter):
            previous = beta.copy()
            for idx in range(X.shape[1]):
                residual = yc - Xc @ beta + Xc[:, idx] * beta[idx]
                rho = float((Xc[:, idx] * residual).mean())
                z = float((Xc[:, idx] ** 2).mean())
                if z == 0:
                    beta[idx] = 0.0
                    continue
                beta[idx] = np.sign(rho) * max(abs(rho) - self.alpha, 0.0) / z
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
            params={"alpha": self.alpha, "feature_columns": self.feature_columns_, "max_iter": self.max_iter, "tolerance": self.tolerance},
            coefficients=coefficients,
            intercept=self.intercept_,
        )


def deserialize_model(artifact: ModelArtifact):
    if artifact.model_name == RandomScoreModel.name:
        return RandomScoreModel(seed=int(artifact.params.get("seed", 42)))
    if artifact.model_name == HeuristicReversalScoreModel.name:
        return HeuristicReversalScoreModel()
    if artifact.model_name == HeuristicMomentumScoreModel.name:
        return HeuristicMomentumScoreModel()
    if artifact.model_name == HeuristicBlendScoreModel.name:
        return HeuristicBlendScoreModel()
    if artifact.model_name == RidgeRegressionModel.name:
        model = RidgeRegressionModel(alpha=float(artifact.params.get("alpha", 1.0)))
        model.feature_columns_ = list(artifact.params.get("feature_columns", []))
        model.coefficients_ = None if artifact.coefficients is None else np.asarray(artifact.coefficients, dtype="float64")
        model.intercept_ = float(artifact.intercept or 0.0)
        return model
    if artifact.model_name == LassoRegressionModel.name:
        model = LassoRegressionModel(
            alpha=float(artifact.params.get("alpha", 1.0)),
            max_iter=int(artifact.params.get("max_iter", 500)),
            tolerance=float(artifact.params.get("tolerance", 1e-6)),
        )
        model.feature_columns_ = list(artifact.params.get("feature_columns", []))
        model.coefficients_ = None if artifact.coefficients is None else np.asarray(artifact.coefficients, dtype="float64")
        model.intercept_ = float(artifact.intercept or 0.0)
        return model
    raise KeyError(f"Unsupported model artifact: {artifact.model_name}")


def tune_linear_model_alpha(
    model_name: str,
    alpha_grid: list[float],
    train_frame: pd.DataFrame,
    valid_frame: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
) -> tuple[float, pd.DataFrame]:
    rows: list[dict[str, float]] = []
    best_alpha = alpha_grid[0]
    best_score = -np.inf
    for alpha in alpha_grid:
        if model_name == RidgeRegressionModel.name:
            model = RidgeRegressionModel(alpha=alpha)
        elif model_name == LassoRegressionModel.name:
            model = LassoRegressionModel(alpha=alpha)
        else:
            raise KeyError(f"Unsupported linear model for tuning: {model_name}")
        model.fit(train_frame, feature_columns, label_column)
        preds = model.predict(valid_frame)
        scored = valid_frame[["date", label_column]].copy()
        scored["prediction"] = preds
        metric = _rank_ic_by_date(scored, "prediction", label_column)
        rows.append({"alpha": alpha, "validation_rank_ic_mean": metric})
        if pd.notna(metric) and metric > best_score:
            best_score = metric
            best_alpha = alpha
    return best_alpha, pd.DataFrame(rows)
