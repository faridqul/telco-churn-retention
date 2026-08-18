"""Tests for config.validate_feature_schema and config.load_threshold.

Run with: pytest test_config.py -v
"""

import json

import pytest

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
