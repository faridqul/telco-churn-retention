from typing import Literal

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import MODEL_PATH, load_threshold, validate_feature_schema
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
    monthlycharges: float = Field(ge=0)
    totalcharges: float | None = Field(default=None, ge=0)


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
    threshold = load_threshold()
    print(f"Using threshold: {threshold}")
    model = joblib.load(MODEL_PATH)
    print("Model loaded.")
    yield
    # Shutdown: nothing to clean up here, but this is where it'd go.


app = FastAPI(title="Telco Churn Prediction API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/predict", response_model=PredictionResponse)
def predict(customer: Customer):
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet.")

    row = pd.DataFrame([customer.model_dump()])
    row = engineer_features(row)

    probability = float(model.predict_proba(row)[:, 1][0])
    flagged = probability >= threshold

    return PredictionResponse(
        churn_probability=round(probability, 4),
        target_for_retention=flagged,
        threshold_used=threshold
    )
