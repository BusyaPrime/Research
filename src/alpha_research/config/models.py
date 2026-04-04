from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TrackingConfig(FrozenModel):
    backend: str
    tracking_uri: str
    log_git_commit: bool
    log_dataset_manifest: bool
    log_config_snapshot: bool
    log_artifacts: bool


class StorageConfig(FrozenModel):
    raw_format: str
    normalized_format: str
    compression: str
    schema_versioning: bool


class ProjectConfig(FrozenModel):
    project_name: str
    project_code: str
    language: str
    market: str
    frequency: str
    timezone: str
    decision_timestamp_policy: str
    execution_timestamp_policy: str
    base_currency: str
    default_random_seed: int
    tracking: TrackingConfig
    storage: StorageConfig
    global_invariants: list[str]


class ProviderConfig(FrozenModel):
    name: str | None = None
    required_events: list[str] | None = None
    priority: list[str] | None = None
    fields_required: list[str] | None = None
    save_raw_payload: bool | None = None
    save_request_manifest: bool | None = None
    available_from_policy: str | None = None
    restatement_tracking: bool | None = None
    required_fields: list[str] | None = None
    ticker_is_not_primary_key: bool | None = None


class DataSourcesConfig(FrozenModel):
    market_provider: ProviderConfig
    fundamentals_provider: ProviderConfig
    corporate_actions_provider: ProviderConfig
    security_master_provider: ProviderConfig


class CalendarConfig(FrozenModel):
    exchange_calendar: str
    use_half_days: bool
    functions_required: list[str]
    forbid_calendar_day_shift_for_labels: bool


class UniverseBucketsConfig(FrozenModel):
    high: str
    medium: str
    low: str


class UniverseConfig(FrozenModel):
    eligible_security_types: list[str]
    excluded_security_types: list[str]
    allowed_exchanges: list[str]
    min_price_usd: float
    min_adv20_usd: float
    optional_min_market_cap_usd: float | None = None
    min_feature_coverage_ratio: float
    min_data_quality_score: float
    liquidity_buckets: UniverseBucketsConfig
    membership_refresh: str
    log_exclusion_reasons: bool


class LabelOverlapPolicy(FrozenModel):
    allow_overlap: bool
    purge_days: int
    embargo_days: int


class LabelsConfig(FrozenModel):
    primary_label: str
    secondary_labels: list[str]
    execution_reference: str
    horizons_trading_days: list[int]
    families: list[str]
    overlap_policy: LabelOverlapPolicy
    benchmark: str
    residualization_controls: list[str]


class FeaturesWinsorPolicy(FrozenModel):
    lower_pct: float
    upper_pct: float


class FeaturesConfig(FrozenModel):
    feature_registry_version: str
    families_enabled: list[str]
    default_cross_section_normalization: str
    default_missing_policy: str
    default_winsor_policy: FeaturesWinsorPolicy
    default_neutralization: str
    fundamental_staleness_thresholds_days: list[int]
    interaction_cap: int


class PreprocessingOption(FrozenModel):
    name: str
    enabled: bool
    lower_pct: float | None = None
    upper_pct: float | None = None


class PreprocessingConfig(FrozenModel):
    winsorization_options: list[PreprocessingOption]
    scalers: list[str]
    neutralizers: list[str]
    missing_policies: list[str]
    fold_safe_fit_required: bool


class TuningConfig(FrozenModel):
    engine: str
    n_trials_default: int
    early_stopping_enabled: bool
    optimize_metric: str


class SampleWeightsConfig(FrozenModel):
    enabled: bool
    policy: str


class ModelsConfig(FrozenModel):
    baseline_models: list[str]
    advanced_models: list[str]
    tuning: TuningConfig
    sample_weights: SampleWeightsConfig


class SplitsConfig(FrozenModel):
    train_years: int
    validation_months: int
    test_months: int
    step_months: int
    expanding_train: bool
    purge_days: int
    embargo_days: int
    nested_validation: bool
    min_train_observations: int
    persist_fold_artifacts: bool


class PortfolioConfig(FrozenModel):
    mode: str
    gross_exposure: float
    net_target: float
    long_quantile: float
    short_quantile: float
    rebalance_frequency: str
    holding_period_days: int
    overlap_sleeves: bool
    max_weight_per_name: float
    max_sector_net_exposure: float
    max_sector_gross_exposure: float
    max_turnover_per_rebalance: float
    beta_neutralize: bool
    sector_neutralize: bool
    max_participation_pct_adv: float
    reject_unborrowable_shorts: bool


class PriceAdvBucket(FrozenModel):
    price_min: float
    price_max: float
    adv_bucket: str
    half_spread_bps: float


class SpreadProxyConfig(FrozenModel):
    method: str
    buckets: list[PriceAdvBucket]


class ParametricCostModel(FrozenModel):
    method: str
    formula: str
    base_bps: float | None = None
    k1: float | None = None
    k2: float | None = None


class BorrowConfig(FrozenModel):
    low_borrow_bps_daily: float
    medium_borrow_bps_daily: float
    high_borrow_bps_daily: float
    hard_to_borrow_policy: str


class CostsConfig(FrozenModel):
    commission_bps: float
    spread_proxy: SpreadProxyConfig
    slippage_proxy: ParametricCostModel
    impact_proxy: ParametricCostModel
    borrow: BorrowConfig
    scenarios: list[str]


class CapacityParticipationLimits(FrozenModel):
    relaxed: float
    base: float
    strict: float
    ultra_strict: float


class CapacityConfig(FrozenModel):
    aum_ladder_usd: list[float]
    participation_limits: CapacityParticipationLimits
    report_metrics: list[str]


class ReportingConfig(FrozenModel):
    formats: list[str]
    include_sections: list[str]
    mandatory_figures: list[str]


class RuntimeIngestConfig(FrozenModel):
    provider_mode: Literal["synthetic_vendor_stub"]
    default_start_date: str
    default_end_date: str
    default_n_securities: int
    page_size: int


class RuntimeConfig(FrozenModel):
    ingest: RuntimeIngestConfig


class ExperimentPreprocessingConfig(FrozenModel):
    winsor: str
    scaler: str
    neutralizer: str


class ExperimentModelConfig(FrozenModel):
    name: str
    alpha_grid: list[float] | None = None
    n_trials: int | None = None
    use_best_previous_params: bool | None = None


class ExperimentPortfolioConfig(FrozenModel):
    mode: str


class ExperimentConfig(FrozenModel):
    experiment_name: str
    dataset_version: str
    label: str
    featureset: str
    preprocessing: ExperimentPreprocessingConfig
    model: ExperimentModelConfig
    portfolio: ExperimentPortfolioConfig
    cost_scenario: Literal["optimistic", "base", "stressed", "severely_stressed"]


class ResolvedConfigBundle(FrozenModel):
    project: ProjectConfig
    data_sources: DataSourcesConfig
    calendar: CalendarConfig
    universe: UniverseConfig
    labels: LabelsConfig
    features: FeaturesConfig
    preprocessing: PreprocessingConfig
    models: ModelsConfig
    splits: SplitsConfig
    portfolio: PortfolioConfig
    costs: CostsConfig
    capacity: CapacityConfig
    reporting: ReportingConfig
    runtime: RuntimeConfig
    experiments: dict[str, ExperimentConfig]
