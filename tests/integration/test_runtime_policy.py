from __future__ import annotations

from dataclasses import replace

import pytest

from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.pipeline.policy import UnsupportedExperimentForOperationalRun
from alpha_research.pipeline.runtime import execute_operational_command


def test_operational_runtime_rejects_unsupported_experiment_before_bundle_resolution(minimal_repo, monkeypatch) -> None:
    loaded = load_resolved_config_bundle(minimal_repo)
    unsupported_experiment = loaded.bundle.experiments["exp_gbm_ranker"].model_copy(
        update={
            "model": loaded.bundle.experiments["exp_gbm_ranker"].model.model_copy(update={"name": "unsupported_pairwise_ranker"})
        }
    )
    loaded = replace(
        loaded,
        bundle=loaded.bundle.model_copy(
            update={
                "experiments": {"exp_bad_model": unsupported_experiment},
                "runtime": loaded.bundle.runtime.model_copy(update={"operational_experiment_key": "exp_bad_model"}),
            }
        ),
    )

    def _unexpected_bundle_resolution(*args, **kwargs):
        raise AssertionError("resolve_operational_bundle не должен вызываться до проверки supported experiment policy")

    monkeypatch.setattr("alpha_research.pipeline.runtime.resolve_operational_bundle", _unexpected_bundle_resolution)

    with pytest.raises(UnsupportedExperimentForOperationalRun):
        execute_operational_command(
            "run-report",
            RepositoryPaths.from_root(minimal_repo),
            loaded,
        )
