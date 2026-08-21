"""Shared configuration for the training/batch script and the API.

Single source of truth for paths and the threshold-loading logic, so
api.py and telco_model.py can't silently drift apart.
"""

import json
import os

import numpy as np
import pandas as pd
import sklearn
import xgboost

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


def _current_library_versions() -> dict[str, str]:
    """Installed versions of the libraries the pickled pipeline is most
    sensitive to. Broken out as its own function (rather than inlined
    into validate_environment_versions) purely so tests can monkeypatch
    it directly, without needing every exact version under test actually
    installed.
    """
    return {
        "scikit-learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }


def validate_environment_versions(metadata_path: str = METADATA_PATH) -> None:
    """Warn -- never raise -- if the currently-installed ML libraries
    differ from the versions that trained/pickled the model artifact.

    joblib/pickle serializes near-literal internal state of the
    ColumnTransformer/OneHotEncoder/XGBClassifier objects, tied to the
    exact library version that created them -- neither scikit-learn nor
    XGBoost guarantee pickle compatibility across releases. This is
    deliberately a DETECTION control, not a gate: it surfaces a version
    drift so it can be investigated, rather than turning a version bump
    that may well be harmless into a guaranteed API outage by crashing
    startup. An earlier version of this function hard-failed on a
    major-version difference -- that traded a probabilistic risk (the
    pickle *might* misbehave) for a certain one (the service *will* be
    down). A hard gate belongs in CI, checked against the artifact before
    it's deployed, not in the live service's boot path.

    Compares full version strings (not just major.minor) since there's no
    parsing here to get subtly wrong -- any difference is reported as-is
    and left for a human to judge, rather than the code guessing which
    differences are "safe."

    No-ops (with a warning, not an error) if model_metadata.json predates
    this check and has no 'library_versions' key.
    """
    with open(metadata_path) as f:
        metadata = json.load(f)

    trained_versions = metadata.get("library_versions")
    if not trained_versions:
        print(f"WARNING: {metadata_path} has no 'library_versions' field "
              f"(artifact trained before this check existed) -- skipping "
              f"environment validation.")
        return

    current_versions = _current_library_versions()
    mismatches = []

    for lib, trained_version in trained_versions.items():
        current_version = current_versions.get(lib)
        if current_version is None:
            continue  # library not tracked by this version of the code
        if trained_version != current_version:
            mismatches.append(
                f"  {lib}: trained with {trained_version}, running {current_version}"
            )

    if mismatches:
        print(
            "WARNING: model artifact was trained with different library "
            "version(s) than are currently installed. joblib/pickle does "
            "not guarantee cross-version compatibility for scikit-learn or "
            "XGBoost objects -- this may be harmless (e.g. a patch bump) or "
            "may produce a load failure or a silently different prediction. "
            "Worth confirming before trusting this deployment:\n"
            + "\n".join(mismatches)
        )


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
