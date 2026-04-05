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
    data_usage_trace: pd.DataFrame
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


def _date_bounds(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    if frame.empty:
        return None, None
    start = pd.Timestamp(frame["date"].min()).date().isoformat()
    end = pd.Timestamp(frame["date"].max()).date().isoformat()
    return start, end


def _build_data_usage_row(
    *,
    fold_id: str,
    model_name: str,
    protocol: str,
    preprocessing_fit_frame: pd.DataFrame,
    tuning_frame: pd.DataFrame,
    final_fit_frame: pd.DataFrame,
    predict_frame: pd.DataFrame,
) -> dict[str, object]:
    preprocessing_start, preprocessing_end = _date_bounds(preprocessing_fit_frame)
    tuning_start, tuning_end = _date_bounds(tuning_frame)
    final_fit_start, final_fit_end = _date_bounds(final_fit_frame)
    predict_start, predict_end = _date_bounds(predict_frame)
    return {
        "fold_id": fold_id,
        "model_name": model_name,
        "protocol": protocol,
        "preprocessing_fit_scope": "train_only",
        "preprocessing_fit_start": preprocessing_start,
        "preprocessing_fit_end": preprocessing_end,
        "preprocessing_fit_rows": int(len(preprocessing_fit_frame)),
        "tuning_scope": "valid_only" if not tuning_frame.empty else "not_used",
        "tuning_start": tuning_start,
        "tuning_end": tuning_end,
        "tuning_rows": int(len(tuning_frame)),
        "final_fit_scope": "train_plus_valid" if protocol == "train_valid_refit_then_test" else "train_only",
        "final_fit_start": final_fit_start,
        "final_fit_end": final_fit_end,
        "final_fit_rows": int(len(final_fit_frame)),
        "predict_scope": "test_only",
        "predict_start": predict_start,
        "predict_end": predict_end,
        "predict_rows": int(len(predict_frame)),
    }


def _assert_oof_purity(predictions: pd.DataFrame, folds: list[FoldDefinition]) -> None:
    duplicates = predictions.duplicated(subset=["date", "security_id", "model_name"], keep=False)
    if duplicates.any():
        raise ValueError("OOF predictions must be unique by date, security_id, and model_name.")

    fold_lookup = {fold.fold_id: set(fold.test_dates) for fold in folds}
    for row in predictions[["fold_id", "date"]].itertuples(index=False):
        expected_dates = fold_lookup.get(str(row.fold_id))
        if expected_dates is None:
            raise ValueError(f"OOF predictions reference unknown fold_id: {row.fold_id}")
        if pd.Timestamp(row.date) not in expected_dates:
            raise ValueError(f"OOF prediction for fold {row.fold_id} leaked outside its test window.")


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
    evaluation_protocol: str = "train_valid_refit_then_test",
) -> OOFRunResult:
    if evaluation_protocol not in {"train_valid_refit_then_test", "pure_train_only_then_test"}:
        raise ValueError(f"Unsupported evaluation protocol: {evaluation_protocol}")

    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    if "row_valid_flag" in frame.columns:
        frame = frame.loc[frame["row_valid_flag"].fillna(False)].copy()

    prediction_ts = pd.Timestamp(prediction_timestamp or pd.Timestamp.utcnow())
    prediction_ts = prediction_ts.tz_localize("UTC") if prediction_ts.tzinfo is None else prediction_ts.tz_convert("UTC")
    prediction_rows: list[pd.DataFrame] = []
    tuning_rows: list[dict[str, object]] = []
    data_usage_rows: list[dict[str, object]] = []

    for fold in folds:
        train_frame = frame.loc[frame["date"].isin(fold.train_dates)].copy()
        valid_frame = frame.loc[frame["date"].isin(fold.valid_dates)].copy()
        test_frame = frame.loc[frame["date"].isin(fold.test_dates)].copy()
        if test_frame.empty:
            continue

        preprocessing_fit_frame = train_frame.copy()
        if preprocessing_spec is not None:
            preprocessor = FoldSafePreprocessor(preprocessing_spec, feature_columns).fit(preprocessing_fit_frame)
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

            if evaluation_protocol == "train_valid_refit_then_test":
                fit_frame = pd.concat([train_frame, valid_frame], ignore_index=True)
            else:
                fit_frame = train_frame.copy()
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
            data_usage_rows.append(
                _build_data_usage_row(
                    fold_id=fold.fold_id,
                    model_name=spec.name,
                    protocol=evaluation_protocol,
                    preprocessing_fit_frame=preprocessing_fit_frame,
                    tuning_frame=valid_frame,
                    final_fit_frame=fit_frame,
                    predict_frame=test_frame,
                )
            )

    if prediction_rows:
        predictions = pd.concat(prediction_rows, ignore_index=True)
    else:
        predictions = pd.DataFrame(columns=["date", "security_id", "fold_id", "model_name", "raw_prediction", "rank_prediction", "bucket_prediction", "prediction_timestamp", "dataset_version"])

    predictions = validate_dataframe(predictions, "oof_predictions")
    _assert_oof_purity(predictions, folds)

    coverage_by_fold = _build_coverage_by_fold(predictions)
    tuning_diagnostics = pd.DataFrame(tuning_rows)
    data_usage_trace = pd.DataFrame(data_usage_rows)
    manifest = {
        "dataset_version": dataset_version,
        "prediction_timestamp": str(prediction_ts),
        "row_count": int(len(predictions)),
        "coverage_by_fold": coverage_by_fold.to_dict(orient="records"),
        "models": [spec.name for spec in model_specs],
        "oof_only_guard": True,
        "config_hash": config_hash,
        "evaluation_protocol": evaluation_protocol,
        "data_usage_trace_rows": int(len(data_usage_trace)),
        "oof_purity_checks": {
            "unique_prediction_rows": True,
            "test_only_predictions": True,
            "preprocessing_fit_scope": "train_only",
            "tuning_scope": "valid_only",
            "final_fit_scope": "train_plus_valid" if evaluation_protocol == "train_valid_refit_then_test" else "train_only",
        },
    }
    return OOFRunResult(
        predictions=predictions,
        coverage_by_fold=coverage_by_fold,
        tuning_diagnostics=tuning_diagnostics,
        data_usage_trace=data_usage_trace,
        manifest=manifest,
    )
