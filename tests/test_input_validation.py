"""Tests for config.validate_input_frame and the API's non-finite handling.

Both consumers must reject the same inputs. api.py gets that from Pydantic;
telco_model.py had nothing at all, so a CSV exported from a slightly
different system could be scored end to end with no error and a silently
different answer -- the pipeline's OneHotEncoder uses handle_unknown='ignore',
so an unrecognised category becomes an all-zeros block indistinguishable
from "no information". A casing slip moves the shipped model's score for
DUMMY_CUSTOMER from 0.5700 to 0.1017, flipping the retention decision.

Note what is deliberately NOT tested here: implausibly large numbers. They
saturate harmlessly in a tree ensemble (tenure 10**15 scores the same as
tenure 1000), so no range check exists to test.

Run with: pytest tests/test_input_validation.py -v
"""

import json
import math
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import config
from config import CATEGORICAL_DOMAINS, NUMERIC_COLUMNS, validate_input_frame

REPO_ROOT = Path(__file__).resolve().parent.parent


def _valid_frame(n=3):
    """n identical valid rows, built from the same DUMMY_CUSTOMER both the
    startup validators and test_artifact.py use."""
    return pd.DataFrame([dict(config.DUMMY_CUSTOMER) for _ in range(n)])


def test_valid_frame_passes():
    validate_input_frame(_valid_frame())  # should not raise


def test_the_real_sample_input_passes():
    """simulated_new_customers.csv is what telco_model.py scores by default;
    if the validator rejected it the batch path would be dead on arrival."""
    df = pd.read_csv(REPO_ROOT / "simulated_new_customers.csv")
    validate_input_frame(df)  # should not raise


@pytest.mark.parametrize("column", sorted(CATEGORICAL_DOMAINS))
def test_unknown_category_rejected_for_every_categorical_column(column):
    """Every categorical column is checked, not just the ones that came to
    mind -- this parametrizes over the domain map itself, so a column added
    there is covered automatically."""
    df = _valid_frame()
    df.loc[df.index[1], column] = "definitely-not-a-real-value"
    with pytest.raises(RuntimeError, match="outside the trained categories"):
        validate_input_frame(df)


@pytest.mark.parametrize(
    "bad_value",
    ["month-to-month", "MONTH-TO-MONTH", "Two Year", "", "Monthly"],
    ids=["lowercased", "uppercased", "wrong-case-two-year", "empty", "renamed"],
)
def test_realistic_contract_corruptions_rejected(bad_value):
    """Each of these silently scores 0.1017 instead of 0.5700 for an
    otherwise-identical customer -- a flipped decision, no error."""
    df = _valid_frame()
    df.loc[df.index[0], "contract"] = bad_value
    with pytest.raises(RuntimeError, match="contract"):
        validate_input_frame(df)


def test_error_names_the_offending_rows_by_file_line():
    """Row numbers are 1-based and count the CSV header, so they match what
    a text editor shows when the user opens the file to fix it."""
    df = _valid_frame(5)
    df.loc[df.index[2], "contract"] = "nope"   # third data row -> file line 4
    with pytest.raises(RuntimeError) as exc:
        validate_input_frame(df)
    assert "rows:    4" in str(exc.value)


def test_all_problems_reported_in_one_pass():
    """A malformed file should be fixable in one pass, not one error at a
    time."""
    df = _valid_frame(4)
    df["monthlycharges"] = df["monthlycharges"].astype(object)
    df.loc[df.index[0], "contract"] = "nope"
    df.loc[df.index[1], "paymentmethod"] = "PayPal"
    df.loc[df.index[2], "monthlycharges"] = -5
    message = str(pytest.raises(RuntimeError, validate_input_frame, df).value)
    assert "contract" in message
    assert "paymentmethod" in message
    assert "negative" in message


def test_missing_columns_reported_together():
    df = _valid_frame().drop(columns=["contract", "tenure"])
    with pytest.raises(RuntimeError, match="missing 2 required column"):
        validate_input_frame(df)


@pytest.mark.parametrize("column", NUMERIC_COLUMNS)
def test_negative_numeric_rejected(column):
    """api.py rejects these with ge=0; the batch path must agree, or the two
    consumers make different decisions about the same customer."""
    df = _valid_frame()
    df[column] = df[column].astype(float)
    df.loc[df.index[0], column] = -1.0
    with pytest.raises(RuntimeError, match="negative"):
        validate_input_frame(df)


@pytest.mark.parametrize("value", [math.inf, -math.inf], ids=["inf", "-inf"])
def test_infinite_numeric_rejected(value):
    """scikit-learn raises mid-scoring on these, so the batch job would die
    partway through a file rather than before touching it."""
    df = _valid_frame()
    df["monthlycharges"] = df["monthlycharges"].astype(float)
    df.loc[df.index[0], "monthlycharges"] = value
    with pytest.raises(RuntimeError, match="infinite"):
        validate_input_frame(df)


def test_unparseable_numeric_rejected():
    df = _valid_frame()
    df["monthlycharges"] = df["monthlycharges"].astype(object)
    df.loc[df.index[0], "monthlycharges"] = "N/A"
    with pytest.raises(RuntimeError, match="not a number"):
        validate_input_frame(df)


def test_blank_totalcharges_is_allowed():
    """The 11 real customers with tenure==0 have a blank totalcharges, and
    the pipeline's SimpleImputer exists to fill exactly that. Rejecting it
    would reject legitimate data."""
    df = _valid_frame()
    df["totalcharges"] = df["totalcharges"].astype(object)
    df.loc[df.index[0], "totalcharges"] = ""
    validate_input_frame(df)  # should not raise


def test_blank_non_nullable_numeric_rejected():
    """tenure has no imputation story -- a blank there is a broken export."""
    df = _valid_frame()
    df["tenure"] = df["tenure"].astype(object)
    df.loc[df.index[0], "tenure"] = ""
    with pytest.raises(RuntimeError, match="empty"):
        validate_input_frame(df)


# ---------------------------------------------------------------------------
# The two consumers must agree on what is valid. config.CATEGORICAL_DOMAINS
# is the batch path's copy; api.Customer's Literal types are the API's. If
# they drift, the same customer gets accepted by one and rejected by the
# other -- exactly the silent divergence config.py exists to prevent.
# ---------------------------------------------------------------------------

def test_api_literals_and_config_domains_agree():
    import typing

    import api

    hints = typing.get_type_hints(api.Customer)
    for column, allowed in CATEGORICAL_DOMAINS.items():
        literal_values = typing.get_args(hints[column])
        assert set(literal_values) == set(allowed), (
            f"{column}: api.Customer allows {sorted(literal_values)} but "
            f"config.CATEGORICAL_DOMAINS allows {sorted(allowed)}"
        )


# ---------------------------------------------------------------------------
# Non-finite numbers through the API. Python's json module accepts Infinity
# and NaN on the way in but refuses to emit them, which is what made this
# reachable: Pydantic rejected the value correctly, then FastAPI's 422 body
# echoed it back and failed to serialize, turning a 422 into a 500.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value", [math.inf, -math.inf, math.nan], ids=["inf", "-inf", "nan"]
)
def test_api_rejects_non_finite_numbers_with_422(value):
    import api

    with TestClient(api.app) as client:
        body = json.dumps({**config.DUMMY_CUSTOMER, "monthlycharges": value})
        response = client.post(
            "/predict", content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 422
    assert "finite" in json.dumps(response.json())


def test_api_still_accepts_a_valid_customer():
    """Guards the exception handler and allow_inf_nan against over-reach."""
    import api

    with TestClient(api.app) as client:
        response = client.post("/predict", json=config.DUMMY_CUSTOMER)
    assert response.status_code == 200
    assert response.json()["churn_probability"] == pytest.approx(0.57, abs=1e-3)
