from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from alpha_research.common.io import write_json
from alpha_research.config.models import SplitsConfig
from alpha_research.time.calendar import ExchangeCalendarAdapter


@dataclass(frozen=True)
class FoldDefinition:
    fold_id: str
    train_dates: tuple[pd.Timestamp, ...]
    valid_dates: tuple[pd.Timestamp, ...]
    test_dates: tuple[pd.Timestamp, ...]
    train_start: pd.Timestamp | None
    train_end: pd.Timestamp | None
    valid_start: pd.Timestamp | None
    valid_end: pd.Timestamp | None
    test_start: pd.Timestamp | None
    test_end: pd.Timestamp | None
    primary_horizon_days: int
    purge_days_applied: int
    embargo_days_applied: int
    expanding_train: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["train_dates"] = [str(date.date()) for date in self.train_dates]
        payload["valid_dates"] = [str(date.date()) for date in self.valid_dates]
        payload["test_dates"] = [str(date.date()) for date in self.test_dates]
        for key in ("train_start", "train_end", "valid_start", "valid_end", "test_start", "test_end"):
            value = payload[key]
            payload[key] = None if value is None else str(value.date())
        return payload


@dataclass(frozen=True)
class SplitArtifacts:
    folds: list[FoldDefinition]
    metadata: pd.DataFrame
    timeline_plot: str
    protocol: "ValidationProtocol"
    role_matrix: pd.DataFrame


@dataclass(frozen=True)
class ValidationProtocol:
    folds: list[FoldDefinition]
    primary_horizon_days: int
    min_train_observations: int
    allow_small_fixture_splits: bool

    def assert_no_overlap(self) -> None:
        for fold in self.folds:
            overlap = (
                set(fold.train_dates) & set(fold.valid_dates)
                | set(fold.train_dates) & set(fold.test_dates)
                | set(fold.valid_dates) & set(fold.test_dates)
            )
            if overlap:
                raise ValueError(f"{fold.fold_id}: обнаружен overlap между ролями дат: {sorted(overlap)}")

    def assert_min_sample_sizes(self) -> None:
        for fold in self.folds:
            observed_rows = len(fold.train_dates) + len(fold.valid_dates) + len(fold.test_dates)
            if observed_rows < self.min_train_observations and not self.allow_small_fixture_splits:
                raise ValueError(
                    f"{fold.fold_id}: недостаточно наблюдений для strict split policy "
                    f"({observed_rows} < {self.min_train_observations})."
                )

    def assert_purge_validity(self, calendar: ExchangeCalendarAdapter) -> None:
        for fold in self.folds:
            if fold.valid_start is None:
                continue
            for train_date in fold.train_dates:
                label_window = calendar.label_window(train_date, self.primary_horizon_days)
                if label_window.end_date >= fold.valid_start:
                    raise ValueError(
                        f"{fold.fold_id}: purge invalid, train date {train_date.date()} пересекает validation окно."
                    )
            if fold.test_start is None:
                continue
            for valid_date in fold.valid_dates:
                label_window = calendar.label_window(valid_date, self.primary_horizon_days)
                if label_window.end_date >= fold.test_start:
                    raise ValueError(
                        f"{fold.fold_id}: purge invalid, valid date {valid_date.date()} пересекает test окно."
                    )

    def assert_embargo_validity(self, calendar: ExchangeCalendarAdapter) -> None:
        for fold in self.folds:
            if fold.valid_start is not None and fold.train_dates:
                distance = calendar.trading_day_distance(fold.train_dates[-1], fold.valid_start)
                if distance <= fold.embargo_days_applied:
                    raise ValueError(
                        f"{fold.fold_id}: embargo invalid между train и valid ({distance} <= {fold.embargo_days_applied})."
                    )
            if fold.test_start is not None and fold.valid_dates:
                distance = calendar.trading_day_distance(fold.valid_dates[-1], fold.test_start)
                if distance <= fold.embargo_days_applied:
                    raise ValueError(
                        f"{fold.fold_id}: embargo invalid между valid и test ({distance} <= {fold.embargo_days_applied})."
                    )

    def assert_calendar_contiguity(self) -> None:
        for fold in self.folds:
            for role_name, role_dates in (
                ("train", fold.train_dates),
                ("valid", fold.valid_dates),
                ("test", fold.test_dates),
            ):
                if tuple(sorted(role_dates)) != role_dates:
                    raise ValueError(f"{fold.fold_id}: даты в роли {role_name} потеряли монотонность.")

    def assert_label_window_separation(self, calendar: ExchangeCalendarAdapter) -> None:
        for fold in self.folds:
            for train_date in fold.train_dates:
                train_window = calendar.label_window(train_date, self.primary_horizon_days)
                for boundary in (fold.valid_start, fold.test_start):
                    if boundary is not None and train_window.end_date >= boundary:
                        raise ValueError(
                            f"{fold.fold_id}: label window для {train_date.date()} заходит за boundary {boundary.date()}."
                        )

    def assert_all(self, calendar: ExchangeCalendarAdapter) -> None:
        self.assert_no_overlap()
        self.assert_min_sample_sizes()
        self.assert_purge_validity(calendar)
        self.assert_embargo_validity(calendar)
        self.assert_calendar_contiguity()
        self.assert_label_window_separation(calendar)

    def to_dict(self) -> dict[str, object]:
        return {
            "fold_count": len(self.folds),
            "primary_horizon_days": self.primary_horizon_days,
            "min_train_observations": self.min_train_observations,
            "allow_small_fixture_splits": self.allow_small_fixture_splits,
            "checks": {
                "no_overlap": True,
                "min_sample_sizes": True,
                "purge_validity": True,
                "embargo_validity": True,
                "calendar_contiguity": True,
                "label_window_separation": True,
            },
        }


def _unique_valid_dates(panel: pd.DataFrame) -> pd.DatetimeIndex:
    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    if "row_valid_flag" in frame.columns:
        frame = frame.loc[frame["row_valid_flag"].fillna(False)]
    dates = pd.DatetimeIndex(sorted(frame["date"].dropna().unique()))
    if dates.empty:
        raise ValueError("No valid dates available for split generation.")
    return dates


def _months_from_dates(dates: pd.DatetimeIndex) -> pd.PeriodIndex:
    return pd.PeriodIndex(sorted(dates.to_period("M").unique()))


def _select_dates_for_months(dates: pd.DatetimeIndex, months: pd.PeriodIndex) -> tuple[pd.Timestamp, ...]:
    month_set = set(months.astype(str).tolist())
    return tuple(date for date in dates if date.to_period("M").strftime("%Y-%m") in month_set)


def _purge_dates(
    dates: tuple[pd.Timestamp, ...],
    boundary_start: pd.Timestamp | None,
    calendar: ExchangeCalendarAdapter,
    primary_horizon_days: int,
) -> tuple[pd.Timestamp, ...]:
    if boundary_start is None:
        return dates
    kept: list[pd.Timestamp] = []
    for date in dates:
        label_window = calendar.label_window(date, primary_horizon_days)
        if label_window.end_date < boundary_start:
            kept.append(date)
    return tuple(kept)


def _embargo_dates(
    dates: tuple[pd.Timestamp, ...],
    boundary_start: pd.Timestamp | None,
    calendar: ExchangeCalendarAdapter,
    embargo_days: int,
) -> tuple[pd.Timestamp, ...]:
    if boundary_start is None or embargo_days <= 0:
        return dates
    kept: list[pd.Timestamp] = []
    for date in dates:
        distance = calendar.trading_day_distance(date, boundary_start)
        if distance > embargo_days:
            kept.append(date)
    return tuple(kept)


def _date_range(values: tuple[pd.Timestamp, ...]) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if not values:
        return None, None
    return values[0], values[-1]


def _fold_metadata_frame(folds: list[FoldDefinition]) -> pd.DataFrame:
    rows = []
    for fold in folds:
        rows.append(
            {
                "fold_id": fold.fold_id,
                "train_rows": len(fold.train_dates),
                "valid_rows": len(fold.valid_dates),
                "test_rows": len(fold.test_dates),
                "train_start": fold.train_start,
                "train_end": fold.train_end,
                "valid_start": fold.valid_start,
                "valid_end": fold.valid_end,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
                "purge_days_applied": fold.purge_days_applied,
                "embargo_days_applied": fold.embargo_days_applied,
                "expanding_train": fold.expanding_train,
            }
        )
    return pd.DataFrame(rows)


def build_validation_protocol_report(folds: list[FoldDefinition]) -> str:
    lines = ["fold_timeline"]
    for fold in folds:
        lines.append(
            f"{fold.fold_id}: train[{fold.train_start} -> {fold.train_end}] "
            f"valid[{fold.valid_start} -> {fold.valid_end}] "
            f"test[{fold.test_start} -> {fold.test_end}]"
        )
    return "\n".join(lines)


def persist_fold_metadata(artifacts: SplitArtifacts, path: Path) -> Path:
    payload = {
        "timeline_plot": artifacts.timeline_plot,
        "protocol": artifacts.protocol.to_dict(),
        "folds": [fold.to_dict() for fold in artifacts.folds],
        "metadata": artifacts.metadata.to_dict(orient="records"),
        "role_matrix": artifacts.role_matrix.to_dict(orient="records"),
    }
    return write_json(payload, path)


def _build_role_matrix(folds: list[FoldDefinition]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fold in folds:
        for role_name, role_dates in (
            ("train", fold.train_dates),
            ("valid", fold.valid_dates),
            ("test", fold.test_dates),
        ):
            for date in role_dates:
                rows.append({"fold_id": fold.fold_id, "date": date, "role": role_name})
    if not rows:
        return pd.DataFrame(columns=["fold_id", "date", "role"])
    return pd.DataFrame(rows).sort_values(["date", "fold_id", "role"], kind="stable").reset_index(drop=True)


def generate_walk_forward_splits(
    panel: pd.DataFrame,
    split_config: SplitsConfig,
    calendar: ExchangeCalendarAdapter,
    *,
    primary_horizon_days: int,
) -> SplitArtifacts:
    dates = _unique_valid_dates(panel)
    months = _months_from_dates(dates)

    train_months = split_config.train_years * 12
    min_months_required = train_months + split_config.validation_months + split_config.test_months
    if len(months) < min_months_required:
        raise ValueError("Insufficient monthly history for requested walk-forward split configuration.")

    folds: list[FoldDefinition] = []
    cursor = train_months
    step = max(split_config.step_months, 1)
    while cursor + split_config.validation_months + split_config.test_months <= len(months):
        train_start_idx = 0 if split_config.expanding_train else cursor - train_months
        train_month_slice = months[train_start_idx:cursor]
        valid_month_slice = months[cursor : cursor + split_config.validation_months]
        test_month_slice = months[
            cursor + split_config.validation_months : cursor + split_config.validation_months + split_config.test_months
        ]

        train_dates = _select_dates_for_months(dates, train_month_slice)
        valid_dates = _select_dates_for_months(dates, valid_month_slice)
        test_dates = _select_dates_for_months(dates, test_month_slice)

        valid_start = valid_dates[0] if valid_dates else None
        test_start = test_dates[0] if test_dates else None
        train_dates = _purge_dates(train_dates, valid_start, calendar, primary_horizon_days)
        valid_dates = _purge_dates(valid_dates, test_start, calendar, primary_horizon_days)
        train_dates = _embargo_dates(train_dates, valid_start, calendar, split_config.embargo_days)
        valid_dates = _embargo_dates(valid_dates, test_start, calendar, split_config.embargo_days)

        train_start, train_end = _date_range(train_dates)
        valid_start, valid_end = _date_range(valid_dates)
        test_start, test_end = _date_range(test_dates)

        overlap = set(train_dates) & set(valid_dates) | set(train_dates) & set(test_dates) | set(valid_dates) & set(test_dates)
        if overlap:
            raise ValueError(f"Split generation produced overlapping dates: {sorted(overlap)}")

        observed_rows = len(train_dates) + len(valid_dates) + len(test_dates)
        if observed_rows < split_config.min_train_observations and not split_config.allow_small_fixture_splits:
            raise ValueError(
                "Strict split policy отвергла fold из-за слишком маленькой выборки "
                f"({observed_rows} < {split_config.min_train_observations})."
            )

        fold = FoldDefinition(
            fold_id=f"fold_{len(folds):03d}",
            train_dates=train_dates,
            valid_dates=valid_dates,
            test_dates=test_dates,
            train_start=train_start,
            train_end=train_end,
            valid_start=valid_start,
            valid_end=valid_end,
            test_start=test_start,
            test_end=test_end,
            primary_horizon_days=primary_horizon_days,
            purge_days_applied=max(primary_horizon_days, split_config.purge_days),
            embargo_days_applied=split_config.embargo_days,
            expanding_train=split_config.expanding_train,
        )
        folds.append(fold)
        cursor += step

    if not folds:
        raise ValueError("Split generation did not produce any folds for the requested configuration.")

    protocol = ValidationProtocol(
        folds=folds,
        primary_horizon_days=primary_horizon_days,
        min_train_observations=split_config.min_train_observations,
        allow_small_fixture_splits=split_config.allow_small_fixture_splits,
    )
    protocol.assert_all(calendar)

    metadata = _fold_metadata_frame(folds)
    role_matrix = _build_role_matrix(folds)
    return SplitArtifacts(
        folds=folds,
        metadata=metadata,
        timeline_plot=build_validation_protocol_report(folds),
        protocol=protocol,
        role_matrix=role_matrix,
    )
