"""Tests for explain.py.

This module produces a list of reasons that a retention manager will read as
an account of why a customer was flagged, and may act on. The failure that
matters is therefore not a crash -- it is a well-formatted, entirely
plausible driver list that describes something other than what the model
actually did. Nothing about such a report looks wrong.

Coverage is weighted toward the three ways that can happen:

  1. THE ADDITIVITY IDENTITY. Tree SHAP contributions plus the bias sum to
     the model's margin, and the sigmoid of that margin is the predicted
     probability. If a column is dropped, double-counted, or attributed to
     the wrong field, that identity breaks. It is asserted for
     DUMMY_CUSTOMER and for every row of simulated_new_customers.csv.

  2. THE COLUMN MAP. A map of the right length whose entries are offset by
     one attributes every contribution to the wrong customer field while
     producing perfectly well-formed output. verify_column_map() is what
     stops that, so it is tested in both directions, including the offset
     case specifically.

  3. THE PROBABILITY'S PROVENANCE. The number reported has to be the one
     predict_proba returned -- the same number /predict would report for the
     same customer -- not the one reconstructed from the contributions. A
     test pins it against model_metadata.json's dummy_customer_score, which
     is the same anchor tests/test_artifact.py uses.

A note on the assertions, learned from tests/test_fairness_analysis.py:
never phrase an assertion in terms of the constant it is testing.
`assert error < explain.RECONSTRUCTION_TOLERANCE` moves when the constant
moves and would catch nothing. The tolerance is compared against the
documented literal 1e-6, and the constant itself is pinned separately.

Tests needing the committed pickle or model_metadata.json skip when those are
absent, so the suite still runs on a clean checkout.

Run with: pytest tests/test_explain.py -v
"""

import ast
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import config
import explain
from feature_engineering_telco import engineer_features
from tests.conftest import DummyModel

REPO_ROOT = Path(__file__).resolve().parent.parent


def _anchor(path_str):
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


# ==========================================================================
# Fixtures
# ==========================================================================

@pytest.fixture(scope="module")
def model():
    """The real pipeline. Module-scoped -- joblib.load is the slow part."""
    path = _anchor(config.MODEL_PATH)
    if not path.exists():
        pytest.skip(f"model artifact not present at {path}")
    return explain.load_model(str(path))


@pytest.fixture(scope="module")
def metadata():
    path = _anchor(config.METADATA_PATH)
    if not path.exists():
        pytest.skip(f"model metadata not present at {path}")
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def dummy_explanation(model):
    """Every driver for config.DUMMY_CUSTOMER, not just the top few."""
    return explain.explain_customer(config.DUMMY_CUSTOMER, model=model, top_n=None)


@pytest.fixture(scope="module")
def simulated_customers():
    path = REPO_ROOT / "simulated_new_customers.csv"
    if not path.exists():
        pytest.skip("simulated_new_customers.csv not present")
    frame = pd.read_csv(path)
    return [frame.iloc[i].to_dict() for i in range(len(frame))]


# --------------------------------------------------------------------------
# Duck-typed stand-ins for the fitted preprocessor.
#
# These let the column-map logic be tested without loading the real artifact
# and without fitting a ColumnTransformer, which keeps these tests fast and
# makes them run on a checkout with no .pkl. They mimic only what
# build_column_map() actually reads: transformers_, a nested steps list, and
# categories_ on whichever step has it.
# --------------------------------------------------------------------------

class _FakeEncoder:
    def __init__(self, categories):
        self.categories_ = [np.array(group) for group in categories]


class _FakeInnerPipeline:
    def __init__(self, encoder):
        # The encoder is deliberately NOT first: build_column_map searches
        # the steps for categories_ rather than trusting a position or a name.
        self.steps = [("imputer", object()), ("encoder", encoder)]


class _FakePreprocessor:
    def __init__(self, transformers):
        self.transformers_ = transformers


def _fake_preprocessor(numeric=(), categorical=()):
    """`categorical` is a sequence of (column, [categories])."""
    transformers = []
    if numeric:
        transformers.append(("num", object(), list(numeric)))
    if categorical:
        encoder = _FakeEncoder([cats for _, cats in categorical])
        transformers.append(
            ("cat", _FakeInnerPipeline(encoder), [col for col, _ in categorical])
        )
    return _FakePreprocessor(transformers)


# ==========================================================================
# 1. The sigmoid and the reconstruction gate
# ==========================================================================

@pytest.mark.parametrize("x", [-40.0, -3.0, -0.5, 0.0, 0.5, 3.0, 40.0])
def test_sigmoid_matches_the_logistic_definition(x):
    assert explain._sigmoid(x) == pytest.approx(1.0 / (1.0 + math.exp(-x)), rel=1e-12)


def test_sigmoid_survives_a_margin_that_would_overflow_the_naive_form():
    """np.exp(-x) for x = -800 overflows; the branch-stable form must not."""
    assert explain._sigmoid(-800.0) == pytest.approx(0.0, abs=1e-300)
    assert explain._sigmoid(800.0) == pytest.approx(1.0)


def test_the_reconstruction_tolerance_is_one_in_a_million():
    """Pinned against a literal. The tolerance is a documented contract --
    it is what separates float32 round-tripping from a real breakage -- so
    widening it must be a deliberate edit, not a silent one."""
    assert explain.RECONSTRUCTION_TOLERANCE == 1e-6


def test_gate_accepts_a_reconstruction_inside_the_tolerance():
    margin = 0.5
    exact = explain._sigmoid(margin)
    # 9e-7 is inside the documented 1e-6 -- literals on both sides, so this
    # test does not move when the constant does.
    error = explain.verify_attribution(exact + 9e-7, margin)
    assert error == pytest.approx(9e-7, rel=1e-6)


def test_gate_raises_when_the_reconstruction_drifts_past_the_tolerance():
    margin = 0.5
    with pytest.raises(RuntimeError):
        explain.verify_attribution(explain._sigmoid(margin) + 1.1e-6, margin)


def test_gate_message_shows_both_numbers_and_the_tolerance():
    """It fires long after whoever changed the model has stopped looking, so
    the message has to carry the evidence with it."""
    margin = 0.5
    with pytest.raises(RuntimeError) as excinfo:
        explain.verify_attribution(0.9, margin)
    message = str(excinfo.value)
    assert "predict_proba" in message
    assert "0.9" in message
    assert "tolerance" in message


def test_gate_catches_a_probability_from_a_different_model():
    """The case that is hardest to spot by eye: a perfectly reasonable
    probability paired with contributions belonging to someone else."""
    with pytest.raises(RuntimeError):
        explain.verify_attribution(0.42, 2.5)


# ==========================================================================
# 2. The column map
# ==========================================================================

def test_map_passes_numeric_columns_through_with_no_category():
    column_map = explain.build_column_map(_fake_preprocessor(numeric=["a", "b"]))
    assert column_map == [("a", None), ("b", None)]


def test_map_expands_each_categorical_column_in_encoder_order():
    column_map = explain.build_column_map(
        _fake_preprocessor(categorical=[("contract", ["Two year", "One year"])])
    )
    # Encoder order, not sorted order -- the transformed columns come out in
    # whatever order categories_ holds, so the map must follow it exactly.
    assert column_map == [("contract", "Two year"), ("contract", "One year")]


def test_map_puts_the_numeric_block_before_the_categorical_block():
    column_map = explain.build_column_map(
        _fake_preprocessor(numeric=["tenure"], categorical=[("gender", ["F", "M"])])
    )
    assert column_map == [("tenure", None), ("gender", "F"), ("gender", "M")]


def test_map_skips_a_dropped_remainder():
    preprocessor = _fake_preprocessor(numeric=["a"])
    preprocessor.transformers_.append(("remainder", "drop", ["ignored"]))
    assert explain.build_column_map(preprocessor) == [("a", None)]


def test_verify_column_map_accepts_names_it_reconstructs():
    explain.verify_column_map(
        [("tenure", None), ("gender", "Female")],
        ["num__tenure", "cat__gender_Female"],
    )


def test_verify_column_map_raises_on_a_length_mismatch():
    with pytest.raises(RuntimeError, match="entries but the preprocessor"):
        explain.verify_column_map([("tenure", None)], ["num__tenure", "cat__gender_F"])


def test_verify_column_map_catches_an_offset_map():
    """The dangerous failure. Lengths agree, every name is individually
    plausible, and every contribution lands on the wrong field."""
    with pytest.raises(RuntimeError, match="position 0"):
        explain.verify_column_map(
            [("gender", "Female"), ("tenure", None)],
            ["num__tenure", "cat__gender_Female"],
        )


def test_verify_column_map_message_shows_both_sides():
    with pytest.raises(RuntimeError) as excinfo:
        explain.verify_column_map([("tenure", None)], ["num__monthlycharges"])
    message = str(excinfo.value)
    assert "num__tenure" in message
    assert "num__monthlycharges" in message


# ==========================================================================
# 3. Collapsing one-hot groups
# ==========================================================================

def test_collapse_sums_a_categorical_group_into_one_number():
    column_map = [("contract", "A"), ("contract", "B"), ("tenure", None)]
    assert explain.collapse_contributions([0.1, 0.2, 0.5], column_map) == {
        "contract": pytest.approx(0.3),
        "tenure": pytest.approx(0.5),
    }


def test_collapse_counts_columns_the_customer_does_not_match():
    """A tree can split on 'contract is not Two year', and that split's credit
    lands on the Two-year column even for a month-to-month customer. Dropping
    the zero-valued columns would silently discard real attribution."""
    column_map = [("contract", "Month-to-month"), ("contract", "Two year")]
    collapsed = explain.collapse_contributions([0.4, -0.9], column_map)
    assert collapsed["contract"] == pytest.approx(-0.5)


def test_collapse_preserves_the_total():
    column_map = [("a", "x"), ("a", "y"), ("b", None), ("c", "z")]
    values = [0.11, -0.22, 0.33, -0.44]
    collapsed = explain.collapse_contributions(values, column_map)
    assert sum(collapsed.values()) == pytest.approx(sum(values), abs=1e-12)


def test_collapse_keeps_first_appearance_order():
    column_map = [("b", None), ("a", "x"), ("b", None)]
    assert list(explain.collapse_contributions([1.0, 2.0, 3.0], column_map)) == ["b", "a"]


# ==========================================================================
# 4. Rejecting a model that cannot be explained
# ==========================================================================

def test_rejects_an_estimator_with_no_named_steps():
    """conftest.DummyModel has predict_proba and nothing else -- exactly the
    stand-in tests/test_api.py serves predictions with. It can be scored and
    it cannot be explained, and the error has to say so rather than raising
    an AttributeError from inside a library call."""
    with pytest.raises(explain.UnexplainableModelError, match="named_steps"):
        explain._split_pipeline(DummyModel())


def test_rejects_a_pipeline_missing_the_preprocessor():
    class OnlyClassifier:
        named_steps = {"classifier": object()}

    with pytest.raises(explain.UnexplainableModelError, match="preprocessor"):
        explain._split_pipeline(OnlyClassifier())


def test_rejects_a_classifier_with_no_booster():
    class Linearish:
        named_steps = {"preprocessor": object(), "classifier": DummyModel()}

    with pytest.raises(explain.UnexplainableModelError, match="get_booster"):
        explain._split_pipeline(Linearish())


def test_rejection_message_names_the_type_it_found():
    with pytest.raises(explain.UnexplainableModelError, match="DummyModel"):
        explain._split_pipeline(DummyModel())


# ==========================================================================
# 5. Labels and the engineered set
# ==========================================================================

def test_every_feature_column_has_a_label(metadata):
    """A new engineered feature must not reach a reader as a raw column
    name. validate_feature_schema() checks the columns exist; this checks
    they can be described."""
    unlabelled = set(metadata["feature_columns"]) - set(explain.FIELD_LABELS)
    assert not unlabelled, f"no FIELD_LABELS entry for: {sorted(unlabelled)}"


def test_no_label_describes_a_column_that_does_not_exist(metadata):
    stale = set(explain.FIELD_LABELS) - set(metadata["feature_columns"])
    assert not stale, f"FIELD_LABELS has entries for absent columns: {sorted(stale)}"


def test_engineered_set_matches_what_feature_engineering_actually_derives():
    """Computed from engineer_features() rather than restated, so the flag
    cannot drift from the module that creates the columns."""
    derived = set(engineer_features(pd.DataFrame([config.DUMMY_CUSTOMER])).columns)
    assert explain.ENGINEERED_FEATURES == derived - set(config.DUMMY_CUSTOMER)


def test_there_are_six_engineered_features():
    assert len(explain.ENGINEERED_FEATURES) == 6


def test_module_does_not_import_the_shap_package():
    """The docstring's central claim: attribution here uses xgboost's own
    pred_contribs so this module stays importable by the serving path
    without moving shap out of the notebook dependency group and into the
    production image."""
    tree = ast.parse(Path(explain.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "shap" not in imported


# ==========================================================================
# 6. The real artifact: additivity and provenance
# ==========================================================================

def test_contributions_and_bias_sum_to_the_margin(dummy_explanation):
    """The identity everything else rests on. A dropped or double-counted
    column breaks it. Both sides are summed in float64, so the two paths
    agree to well under 1e-12 -- the tolerance is last-ulp room, not slack."""
    total = sum(dummy_explanation["contributions"].values()) + dummy_explanation["bias"]
    assert total == pytest.approx(dummy_explanation["margin"], abs=1e-12)


def test_sigmoid_of_the_margin_reproduces_the_reported_probability(dummy_explanation):
    reconstructed = explain._sigmoid(dummy_explanation["margin"])
    assert reconstructed == pytest.approx(
        dummy_explanation["churn_probability"], abs=1e-6
    )


def test_reported_error_is_the_gap_it_claims_to_be(dummy_explanation):
    expected = abs(
        explain._sigmoid(dummy_explanation["margin"])
        - dummy_explanation["churn_probability"]
    )
    assert dummy_explanation["reconstruction_error"] == pytest.approx(expected, abs=1e-15)


def test_probability_matches_the_pin_in_the_metadata(dummy_explanation, metadata):
    """The provenance test. The explained probability must be the number
    predict_proba returns -- the one /predict reports and
    tests/test_artifact.py pins -- not the one reconstructed from the
    contributions. Reading the pin from metadata means a retrain updates the
    artifact and this expectation together, exactly as test_artifact.py does.
    """
    expected = metadata.get("dummy_customer_score")
    assert expected is not None, (
        "model_metadata.json has no 'dummy_customer_score' -- re-run the "
        "notebook's save cell to record it."
    )
    assert dummy_explanation["churn_probability"] == pytest.approx(expected, abs=1e-6)


def test_probability_is_predict_probas_own_number_bit_for_bit(model):
    """Exact equality, deliberately, where every other numeric assertion in
    this file uses a tolerance.

    sigmoid(margin) and predict_proba agree to ~5e-08 on this artifact, so
    returning the reconstructed number instead of the model's own would pass
    every approximate check here while quietly breaking the contract that
    /explain and /predict report the same number. Only an exact comparison
    can tell those two apart, so this is the one place that makes it.
    """
    frame = engineer_features(pd.DataFrame([config.DUMMY_CUSTOMER]))
    expected = float(model.predict_proba(frame)[:, 1][0])
    explanation = explain.explain_customer(config.DUMMY_CUSTOMER, model=model)
    assert explanation["churn_probability"] == expected


def test_dummy_customers_strongest_driver_is_their_contract(dummy_explanation):
    """A canary on the whole chain: transform, attribute, collapse, sort.

    DUMMY_CUSTOMER is month-to-month with one month of tenure, and contract
    is the single most separating column in the dataset (15.2x spread, per
    docs/DATA_DICTIONARY.txt), so this is what a correct pipeline must say. Its
    real value is catching attribution that lands on the wrong field while
    still summing correctly -- a column map offset by one preserves the total
    exactly and shifts every contribution to its neighbour, which no
    additivity check can see.

    A deliberate retrain could legitimately move this. If it does, confirm
    the new top driver is defensible and update the expectation here rather
    than deleting the test.
    """
    assert dummy_explanation["drivers"][0]["field"] == "contract"


def test_decision_uses_the_same_inclusive_comparison_as_both_consumers(
    dummy_explanation,
):
    probability = dummy_explanation["churn_probability"]
    threshold = dummy_explanation["threshold_used"]
    assert dummy_explanation["target_for_retention"] == (probability >= threshold)


def test_the_threshold_is_the_shared_one(dummy_explanation):
    assert dummy_explanation["threshold_used"] == config.load_threshold(
        str(_anchor(config.METADATA_PATH))
    )


def test_decision_is_inclusive_at_the_boundary(model):
    """`>=`, matching api.py and telco_model.py. A `>` here would explain a
    customer as 'leave alone' whom both services flag."""
    explanation = explain.explain_customer(config.DUMMY_CUSTOMER, model=model)
    at_boundary = explain.explain_customer(
        config.DUMMY_CUSTOMER, model=model,
        threshold=explanation["churn_probability"],
    )
    assert at_boundary["target_for_retention"] is True


def test_additivity_holds_for_every_simulated_customer(model, simulated_customers):
    """One customer proving the identity could be luck. Fifty could not."""
    for index, customer in enumerate(simulated_customers):
        explanation = explain.explain_customer(customer, model=model, top_n=None)
        total = sum(explanation["contributions"].values()) + explanation["bias"]
        assert total == pytest.approx(explanation["margin"], abs=1e-12), f"row {index}"
        assert explanation["reconstruction_error"] < 1e-6, f"row {index}"


def test_column_map_agrees_with_sklearn_on_the_real_preprocessor(model):
    """The two independent derivations checking each other, against the
    fitted object rather than a stand-in."""
    preprocessor, _ = explain._split_pipeline(model)
    names = list(preprocessor.get_feature_names_out())
    explain.verify_column_map(explain.build_column_map(preprocessor), names)


def test_collapsed_fields_are_exactly_the_metadata_feature_columns(
    dummy_explanation, metadata
):
    assert set(dummy_explanation["contributions"]) == set(metadata["feature_columns"])


# ==========================================================================
# 7. Presentation of the driver list
# ==========================================================================

def test_drivers_are_sorted_by_absolute_contribution(dummy_explanation):
    """Magnitude, not signed value. A driver that strongly lowers risk is as
    much a part of the explanation as one that raises it, and signed sorting
    would bury it at the bottom."""
    magnitudes = [abs(d["contribution"]) for d in dummy_explanation["drivers"]]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_a_strongly_negative_driver_outranks_a_weakly_positive_one(dummy_explanation):
    """Guards the specific mutation of sorting by raw value: with signed
    sorting every negative driver falls below every positive one."""
    contributions = [d["contribution"] for d in dummy_explanation["drivers"]]
    negatives = [i for i, c in enumerate(contributions) if c < 0]
    positives = [i for i, c in enumerate(contributions) if c > 0]
    assert negatives and positives, "DUMMY_CUSTOMER should have drivers both ways"
    assert min(negatives) < max(positives)


def test_top_n_truncates_without_reordering(model):
    full = explain.explain_customer(config.DUMMY_CUSTOMER, model=model, top_n=None)
    top3 = explain.explain_customer(config.DUMMY_CUSTOMER, model=model, top_n=3)
    assert len(top3["drivers"]) == 3
    assert [d["field"] for d in top3["drivers"]] == [
        d["field"] for d in full["drivers"][:3]
    ]


def test_contributions_are_reported_at_full_precision(dummy_explanation):
    """Rounding belongs to the renderer. Rounding in the returned structure
    would break the additivity identity above and quietly change what a
    downstream consumer sees."""
    assert any(
        round(d["contribution"], 4) != d["contribution"]
        for d in dummy_explanation["drivers"]
    )


def test_direction_matches_the_sign_of_every_contribution(dummy_explanation):
    for driver in dummy_explanation["drivers"]:
        contribution = driver["contribution"]
        expected = (
            "increases" if contribution > 0
            else "decreases" if contribution < 0
            else "neutral"
        )
        assert driver["direction"] == expected


def test_engineered_drivers_are_flagged(dummy_explanation):
    for driver in dummy_explanation["drivers"]:
        assert driver["engineered"] == (driver["field"] in explain.ENGINEERED_FEATURES)


def test_every_driver_carries_a_human_label(dummy_explanation):
    for driver in dummy_explanation["drivers"]:
        assert driver["label"] == explain.FIELD_LABELS[driver["field"]]
        assert driver["label"] != driver["field"] or driver["field"] == "gender"


def test_driver_values_come_from_the_engineered_row(dummy_explanation):
    """Engineered drivers report their computed value, not a raw field."""
    by_field = {d["field"]: d["value"] for d in dummy_explanation["drivers"]}
    assert by_field["contract"] == config.DUMMY_CUSTOMER["contract"]
    assert by_field["contractvstenure"] == 1  # rank 1 (Month-to-month) * tenure 1


def test_the_explanation_is_json_serialisable(dummy_explanation):
    """numpy scalars leaking through would serialise fine in a print and
    then fail in a response body."""
    json.dumps(dummy_explanation)


def test_the_same_customer_twice_gives_an_identical_explanation(model):
    first = explain.explain_customer(config.DUMMY_CUSTOMER, model=model, top_n=None)
    second = explain.explain_customer(config.DUMMY_CUSTOMER, model=model, top_n=None)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ==========================================================================
# 7b. Reference points: the training medians narrate.py compares against
# ==========================================================================

NUMERIC_FIELDS = {
    "seniorcitizen", "tenure", "monthlycharges", "totalcharges",
    "total_services", "is_auto_pay", "family_tie", "contractvstenure",
    "average_monthly_charges", "charge_change_ratio",
}


def test_reference_covers_exactly_the_numeric_fields(dummy_explanation):
    """A categorical field has no median, so no entry; a numeric field with
    no entry would reach the narration with nothing to compare against."""
    assert set(dummy_explanation["reference"]) == NUMERIC_FIELDS


def test_reference_medians_are_the_training_medians(dummy_explanation):
    """Pinned against literals read once from the committed artifact. The
    totalcharges median is $1,396 -- which is why customer row 7's $5,762.95
    is "well above typical", not the "lower total" stage 1's narrative
    invented."""
    reference = dummy_explanation["reference"]
    assert reference["tenure"]["median"] == 29.0
    assert reference["totalcharges"]["median"] == 1396.0
    assert reference["totalcharges"]["spread"] == pytest.approx(2273.855, abs=1e-3)


def test_reference_refuses_a_numeric_branch_with_no_median_imputer():
    preprocessor = _fake_preprocessor(numeric=["tenure"])
    with pytest.raises(explain.UnexplainableModelError, match="median"):
        explain.reference_points(preprocessor)


# ==========================================================================
# 8. Rendering
# ==========================================================================

@pytest.fixture
def rendered(dummy_explanation):
    return "\n".join(explain.render(dummy_explanation, "TEST"))


def test_render_states_the_decision_and_the_threshold(rendered):
    assert "TARGET FOR RETENTION" in rendered
    assert "threshold 0.40" in rendered


def test_render_marks_engineered_drivers(dummy_explanation):
    text = "\n".join(explain.render(dummy_explanation, "TEST"))
    assert "(E)" in text


def test_render_shows_the_baseline(rendered):
    assert "baseline (all customers)" in rendered


def test_render_reports_the_reconstruction_error(rendered):
    assert "reconstruction error" in rendered
