# syntax=docker/dockerfile:1.7

# Telco churn API + batch scorer.
#
# One image serves both entrypoints. api.py and telco_model.py have an
# identical dependency set and share config.py and
# feature_engineering_telco.py, and the project's central invariant is that
# the two paths make the *same* decision: same model, same threshold, same
# `>=` comparison. Two images would duplicate every layer for no benefit
# while creating exactly the divergence that invariant exists to prevent.
#
#   docker build -t telco-churn .
#   docker run -p 8000:8000 telco-churn                 # API (default CMD)
#   docker run -v ./data:/data telco-churn python telco_model.py   # batch scorer
#
# The model is COPYed in, never trained here. xgboost_churn_pipeline.pkl and
# model_metadata.json are committed and byte-reproducible, and training needs
# the `notebook` dependency group (jupyter, matplotlib, seaborn, shap,
# kagglehub, scipy) which this image deliberately does not install.

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.12.5


# ---------------------------------------------------------------------------
# Stage 0: the uv binary, pinned.
# ---------------------------------------------------------------------------
# Given its own stage rather than referenced inline from the builder, because
# `COPY --from` cannot expand a build argument in an image reference -- only
# FROM can. Pinned rather than :latest: an unpinned installer would make the
# build non-reproducible in exactly the dimension this image exists to control.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv


# ---------------------------------------------------------------------------
# Stage 1: build the virtualenv.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

COPY --from=uv /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency manifests only, so this layer -- the expensive one -- is
# invalidated by a dependency change and not by an edit to api.py.
COPY pyproject.toml uv.lock ./

# --frozen fails the build if uv.lock is out of sync with pyproject.toml
# rather than silently re-resolving, which is the same posture CI takes. An
# image whose contents differ from the committed lockfile would defeat the
# point of pinning them.
#
# --no-dev drops the `dev` group (pytest, httpx: 34 packages -> 26). Verified
# by import audit: no runtime module -- api.py, telco_model.py, config.py,
# feature_engineering_telco.py, check_model_environment.py -- imports either.
# A production image has no business shipping a test runner.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# xgboost declares nvidia-nccl-cu13 as a hard dependency on Linux. It is
# 288 MB -- larger than xgboost, pandas and scikit-learn combined -- and it
# exists purely for GPU-distributed *training*, which a CPU inference
# container never reaches. Dropping the payload takes the image from ~900 MB
# to ~610 MB.
#
# Done here rather than by switching to the `xgboost-cpu` distribution on
# purpose: check_model_environment.py resolves versions via
# importlib.metadata.version("xgboost"), which raises PackageNotFoundError
# under xgboost-cpu, so that swap would fail the gate below. Done here rather
# than in pyproject.toml on purpose too -- this is a property of the image,
# not of the project, so uv.lock, CI and a local `uv sync` are untouched.
# The dist-info is left in place so the environment still describes itself
# the way uv.lock does.
#
# This locates the directory rather than hardcoding a path, and fails when it
# finds nothing. A bare `rm -rf` on a path that moved would exit 0 and quietly
# stop trimming; making absence an error means that if xgboost ever drops the
# dependency, someone deletes this block on purpose instead of carrying a
# no-op forever.
RUN set -eu; \
    nvidia_dir="$(find /app/.venv -type d -name nvidia -maxdepth 4 -print -quit)"; \
    if [ -z "$nvidia_dir" ]; then \
        echo "nvidia payload not found under /app/.venv -- this trim is now a no-op, remove it"; \
        exit 1; \
    fi; \
    echo "trimming $nvidia_dir ($(du -sh "$nvidia_dir" | cut -f1))"; \
    rm -rf "$nvidia_dir"


# ---------------------------------------------------------------------------
# Stage 2: runtime.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# api.py loads a pickle, and joblib.load executes arbitrary code on
# deserialization. A fixed high uid keeps file ownership predictable when a
# host directory is mounted for batch scoring.
RUN groupadd --system --gid 10001 appuser \
 && useradd --system --uid 10001 --gid appuser --create-home appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

# The runtime module set, listed explicitly rather than `COPY . .` so that
# what ships is a decision instead of whatever happened to be in the tree.
#
# campaign_profit.py is deliberately absent: it holds the profit formula the
# notebook uses to *choose* the threshold, and neither entrypoint imports it.
# The threshold that decision produced is already baked into
# model_metadata.json, which is what the container actually reads.
#
# --chmod=0644 is load-bearing, not tidiness. COPY preserves host file modes,
# and several of these are 0600 in the working tree from a restrictive local
# umask -- which meant appuser could not read them and the API died on its
# first request with PermissionError on config.py. Normalising the mode here
# makes the image independent of whatever umask the build host happens to
# have. Read-only for everyone: nothing in the container writes to /app.
COPY --chmod=0644 api.py telco_model.py config.py feature_engineering_telco.py ./
COPY --chmod=0644 check_model_environment.py ./

# The artifact. Committed and byte-reproducible, so copying it is what makes
# a built image and a fresh clone agree on every prediction.
COPY --chmod=0644 xgboost_churn_pipeline.pkl model_metadata.json ./

# The batch scorer's working directory, and the only writable path in the
# image -- /app is owned by root at mode 0644 so nothing the container runs
# can modify its own code or its model.
#
# Mounting a host directory here is the whole interface for real use:
#
#   docker run -v ./data:/data telco-churn python telco_model.py
#
# The mount shadows the sample input copied in below, which is the intended
# behaviour: you bring your own CSV, and the shipped one exists only so that
# a bare `docker run` with no mount still demonstrates the batch path.
RUN install -d -o appuser -g appuser -m 0755 /data
COPY --chmod=0644 --chown=appuser:appuser simulated_new_customers.csv /data/

# Point the batch scorer at /data by default. Without this, telco_model.py's
# defaults resolve relative to WORKDIR /app, and writing the output there
# fails with PermissionError under the non-root user -- correctly, since /app
# is meant to be read-only. Overridable per-run for any other layout.
ENV INPUT_PATH=/data/simulated_new_customers.csv \
    OUTPUT_PATH=/data/retention_campaign_targets.csv

USER appuser

# --- Build-time verification -------------------------------------------------
# Both checks run as appuser, after USER, so they also prove the unprivileged
# runtime user can actually read the artifact.

# The hard version gate. Exits non-zero when an installed library differs from
# model_metadata.json["library_versions"]. joblib/pickle gives no cross-version
# compatibility guarantee for scikit-learn or XGBoost objects, so a skew can
# mean a failed load or -- worse -- silently different predictions. Because
# this image pins its dependencies from uv.lock, running the gate here turns
# "this image cannot load its own artifact" from a runtime surprise at first
# request into a build failure.
RUN python check_model_environment.py

# Stronger than the version gate, and complementary to it: the gate proves the
# versions match, this proves the pickle actually loads and reproduces its
# recorded prediction. Catches a corrupt or mismatched .pkl that version
# equality cannot see. Mirrors tests/test_artifact.py, which cannot run here
# because the image has no pytest.
RUN python - <<'PY'
import joblib, json, pandas as pd, config
from feature_engineering_telco import engineer_features

expected = json.load(open(config.METADATA_PATH))["dummy_customer_score"]
model = joblib.load(config.MODEL_PATH)
actual = float(model.predict_proba(
    engineer_features(pd.DataFrame([config.DUMMY_CUSTOMER])))[:, 1][0])

assert abs(actual - expected) < 1e-9, (
    f"artifact smoke test failed: DUMMY_CUSTOMER scored {actual!r}, "
    f"model_metadata.json records {expected!r}")
print(f"OK: artifact loads and reproduces dummy_customer_score ({actual}).")
PY
# -----------------------------------------------------------------------------

EXPOSE 8000

# No curl in the slim base, and adding one for a healthcheck is not worth the
# extra surface. /health reports model_loaded, which is only True once the
# lifespan handler has finished loading the pickle -- so this distinguishes
# "process is up" from "ready to answer", and start-period covers the load.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# 0.0.0.0 so the port is reachable from outside the container. No --reload:
# that is a development convenience and it would double memory by running a
# reloader parent alongside the worker.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
