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

# Fallback used when model_metadata.json is readable but its "threshold"
# value is unusable (absent, null, a list, an uncastable string). A missing
# or unparseable metadata FILE is fatal instead -- see _load_metadata.
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


def _load_metadata(metadata_path: str = METADATA_PATH) -> dict:
    """Read and parse model_metadata.json, or fail with a readable message.

    Missing-metadata policy, decided deliberately and applied consistently
    by all three functions below: **a missing or unparseable metadata file
    is fatal.** The metadata records the operating threshold, the feature
    schema and the library versions the pickle was built with -- without it
    there is no way to know whether the artifact next to it is the one the
    code expects, so serving predictions anyway would mean guessing. Both
    consumers call validate_feature_schema() first, so this is what they
    hit, and it's a RuntimeError naming the file rather than a bare
    FileNotFoundError traceback from inside a library call.

    A *malformed value inside a readable file* is treated differently --
    load_threshold() degrades to DEFAULT_THRESHOLD there, because the model
    itself is probably fine and a sane default beats an outage.

    Previously load_threshold() caught FileNotFoundError and returned
    DEFAULT_THRESHOLD, but that branch was unreachable in production: both
    consumers run the validators first, and those opened the same file and
    raised. The fallback looked like graceful degradation while delivering
    a raw traceback. This makes the fatal case explicit and readable
    instead of half-implementing tolerance that never applied.
    """
    try:
        with open(metadata_path) as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Model metadata not found at {metadata_path}. The API and batch "
            f"script both require it -- it records the operating threshold, "
            f"the feature schema and the library versions the pickled model "
            f"was built with. Run the notebook's save cell to regenerate it, "
            f"or point METADATA_PATH at the right file."
        ) from e
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Model metadata at {metadata_path} is not valid JSON ({e}). "
            f"It was likely truncated or hand-edited; regenerate it by "
            f"running the notebook's save cell."
        ) from e


def load_threshold(metadata_path: str = METADATA_PATH) -> float:
    """Operating threshold from the metadata, or DEFAULT_THRESHOLD if the
    file is readable but its "threshold" value isn't usable.

    A missing or unparseable file raises (see _load_metadata). TypeError is
    caught alongside KeyError/ValueError because float(None) and
    float([0.4]) both raise it -- null is what a hand-edit or a templating
    step emits for a missing value, so it's a likelier corruption than the
    uncastable-string case, and it used to crash startup.
    """
    metadata = _load_metadata(metadata_path)
    try:
        return float(metadata["threshold"])
    except (KeyError, TypeError, ValueError) as e:
        print(f"WARNING: could not read a usable threshold from "
              f"{metadata_path} ({e}); falling back to "
              f"DEFAULT_THRESHOLD={DEFAULT_THRESHOLD}")
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

    "Never raises" is enforced rather than merely asserted: an unreadable
    metadata file, or a 'library_versions' that isn't a dict, warns and
    returns. This function is a detection control only, and the fatal
    missing-metadata case is already handled by validate_feature_schema(),
    which both consumers call first. It previously raised AttributeError on
    a 'library_versions' that was a list or a string, and FileNotFoundError
    on a missing file, contradicting this docstring.
    """
    try:
        metadata = _load_metadata(metadata_path)
    except RuntimeError as e:
        print(f"WARNING: skipping environment validation -- {e}")
        return

    trained_versions = metadata.get("library_versions")
    if not trained_versions:
        print(f"WARNING: {metadata_path} has no 'library_versions' field "
              f"(artifact trained before this check existed) -- skipping "
              f"environment validation.")
        return

    if not isinstance(trained_versions, dict):
        print(f"WARNING: 'library_versions' in {metadata_path} is a "
              f"{type(trained_versions).__name__}, expected an object mapping "
              f"library name to version -- skipping environment validation.")
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
    metadata = _load_metadata(metadata_path)
    feature_columns = metadata.get("feature_columns")
    if not feature_columns:
        raise RuntimeError(
            f"{metadata_path} has no 'feature_columns' field, so there is "
            f"nothing to validate engineer_features() against. Regenerate "
            f"it by running the notebook's save cell."
        )
    expected = set(feature_columns)

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
