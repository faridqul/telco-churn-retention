"""Smoke tests for telco_model.main(): the batch scoring script. Checks
that it reads the input CSV, engineers features, scores with the model,
and writes an output CSV with the right shape/columns -- not whether the
model's predictions are accurate (same philosophy as test_api.py: the
model here is a mocked stand-in, so these tests run fast and don't
depend on a trained .pkl or model_metadata.json existing on disk).

Run with: pytest test_telco_model.py -v
"""

import numpy as np
import pandas as pd
import pytest

import telco_model


class DummyModel:
    """Deterministic stand-in for the real XGBoost pipeline -- same pattern
    as test_api.py's DummyModel. Always predicts a 0.8 churn probability,
    good enough for testing the script's wiring, not model quality."""

    def predict_proba(self, X):
        n = len(X)
        return np.column_stack([np.full(n, 0.2), np.full(n, 0.8)])


RAW_CUSTOMER_ROW = {
    "gender": "Female", "seniorcitizen": 0, "partner": "Yes", "dependents": "No",
    "tenure": 3, "phoneservice": "Yes", "multiplelines": "No",
    "internetservice": "Fiber optic", "onlinesecurity": "No", "onlinebackup": "No",
    "deviceprotection": "No", "techsupport": "No", "streamingtv": "Yes",
    "streamingmovies": "Yes", "contract": "Month-to-month", "paperlessbilling": "Yes",
    "paymentmethod": "Electronic check", "monthlycharges": 85.5, "totalcharges": 256.5,
}


@pytest.fixture
def isolated_run(tmp_path, monkeypatch):
    """Points INPUT_PATH/OUTPUT_PATH at tmp_path and mocks out
    validate_feature_schema, validate_environment_versions,
    load_threshold, and joblib.load -- mirrors test_api.py's client
    fixture. No real .pkl or model_metadata.json required, and nothing
    is written outside tmp_path. Returns the output path so tests can
    read back what main() wrote."""
    input_path = tmp_path / "simulated_new_customers.csv"
    output_path = tmp_path / "retention_campaign_targets.csv"

    pd.DataFrame([RAW_CUSTOMER_ROW, RAW_CUSTOMER_ROW]).to_csv(input_path, index=False)

    monkeypatch.setattr(telco_model, "INPUT_PATH", str(input_path))
    monkeypatch.setattr(telco_model, "OUTPUT_PATH", str(output_path))
    monkeypatch.setattr(telco_model, "validate_feature_schema", lambda: None)
    monkeypatch.setattr(telco_model, "validate_environment_versions", lambda: None)
    monkeypatch.setattr(telco_model, "load_threshold", lambda: 0.5)
    monkeypatch.setattr(telco_model.joblib, "load", lambda path: DummyModel())

    return output_path


def test_main_writes_output_csv_with_expected_columns(isolated_run):
    telco_model.main()

    result = pd.read_csv(isolated_run)
    assert "Churn_Probability" in result.columns
    assert "Target_For_Retention" in result.columns


def test_main_output_row_count_matches_input(isolated_run):
    telco_model.main()

    result = pd.read_csv(isolated_run)
    assert len(result) == 2  # matches the 2 rows written to the input fixture


def test_main_flags_all_rows_when_probability_exceeds_threshold(isolated_run):
    """DummyModel always returns 0.8, threshold is fixed at 0.5 -> every row
    should be flagged for retention (mirrors test_api.py's equivalent
    assertion for /predict)."""
    telco_model.main()

    result = pd.read_csv(isolated_run)
    # pytest.approx(0.8) doesn't broadcast element-wise against a pandas
    # Series via == -- it collapses to a single False instead of comparing
    # each element. np.allclose does the correct element-wise comparison.
    assert np.allclose(result["Churn_Probability"], 0.8)
    assert (result["Target_For_Retention"] == 1).all()


def test_main_engineers_features_before_scoring(isolated_run):
    """DummyModel ignores its input entirely, so main() would still
    "succeed" even if engineer_features() were silently skipped. This
    checks the engineered columns actually land in the written output --
    i.e. that scoring runs on engineered data, not just that main()
    doesn't crash."""
    telco_model.main()

    result = pd.read_csv(isolated_run)
    for engineered_col in [
        "total_services", "is_auto_pay", "family_tie",
        "contractvstenure", "average_monthly_charges", "charge_change_ratio",
    ]:
        assert engineered_col in result.columns


def test_main_raises_when_input_csv_missing(tmp_path, monkeypatch):
    """No simulated_new_customers.csv present (e.g. fresh clone, script run
    out of order) should fail loudly with pandas' own FileNotFoundError,
    not silently produce an empty or wrong output file."""
    missing_input = tmp_path / "does_not_exist.csv"
    output_path = tmp_path / "retention_campaign_targets.csv"

    monkeypatch.setattr(telco_model, "INPUT_PATH", str(missing_input))
    monkeypatch.setattr(telco_model, "OUTPUT_PATH", str(output_path))
    monkeypatch.setattr(telco_model, "validate_feature_schema", lambda: None)
    monkeypatch.setattr(telco_model, "validate_environment_versions", lambda: None)
    monkeypatch.setattr(telco_model, "load_threshold", lambda: 0.5)
    monkeypatch.setattr(telco_model.joblib, "load", lambda path: DummyModel())

    with pytest.raises(FileNotFoundError):
        telco_model.main()

    assert not output_path.exists()
