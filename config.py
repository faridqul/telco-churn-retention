"""Shared configuration for the training/batch script and the API.

Single source of truth for paths and the threshold-loading logic, so
api.py and telco_model.py can't silently drift apart.
"""

import importlib.metadata
import json
import os
import sys

import numpy as np
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

# Fallback used when model_metadata.json is readable but its "threshold"
# value is unusable (absent, null, a list, an uncastable string). A missing
# or unparseable metadata FILE is fatal instead -- see _load_metadata.
DEFAULT_THRESHOLD = 0.4

# The feature-contract version this code implements. The notebook stamps the
# same string into model_metadata.json when it saves. Bump BOTH together when
# engineer_features() changes shape in a way an old artifact wouldn't survive.
#
# The column-set check below already catches a renamed or dropped column. This
# catches the case it can't see: same column names, different meaning -- a
# formula corrected, a unit changed, a category folded. The columns still line
# up, so the model loads and predicts, wrongly and quietly.
SUPPORTED_FEATURE_SCHEMA_VERSION = "1.0"

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


# Allowed values for every categorical column, and the numeric columns that
# must parse as finite numbers. These mirror the Literal types on
# api.Customer exactly -- tests/test_input_validation.py asserts the two
# agree, so they cannot drift apart silently. They live here rather than in
# api.py because telco_model.py needs them too, and this module exists
# specifically to stop the two consumers diverging.
#
# Why this matters more than a range check on the numbers: the pipeline's
# OneHotEncoder uses handle_unknown='ignore', so an unrecognised category
# becomes an all-zeros block that is indistinguishable from "no
# information" -- no error, just a different answer. A casing slip in a CSV
# ('month-to-month' for 'Month-to-month') moves DUMMY_CUSTOMER from 0.5700
# to 0.1017, flipping the retention decision silently. Out-of-range
# *numbers*, by contrast, saturate harmlessly in a tree ensemble: tenure
# 10**15 scores the same as tenure 1000.
CATEGORICAL_DOMAINS: dict[str, tuple[str, ...]] = {
    "gender": ("Male", "Female"),
    "partner": ("Yes", "No"),
    "dependents": ("Yes", "No"),
    "phoneservice": ("Yes", "No"),
    "multiplelines": ("Yes", "No", "No phone service"),
    "internetservice": ("DSL", "Fiber optic", "No"),
    "onlinesecurity": ("Yes", "No", "No internet service"),
    "onlinebackup": ("Yes", "No", "No internet service"),
    "deviceprotection": ("Yes", "No", "No internet service"),
    "techsupport": ("Yes", "No", "No internet service"),
    "streamingtv": ("Yes", "No", "No internet service"),
    "streamingmovies": ("Yes", "No", "No internet service"),
    "contract": ("Month-to-month", "One year", "Two year"),
    "paperlessbilling": ("Yes", "No"),
    "paymentmethod": (
        "Electronic check", "Mailed check",
        "Bank transfer (automatic)", "Credit card (automatic)",
    ),
}

# seniorcitizen is 0/1, tenure is a count of months, the two charge columns
# are money. All must be non-negative, matching api.Customer's ge=0 fields.
NUMERIC_COLUMNS: tuple[str, ...] = (
    "seniorcitizen", "tenure", "monthlycharges", "totalcharges",
)

# totalcharges is blank for the 11 real customers with tenure==0, and the
# pipeline's SimpleImputer is there to fill exactly that. So a *missing*
# numeric is allowed; an unparseable or infinite one is not.
NULLABLE_NUMERIC_COLUMNS: tuple[str, ...] = ("totalcharges",)

# How many offending rows to name per problem before summarising the rest --
# a 50,000-row CSV with a systematically wrong column shouldn't print 50,000
# line numbers.
_MAX_REPORTED_ROWS = 5


def _describe_rows(positions) -> str:
    """Human-readable row list, 1-based and counting the CSV header, so the
    numbers match what a text editor shows."""
    lines = [p + 2 for p in positions[:_MAX_REPORTED_ROWS]]
    rendered = ", ".join(str(n) for n in lines)
    if len(positions) > _MAX_REPORTED_ROWS:
        rendered += f", ... ({len(positions)} rows total)"
    return rendered


def validate_input_frame(df: pd.DataFrame) -> None:
    """Reject a batch input frame that the model cannot score honestly.

    api.py gets this for free from Pydantic -- unknown categories and
    negative numbers are rejected with a 422 before anything is scored.
    telco_model.py had no equivalent, so a CSV from a slightly different
    export could be scored end to end with no error and a silently
    different answer. This closes that gap using the same domains.

    Deliberately checks membership and finiteness, NOT plausible ranges.
    An implausibly large tenure still produces a sensible, saturated
    prediction; an unrecognised contract value does not, and gives no sign
    that anything went wrong. Adding upper bounds would reject inputs the
    model handles correctly while doing nothing about the case that
    actually loses money.

    Raises RuntimeError naming every problem found, rather than the first
    one, so a malformed file can be fixed in one pass.
    """
    problems: list[str] = []

    required = tuple(CATEGORICAL_DOMAINS) + NUMERIC_COLUMNS
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise RuntimeError(
            f"Input is missing {len(missing_cols)} required column(s): "
            f"{sorted(missing_cols)}.\nExpected all of: {sorted(required)}"
        )

    for column, allowed in CATEGORICAL_DOMAINS.items():
        offending = df.index[~df[column].isin(allowed)]
        if len(offending):
            positions = [df.index.get_loc(i) for i in offending]
            seen = sorted({repr(v) for v in df.loc[offending, column].unique()})
            problems.append(
                f"  {column}: {len(offending)} row(s) with a value outside "
                f"the trained categories.\n"
                f"      found:   {', '.join(seen[:_MAX_REPORTED_ROWS])}\n"
                f"      allowed: {', '.join(repr(v) for v in allowed)}\n"
                f"      rows:    {_describe_rows(positions)}"
            )

    for column in NUMERIC_COLUMNS:
        values = pd.to_numeric(df[column], errors="coerce")
        blank = df[column].isna() | (
            df[column].astype(str).str.strip() == "" if df[column].dtype == object
            else False
        )
        unparseable = values.isna() & ~blank
        if unparseable.any():
            positions = [df.index.get_loc(i) for i in df.index[unparseable]]
            problems.append(
                f"  {column}: {int(unparseable.sum())} row(s) that are not a "
                f"number.\n      rows:    {_describe_rows(positions)}"
            )

        if column not in NULLABLE_NUMERIC_COLUMNS and blank.any():
            positions = [df.index.get_loc(i) for i in df.index[blank]]
            problems.append(
                f"  {column}: {int(blank.sum())} row(s) are empty. Only "
                f"{', '.join(NULLABLE_NUMERIC_COLUMNS)} may be blank "
                f"(tenure==0 customers).\n"
                f"      rows:    {_describe_rows(positions)}"
            )

        nonfinite = np.isinf(values.to_numpy(dtype="float64", na_value=0.0))
        if nonfinite.any():
            positions = list(np.flatnonzero(nonfinite))
            problems.append(
                f"  {column}: {len(positions)} row(s) are infinite. The "
                f"scaler cannot transform these and scikit-learn raises "
                f"mid-scoring.\n      rows:    {_describe_rows(positions)}"
            )

        negative = (values < 0).fillna(False).to_numpy()
        if negative.any():
            positions = list(np.flatnonzero(negative))
            problems.append(
                f"  {column}: {len(positions)} row(s) are negative. The API "
                f"rejects these (ge=0) and the batch path must agree.\n"
                f"      rows:    {_describe_rows(positions)}"
            )

    if problems:
        raise RuntimeError(
            "Input validation failed -- refusing to score. The pipeline's "
            "OneHotEncoder ignores unknown categories rather than erroring, "
            "so scoring this file would produce plausible-looking but wrong "
            "predictions instead of a failure.\n\n"
            + "\n".join(problems)
        )


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


# Distribution name -> import name, for the libraries the pickled pipeline is
# most sensitive to. The two differ for scikit-learn, which is why this map
# exists rather than a plain list.
_TRACKED_LIBRARIES = {
    "scikit-learn": "sklearn",
    "xgboost": "xgboost",
    "numpy": "numpy",
    "pandas": "pandas",
}


def _current_library_versions() -> dict[str, str]:
    """Installed versions of the libraries the pickled pipeline is most
    sensitive to. Broken out as its own function (rather than inlined
    into validate_environment_versions) purely so tests can monkeypatch
    it directly, without needing every exact version under test actually
    installed.

    Reads an already-imported module's __version__ when there is one, and
    falls back to installed-distribution metadata otherwise. Both halves
    earn their place. The module attribute is the more truthful answer --
    it is the copy that will actually unpickle the artifact, which is what
    this check is about, and it is what wins if a shadowed second install
    ever makes the two disagree. The metadata fallback is what lets this
    module stop importing scikit-learn and XGBoost purely to read a string:
    that import cost 559ms and 33ms of a 771ms `import config`, paid by
    every consumer including tests that never touch either library.
    """
    versions = {}
    for distribution, module_name in _TRACKED_LIBRARIES.items():
        module = sys.modules.get(module_name)
        version = getattr(module, "__version__", None) if module else None
        if version is None:
            try:
                version = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                continue  # not installed; nothing to compare against
        versions[distribution] = version
    return versions


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
    down). The hard gate lives in check_model_environment.py, which CI runs
    against the artifact before it is deployed; this function is the weaker
    check that remains appropriate in a live service's boot path. The two
    share _current_library_versions() so they can never disagree about what
    is installed.

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

    Checks two things: the declared feature_schema_version, and then the
    actual column set. The version catches same-names-different-meaning
    drift that a column comparison is blind to.
    """
    metadata = _load_metadata(metadata_path)

    schema_version = metadata.get("feature_schema_version")
    if schema_version is None:
        print(f"WARNING: {metadata_path} declares no 'feature_schema_version' "
              f"(artifact predates the check) -- validating columns only.")
    elif schema_version != SUPPORTED_FEATURE_SCHEMA_VERSION:
        raise RuntimeError(
            f"Feature schema version mismatch: {metadata_path} declares "
            f"{schema_version!r}, this code implements "
            f"{SUPPORTED_FEATURE_SCHEMA_VERSION!r}. The engineered columns may "
            f"carry the same names and different meanings, which the column "
            f"check below cannot detect. Retrain with the current "
            f"feature_engineering_telco.py, or check out the code that matches "
            f"the artifact."
        )

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
