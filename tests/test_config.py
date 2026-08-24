"""Tests for config.validate_feature_schema, config.load_threshold, and
config.validate_environment_versions.

Run with: pytest tests/test_config.py -v
"""

import json

import pytest

import config
from config import DEFAULT_THRESHOLD, load_threshold, validate_feature_schema

# Copied verbatim from the real model_metadata.json's feature_columns list,
# so this test can't silently drift from the actual contract.
REAL_FEATURE_COLUMNS = [
    "gender", "seniorcitizen", "partner", "dependents", "tenure",
    "phoneservice", "multiplelines", "internetservice", "onlinesecurity",
    "onlinebackup", "deviceprotection", "techsupport", "streamingtv",
    "streamingmovies", "contract", "paperlessbilling", "paymentmethod",
    "monthlycharges", "totalcharges", "total_services", "is_auto_pay",
    "family_tie", "contractvstenure", "average_monthly_charges",
    "charge_change_ratio",
]


def test_validate_feature_schema_passes_with_matching_metadata(tmp_path):
    metadata = {"feature_columns": REAL_FEATURE_COLUMNS}
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(metadata))
    validate_feature_schema(str(path))  # should not raise


def test_validate_feature_schema_raises_on_missing_column(tmp_path):
    """Simulates a model trained on a column that engineer_features() no
    longer produces (e.g. it was renamed or deleted from the code)."""
    metadata = {"feature_columns": REAL_FEATURE_COLUMNS + ["some_deleted_feature"]}
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(metadata))
    with pytest.raises(RuntimeError, match="Feature schema mismatch"):
        validate_feature_schema(str(path))


def test_validate_feature_schema_raises_on_extra_column(tmp_path):
    """Simulates engineer_features() producing a new column the currently
    loaded model was never trained on."""
    incomplete_columns = [c for c in REAL_FEATURE_COLUMNS if c != "charge_change_ratio"]
    metadata = {"feature_columns": incomplete_columns}
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(metadata))
    with pytest.raises(RuntimeError, match="Feature schema mismatch"):
        validate_feature_schema(str(path))


# ---------------------------------------------------------------------------
# load_threshold -- the missing-metadata policy is deliberate and split:
# a metadata FILE that is missing or unparseable is fatal (RuntimeError with
# a readable message), because without it nothing can confirm the pickle
# next to it is the one the code expects. A malformed VALUE inside a
# readable file degrades to DEFAULT_THRESHOLD, because the model is probably
# fine there and a sane default beats an outage.
#
# The previous "missing file falls back to DEFAULT_THRESHOLD" test asserted
# a property the system did not have: both consumers call the validators
# first, and those opened the same file and raised FileNotFoundError three
# lines earlier, so load_threshold's fallback was never reached in
# production. It has been replaced by the two tests below.
# ---------------------------------------------------------------------------

def test_load_threshold_reads_valid_metadata(tmp_path):
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"threshold": 0.37}))
    assert load_threshold(str(path)) == pytest.approx(0.37)


def test_load_threshold_raises_readable_error_when_file_missing(tmp_path):
    """No metadata file at all (e.g. fresh clone, notebook never run) is
    fatal by design -- but with a message naming the file and saying how to
    regenerate it, not a bare FileNotFoundError from inside json.load."""
    missing_path = tmp_path / "does_not_exist.json"
    with pytest.raises(RuntimeError, match="Model metadata not found"):
        load_threshold(str(missing_path))


def test_load_threshold_raises_readable_error_on_corrupt_json(tmp_path):
    """A truncated or hand-mangled file is fatal for the same reason, and
    must not surface as a raw JSONDecodeError either."""
    path = tmp_path / "meta.json"
    path.write_text('{"threshold": 0.4')  # truncated
    with pytest.raises(RuntimeError, match="not valid JSON"):
        load_threshold(str(path))


def test_load_threshold_falls_back_when_key_missing(tmp_path):
    """Metadata file exists but has no "threshold" key (e.g. an older
    metadata schema, or a hand-edited file)."""
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"model": "XGBoost (Tuned)"}))
    assert load_threshold(str(path)) == DEFAULT_THRESHOLD


@pytest.mark.parametrize(
    "bad_value, raised_before",
    [
        ("not-a-number", "ValueError"),
        (None, "TypeError"),      # what a hand-edit or templating step emits
        ([0.4], "TypeError"),     # a value wrapped in a list
        ({"value": 0.4}, "TypeError"),
    ],
    ids=["string", "null", "list", "object"],
)
def test_load_threshold_falls_back_on_unusable_value(tmp_path, bad_value, raised_before):
    """A readable file whose "threshold" can't become a float degrades to
    DEFAULT_THRESHOLD rather than crashing startup.

    Only the string case used to pass. float(None) and float([0.4]) raise
    TypeError, which the original except clause did not catch, so a
    metadata file containing `{"threshold": null}` took the API down at
    startup -- and null is a likelier corruption than an uncastable string,
    since it's what any writer emits for a missing value.
    """
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"threshold": bad_value}))
    assert load_threshold(str(path)) == DEFAULT_THRESHOLD


# ---------------------------------------------------------------------------
# validate_environment_versions -- joblib/pickle ties a Pipeline's
# serialized state to the exact scikit-learn/XGBoost version that created
# it, so a version drift between training and runtime is worth surfacing.
# This is a warn-only detection control, never a fatal one: it must not
# raise under any input here, only print. _current_library_versions is
# monkeypatched throughout so these tests don't depend on any particular
# library version actually being installed.
# ---------------------------------------------------------------------------

FAKE_CURRENT_VERSIONS = {
    "scikit-learn": "1.9.2",
    "xgboost": "3.4.1",
    "numpy": "2.5.2",
    "pandas": "3.0.5",
}


def test_validate_environment_versions_no_warning_when_versions_match(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(config, "_current_library_versions", lambda: FAKE_CURRENT_VERSIONS)
    metadata = {"library_versions": FAKE_CURRENT_VERSIONS}
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(metadata))
    config.validate_environment_versions(str(path))  # should not raise
    assert "WARNING" not in capsys.readouterr().out


def test_validate_environment_versions_warns_but_never_raises_on_mismatch(
    tmp_path, monkeypatch, capsys
):
    """Covers a real, plausible drift (e.g. an unpinned '>=' dependency in
    pyproject.toml pulling a newer scikit-learn after retraining). Must
    warn loudly but must NOT raise -- this is a detection control, not a
    gate; a hard block belongs in CI, not in the live API's boot path."""
    monkeypatch.setattr(config, "_current_library_versions", lambda: FAKE_CURRENT_VERSIONS)
    trained_versions = {**FAKE_CURRENT_VERSIONS, "scikit-learn": "2.0.0"}
    metadata = {"library_versions": trained_versions}
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(metadata))
    config.validate_environment_versions(str(path))  # should not raise
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "scikit-learn" in out


def test_validate_environment_versions_warns_even_on_patch_only_difference(
    tmp_path, monkeypatch, capsys
):
    """Deliberate design choice: this compares full version strings, not
    just major.minor, and doesn't try to guess which differences are
    'safe' -- that guessing is exactly what a previous, more complex
    version of this function got subtly wrong. A patch-level difference
    still gets reported; it's just a warning, so the cost of a false
    positive here is low."""
    monkeypatch.setattr(config, "_current_library_versions", lambda: FAKE_CURRENT_VERSIONS)
    trained_versions = {**FAKE_CURRENT_VERSIONS, "xgboost": "3.4.0"}
    metadata = {"library_versions": trained_versions}
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(metadata))
    config.validate_environment_versions(str(path))  # should not raise
    assert "WARNING" in capsys.readouterr().out


def test_validate_environment_versions_skips_when_key_missing(tmp_path, monkeypatch, capsys):
    """model_metadata.json trained before this check existed won't have a
    'library_versions' key -- must degrade to a warning, not crash
    startup."""
    monkeypatch.setattr(config, "_current_library_versions", lambda: FAKE_CURRENT_VERSIONS)
    metadata = {"threshold": 0.4}
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(metadata))
    config.validate_environment_versions(str(path))  # should not raise
    assert "WARNING" in capsys.readouterr().out


def test_validate_environment_versions_ignores_untracked_library(
    tmp_path, monkeypatch, capsys
):
    """A library recorded in metadata that the current code doesn't track
    (e.g. metadata from a newer schema version) shouldn't be reported as
    a mismatch -- just skipped."""
    monkeypatch.setattr(config, "_current_library_versions", lambda: FAKE_CURRENT_VERSIONS)
    trained_versions = {**FAKE_CURRENT_VERSIONS, "shap": "0.52.0"}
    metadata = {"library_versions": trained_versions}
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(metadata))
    config.validate_environment_versions(str(path))  # should not raise
    assert "WARNING" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "bad_library_versions",
    [
        ["scikit-learn==1.9.0"],          # a list of pinned strings
        "1.9.0",                          # a bare version string
        42,                               # a number
    ],
    ids=["list", "string", "number"],
)
def test_validate_environment_versions_never_raises_on_malformed_field(
    tmp_path, monkeypatch, capsys, bad_library_versions
):
    """The docstring promises "warn -- never raise". It used to raise
    AttributeError on any 'library_versions' that wasn't a dict, because it
    called .items() on it unconditionally. A confident docstring asserting
    a safety property the code doesn't enforce is worse than no docstring.
    """
    monkeypatch.setattr(config, "_current_library_versions", lambda: FAKE_CURRENT_VERSIONS)
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"library_versions": bad_library_versions}))
    config.validate_environment_versions(str(path))  # must not raise
    assert "WARNING" in capsys.readouterr().out


def test_validate_environment_versions_never_raises_when_file_missing(
    tmp_path, monkeypatch, capsys
):
    """Missing metadata is fatal for the project, but not *here* -- this is
    a detection control, and validate_feature_schema() is what both
    consumers call first to enforce the fatal policy. This function warns
    and returns rather than raising a second, redundant error.
    """
    monkeypatch.setattr(config, "_current_library_versions", lambda: FAKE_CURRENT_VERSIONS)
    config.validate_environment_versions(str(tmp_path / "gone.json"))  # must not raise
    assert "WARNING" in capsys.readouterr().out


def test_validate_environment_versions_never_raises_on_corrupt_json(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(config, "_current_library_versions", lambda: FAKE_CURRENT_VERSIONS)
    path = tmp_path / "meta.json"
    path.write_text("{not json")
    config.validate_environment_versions(str(path))  # must not raise
    assert "WARNING" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# validate_feature_schema -- the fatal side of the missing-metadata policy.
# Every failure it reports should be a readable RuntimeError explaining what
# to do, not a raw exception leaking from json.load or a dict lookup.
# ---------------------------------------------------------------------------

def test_validate_feature_schema_raises_readable_error_when_file_missing(tmp_path):
    """A fresh clone with no model_metadata.json is the case both consumers
    hit first, so this message is the one a new user actually sees."""
    with pytest.raises(RuntimeError, match="Model metadata not found"):
        validate_feature_schema(str(tmp_path / "does_not_exist.json"))


def test_validate_feature_schema_raises_readable_error_on_corrupt_json(tmp_path):
    path = tmp_path / "meta.json"
    path.write_text('{"feature_columns": [')
    with pytest.raises(RuntimeError, match="not valid JSON"):
        validate_feature_schema(str(path))


def test_validate_feature_schema_raises_readable_error_when_key_missing(tmp_path):
    """Used to surface as a bare KeyError('feature_columns'), inconsistent
    with the readable RuntimeError this function raises for every other
    schema problem."""
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"threshold": 0.4}))
    with pytest.raises(RuntimeError, match="no 'feature_columns' field"):
        validate_feature_schema(str(path))


# --- feature_schema_version (a mechanism now, not just a recorded string) ---

def _metadata_with(tmp_path, **overrides):
    """Real metadata with fields replaced, written to a temp file."""
    with open(config.METADATA_PATH) as f:
        data = json.load(f)
    data.update(overrides)
    path = tmp_path / "model_metadata.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_schema_version_mismatch_is_fatal(tmp_path):
    """Same columns, different meaning is the case the column check cannot
    see -- a corrected formula or changed unit keeps every name intact. The
    declared version is the only signal, so a mismatch has to stop startup.
    """
    path = _metadata_with(tmp_path, feature_schema_version="2.0")
    with pytest.raises(RuntimeError, match="Feature schema version mismatch"):
        config.validate_feature_schema(path)


def test_matching_schema_version_passes(tmp_path):
    path = _metadata_with(
        tmp_path, feature_schema_version=config.SUPPORTED_FEATURE_SCHEMA_VERSION
    )
    config.validate_feature_schema(path)


def test_absent_schema_version_warns_but_still_checks_columns(tmp_path, capsys):
    """An artifact predating the check should still be usable -- degrade to
    the column comparison rather than refusing to start.
    """
    with open(config.METADATA_PATH) as f:
        data = json.load(f)
    data.pop("feature_schema_version", None)
    path = tmp_path / "model_metadata.json"
    path.write_text(json.dumps(data))

    config.validate_feature_schema(str(path))
    assert "feature_schema_version" in capsys.readouterr().out
