#!/usr/bin/env bash
# Actually tests validate_environment_versions() against the real trained
# artifact, in two real throwaway environments -- not mocked dicts.
#
# v2: fixes a real bug in the first version. `uv sync --python <path>`
# does NOT install into an arbitrary venv at <path> -- it always targets
# the *project's own* .venv (or $UV_PROJECT_ENVIRONMENT), using --python
# only to pick which interpreter that project venv gets built with. So
# the first version silently synced your real .venv and left the /tmp
# venvs empty, hence "ModuleNotFoundError: No module named 'numpy'".
# Source: https://docs.astral.sh/uv/pip/environments/ -- "uv can also
# install into arbitrary ... environments, with the --python option" on
# `uv pip install`, specifically (the pip-compatible interface, not
# `uv sync`).
#
# Fix: export the lockfile to a plain requirements.txt, then use
# `uv pip install --python <path> -r ...` to actually target the /tmp
# venvs directly.
#
# Run this from your repo root, after you've re-run the notebook so
# model_metadata.json actually has a 'library_versions' key populated.

set -euo pipefail

if [ ! -f "model_metadata.json" ]; then
  echo "ERROR: model_metadata.json not found in $(pwd)."
  echo "Run this from the repo root, and re-run the notebook first if you haven't."
  exit 1
fi

if ! python3 -c "import json,sys; d=json.load(open('model_metadata.json')); sys.exit(0 if 'library_versions' in d else 1)"; then
  echo "ERROR: model_metadata.json has no 'library_versions' key."
  echo "Re-run the notebook (or at least the save cell) first, then retry."
  exit 1
fi

TRAINED_SKLEARN=$(python3 -c "import json; print(json.load(open('model_metadata.json'))['library_versions']['scikit-learn'])")
echo "Artifact was trained with scikit-learn ${TRAINED_SKLEARN}"
echo

# Export the locked dependency set once, share it between both venvs.
echo "=== Exporting locked dependencies from uv.lock ==="
uv export --format requirements.txt --no-emit-project --no-hashes --frozen -o /tmp/locked-requirements.txt -q
echo "wrote /tmp/locked-requirements.txt ($(wc -l < /tmp/locked-requirements.txt) lines)"
echo

# --- Control group: venv matching the exact locked versions ---------------
# Expectation: validate_environment_versions() prints NOTHING (no WARNING).
echo "=== CONTROL: venv with matching (locked) versions ==="
uv venv /tmp/control-venv --python 3.12 --clear -q
uv pip install --python /tmp/control-venv/bin/python -r /tmp/locked-requirements.txt -q
/tmp/control-venv/bin/python -c "
import config
print('--- calling validate_environment_versions() ---')
config.validate_environment_versions()
print('--- done (if nothing printed above besides these markers, no warning fired -- correct) ---')
"
echo

# --- Test group: venv with a deliberately OLDER scikit-learn --------------
# Expectation: validate_environment_versions() DOES print a WARNING
# mentioning scikit-learn, the trained version, and the installed version.
#
# NOTE: an earlier version of this script hardcoded a specific version
# number ("1.9.1") as the mismatch target without checking it actually
# exists on PyPI -- it didn't (1.9.0 is scikit-learn's current latest as
# of writing this), so `uv pip install` failed with "No solution found".
# Fixed by using a "<" constraint instead of a specific pin, so the
# resolver picks whatever real older version actually exists, rather
# than me guessing a version number that may or may not have been
# released.
echo "=== TEST: venv with scikit-learn<${TRAINED_SKLEARN} (deliberately older) ==="
uv venv /tmp/mismatch-venv --python 3.12 --clear -q
uv pip install --python /tmp/mismatch-venv/bin/python -r /tmp/locked-requirements.txt -q
uv pip install --python /tmp/mismatch-venv/bin/python "scikit-learn<${TRAINED_SKLEARN}" -q
INSTALLED_MISMATCH=$(/tmp/mismatch-venv/bin/python -c "import sklearn; print(sklearn.__version__)")
echo "Resolver actually installed: scikit-learn ${INSTALLED_MISMATCH}"
/tmp/mismatch-venv/bin/python -c "
import config
print('--- calling validate_environment_versions() ---')
config.validate_environment_versions()
print('--- done (a WARNING mentioning scikit-learn should have printed above) ---')
"
echo

# --- The other half of the real risk: does joblib.load even survive? ------
echo "=== Does joblib.load() of the REAL pickle survive the mismatch? ==="
/tmp/mismatch-venv/bin/python -c "
import joblib
try:
    model = joblib.load('xgboost_churn_pipeline.pkl')
    print('joblib.load() SUCCEEDED under the mismatched environment.')
    print('Worth then checking predict_proba() output against a known-good')
    print('prediction from the control venv, to rule out a SILENT behavior')
    print('change -- success does not necessarily mean identical predictions.')
except Exception as e:
    print(f'joblib.load() FAILED under the mismatch: {type(e).__name__}: {e}')
    print('This is the load-time crash the warning is meant to help you')
    print('catch *before* it happens in production.')
"

echo
echo "Cleanup: rm -rf /tmp/control-venv /tmp/mismatch-venv /tmp/locked-requirements.txt"
