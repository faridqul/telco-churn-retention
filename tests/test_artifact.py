"""Canary tests for the committed model artifact itself.

Every other test in this suite either mocks the model out (test_api.py,
test_telco_model.py) or fits a fresh one on synthetic data
(test_integration.py). None of them open xgboost_churn_pipeline.pkl -- so
the exact bytes api.py and telco_model.py load in production were never
exercised, in a repo whose version-drift warning, library_versions metadata
field and verify_version_check.sh all exist because that artifact is
fragile.

These tests close that gap. They catch three things:

  1. A corrupted or unloadable pickle.
  2. A library version bump that unpickles cleanly but predicts
     differently -- the silent-behaviour-change case verify_version_check.sh
     explicitly says it cannot detect ("success does not necessarily mean
     identical predictions").
  3. A feature-engineering change that shifts the model's input without
     changing the column names, which validate_feature_schema()'s set
     comparison would wave through.

The expected probability is NOT hard-coded here -- it is read from
model_metadata.json's "dummy_customer_score", which the notebook's save cell
writes at the same moment it writes the pickle. A retrain therefore updates
the artifact and its canary value together and these tests stay green, which
is intended: they pin the artifact against its *environment*, not against
model changes you made on purpose.

Run with: pytest tests/test_artifact.py -v
"""

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest

import config
from feature_engineering_telco import engineer_features

REPO_ROOT = Path(__file__).resolve().parent.parent


def _anchor(path_str):
    """Resolve a config path against the repo root when it's relative, so
    these tests don't depend on pytest's working directory. An absolute
    override (MODEL_PATH/METADATA_PATH env vars) is honoured as-is.
    """
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


@pytest.fixture(scope="module")
def artifact():
    """The real pickle. Module-scoped -- joblib.load is the slow part and
    nothing here mutates the estimator.
    """
    path = _anchor(config.MODEL_PATH)
    if not path.exists():
        pytest.fail(
            f"Model artifact missing at {path}. It is committed on purpose so "
            f"a fresh clone runs immediately -- if it's gone, re-run the "
            f"notebook's save cell rather than skipping this test."
        )
    return joblib.load(path)


@pytest.fixture(scope="module")
def metadata():
    with open(_anchor(config.METADATA_PATH)) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def dummy_score(artifact):
    """The shipped pipeline's churn probability for config.DUMMY_CUSTOMER."""
    row = engineer_features(pd.DataFrame([config.DUMMY_CUSTOMER]))
    return float(artifact.predict_proba(row)[:, 1][0])


def test_real_artifact_loads_and_predicts(artifact):
    """Unpickles at all, and is the estimator interface both consumers assume."""
    assert hasattr(artifact, "predict_proba")
    assert hasattr(artifact, "predict")


def test_real_artifact_reproduces_pinned_prediction(dummy_score, metadata):
    """The canary. See the module docstring for what a failure here means."""
    expected = metadata.get("dummy_customer_score")
    assert expected is not None, (
        "model_metadata.json has no 'dummy_customer_score' -- the artifact "
        "predates this canary. Re-run the notebook's save cell to record it."
    )
    # Tolerance is float32 round-tripping room, not modelling slack: the
    # pipeline predicts in float32 and the pin is stored as a JSON double.
    # A genuine behaviour change moves this far more than 1e-6.
    assert dummy_score == pytest.approx(expected, abs=1e-6)


def test_pinned_prediction_still_lands_on_the_same_decision(dummy_score):
    """The probability is only half the contract -- the decision api.py and
    telco_model.py both derive from it is what a caller actually sees. Uses
    the same `>=` comparison as both consumers.
    """
    threshold = config.load_threshold(str(_anchor(config.METADATA_PATH)))
    assert dummy_score >= threshold, (
        f"DUMMY_CUSTOMER scores {dummy_score:.6f}, below the operating "
        f"threshold {threshold} -- the artifact's decision for this input "
        f"has flipped."
    )


def test_artifact_accepts_exactly_the_metadata_feature_schema(artifact, metadata):
    """Dropping a column the pipeline expects raises at predict time; this
    proves the committed pickle and the committed schema agree, rather than
    trusting validate_feature_schema()'s check of engineer_features() alone.
    """
    row = engineer_features(pd.DataFrame([config.DUMMY_CUSTOMER]))
    assert set(row.columns) == set(metadata["feature_columns"])
    artifact.predict_proba(row)  # should not raise
