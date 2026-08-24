"""Tests for the CI version gate.

The point of these is narrow but important: a gate that cannot fail is
indistinguishable from no gate at all, and "no gate" is the exact defect this
script was written to close. So most of what follows drives the failure paths
rather than the happy one.
"""
import json

import pytest

import check_model_environment as gate
import config


@pytest.fixture
def metadata_file(tmp_path):
    """Writes a metadata file with whatever library_versions we hand it,
    and returns the path.
    """
    def _write(library_versions, **extra):
        data = {"feature_columns": ["a"], **extra}
        if library_versions is not None:
            data["library_versions"] = library_versions
        path = tmp_path / "model_metadata.json"
        path.write_text(json.dumps(data))
        return str(path)
    return _write


def test_real_artifact_matches_this_environment():
    """The committed metadata and the installed libraries agree. If this
    fails, the repository itself is in the state the gate exists to catch.
    """
    assert gate.check_environment() == []


def test_a_version_mismatch_is_reported(metadata_file, monkeypatch):
    monkeypatch.setattr(
        config, "_current_library_versions", lambda: {"scikit-learn": "1.9.0"}
    )
    problems = gate.check_environment(metadata_file({"scikit-learn": "1.0.0"}))
    assert len(problems) == 1
    assert "scikit-learn" in problems[0]
    assert "1.0.0" in problems[0] and "1.9.0" in problems[0]


def test_gate_reads_the_same_versions_the_service_does(metadata_file, monkeypatch):
    """Parity, not duplication. The gate must resolve versions through
    config._current_library_versions() -- if it kept its own list, CI could
    pass while the running service disagreed, which is worse than no gate.
    """
    monkeypatch.setattr(
        config, "_current_library_versions", lambda: {"xgboost": "9.9.9"}
    )
    assert gate.check_environment(metadata_file({"xgboost": "9.9.9"})) == []
    assert gate.check_environment(metadata_file({"xgboost": "3.4.1"})) != []


def test_library_the_service_does_not_track_is_still_checked(metadata_file):
    """fastapi isn't in _current_library_versions(), so without the
    importlib fallback a wrong version here would be skipped silently.
    """
    problems = gate.check_environment(metadata_file({"fastapi": "0.0.1"}))
    assert len(problems) == 1
    assert "fastapi" in problems[0]


def test_uninstalled_library_is_a_failure_not_a_skip(metadata_file):
    problems = gate.check_environment(
        metadata_file({"a-library-that-does-not-exist": "1.0"})
    )
    assert len(problems) == 1
    assert "not installed" in problems[0]


def test_missing_library_versions_block_fails(metadata_file):
    """The running service treats this as 'skip, warn'. CI must not: an
    artifact that records nothing about its environment cannot be verified,
    and unverifiable is not the same as fine.
    """
    problems = gate.check_environment(metadata_file(None))
    assert len(problems) == 1
    assert "library_versions" in problems[0]


@pytest.mark.parametrize(
    "bad_value", [["scikit-learn==1.9.0"], "scikit-learn==1.9.0", 42],
    ids=["list", "string", "int"],
)
def test_library_versions_of_the_wrong_type_fails(metadata_file, bad_value):
    problems = gate.check_environment(metadata_file(bad_value))
    assert len(problems) == 1


def test_unreadable_metadata_fails(tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json")
    assert gate.check_environment(str(corrupt)) != []
    assert gate.check_environment(str(tmp_path / "absent.json")) != []


def test_main_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(gate, "check_environment", lambda: [])
    assert gate.main() == gate.EXIT_OK

    monkeypatch.setattr(gate, "check_environment", lambda: ["xgboost: boom"])
    assert gate.main() == gate.EXIT_MISMATCH
    # The failure output has to name the offending library, or a red build
    # tells whoever sees it nothing actionable.
    assert "xgboost: boom" in capsys.readouterr().out


def test_every_library_in_the_artifact_gets_reported(metadata_file, monkeypatch):
    """One mismatch must not mask the others -- a build that fixes the first
    problem and re-fails on the second wastes a full CI cycle each time.
    """
    monkeypatch.setattr(
        config,
        "_current_library_versions",
        lambda: {"numpy": "2.5.2", "pandas": "3.0.5"},
    )
    problems = gate.check_environment(
        metadata_file({"numpy": "1.0.0", "pandas": "2.0.0"})
    )
    assert len(problems) == 2
