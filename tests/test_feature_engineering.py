"""Unit tests for feature_engineering_telco.engineer_features.

These test the feature-engineering function in isolation -- no model, no
API, no notebook. They check that the code does what it's supposed to do,
not whether the model's predictions are accurate (that's what ROC-AUC /
model_metadata.json are for).

Run with: pytest tests/test_feature_engineering.py -v
"""

import numpy as np
import pandas as pd
import pytest

from feature_engineering_telco import engineer_features


def make_customer(**overrides) -> pd.DataFrame:
    """Builds a single-row DataFrame of a 'normal' customer, with any field
    overridden by keyword. Keeps each test focused on the one field it's
    actually exercising instead of restating all 19 columns every time."""
    base = {
        "gender": "Female",
        "seniorcitizen": 0,
        "partner": "Yes",
        "dependents": "No",
        "tenure": 12,
        "phoneservice": "Yes",
        "multiplelines": "No",
        "internetservice": "Fiber optic",
        "onlinesecurity": "No",
        "onlinebackup": "No",
        "deviceprotection": "No",
        "techsupport": "No",
        "streamingtv": "No",
        "streamingmovies": "No",
        "contract": "Month-to-month",
        "paperlessbilling": "Yes",
        "paymentmethod": "Electronic check",
        "monthlycharges": 70.0,
        "totalcharges": 840.0,  # roughly 70 * 12, i.e. a stable spender
    }
    base.update(overrides)
    return pd.DataFrame([base])


# ---------------------------------------------------------------------------
# total_services
# ---------------------------------------------------------------------------

def test_total_services_counts_only_yes():
    row = make_customer(
        onlinesecurity="Yes", onlinebackup="Yes", deviceprotection="No",
        techsupport="No internet service", streamingtv="Yes", streamingmovies="No",
    )
    result = engineer_features(row)
    assert result["total_services"].iloc[0] == 3


def test_total_services_zero_when_no_addons():
    row = make_customer(
        onlinesecurity="No", onlinebackup="No", deviceprotection="No internet service",
        techsupport="No internet service", streamingtv="No internet service",
        streamingmovies="No internet service",
    )
    result = engineer_features(row)
    assert result["total_services"].iloc[0] == 0


def test_total_services_max_when_all_addons():
    row = make_customer(
        onlinesecurity="Yes", onlinebackup="Yes", deviceprotection="Yes",
        techsupport="Yes", streamingtv="Yes", streamingmovies="Yes",
    )
    result = engineer_features(row)
    assert result["total_services"].iloc[0] == 6


# ---------------------------------------------------------------------------
# is_auto_pay
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payment_method,expected", [
    ("Bank transfer (automatic)", 1),
    ("Credit card (automatic)", 1),
    ("Electronic check", 0),
    ("Mailed check", 0),
])
def test_is_auto_pay_flag(payment_method, expected):
    row = make_customer(paymentmethod=payment_method)
    result = engineer_features(row)
    assert result["is_auto_pay"].iloc[0] == expected


# ---------------------------------------------------------------------------
# family_tie
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("partner,dependents,expected", [
    ("Yes", "No", 1),
    ("No", "Yes", 1),
    ("Yes", "Yes", 1),
    ("No", "No", 0),
])
def test_family_tie(partner, dependents, expected):
    row = make_customer(partner=partner, dependents=dependents)
    result = engineer_features(row)
    assert result["family_tie"].iloc[0] == expected


# ---------------------------------------------------------------------------
# contractvstenure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("contract,tenure,expected", [
    ("Month-to-month", 10, 10),   # multiplier 1
    ("One year", 10, 20),         # multiplier 2
    ("Two year", 10, 30),         # multiplier 3
])
def test_contractvstenure_multiplier(contract, tenure, expected):
    row = make_customer(contract=contract, tenure=tenure)
    result = engineer_features(row)
    assert result["contractvstenure"].iloc[0] == expected


# ---------------------------------------------------------------------------
# average_monthly_charges / charge_change_ratio -- the two edge cases that
# motivated this file in the first place.
# ---------------------------------------------------------------------------

def test_new_customer_tenure_zero_falls_back_to_monthly_charges():
    """A brand-new customer (tenure=0) can't have a historical average, so
    the function should fall back to their current monthly charge instead
    of dividing by zero."""
    row = make_customer(tenure=0, totalcharges=0.0, monthlycharges=55.0)
    result = engineer_features(row)
    assert result["average_monthly_charges"].iloc[0] == 55.0
    assert np.isfinite(result["average_monthly_charges"].iloc[0])


def test_totalcharges_none_with_positive_tenure_does_not_crash():
    """totalcharges can be missing (11 rows in the raw Kaggle data, and
    api.py's Customer model allows totalcharges=None). This must not raise,
    even though tenure > 0 would normally trigger the totalcharges/tenure
    division."""
    row = make_customer(tenure=5, totalcharges=None, monthlycharges=85.5)
    result = engineer_features(row)  # should not raise
    # average_monthly_charges legitimately can't be computed -> NaN is
    # correct/expected here, not a bug.
    assert pd.isna(result["average_monthly_charges"].iloc[0])
    # charge_change_ratio's own zero/NaN guard should still catch this and
    # default sensibly rather than propagating NaN further.
    assert result["charge_change_ratio"].iloc[0] == 1.0


def test_average_monthly_charges_normal_customer():
    row = make_customer(tenure=10, totalcharges=1000.0, monthlycharges=110.0)
    result = engineer_features(row)
    assert result["average_monthly_charges"].iloc[0] == pytest.approx(100.0)


def test_charge_change_ratio_reflects_price_increase():
    # Historical average is 100/mo, current bill is 110 -> ratio > 1
    row = make_customer(tenure=10, totalcharges=1000.0, monthlycharges=110.0)
    result = engineer_features(row)
    assert result["charge_change_ratio"].iloc[0] == pytest.approx(1.1)


def test_charge_change_ratio_defaults_when_average_is_zero():
    # tenure > 0 but totalcharges = 0 -> average_monthly_charges = 0,
    # which should trip the ratio's own zero-guard rather than divide by zero.
    row = make_customer(tenure=10, totalcharges=0.0, monthlycharges=50.0)
    result = engineer_features(row)
    assert result["average_monthly_charges"].iloc[0] == 0.0
    assert result["charge_change_ratio"].iloc[0] == 1.0


# ---------------------------------------------------------------------------
# Function should not mutate its input (engineer_features does df.copy()
# internally -- this locks that contract in, since api.py and the notebook
# both rely on being able to call it without side effects on the original).
# ---------------------------------------------------------------------------

def test_does_not_mutate_input_dataframe():
    row = make_customer()
    original_columns = list(row.columns)
    engineer_features(row)
    assert list(row.columns) == original_columns
