from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class ModelMetadata:
    name: str
    tier: str
    family: str
    objective: str
    supports_grouped_ranking: bool
    serialization_mode: str
    missing_value_behavior: str
    inference_deterministic: bool
    tuning_strategy: str


MODEL_REGISTRY: dict[str, ModelMetadata] = {
    "random_score": ModelMetadata(
        name="random_score",
        tier="tier_0",
        family="sanity_baseline",
        objective="sanity_noise_reference",
        supports_grouped_ranking=False,
        serialization_mode="seed_only",
        missing_value_behavior="ignore",
        inference_deterministic=True,
        tuning_strategy="none",
    ),
    "heuristic_reversal_score": ModelMetadata(
        name="heuristic_reversal_score",
        tier="tier_0",
        family="heuristic_signal",
        objective="reversal_score",
        supports_grouped_ranking=False,
        serialization_mode="stateless",
        missing_value_behavior="feature_default_zero",
        inference_deterministic=True,
        tuning_strategy="none",
    ),
    "heuristic_momentum_score": ModelMetadata(
        name="heuristic_momentum_score",
        tier="tier_0",
        family="heuristic_signal",
        objective="momentum_score",
        supports_grouped_ranking=False,
        serialization_mode="stateless",
        missing_value_behavior="feature_default_zero",
        inference_deterministic=True,
        tuning_strategy="none",
    ),
    "heuristic_blend_score": ModelMetadata(
        name="heuristic_blend_score",
        tier="tier_0",
        family="heuristic_signal",
        objective="blended_cross_section_score",
        supports_grouped_ranking=False,
        serialization_mode="stateless",
        missing_value_behavior="feature_default_zero",
        inference_deterministic=True,
        tuning_strategy="none",
    ),
    "ridge_regression": ModelMetadata(
        name="ridge_regression",
        tier="tier_0",
        family="linear_reference",
        objective="squared_error",
        supports_grouped_ranking=False,
        serialization_mode="coefficients_and_intercept",
        missing_value_behavior="preprocessed_input_required",
        inference_deterministic=True,
        tuning_strategy="alpha_grid",
    ),
    "lasso_regression": ModelMetadata(
        name="lasso_regression",
        tier="tier_0",
        family="linear_reference",
        objective="squared_error_sparse",
        supports_grouped_ranking=False,
        serialization_mode="coefficients_and_intercept",
        missing_value_behavior="preprocessed_input_required",
        inference_deterministic=True,
        tuning_strategy="alpha_grid",
    ),
    "elastic_net_regression": ModelMetadata(
        name="elastic_net_regression",
        tier="tier_1",
        family="serious_linear",
        objective="squared_error_elastic_net",
        supports_grouped_ranking=False,
        serialization_mode="coefficients_and_intercept",
        missing_value_behavior="preprocessed_input_required",
        inference_deterministic=True,
        tuning_strategy="alpha_times_l1_ratio_grid",
    ),
    "rank_ridge_regression": ModelMetadata(
        name="rank_ridge_regression",
        tier="tier_1",
        family="grouped_ranking_linear",
        objective="date_group_rank_target",
        supports_grouped_ranking=True,
        serialization_mode="coefficients_and_intercept",
        missing_value_behavior="preprocessed_input_required",
        inference_deterministic=True,
        tuning_strategy="alpha_grid",
    ),
    "gradient_boosting_regressor": ModelMetadata(
        name="gradient_boosting_regressor",
        tier="tier_1",
        family="tree_ensemble",
        objective="squared_error_boosting",
        supports_grouped_ranking=False,
        serialization_mode="runtime_manifest_and_best_params",
        missing_value_behavior="median_fill_inside_model",
        inference_deterministic=True,
        tuning_strategy="structured_random_search",
    ),
    "gradient_boosting_ranker": ModelMetadata(
        name="gradient_boosting_ranker",
        tier="tier_1",
        family="tree_ensemble",
        objective="date_group_rank_target_boosting",
        supports_grouped_ranking=True,
        serialization_mode="runtime_manifest_and_best_params",
        missing_value_behavior="median_fill_inside_model",
        inference_deterministic=True,
        tuning_strategy="structured_random_search",
    ),
}


def get_model_metadata(model_name: str) -> ModelMetadata:
    if model_name not in MODEL_REGISTRY:
        raise KeyError(f"Unknown model registry entry: {model_name}")
    return MODEL_REGISTRY[model_name]


def build_model_registry_frame() -> pd.DataFrame:
    rows = [asdict(metadata) for metadata in MODEL_REGISTRY.values()]
    return pd.DataFrame(rows).sort_values(["tier", "name"], kind="stable").reset_index(drop=True)


def model_names_by_tier(tier: str) -> list[str]:
    return [metadata.name for metadata in MODEL_REGISTRY.values() if metadata.tier == tier]
