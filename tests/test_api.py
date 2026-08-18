"""Smoke tests for the FastAPI service: does it start up, does /health
report correctly, does /predict accept a valid payload and reject bad
ones. Not testing model accuracy -- the model here is a mocked stand-in
so these tests run fast and don't depend on a trained .pkl existing on
disk.

Run with: pytest tests/test_api.py -v
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import api as api_module


class DummyModel:
    """Deterministic stand-in for the real XGBoost pipeline. Always
    predicts a 0.8 churn probability, regardless of input -- good enough
    for testing that the API wiring works, not for testing model quality."""

    def predict_proba(self, X):
        n = len(X)
        return np.column_stack([np.full(n, 0.2), np.full(n, 0.8)])


@pytest.fixture
def client(monkeypatch):
    """Patches out joblib.load and load_threshold so these tests don't
    require a real xgboost_churn_pipeline.pkl / model_metadata.json to be
    present on disk. Threshold is fixed at 0.5 so predictions are
    deterministic for the assertions below."""
    monkeypatch.setattr(api_module.joblib, "load", lambda path: DummyModel())
    monkeypatch.setattr(api_module, "load_threshold", lambda: 0.5)
    with TestClient(api_module.app) as test_client:
        yield test_client


VALID_PAYLOAD = {
    "gender": "Female", "seniorcitizen": 0, "partner": "Yes", "dependents": "No",
    "tenure": 3, "phoneservice": "Yes", "multiplelines": "No",
    "internetservice": "Fiber optic", "onlinesecurity": "No", "onlinebackup": "No",
    "deviceprotection": "No", "techsupport": "No", "streamingtv": "Yes",
    "streamingmovies": "Yes", "contract": "Month-to-month", "paperlessbilling": "Yes",
    "paymentmethod": "Electronic check", "monthlycharges": 85.5, "totalcharges": 256.5,
}


def test_health_reports_model_loaded(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": True}


def test_predict_valid_payload_returns_expected_shape(client):
    response = client.post("/predict", json=VALID_PAYLOAD)
    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"churn_probability", "target_for_retention", "threshold_used"}
    assert body["churn_probability"] == pytest.approx(0.8)
    assert body["threshold_used"] == 0.5
    # DummyModel always returns 0.8, threshold is fixed at 0.5 -> should flag
    assert body["target_for_retention"] is True


def test_predict_totalcharges_is_optional(client):
    """totalcharges=None must be accepted (matches real-world rows where
    it's missing) and must not crash the request."""
    payload = {**VALID_PAYLOAD}
    del payload["totalcharges"]
    response = client.post("/predict", json=payload)
    assert response.status_code == 200


def test_predict_rejects_invalid_categorical_value(client):
    """gender is a Literal["Male", "Female"] -- anything else should be a
    422 from Pydantic validation, not a 500 from the model choking on it."""
    payload = {**VALID_PAYLOAD, "gender": "Not A Valid Option"}
    response = client.post("/predict", json=payload)
    assert response.status_code == 422


def test_predict_rejects_missing_required_field(client):
    payload = {**VALID_PAYLOAD}
    del payload["tenure"]
    response = client.post("/predict", json=payload)
    assert response.status_code == 422


def test_predict_rejects_negative_tenure(client):
    payload = {**VALID_PAYLOAD, "tenure": -1}
    response = client.post("/predict", json=payload)
    assert response.status_code == 422
