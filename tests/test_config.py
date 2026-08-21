"""Tests for config.validate_feature_schema, config.load_threshold, and
config.validate_environment_versions.

Run with: pytest test_config.py -v
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
# load_threshold -- the fallback path exists specifically so a missing or
# malformed metadata file degrades to DEFAULT_THRESHOLD instead of crashing
# the API/batch script at startup. That contract was previously untested.
# ---------------------------------------------------------------------------

def test_load_threshold_reads_valid_metadata(tmp_path):
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"threshold": 0.37}))
    assert load_threshold(str(path)) == pytest.approx(0.37)


def test_load_threshold_falls_back_when_file_missing(tmp_path):
    """No metadata file at all (e.g. fresh clone, notebook never run) must
    not raise -- it should degrade to DEFAULT_THRESHOLD."""
    missing_path = tmp_path / "does_not_exist.json"
    assert load_threshold(str(missing_path)) == DEFAULT_THRESHOLD


def test_load_threshold_falls_back_when_key_missing(tmp_path):
    """Metadata file exists but has no "threshold" key (e.g. an older
    metadata schema, or a hand-edited file)."""
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"model": "XGBoost (Tuned)"}))
    assert load_threshold(str(path)) == DEFAULT_THRESHOLD


def test_load_threshold_falls_back_when_value_not_castable_to_float(tmp_path):
    """A "threshold" value that can't be cast to float (e.g. corrupted or
    hand-edited file) should fall back, not raise ValueError."""
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"threshold": "not-a-number"}))
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
