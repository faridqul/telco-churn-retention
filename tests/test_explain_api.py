"""Tests for POST /explain. No API key, no network, no cost.

/explain is /predict plus the reasons, and it is the first endpoint in this
project that can cost money, be slow, and legitimately have no answer. What
is pinned here, weighted toward the failures that would be silent:

  1. THE SAME DECISION AS /predict. Both endpoints report a probability and a
     decision for the same body. If they could differ, a page showing one
     beside the other would contradict itself with two confident numbers.
     Asserted for the pinned demo customer and for every row of
     simulated_new_customers.csv, with `==`, not approx.

  2. NOTHING IS LOST WHEN THE SENTENCE IS. No key, a rejected reply and a
     failed upstream call are three different reasons for `explanation` to be
     null, and all three are a 200 with the drivers intact. Only a missing
     model and a build without the explanation layer are a 503.

  3. A PROTECTED ATTRIBUTE NEVER REACHES A READER. Not in `drivers`, not in
     what the language model is sent -- and its omission is named rather than
     hidden.

  4. THE CACHE WORKS THROUGH THE REAL ROUTE. The handler runs in a worker
     thread, where a sqlite3 connection made elsewhere raises on first use;
     the cache swallows that by design, so a wrong connection lifetime shows
     up as nothing at all except a bill. The test goes through TestClient for
     exactly that reason.

  5. THE CONTAINER STILL STARTS. The image holds api.py, config.py and
     feature_engineering_telco.py and none of explain.py, narrate.py or
     narration_cache.py. The last test imports api.py from a directory laid
     out that way.

The churn model here is the real committed pipeline -- explain_customer()
needs its preprocessor and booster, so DummyModel cannot stand in -- and the
language model is the scripted FakeLLM from tests/conftest.py. Tests that need
the artifact skip when it is absent, as tests/test_explain.py does.

Run with: pytest tests/test_explain_api.py -v
"""

import contextlib
import json
import os
import shutil
import subprocess
import sys
import typing
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api as api_module
import config
import explain
import narrate
import narration_cache
from tests.conftest import FakeLLM

REPO_ROOT = Path(__file__).resolve().parent.parent

# The demo customer from docs/DEMO.md. The real pipeline scores it at exactly
# this value; CI's container smoke test pins the same number on /predict.
VALID_PAYLOAD = {
    "gender": "Female", "seniorcitizen": 0, "partner": "Yes", "dependents": "No",
    "tenure": 3, "phoneservice": "Yes", "multiplelines": "No",
    "internetservice": "Fiber optic", "onlinesecurity": "No", "onlinebackup": "No",
    "deviceprotection": "No", "techsupport": "No", "streamingtv": "Yes",
    "streamingmovies": "Yes", "contract": "Month-to-month", "paperlessbilling": "Yes",
    "paymentmethod": "Electronic check", "monthlycharges": 85.5, "totalcharges": 256.5,
}
VALID_PROBABILITY = 0.7443000078201294

# What that customer's explanation is, written out rather than computed, so
# these tests are not phrased in terms of the code they check.
VALID_DRIVER_FIELDS = [
    "contract", "contractvstenure", "internetservice", "tenure", "onlinesecurity",
]
VALID_REASONS = [
    {"field": "contract", "direction": "raises risk"},
    {"field": "contractvstenure", "direction": "raises risk"},
    {"field": "internetservice", "direction": "raises risk"},
]
GOOD_SUMMARY = (
    "This customer is on a month-to-month contract with fiber optic internet, "
    "and their overall commitment is lower than most customers."
)


def reply(summary=GOOD_SUMMARY, risk_level="very high", reasons=VALID_REASONS):
    return json.dumps({
        "risk_level": risk_level, "reasons": reasons, "summary": summary,
    })


GOOD = reply()
# Rejected as hallucinated_number: no percentage was ever sent.
BAD_NUMBER = reply("This customer is on a month-to-month contract and has a "
                   "74% chance of leaving.")
# Rejected as protected_attribute.
BAD_PROTECTED = reply("This customer is a senior citizen on a month-to-month "
                      "contract.")

NO_KEY = "OPENAI_API_KEY is not set. (scripted by the test fixture)"

EXPLAIN_KEYS = {
    "churn_probability", "target_for_retention", "threshold_used",
    "risk_level", "drivers", "explanation", "meta",
}
META_KEYS = {
    "status", "detail", "rejection_type", "prompt_version", "model",
    "cache_hit", "attempts", "protected_drivers_omitted",
}
DRIVER_KEYS = {
    "field", "label", "value", "vs_other_customers", "direction", "contribution",
}


# ==========================================================================
# Fixtures
# ==========================================================================

@pytest.fixture(scope="module")
def pipeline():
    """The real pipeline, loaded once."""
    path = Path(config.MODEL_PATH)
    path = path if path.is_absolute() else REPO_ROOT / path
    if not path.exists():
        pytest.skip(f"model artifact not present at {path}")
    return explain.load_model(str(path))


class _Loads:
    """Stands in for `joblib` inside api.py, handing back one object."""

    def __init__(self, loaded):
        self._loaded = loaded

    def load(self, path):
        return self._loaded


@pytest.fixture
def start(monkeypatch, pipeline):
    """start(llm=None, threshold=0.4) -> a TestClient on a started app.

    `llm` is the language-model client the app will believe it built at
    startup: a FakeLLM, or None for a process with no API key. Nothing here
    can reach a real one -- _make_llm_client is replaced outright.

    The four globals the lifespan assigns are set through monkeypatch first,
    so whatever the app writes into them is undone at teardown and no FakeLLM
    outlives its test.
    """
    stack = contextlib.ExitStack()

    def _start(llm=None, threshold=0.4, problem=NO_KEY):
        for name in ("model", "threshold", "llm_client", "llm_problem"):
            monkeypatch.setattr(api_module, name, None)
        monkeypatch.setattr(api_module, "joblib", _Loads(pipeline))
        monkeypatch.setattr(api_module, "load_threshold", lambda: threshold)
        monkeypatch.setattr(api_module, "validate_feature_schema", lambda: None)
        monkeypatch.setattr(api_module, "validate_environment_versions", lambda: None)
        monkeypatch.setattr(
            api_module, "_make_llm_client",
            lambda: (llm, None) if llm is not None else (None, problem),
        )
        return stack.enter_context(TestClient(api_module.app))

    yield _start
    stack.close()


@pytest.fixture(scope="module")
def simulated_customers():
    path = REPO_ROOT / "simulated_new_customers.csv"
    if not path.exists():
        pytest.skip("simulated_new_customers.csv not present")
    frame = pd.read_csv(path)
    return [frame.iloc[i].to_dict() for i in range(len(frame))]


def sent_to_the_model(llm, call=0):
    """The user message of one FakeLLM call, parsed."""
    return json.loads(llm.calls[call]["messages"][1]["content"])


# ==========================================================================
# 1. The same decision as /predict
# ==========================================================================

def test_explain_reports_the_pinned_probability(start):
    client = start()
    body = client.post("/explain", json=VALID_PAYLOAD).json()
    assert body["churn_probability"] == VALID_PROBABILITY
    assert body["target_for_retention"] is True
    assert body["threshold_used"] == 0.4


def test_explain_and_predict_agree_on_every_simulated_customer(start, simulated_customers):
    """Exact equality on all three fields, for all fifty. No language model
    is involved: the app is started without one."""
    client = start()
    assert len(simulated_customers) == 50
    for index, customer in enumerate(simulated_customers):
        predicted = client.post("/predict", json=customer)
        explained = client.post("/explain", json=customer)
        assert predicted.status_code == explained.status_code == 200, index
        explained = explained.json()
        for key in ("churn_probability", "target_for_retention", "threshold_used"):
            assert explained[key] == predicted.json()[key], (index, key)


@pytest.mark.parametrize("threshold, flagged, band", [
    (0.4, True, "very high"),    # 0.744 >= 0.70, halfway from 0.4 to 1
    (0.6, True, "high"),         # at or above 0.6, below 0.8
    (0.9, False, "moderate"),    # below 0.9, at or above 0.45
])
def test_explain_uses_the_threshold_the_app_loaded(start, threshold, flagged, band):
    """Not the one in model_metadata.json. explain_customer() reads the
    metadata when it is not handed a threshold, which would let /explain
    describe a decision /predict did not make."""
    client = start(threshold=threshold)
    explained = client.post("/explain", json=VALID_PAYLOAD).json()
    predicted = client.post("/predict", json=VALID_PAYLOAD).json()
    assert explained["threshold_used"] == predicted["threshold_used"] == threshold
    assert explained["target_for_retention"] is predicted["target_for_retention"] is flagged
    assert explained["risk_level"] == band


def test_explain_does_not_load_a_second_copy_of_the_model(start, monkeypatch):
    def refuse(path=None):
        raise AssertionError("explain.load_model() was called: /explain is "
                             "meant to reuse the pipeline the app already holds")

    client = start()
    monkeypatch.setattr(explain, "load_model", refuse)
    assert client.post("/explain", json=VALID_PAYLOAD).status_code == 200


def test_a_mismatched_explanation_is_refused_not_returned(start, monkeypatch):
    """The gate inside the handler. An explanation whose probability is not
    the one /predict reports must not go out under /predict's number."""
    real = explain.explain_customer

    def drifted(customer, **kwargs):
        explanation = real(customer, **kwargs)
        return {**explanation, "churn_probability": explanation["churn_probability"] + 1e-9}

    client = start()
    monkeypatch.setattr(explain, "explain_customer", drifted)
    response = client.post("/explain", json=VALID_PAYLOAD)
    assert response.status_code == 500
    assert "different prediction" in response.json()["detail"]


# ==========================================================================
# 2. The request: /predict's own validation, before anything is spent
# ==========================================================================

@pytest.mark.parametrize("change", [
    {"contract": "Three year"},
    {"gender": "Not A Valid Option"},
    {"tenure": -1},
    {"monthlycharges": "expensive"},
])
def test_explain_rejects_what_predict_rejects_and_calls_nothing(start, change):
    llm = FakeLLM([GOOD])
    client = start(llm)
    payload = {**VALID_PAYLOAD, **change}
    assert client.post("/predict", json=payload).status_code == 422
    assert client.post("/explain", json=payload).status_code == 422
    assert llm.calls == []


def test_explain_rejects_a_missing_required_field(start):
    llm = FakeLLM([GOOD])
    client = start(llm)
    payload = {**VALID_PAYLOAD}
    del payload["tenure"]
    assert client.post("/explain", json=payload).status_code == 422
    assert llm.calls == []


def test_explain_rejects_a_non_finite_number_with_a_readable_422(start):
    client = start()
    body = json.dumps({**VALID_PAYLOAD, "monthlycharges": float("inf")})
    response = client.post(
        "/explain", content=body, headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "finite" in json.dumps(response.json())


def test_explain_accepts_a_customer_with_no_totalcharges(start):
    """A legitimate input (the dataset has 11), and one that leaves
    average_monthly_charges as NaN, which JSON cannot carry."""
    client = start()
    payload = {**VALID_PAYLOAD}
    del payload["totalcharges"]
    response = client.post("/explain", json=payload)
    assert response.status_code == 200
    assert len(response.json()["drivers"]) == 5


def test_a_missing_value_among_the_drivers_is_null_not_a_500(start, monkeypatch):
    """Forces the case the real artifact does not happen to produce for any
    simulated customer: the strongest driver's value is NaN."""
    real = explain.explain_customer

    def with_a_missing_top_value(customer, **kwargs):
        explanation = real(customer, **kwargs)
        top = next(d for d in explanation["drivers"] if d["field"] == "tenure")
        top["value"] = float("nan")
        return explanation

    client = start()
    monkeypatch.setattr(explain, "explain_customer", with_a_missing_top_value)
    response = client.post("/explain", json=VALID_PAYLOAD)
    assert response.status_code == 200
    tenure = next(d for d in response.json()["drivers"] if d["field"] == "tenure")
    assert tenure["value"] is None
    # No comparison either: "much lower than most customers" would be a claim
    # about a number that is not there.
    assert tenure["vs_other_customers"] is None
    assert tenure["direction"] == "raises risk"


# ==========================================================================
# 3. The response shape
# ==========================================================================

def test_response_has_exactly_the_documented_keys(start):
    body = start(FakeLLM([GOOD])).post("/explain", json=VALID_PAYLOAD).json()
    assert set(body) == EXPLAIN_KEYS
    assert set(body["meta"]) == META_KEYS
    assert all(set(driver) == DRIVER_KEYS for driver in body["drivers"])
    assert set(body["explanation"]) == {"risk_level", "reasons", "summary"}


def test_the_first_three_keys_are_predicts_own(start):
    """ExplainResponse subclasses PredictionResponse; this is what that buys."""
    client = start()
    predicted = client.post("/predict", json=VALID_PAYLOAD).json()
    explained = client.post("/explain", json=VALID_PAYLOAD).json()
    assert set(predicted) < set(explained)
    assert {key: explained[key] for key in predicted} == predicted


def test_drivers_are_the_top_five_strongest_first(start):
    drivers = start().post("/explain", json=VALID_PAYLOAD).json()["drivers"]
    assert [driver["field"] for driver in drivers] == VALID_DRIVER_FIELDS
    sizes = [abs(driver["contribution"]) for driver in drivers]
    assert sizes == sorted(sizes, reverse=True)


def test_driver_contributions_are_the_models_unrounded(start, pipeline):
    drivers = start().post("/explain", json=VALID_PAYLOAD).json()["drivers"]
    exact = explain.explain_customer(
        VALID_PAYLOAD, model=pipeline, threshold=0.4, top_n=None,
    )["contributions"]
    for driver in drivers:
        assert driver["contribution"] == exact[driver["field"]]


def test_a_drivers_direction_agrees_with_the_sign_of_its_contribution(
    start, simulated_customers,
):
    client = start()
    seen = set()
    for customer in simulated_customers:
        for driver in client.post("/explain", json=customer).json()["drivers"]:
            expected = "raises risk" if driver["contribution"] > 0 else "lowers risk"
            assert driver["direction"] == expected
            seen.add(driver["direction"])
    assert seen == {"raises risk", "lowers risk"}  # both directions exercised


def test_drivers_carry_labels_values_and_worded_comparisons(start):
    drivers = {d["field"]: d for d in
               start().post("/explain", json=VALID_PAYLOAD).json()["drivers"]}
    assert drivers["contract"]["label"] == "contract type"
    assert drivers["contract"]["value"] == "Month-to-month"
    assert drivers["contract"]["vs_other_customers"] is None  # not numeric
    assert drivers["tenure"]["value"] == 3
    assert drivers["tenure"]["vs_other_customers"] == "much lower than most customers"
    # An engineered product with no meaning to a reader: compared, not quoted.
    assert drivers["contractvstenure"]["value"] is None
    assert drivers["contractvstenure"]["vs_other_customers"] == "lower than most customers"


def test_the_model_is_shown_the_first_three_drivers_and_nothing_else(start):
    llm = FakeLLM([GOOD])
    body = start(llm).post("/explain", json=VALID_PAYLOAD).json()
    sent = sent_to_the_model(llm)
    assert set(sent) == {"risk_level", "factors"}
    assert [factor["field"] for factor in sent["factors"]] == VALID_DRIVER_FIELDS[:3]
    assert sent["risk_level"] == body["risk_level"] == "very high"
    # Neither the probability nor the decision leaves the process.
    assert "0.74" not in llm.calls[0]["messages"][1]["content"]
    assert "retention" not in llm.calls[0]["messages"][1]["content"]


def test_api_literals_agree_with_narrates_vocabulary():
    """api.py restates the two closed vocabularies, because narrate may not be
    importable where api.py runs. If they drift, a valid narration fails
    response validation and the caller gets a 500 for a correct answer."""
    explanation = typing.get_type_hints(api_module.Explanation)
    response = typing.get_type_hints(api_module.ExplainResponse)
    assert typing.get_args(explanation["risk_level"]) == narrate.RISK_LEVELS
    assert typing.get_args(response["risk_level"]) == narrate.RISK_LEVELS
    for model in (api_module.Driver, api_module.Reason):
        direction = typing.get_type_hints(model)["direction"]
        assert typing.get_args(direction) == narrate.DIRECTIONS


def test_five_drivers_are_returned_where_the_model_sees_three():
    assert api_module.EXPLAIN_TOP_N == 5
    assert narrate.NARRATION_TOP_N == 3


# ==========================================================================
# 4. The explanation: accepted, retried, rejected
# ==========================================================================

def test_an_accepted_reply_is_returned_as_the_explanation(start):
    llm = FakeLLM([GOOD])
    body = start(llm).post("/explain", json=VALID_PAYLOAD).json()
    assert body["explanation"] == {
        "risk_level": "very high", "reasons": VALID_REASONS, "summary": GOOD_SUMMARY,
    }
    assert body["meta"] == {
        "status": "ok", "detail": None, "rejection_type": None,
        "prompt_version": "explanation_v5", "model": "gpt-4o-mini",
        "cache_hit": False, "attempts": 1, "protected_drivers_omitted": [],
    }
    assert len(llm.calls) == 1


def test_every_reason_names_a_driver_that_is_in_the_response(start):
    body = start(FakeLLM([GOOD])).post("/explain", json=VALID_PAYLOAD).json()
    driver_fields = [driver["field"] for driver in body["drivers"]]
    for reason in body["explanation"]["reasons"]:
        assert reason["field"] in driver_fields


def test_a_rejected_then_accepted_reply_reports_two_attempts(start):
    llm = FakeLLM([BAD_NUMBER, GOOD])
    body = start(llm).post("/explain", json=VALID_PAYLOAD).json()
    assert body["explanation"]["summary"] == GOOD_SUMMARY
    assert body["meta"]["status"] == "ok"
    assert body["meta"]["attempts"] == 2
    assert body["meta"]["rejection_type"] is None


def test_two_rejected_replies_are_a_200_with_no_explanation(start):
    llm = FakeLLM([BAD_NUMBER, BAD_PROTECTED])
    response = start(llm).post("/explain", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["explanation"] is None
    assert body["meta"]["status"] == "rejected"
    # The guard that refused the LAST attempt.
    assert body["meta"]["rejection_type"] == "protected_attribute"
    assert body["meta"]["attempts"] == 2
    # Everything that is arithmetic survives.
    assert body["churn_probability"] == VALID_PROBABILITY
    assert body["risk_level"] == "very high"
    assert [driver["field"] for driver in body["drivers"]] == VALID_DRIVER_FIELDS


def test_a_rejected_reply_never_reaches_the_caller(start):
    llm = FakeLLM([BAD_PROTECTED, BAD_PROTECTED])
    response = start(llm).post("/explain", json=VALID_PAYLOAD)
    assert "senior" not in response.text


# ==========================================================================
# 5. No sentence, and why: unavailable and error
# ==========================================================================

def test_without_a_client_explain_still_returns_the_drivers(start):
    response = start(llm=None).post("/explain", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["explanation"] is None
    assert body["meta"]["status"] == "unavailable"
    assert body["meta"]["detail"] == NO_KEY
    assert body["meta"]["attempts"] == 0
    assert body["meta"]["cache_hit"] is False
    assert [driver["field"] for driver in body["drivers"]] == VALID_DRIVER_FIELDS
    assert body["risk_level"] == "very high"


def test_a_failed_upstream_call_is_a_200_with_the_drivers(start):
    llm = FakeLLM([TimeoutError("upstream stalled; key sk-do-not-echo-this")])
    with pytest.warns(RuntimeWarning, match="language-model call failed"):
        response = start(llm).post("/explain", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["explanation"] is None
    assert body["meta"]["status"] == "error"
    assert body["meta"]["detail"] == "TimeoutError"
    assert [driver["field"] for driver in body["drivers"]] == VALID_DRIVER_FIELDS


def test_an_upstream_error_message_is_not_sent_to_the_caller(start):
    """Provider errors can quote part of the key. Only the type goes out."""
    llm = FakeLLM([RuntimeError("Incorrect API key provided: sk-do-not-echo-this")])
    with pytest.warns(RuntimeWarning):
        response = start(llm).post("/explain", json=VALID_PAYLOAD)
    assert "sk-do-not-echo-this" not in response.text
    assert "Incorrect API key" not in response.text


def test_a_failed_call_is_not_cached(start):
    llm = FakeLLM([TimeoutError("stalled"), GOOD])
    client = start(llm)
    with pytest.warns(RuntimeWarning):
        first = client.post("/explain", json=VALID_PAYLOAD).json()
    second = client.post("/explain", json=VALID_PAYLOAD).json()
    assert first["meta"]["status"] == "error"
    assert second["meta"]["status"] == "ok"
    assert second["meta"]["cache_hit"] is False
    assert len(llm.calls) == 2


# ==========================================================================
# 6. The cache, through the real route
# ==========================================================================

def test_the_second_identical_request_makes_no_call(start):
    llm = FakeLLM([GOOD])  # one scripted reply: a second call would raise
    client = start(llm)
    first = client.post("/explain", json=VALID_PAYLOAD).json()
    second = client.post("/explain", json=VALID_PAYLOAD).json()
    assert len(llm.calls) == 1
    assert first["meta"]["cache_hit"] is False
    assert second["meta"]["cache_hit"] is True
    assert second["meta"]["status"] == "ok"
    assert second["meta"]["attempts"] == 0
    assert second["explanation"] == first["explanation"]
    assert second["drivers"] == first["drivers"]


def test_a_rejected_answer_is_not_cached(start):
    llm = FakeLLM([BAD_NUMBER, BAD_NUMBER, GOOD])
    client = start(llm)
    assert client.post("/explain", json=VALID_PAYLOAD).json()["meta"]["status"] == "rejected"
    second = client.post("/explain", json=VALID_PAYLOAD).json()
    assert second["meta"]["status"] == "ok"
    assert second["meta"]["cache_hit"] is False
    assert len(llm.calls) == 3


def test_the_cache_is_the_shared_file_the_cli_uses(start):
    """Not a private one: an answer /explain paid for is there for
    `narrate.py`, and `narration_cache.py --import-all` fills /explain."""
    client = start(FakeLLM([GOOD]))
    client.post("/explain", json=VALID_PAYLOAD)
    cache = narration_cache.from_env()
    try:
        rows = {table: count for table, (count, _) in cache.stats().items()}
        assert rows == {"cache_explanation_v5": 1}
    finally:
        cache.close()


def test_a_process_with_no_key_still_serves_what_is_cached(start):
    """The free mode: answers already paid for need neither the key nor the
    openai package, because narrate() looks in the cache before it asks its
    client for anything."""
    paid = start(FakeLLM([GOOD])).post("/explain", json=VALID_PAYLOAD).json()
    keyless = start(llm=None)
    assert keyless.get("/health").json()["narration_available"] is False
    served = keyless.post("/explain", json=VALID_PAYLOAD).json()
    assert served["meta"]["status"] == "ok"
    assert served["meta"]["cache_hit"] is True
    assert served["explanation"] == paid["explanation"]


def test_an_unusable_cache_costs_a_call_not_an_answer(start, monkeypatch, tmp_path):
    """Pointed at a directory, the cache cannot open. /explain must answer
    anyway -- from a live call, both times."""
    monkeypatch.setattr(narration_cache, "DEFAULT_DB_PATH", str(tmp_path))
    llm = FakeLLM([GOOD, GOOD])
    client = start(llm)
    with pytest.warns(RuntimeWarning):
        first = client.post("/explain", json=VALID_PAYLOAD).json()
        second = client.post("/explain", json=VALID_PAYLOAD).json()
    assert first["meta"]["status"] == second["meta"]["status"] == "ok"
    assert second["meta"]["cache_hit"] is False
    assert len(llm.calls) == 2


# ==========================================================================
# 7. Protected attributes
# ==========================================================================

PROTECTED = {"gender", "seniorcitizen", "partner", "dependents", "family_tie"}


def test_no_protected_attribute_is_ever_a_driver(start, simulated_customers):
    client = start()
    for index, customer in enumerate(simulated_customers):
        body = client.post("/explain", json=customer).json()
        fields = {driver["field"] for driver in body["drivers"]}
        assert not fields & PROTECTED, index
        assert set(body["meta"]["protected_drivers_omitted"]) <= PROTECTED


def test_an_omitted_protected_driver_is_named_and_its_slot_is_refilled(
    start, simulated_customers,
):
    """Row 32: being a senior citizen is among this customer's five strongest
    drivers. It is left out, said to be left out, and the list is still five
    long -- filtered first, then cut."""
    body = start().post("/explain", json=simulated_customers[32]).json()
    assert body["meta"]["protected_drivers_omitted"] == ["seniorcitizen"]
    assert len(body["drivers"]) == 5
    assert "seniorcitizen" not in [driver["field"] for driver in body["drivers"]]


def test_protected_attributes_are_not_sent_to_the_model(start, simulated_customers):
    # A reply is scripted only so the call completes; whether it is accepted
    # is beside the point here.
    llm = FakeLLM([GOOD, GOOD])
    start(llm).post("/explain", json=simulated_customers[32])
    content = llm.calls[0]["messages"][1]["content"]
    for field in PROTECTED:
        assert field not in content
    assert "senior" not in content.lower()
    assert "gender" not in content.lower()


# ==========================================================================
# 8. 503: no model, or no explanation layer
# ==========================================================================

def test_explain_returns_503_when_the_model_is_not_loaded(monkeypatch):
    monkeypatch.setattr(api_module, "model", None)
    monkeypatch.setattr(api_module, "threshold", None)
    response = TestClient(api_module.app).post("/explain", json=VALID_PAYLOAD)
    assert response.status_code == 503
    assert response.json()["detail"] == "Model not loaded yet."


def test_explain_returns_503_when_the_threshold_is_missing(monkeypatch, pipeline):
    monkeypatch.setattr(api_module, "model", pipeline)
    monkeypatch.setattr(api_module, "threshold", None)
    response = TestClient(api_module.app).post("/explain", json=VALID_PAYLOAD)
    assert response.status_code == 503


def test_explain_returns_503_in_a_build_without_the_layer(start, monkeypatch):
    client = start()
    for name in ("explain", "narrate", "narration_cache"):
        monkeypatch.setattr(api_module, name, None)
    monkeypatch.setattr(api_module, "EXPLAIN_LAYER_PROBLEM",
                        "ModuleNotFoundError: No module named 'explain'")
    response = client.post("/explain", json=VALID_PAYLOAD)
    assert response.status_code == 503
    assert "not part of this build" in response.json()["detail"]
    assert "No module named 'explain'" in response.json()["detail"]
    # ...and the endpoint the image exists for is untouched.
    predicted = client.post("/predict", json=VALID_PAYLOAD)
    assert predicted.status_code == 200
    assert predicted.json()["churn_probability"] == VALID_PROBABILITY


# ==========================================================================
# 9. /health
# ==========================================================================

def test_health_reports_a_live_layer(start):
    assert start(FakeLLM([])).get("/health").json() == {
        "status": "ok", "model_loaded": True,
        "explain_available": True, "narration_available": True,
    }


def test_health_reports_drivers_only_when_there_is_no_client(start):
    assert start(llm=None).get("/health").json() == {
        "status": "ok", "model_loaded": True,
        "explain_available": True, "narration_available": False,
    }


def test_health_reports_a_build_without_the_layer(start, monkeypatch):
    client = start()
    monkeypatch.setattr(api_module, "explain", None)
    health = client.get("/health").json()
    assert health["explain_available"] is False
    assert health["model_loaded"] is True


# ==========================================================================
# 10. Building the client
# ==========================================================================

def test_the_client_is_built_with_a_timeout_and_no_sdk_retries(monkeypatch):
    """The SDK's own defaults are a 600-second read timeout and two retries.
    Compared against literals: a test quoting the constants would pass
    whatever they became."""
    built = {}

    class Recorder:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr(narrate, "OpenAIClient", Recorder)
    client, problem = api_module._make_llm_client()
    assert isinstance(client, Recorder)
    assert problem is None
    assert built == {"timeout": 15.0, "max_retries": 0}


@pytest.mark.parametrize("message", [
    "OPENAI_API_KEY is not set. Export it.",
    "The openai package is not installed.",
])
def test_a_client_that_cannot_be_built_is_a_reason_not_a_crash(monkeypatch, message):
    def refuse(**kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(narrate, "OpenAIClient", refuse)
    assert api_module._make_llm_client() == (None, message)


def test_no_client_is_built_without_the_layer(monkeypatch):
    monkeypatch.setattr(api_module, "narrate", None)
    monkeypatch.setattr(api_module, "EXPLAIN_LAYER_PROBLEM", "ModuleNotFoundError: x")
    assert api_module._make_llm_client() == (None, "ModuleNotFoundError: x")


def test_the_stand_in_client_raises_only_when_asked_to_complete():
    stand_in = api_module._NoLiveClient("no key")
    with pytest.raises(api_module._NarrationUnavailable, match="no key"):
        stand_in.complete([], model="m", temperature=0.0)


# ==========================================================================
# 11. The container's module set
# ==========================================================================

IMAGE_MODULES = ("api.py", "config.py", "feature_engineering_telco.py", "telco_model.py")

IMAGE_SCRIPT = """
import json, sys
import api
assert api.explain is None and api.narrate is None and api.narration_cache is None, \\
    "the explanation layer was importable; this test is not simulating the image"
from fastapi.testclient import TestClient
customer = json.loads(sys.argv[1])
with TestClient(api.app) as client:
    health = client.get("/health").json()
    predicted = client.post("/predict", json=customer)
    explained = client.post("/explain", json=customer)
print(json.dumps({
    "health": health,
    "predict": [predicted.status_code, predicted.json()],
    "explain": [explained.status_code, explained.json()],
}))
"""


def test_api_starts_and_predicts_with_only_the_images_modules(tmp_path, pipeline):
    """The Dockerfile copies four modules and the artifact. In that layout
    `import explain` fails -- and must cost /explain, not the service."""
    for name in IMAGE_MODULES:
        shutil.copy(REPO_ROOT / name, tmp_path / name)
    environment = {
        key: value for key, value in os.environ.items()
        if key not in ("PYTHONPATH", "OPENAI_API_KEY")
    }
    environment["MODEL_PATH"] = str(REPO_ROOT / "xgboost_churn_pipeline.pkl")
    environment["METADATA_PATH"] = str(REPO_ROOT / "model_metadata.json")
    completed = subprocess.run(
        [sys.executable, "-c", IMAGE_SCRIPT, json.dumps(VALID_PAYLOAD)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["health"] == {
        "status": "ok", "model_loaded": True,
        "explain_available": False, "narration_available": False,
    }
    assert result["predict"][0] == 200
    assert result["predict"][1]["churn_probability"] == VALID_PROBABILITY
    assert result["explain"][0] == 503
    assert "not part of this build" in result["explain"][1]["detail"]
