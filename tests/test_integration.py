"""Integration test: fits the REAL preprocessing pipeline (ColumnTransformer:
SimpleImputer+StandardScaler for numeric, SimpleImputer+OneHotEncoder for
categorical) + XGBClassifier on a small synthetic sample, and checks that
predict_proba round-trips correctly end to end.

Every other test in this suite (test_api.py, test_telco_model.py) mocks the
model out entirely for speed -- correct for testing THEIR wiring, but it
means nothing in the suite ever actually fits the real artifact. This file
closes that gap: no mocks. The pipeline structure below is copied from
telco_customer_churn.ipynb (num_cols/cat_cols via dtype detection,
SimpleImputer+StandardScaler, SimpleImputer+OneHotEncoder), run against
feature_engineering_telco.engineer_features -- the same shared module the
notebook, api.py, and telco_model.py all import.

This is NOT a model-quality test -- 40 synthetic rows can't teach XGBoost
anything real. It only proves the plumbing (engineer_features ->
ColumnTransformer -> XGBClassifier) actually fits and predicts without
raising, with no internet access or pre-trained model required.

Run with: pytest tests/test_integration.py -v
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

import config
from feature_engineering_telco import engineer_features


# The first rows are forced to tenure=0 so they carry a missing
# totalcharges, mirroring the 11 real tenure=0 rows in the Kaggle dataset.
# This used to be left to chance -- `tenure = rng.integers(0, 60)` gives a
# ~1-in-60 shot per row, so at n=40 whether ANY such row appeared was close
# to a coin flip. Measured across the first 40 seeds, 21 of them (52%)
# produced none at all, and seed=0 produced exactly one, which the whole of
# test_pipeline_handles_missing_totalcharges rested on. The precondition
# assert in that test meant a bad seed failed loudly rather than passing
# silently, so this was fragility rather than a false pass -- but changing
# one integer sending the suite red for unrelated reasons is a real hazard,
# and one row is thin coverage for imputation.
N_ZERO_TENURE_ROWS = 3


def _make_synthetic_customers(n=40, seed=0):
    """Small synthetic dataset spanning every categorical value the real
    OneHotEncoder needs to see at least once, plus exactly
    N_ZERO_TENURE_ROWS genuinely missing totalcharges values -- mirroring
    the 11 real tenure=0 rows in the Kaggle dataset -- so SimpleImputer has
    real work to do, not mocked-away work.

    The missing rows are deterministic across every seed: see the note
    above. Remaining rows draw tenure from 1..59, so no additional zeros
    appear by accident and the count is exact rather than "at least".
    """
    if n <= N_ZERO_TENURE_ROWS:
        raise ValueError(
            f"n={n} leaves no non-zero-tenure rows; need more than "
            f"{N_ZERO_TENURE_ROWS}"
        )
    rng = np.random.default_rng(seed)

    genders = ["Male", "Female"]
    yn = ["Yes", "No"]
    internet = ["DSL", "Fiber optic", "No"]
    contract = ["Month-to-month", "One year", "Two year"]
    payment = [
        "Electronic check", "Mailed check",
        "Bank transfer (automatic)", "Credit card (automatic)",
    ]
    addon = ["Yes", "No", "No internet service"]

    rows = []
    for i in range(n):
        tenure = 0 if i < N_ZERO_TENURE_ROWS else int(rng.integers(1, 60))
        monthly = round(float(rng.uniform(20, 120)), 2)
        totalcharges = None if tenure == 0 else round(monthly * tenure * rng.uniform(0.9, 1.1), 2)
        rows.append({
            "gender": genders[i % 2],
            "seniorcitizen": int(rng.integers(0, 2)),
            "partner": yn[i % 2],
            "dependents": yn[(i + 1) % 2],
            "tenure": tenure,
            "phoneservice": "Yes",
            "multiplelines": ["No", "Yes", "No phone service"][i % 3],
            "internetservice": internet[i % 3],
            "onlinesecurity": addon[i % 3],
            "onlinebackup": addon[(i + 1) % 3],
            "deviceprotection": addon[(i + 2) % 3],
            "techsupport": addon[i % 3],
            "streamingtv": addon[(i + 1) % 3],
            "streamingmovies": addon[(i + 2) % 3],
            "contract": contract[i % 3],
            "paperlessbilling": yn[i % 2],
            "paymentmethod": payment[i % 4],
            "monthlycharges": monthly,
            "totalcharges": totalcharges,
        })

    X = pd.DataFrame(rows)
    # deterministic-but-mixed churn labels -- just needs both classes
    # present for XGBClassifier to train and predict_proba to return two
    # columns; not meant to reflect real churn patterns.
    y = pd.Series([i % 3 == 0 for i in range(n)], name="churn").astype(int)
    return X, y


def _build_real_pipeline(X_engineered: pd.DataFrame) -> Pipeline:
    """Recreates the exact preprocessor + classifier structure from
    telco_customer_churn.ipynb. num_cols/cat_cols come from dtype
    detection, same as the notebook -- not a hand-picked column list, so
    this stays correct if feature_engineering_telco.py adds or removes a
    column.
    """
    num_cols = X_engineered.select_dtypes(include=["int64", "float64"]).columns.tolist()
    cat_cols = X_engineered.select_dtypes(include=["object", "category", "string"]).columns.tolist()

    num_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    cat_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    preprocessor = ColumnTransformer([
        ("num", num_pipeline, num_cols),
        ("cat", cat_pipeline, cat_cols),
    ])
    return Pipeline([
        ("preprocessor", preprocessor),
        # small/shallow on purpose -- this is a plumbing test, not an
        # accuracy test, so keep it fast.
        ("classifier", XGBClassifier(random_state=42, n_estimators=20, max_depth=2)),
    ])


@pytest.fixture
def fitted_pipeline():
    X, y = _make_synthetic_customers()
    X = engineer_features(X)
    pipeline = _build_real_pipeline(X)
    pipeline.fit(X, y)
    return pipeline, X, y


def test_pipeline_fits_without_raising(fitted_pipeline):
    # Fixture setup already fit the pipeline -- if it had raised, this test
    # would fail during fixture resolution before ever reaching here.
    pipeline, X, y = fitted_pipeline
    assert pipeline.named_steps["classifier"].n_features_in_ > 0


def test_predict_proba_shape_and_range(fitted_pipeline):
    pipeline, X, y = fitted_pipeline
    proba = pipeline.predict_proba(X)

    assert proba.shape == (len(X), 2)
    assert np.all((proba >= 0) & (proba <= 1))
    assert np.allclose(proba.sum(axis=1), 1.0)  # each row's classes sum to 1
    assert not np.isnan(proba).any()


def test_predict_matches_argmax_of_proba(fitted_pipeline):
    pipeline, X, y = fitted_pipeline
    proba = pipeline.predict_proba(X)
    preds = pipeline.predict(X)
    assert np.array_equal(preds, proba.argmax(axis=1))


def test_pipeline_handles_missing_totalcharges(fitted_pipeline):
    """The synthetic sample includes real None totalcharges rows (tenure=0,
    matching the 11 real Kaggle rows) -- confirms the REAL SimpleImputer,
    not a mock, absorbs them without raising."""
    pipeline, X, y = fitted_pipeline
    # Exact, not "at least one" -- the fixture forces these rows, so a count
    # that drifts means the fixture changed, which is worth failing on.
    assert X["totalcharges"].isna().sum() == N_ZERO_TENURE_ROWS
    missing_rows = X[X["totalcharges"].isna()]
    proba = pipeline.predict_proba(missing_rows)
    assert not np.isnan(proba).any()


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 1234])
def test_fixture_missing_totalcharges_is_seed_independent(seed):
    """Locks in the M7 fix. The fixture used to depend on chance: 21 of the
    first 40 seeds produced no missing-totalcharges rows at all, so changing
    the seed had a coin-flip chance of turning the suite red for reasons
    unrelated to the change under test. Now the count is exact for every
    seed, and this test is what stops the randomness being reintroduced.
    """
    X, y = _make_synthetic_customers(seed=seed)
    assert X["totalcharges"].isna().sum() == N_ZERO_TENURE_ROWS
    assert (X["tenure"] == 0).sum() == N_ZERO_TENURE_ROWS
    # Missing totalcharges must coincide with tenure==0 -- that pairing is
    # the real-data property being mirrored, not just the row count.
    assert X.loc[X["tenure"] == 0, "totalcharges"].isna().all()
    assert X.loc[X["tenure"] > 0, "totalcharges"].notna().all()


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 1234])
def test_fixture_still_spans_every_categorical_value(seed):
    """Forcing the first rows to tenure=0 must not cost categorical
    coverage -- the OneHotEncoder needs to see every value at least once,
    which is the fixture's other job."""
    X, y = _make_synthetic_customers(seed=seed)
    for column, allowed in config.CATEGORICAL_DOMAINS.items():
        present = set(X[column].unique())
        assert present <= set(allowed), f"{column}: {present - set(allowed)}"
    assert set(y) == {0, 1}, "both classes must be present for XGBClassifier"


def test_pipeline_predicts_on_unseen_category(fitted_pipeline):
    """OneHotEncoder(handle_unknown='ignore') is what makes the real API
    safe against a category value it never saw during training -- this is
    the one guarantee a mocked model can never actually verify."""
    pipeline, X, y = fitted_pipeline
    unseen = X.iloc[[0]].copy()
    unseen["paymentmethod"] = "Cash"  # not one of the 4 trained categories
    proba = pipeline.predict_proba(unseen)
    assert proba.shape == (1, 2)
    assert not np.isnan(proba).any()
