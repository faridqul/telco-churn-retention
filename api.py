import math
import warnings
from typing import Literal

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import (
    MODEL_PATH,
    load_threshold,
    validate_environment_versions,
    validate_feature_schema,
)
from feature_engineering_telco import engineer_features

from contextlib import asynccontextmanager

# The explanation layer is optional, and this is the only place that decides
# whether it is here. The production image copies in api.py, telco_model.py,
# config.py and feature_engineering_telco.py and nothing else (see the
# Dockerfile), so in a container these three modules do not exist -- and
# /predict, /health and the build-time checks must keep working exactly as
# they did. An unguarded import would take the whole service down for the
# sake of an endpoint it can run without.
#
# Only ImportError is caught. A module that is present and broken should fail
# the start, loudly, rather than be reported as "not installed".
try:
    import explain
    import narrate
    import narration_cache
except ImportError as _import_error:
    explain = narrate = narration_cache = None
    EXPLAIN_LAYER_PROBLEM = f"{type(_import_error).__name__}: {_import_error}"
else:
    EXPLAIN_LAYER_PROBLEM = None

# How many drivers /explain returns. Five, where the language model is shown
# three (narrate.NARRATION_TOP_N): the response is allowed to carry more of the
# model's own arithmetic than the sentence was written from.
EXPLAIN_TOP_N = 5

# The OpenAI SDK's defaults are a 600-second read timeout and two retries,
# which is reasonable for a batch and wrong for a request a browser is waiting
# on: one stalled upstream call would hold the request for half an hour. A
# normal call takes about two seconds. No SDK-level retry, because narrate()
# already retries once when a reply is rejected, so the worst case here is two
# attempts of fifteen seconds each.
LLM_TIMEOUT_SECONDS = 15.0
LLM_MAX_RETRIES = 0


class Customer(BaseModel):
    """Raw customer fields, matching the columns the pipeline was trained on
    (pre-feature-engineering). See feature_engineering_telco.py for the
    derived columns computed from these."""
    gender: Literal["Male", "Female"]
    seniorcitizen: int = Field(ge=0, le=1)
    partner: Literal["Yes", "No"]
    dependents: Literal["Yes", "No"]
    tenure: int = Field(ge=0)
    phoneservice: Literal["Yes", "No"]
    multiplelines: Literal["Yes", "No", "No phone service"]
    internetservice: Literal["DSL", "Fiber optic", "No"]
    onlinesecurity: Literal["Yes", "No", "No internet service"]
    onlinebackup: Literal["Yes", "No", "No internet service"]
    deviceprotection: Literal["Yes", "No", "No internet service"]
    techsupport: Literal["Yes", "No", "No internet service"]
    streamingtv: Literal["Yes", "No", "No internet service"]
    streamingmovies: Literal["Yes", "No", "No internet service"]
    contract: Literal["Month-to-month", "One year", "Two year"]
    paperlessbilling: Literal["Yes", "No"]
    paymentmethod: Literal[
        "Electronic check", "Mailed check",
        "Bank transfer (automatic)", "Credit card (automatic)"
    ]
    # allow_inf_nan=False because ge=0 lets Infinity through -- inf >= 0 is
    # True -- and it then reaches the scaler, which raises ValueError
    # mid-request and returns a 500 instead of a 422. NaN is worse: the
    # pipeline's SimpleImputer silently replaces it with the training
    # median, so a garbage input comes back as a confident prediction.
    monthlycharges: float = Field(ge=0, allow_inf_nan=False)
    totalcharges: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class PredictionResponse(BaseModel):
    churn_probability: float
    target_for_retention: bool
    threshold_used: float


class Driver(BaseModel):
    """One of the model's own reasons: arithmetic, not prose.

    `contribution` is the model's exact attribution in log-odds, unrounded.
    `value` and `vs_other_customers` are absent (null) when there is nothing
    true to say -- a value the customer does not have, or a field with no
    typical value to compare against.
    """
    field: str
    label: str
    value: str | int | float | None = None
    vs_other_customers: str | None = None
    direction: Literal["raises risk", "lowers risk"]
    contribution: float


class Reason(BaseModel):
    field: str
    direction: Literal["raises risk", "lowers risk"]


class Explanation(BaseModel):
    """The language model's accepted answer, exactly as it passed the guards."""
    risk_level: Literal["low", "moderate", "high", "very high"]
    reasons: list[Reason]
    summary: str


class ExplainMeta(BaseModel):
    """Where the explanation came from, or why there is none.

    `status` is the one field to branch on:
      ok          -- `explanation` is present and passed every guard.
      rejected    -- the model answered and every attempt was refused;
                     `rejection_type` names the guard that refused the last.
      unavailable -- no call could be made (no API key, or the openai package
                     is not installed) and nothing was cached; `detail` says
                     which.
      error       -- the call was made and failed (network, rate limit);
                     `detail` is the error's type.
    """
    status: Literal["ok", "rejected", "unavailable", "error"]
    detail: str | None = None
    rejection_type: str | None = None
    prompt_version: str
    model: str
    cache_hit: bool
    attempts: int
    protected_drivers_omitted: list[str]


class ExplainResponse(PredictionResponse):
    """A PredictionResponse with its reasons attached.

    Subclassed rather than restated, so the first three fields are /predict's
    by construction. `risk_level` and `drivers` are deterministic and always
    present; only `explanation` can be null.
    """
    risk_level: Literal["low", "moderate", "high", "very high"]
    drivers: list[Driver]
    explanation: Explanation | None
    meta: ExplainMeta


class _NarrationUnavailable(RuntimeError):
    """No live call can be made. Not an upstream failure: nothing was sent."""


class _NoLiveClient:
    """Stands in for the language-model client when one cannot be built.

    Handed to narrate() instead of short-circuiting before it, because
    narrate() checks the cache first and only then asks its client for
    anything. So a process with no API key still serves every answer it
    already has -- which makes "start it without the key" a free, cache-only
    mode -- and raises this only on a miss.
    """

    def __init__(self, reason: str | None):
        self.reason = reason or "narration is not configured"

    def complete(self, *args, **kwargs):
        raise _NarrationUnavailable(self.reason)


def _make_llm_client():
    """(client, None), or (None, why there isn't one). Never raises.

    Called once, at startup. The two ordinary reasons are the ones
    narrate.OpenAIClient already explains in a sentence each -- the `llm`
    dependency group is not installed, or OPENAI_API_KEY did not reach this
    process -- and neither is a reason to refuse to serve predictions.
    """
    if narrate is None:
        return None, EXPLAIN_LAYER_PROBLEM
    try:
        client = narrate.OpenAIClient(
            timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES,
        )
    except RuntimeError as error:
        return None, str(error)
    return client, None



model = None
threshold = None
# The language-model client, or None with the reason beside it. Decided once
# at startup rather than per request, so /health can report it and a
# misconfigured process does not rediscover the same mistake on every click.
llm_client = None
llm_problem = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: runs once, before the app starts accepting requests.
    global model, threshold, llm_client, llm_problem
    validate_feature_schema()  # fail fast on feature/model schema drift
    validate_environment_versions()  # warns (does not block) on library version drift
    threshold = load_threshold()
    print(f"Using threshold: {threshold}")
    model = joblib.load(MODEL_PATH)
    print("Model loaded.")
    llm_client, llm_problem = _make_llm_client()
    if explain is None:
        print(f"/explain is off: the explanation layer is not in this build "
              f"({EXPLAIN_LAYER_PROBLEM}).")
    elif llm_client is None:
        print(f"/explain will serve drivers and cached summaries only: {llm_problem}")
    else:
        print("/explain is on.")
    yield
    # Shutdown: nothing to clean up here, but this is where it'd go.


app = FastAPI(title="Telco Churn Prediction API", lifespan=lifespan)

# A browser refuses to let a page call an API on a different origin unless the
# API says it is allowed. frontend/index.html is opened from a file or a local
# static server, so it is always a different origin from this service --
# without this middleware its requests never arrive here at all, and it sees a
# network error rather than a response. Browsers only: curl, telco_model.py and
# the tests are unaffected either way.
#
# allow_origins=["*"] is appropriate for a demo API with no authentication:
# there are no cookies or credentials for another site to ride on, and /predict
# only scores a customer the caller typed in themselves. Narrow this to the
# frontend's real origin if the service ever gains auth.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _json_safe(value):
    """Replace non-finite floats with a string so a payload can be
    serialized. Recurses through the dicts and lists FastAPI builds its
    validation errors from.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)  # 'inf', '-inf', 'nan'
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


@app.exception_handler(RequestValidationError)
async def non_finite_safe_validation_handler(request: Request, exc: RequestValidationError):
    """Return FastAPI's normal 422 body, with non-finite inputs stringified.

    allow_inf_nan=False on the Customer model correctly rejects a body
    containing Infinity or NaN, but FastAPI's default error response echoes
    the offending value back under "input" -- and json.dumps refuses to
    serialize inf, so building the 422 raised ValueError and the client got
    a 500 instead. Python's json module *accepts* Infinity on the way in
    while refusing to emit it on the way out, which is what makes this
    reachable at all. Only the reporting is changed here; the rejection
    itself is Pydantic's.
    """
    return JSONResponse(status_code=422, content={"detail": _json_safe(exc.errors())})


@app.get("/health")
def health():
    # Three independent facts, so a page can decide what to offer before
    # anyone clicks. `explain_available`: the explanation layer is part of
    # this build, so /explain answers with drivers. `narration_available`: a
    # live call to the language model is possible. With the first true and the
    # second false, /explain still works -- it returns the drivers, and a
    # written summary only where one is already cached.
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "explain_available": explain is not None,
        "narration_available": llm_client is not None,
    }


def _score(customer: Customer) -> PredictionResponse:
    """The decision, made once, for every endpoint that reports one.

    /explain calls this as well as /predict rather than trusting the
    explanation's own copy of the number, so the two endpoints cannot return
    different decisions for the same customer.
    """
    # Both globals are needed below; checking only `model` would leave
    # `probability >= threshold` to raise a TypeError and surface as a 500.
    if model is None or threshold is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet.")

    row = pd.DataFrame([customer.model_dump()])
    row = engineer_features(row)

    # Reported at full precision, and compared at full precision. Rounding
    # the number that goes out while comparing the one that stayed behind
    # would let a response read 0.4 >= 0.4 alongside "false"; rounding
    # before the comparison instead would flag customers the batch scorer
    # does not, since it compares raw probabilities. The two paths have to
    # reach the same decision, so neither of them rounds.
    probability = float(model.predict_proba(row)[:, 1][0])
    flagged = probability >= threshold

    return PredictionResponse(
        churn_probability=probability,
        target_for_retention=flagged,
        threshold_used=threshold
    )


@app.post("/predict", response_model=PredictionResponse)
def predict(customer: Customer):
    return _score(customer)


@app.post("/explain", response_model=ExplainResponse)
def explain_prediction(customer: Customer):
    """Why this customer scored the way they did.

    Takes exactly what /predict takes and returns exactly what /predict
    returns, plus three things in decreasing order of certainty: `risk_level`
    and `drivers` (the model's own arithmetic -- free, offline, always
    present), and `explanation` (one or two sentences written by a language
    model and checked against those drivers -- about two seconds and a
    fraction of a cent on the first request, instant and free after that).

    `explanation` is null whenever there is no checked sentence to show, and
    `meta.status` says why. That is a 200, not an error: the numbers are still
    true. Only two things are a 503 -- no model, or a build without the
    explanation layer.
    """
    scored = _score(customer)
    if explain is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"The explanation layer is not part of this build "
                f"({EXPLAIN_LAYER_PROBLEM}). /predict is unaffected."
            ),
        )

    # Handed the model and threshold this process already holds. Left to its
    # defaults, explain_customer() would load a second copy of the pipeline
    # and re-read the threshold from disk -- twice the memory, and a second
    # place for the two to come apart. top_n=None because the protected
    # filter below runs on the full list: cutting to five first would let a
    # protected driver use up a slot.
    explanation = explain.explain_customer(
        customer.model_dump(), model=model, threshold=threshold, top_n=None,
    )
    if (
        explanation["churn_probability"] != scored.churn_probability
        or explanation["target_for_retention"] != scored.target_for_retention
    ):
        # Same reasoning as explain.verify_attribution(): a well-formed list
        # of reasons for a different number is worse than no reasons.
        raise HTTPException(
            status_code=500,
            detail=(
                "The explanation describes a different prediction from the "
                "one /predict reports for this customer, so it was not "
                "returned."
            ),
        )

    # narrate.narration_payload() is what decides which drivers a reader may
    # see: protected attributes removed (and named in
    # protected_drivers_omitted), zero contributions dropped, values worded.
    # Reused at five instead of reimplemented, so the first three drivers here
    # are exactly the three factors the language model is shown.
    shown = narrate.narration_payload(explanation, top_n=EXPLAIN_TOP_N)
    drivers = [
        Driver(
            field=factor["field"],
            label=factor["name"],
            value=factor.get("value"),
            vs_other_customers=factor.get("vs_other_customers"),
            direction=factor["direction"],
            contribution=explanation["contributions"][factor["field"]],
        )
        for factor in shown["factors"]
    ]

    status, detail, result = "ok", None, None
    # Opened per request, not once at startup: this handler runs in a worker
    # thread, and a sqlite3 connection refuses to be used from any thread but
    # the one that made it. A shared connection would fail on every lookup,
    # the cache would swallow the error as it is designed to, and every click
    # would quietly become a paid call. Opening is well under a millisecond.
    cache = narration_cache.from_env()
    try:
        result = narrate.narrate(
            explanation,
            client=llm_client if llm_client is not None else _NoLiveClient(llm_problem),
            cache=cache,
        )
    except _NarrationUnavailable as error:
        status, detail = "unavailable", str(error)
    except Exception as error:  # noqa: BLE001 -- the drivers are already in
        # hand and true; an upstream failure must not take them down with it.
        # Only the type goes to the caller: provider error messages can quote
        # part of the key. The full message goes to the server's own log.
        warnings.warn(
            f"/explain: the language-model call failed ({type(error).__name__}: "
            f"{error}); returning drivers without a summary.",
            RuntimeWarning,
            stacklevel=2,
        )
        status, detail = "error", type(error).__name__
    finally:
        cache.close()

    structured = result["structured"] if result is not None else None
    if result is not None and structured is None:
        status = "rejected"

    return ExplainResponse(
        **scored.model_dump(),
        risk_level=shown["risk_level"],
        drivers=drivers,
        explanation=structured,
        meta=ExplainMeta(
            status=status,
            detail=detail,
            rejection_type=result["final_rejection_type"] if result is not None else None,
            prompt_version=narrate.PROMPT_VERSION,
            model=narrate.DEFAULT_MODEL,
            cache_hit=bool(result and result.get("cache_hit")),
            attempts=len(result["attempts"]) if result is not None else 0,
            protected_drivers_omitted=shown["protected_drivers_omitted"],
        ),
    )
