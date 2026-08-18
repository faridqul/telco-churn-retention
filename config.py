"""Shared configuration for the training/batch script and the API.

Single source of truth for paths and the threshold-loading logic, so
api.py and telco_model.py can't silently drift apart.
"""

import json
import os

import pandas as pd

from feature_engineering_telco import engineer_features

# Overridable via env vars so the artifact location can change per
# environment (staging vs. prod, a mounted volume in a container, a
# rollback to a previous model) without a code change. Defaults preserve
# today's local-dev behavior. MODEL_PATH loads a pickle-based artifact --
# only point it at a source you trust, since deserializing a pickle
# executes arbitrary code.
MODEL_PATH = os.environ.get("MODEL_PATH", "xgboost_churn_pipeline.pkl")
METADATA_PATH = os.environ.get("METADATA_PATH", "model_metadata.json")

# Fallback only used if model_metadata.json is missing -- keeps callers from
# crashing, but should basically never be hit in normal operation.
DEFAULT_THRESHOLD = 0.4

# Minimal, arbitrary-but-valid customer used only to probe
# engineer_features()'s output columns at startup. Values don't matter --
# only the resulting column names do.
DUMMY_CUSTOMER = {
    "gender": "Female", "seniorcitizen": 0, "partner": "No", "dependents": "No",
    "tenure": 1, "phoneservice": "Yes", "multiplelines": "No",
    "internetservice": "No", "onlinesecurity": "No", "onlinebackup": "No",
    "deviceprotection": "No", "techsupport": "No", "streamingtv": "No",
    "streamingmovies": "No", "contract": "Month-to-month", "paperlessbilling": "No",
    "paymentmethod": "Mailed check", "monthlycharges": 1.0, "totalcharges": 1.0,
}


def load_threshold(metadata_path: str = METADATA_PATH) -> float:
    try:
        with open(metadata_path) as f:
            metadata = json.load(f)
        return float(metadata["threshold"])
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"WARNING: could not load threshold from {metadata_path} ({e}); "
              f"falling back to DEFAULT_THRESHOLD={DEFAULT_THRESHOLD}")
        return DEFAULT_THRESHOLD


def validate_feature_schema(metadata_path: str = METADATA_PATH) -> None:
    """Fail fast if engineer_features() no longer matches what the trained
    model expects. Without this, a schema drift (e.g. a renamed or removed
    engineered column) would silently produce a 500 -- or worse, a silently
    wrong prediction -- at request time instead of failing loudly at
    startup.
    """
    with open(metadata_path) as f:
        metadata = json.load(f)
    expected = set(metadata["feature_columns"])

    dummy_row = pd.DataFrame([DUMMY_CUSTOMER])
    actual = set(engineer_features(dummy_row).columns)

    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        raise RuntimeError(
            f"Feature schema mismatch between engineer_features() and "
            f"{metadata_path}.\nMissing: {sorted(missing)}\nExtra: {sorted(extra)}\n"
            f"Either retrain the model or fix feature_engineering_telco.py."
        )
