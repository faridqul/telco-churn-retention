import math
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



model = None
threshold = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: runs once, before the app starts accepting requests.
    global model, threshold
    validate_feature_schema()  # fail fast on feature/model schema drift
    validate_environment_versions()  # warns (does not block) on library version drift
    threshold = load_threshold()
    print(f"Using threshold: {threshold}")
    model = joblib.load(MODEL_PATH)
    print("Model loaded.")
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
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/predict", response_model=PredictionResponse)
def predict(customer: Customer):
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
