from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from alpha_research.data.schemas import validate_dataframe
from alpha_research.models.baselines import (
    HeuristicBlendScoreModel,
    HeuristicMomentumScoreModel,
    HeuristicReversalScoreModel,
    LassoRegressionModel,
    RandomScoreModel,
    RidgeRegressionModel,
    tune_linear_model_alpha,
)
from alpha_research.models.boosting import (
    GradientBoostingRankerModel,
    GradientBoostingRegressorModel,
    tune_boosting_model,
)
from alpha_research.preprocessing.transforms import FoldSafePreprocessor, PreprocessingSpec
from alpha_research.splits.engine import FoldDefinition


@dataclass(frozen=True)
class ModelRunSpec:
    name: str
    alpha_grid: tuple[float, ...] = field(default_factory=tuple)
    n_trials: int | None = None
    params: dict[str, object] = field(default_factory=dict)
    seed: int = 42


@dataclass(frozen=True)
class OOFRunResult:
    predictions: pd.DataFrame
    coverage_by_fold: pd.DataFrame
    tuning_diagnostics: pd.DataFrame
    manifest: dict[str, object]


def _instantiate_model(spec: ModelRunSpec):
    if spec.name == "random_score":
        return RandomScoreModel(seed=spec.seed)
    if spec.name == "heuristic_reversal_score":
        return HeuristicReversalScoreModel()
    if spec.name == "heuristic_momentum_score":
        return HeuristicMomentumScoreModel()
    if spec.name == "heuristic_blend_score":
        return HeuristicBlendScoreModel()
    if spec.name == "ridge_regression":
        return RidgeRegressionModel(alpha=float(spec.alpha_grid[0] if spec.alpha_grid else 1.0))
    if spec.name == "lasso_regression":
        return LassoRegressionModel(alpha=float(spec.alpha_grid[0] if spec.alpha_grid else 1.0))
    if spec.name == "gradient_boosting_regressor":
        return GradientBoostingRegressorModel(
            n_estimators=int(spec.params.get("n_estimators", 24)),
            learning_rate=float(spec.params.get("learning_rate", 0.05)),
            max_bins=int(spec.params.get("max_bins", 12)),
            min_leaf_size=int(spec.params.get("min_leaf_size", 16)),
            random_seed=spec.seed,
        )
    if spec.name == "gradient_boosting_ranker":
        return GradientBoostingRankerModel(
            n_estimators=int(spec.params.get("n_estimators", 24)),
            learning_rate=float(spec.params.get("learning_rate", 0.05)),
            max_bins=int(spec.params.get("max_bins", 12)),
            min_leaf_size=int(spec.params.get("min_leaf_size", 16)),
            random_seed=spec.seed,
        )
    raise KeyError(f"Unsupported model spec: {spec.name}")


def _rank_and_bucket(predictions: pd.DataFrame) -> pd.DataFrame:
    output = predictions.copy()
    output["rank_prediction"] = output.groupby("date", dropna=False)["raw_prediction"].transform(lambda values: values.rank(method="average", pct=True))
    output["bucket_prediction"] = pd.Series(pd.NA, index=output.index, dtype="Int32")
    valid = output["rank_prediction"].notna()
    output.loc[valid, "bucket_prediction"] = np.minimum(np.floor(output.loc[valid, "rank_prediction"] * 10).astype(int), 9).astype("Int32")
    return output


def _build_coverage_by_fold(predictions: pd.DataFrame) -> pd.DataFrame:
    return (
        predictions.groupby(["fold_id", "model_name"], dropna=False)
        .agg(row_count=("security_id", "size"), unique_dates=("date", "nunique"))
        .reset_index()
        .sort_values(["fold_id", "model_name"], kind="stable")
        .reset_index(drop=True)
    )


def generate_oof_predictions(
    panel: pd.DataFrame,
    folds: list[FoldDefinition],
    *,
    model_specs: list[ModelRunSpec],
    feature_columns: list[str],
    label_column: str,
    dataset_version: str,
    config_hash: str = "unknown",
    prediction_timestamp: str | pd.Timestamp | None = None,
    preprocessing_spec: PreprocessingSpec | None = None,
) -> OOFRunResult:
    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    if "row_valid_flag" in frame.columns:
        frame = frame.loc[frame["row_valid_flag"].fillna(False)].copy()

    prediction_ts = pd.Timestamp(prediction_timestamp or pd.Timestamp.utcnow())
    prediction_ts = prediction_ts.tz_localize("UTC") if prediction_ts.tzinfo is None else prediction_ts.tz_convert("UTC")
    prediction_rows: list[pd.DataFrame] = []
    tuning_rows: list[dict[str, object]] = []

    for fold in folds:
        train_frame = frame.loc[frame["date"].isin(fold.train_dates)].copy()
        valid_frame = frame.loc[frame["date"].isin(fold.valid_dates)].copy()
        test_frame = frame.loc[frame["date"].isin(fold.test_dates)].copy()
        if test_frame.empty:
            continue

        if preprocessing_spec is not None:
            preprocessor = FoldSafePreprocessor(preprocessing_spec, feature_columns).fit(train_frame)
            train_frame = preprocessor.transform(train_frame)
            valid_frame = preprocessor.transform(valid_frame)
            test_frame = preprocessor.transform(test_frame)

        for spec in model_specs:
            tuned_alpha = None
            model = _instantiate_model(spec)
            if spec.name in {"ridge_regression", "lasso_regression"} and spec.alpha_grid:
                tuned_alpha, tuning_frame = tune_linear_model_alpha(spec.name, list(spec.alpha_grid), train_frame, valid_frame, feature_columns, label_column)
                tuning_frame["fold_id"] = fold.fold_id
                tuning_frame["model_name"] = spec.name
                tuning_rows.extend(tuning_frame.to_dict(orient="records"))
                model = RidgeRegressionModel(alpha=tuned_alpha) if spec.name == "ridge_regression" else LassoRegressionModel(alpha=tuned_alpha)
            elif spec.name in {"gradient_boosting_regressor", "gradient_boosting_ranker"}:
                tuned_params = dict(spec.params)
                if not tuned_params:
                    tuned_params, tuning_frame = tune_boosting_model(
                        spec.name,
                        n_trials=int(spec.n_trials or 16),
                        train_frame=train_frame,
                        valid_frame=valid_frame,
                        feature_columns=feature_columns,
                        label_column=label_column,
                        seed=spec.seed,
                    )
                    tuning_frame["fold_id"] = fold.fold_id
                    tuning_frame["model_name"] = spec.name
                    tuning_rows.extend(tuning_frame.to_dict(orient="records"))
                tuned_spec = ModelRunSpec(name=spec.name, params=tuned_params, seed=spec.seed, n_trials=spec.n_trials)
                model = _instantiate_model(tuned_spec)

            fit_frame = pd.concat([train_frame, valid_frame], ignore_index=True)
            model.fit(fit_frame, feature_columns, label_column)
            preds = pd.DataFrame(
                {
                    "date": test_frame["date"].to_numpy(),
                    "security_id": test_frame["security_id"].astype("string").to_numpy(),
                    "fold_id": fold.fold_id,
                    "model_name": spec.name,
                    "raw_prediction": model.predict(test_frame),
                    "prediction_timestamp": prediction_ts,
                    "dataset_version": dataset_version,
                    "config_hash": config_hash,
                }
            )
            preds = _rank_and_bucket(preds)
            prediction_rows.append(preds)

    if prediction_rows:
        predictions = pd.concat(prediction_rows, ignore_index=True)
    else:
        predictions = pd.DataFrame(columns=["date", "security_id", "fold_id", "model_name", "raw_prediction", "rank_prediction", "bucket_prediction", "prediction_timestamp", "dataset_version"])

    predictions = validate_dataframe(predictions, "oof_predictions")
    duplicates = predictions.duplicated(subset=["date", "security_id", "model_name"], keep=False)
    if duplicates.any():
        raise ValueError("OOF predictions must be unique by date, security_id, and model_name.")

    coverage_by_fold = _build_coverage_by_fold(predictions)
    tuning_diagnostics = pd.DataFrame(tuning_rows)
    manifest = {
        "dataset_version": dataset_version,
        "prediction_timestamp": str(prediction_ts),
        "row_count": int(len(predictions)),
        "coverage_by_fold": coverage_by_fold.to_dict(orient="records"),
        "models": [spec.name for spec in model_specs],
        "oof_only_guard": True,
        "config_hash": config_hash,
    }
    return OOFRunResult(predictions=predictions, coverage_by_fold=coverage_by_fold, tuning_diagnostics=tuning_diagnostics, manifest=manifest)
