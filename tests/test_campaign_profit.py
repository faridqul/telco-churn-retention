"""Tests for campaign_profit.py -- the profit arithmetic every threshold
decision in this project rests on.

This formula used to be retyped in five places in the notebook, in three
different shapes (a pandas column, a scalar, a loop body). The risk that
creates is not that the arithmetic is hard, it is that one copy drifts from
the others and the number you tune on stops matching the number you report.
These tests pin the behaviour so the single shared copy can be trusted.

Run with: pytest tests/test_campaign_profit.py -v
"""

import numpy as np
import pandas as pd
import pytest

from campaign_profit import (
    DEFAULT_CLV,
    DEFAULT_COST,
    DEFAULT_SUCCESS_RATE,
    best_threshold,
    break_even_threshold,
    campaign_profit,
    confusion_at_threshold,
    profit_curve,
)

ECON = {"clv": 200, "cost": 20, "success_rate": 0.3}


# ---------------------------------------------------------------------------
# campaign_profit
# ---------------------------------------------------------------------------

def test_matches_hand_computed_value():
    """100 retained churners at 0.3 x $200 = $6,000 revenue; 150 customers
    contacted at $20 = $3,000 spend."""
    assert campaign_profit(100, 50, **ECON) == pytest.approx(3000.0)


def test_reproduces_the_published_test_set_profit():
    """The README's $6,660 comes from TP=256, FP=179 at threshold 0.40. If
    this ever stops matching, either the formula or the README moved."""
    assert campaign_profit(256, 179, **ECON) == pytest.approx(6660.0)


def test_false_positives_only_cost_money():
    """A campaign that retains nobody can only lose the contact spend."""
    assert campaign_profit(0, 25, **ECON) == pytest.approx(-500.0)


def test_doing_nothing_is_exactly_zero():
    assert campaign_profit(0, 0, **ECON) == 0.0


@pytest.mark.parametrize(
    "container", [list, np.array, pd.Series], ids=["list", "ndarray", "Series"]
)
def test_works_elementwise_for_every_container_the_notebook_uses(container):
    """Cell 26 passes pandas columns, the appendices pass numpy arrays, the
    test-set cell passes scalars. All three must give the same answers."""
    tp = container([100, 0, 256])
    fp = container([50, 25, 179])
    result = np.asarray(campaign_profit(tp, fp, **ECON), dtype=float)
    np.testing.assert_allclose(result, [3000.0, -500.0, 6660.0])


def test_economics_are_keyword_only():
    """campaign_profit(tp, fp, 20, 200, 0.3) with clv and cost swapped would
    silently be wrong by 100x. Positional passing must not be possible."""
    with pytest.raises(TypeError):
        campaign_profit(100, 50, 200, 20, 0.3)


def test_defaults_are_the_shipped_economics():
    assert (DEFAULT_CLV, DEFAULT_COST, DEFAULT_SUCCESS_RATE) == (200.0, 20.0, 0.3)
    assert campaign_profit(256, 179) == campaign_profit(256, 179, **ECON)


@pytest.mark.parametrize(
    "bad",
    [{"clv": -1}, {"cost": -1}, {"success_rate": -0.1}, {"success_rate": 1.5}],
    ids=["negative-clv", "negative-cost", "negative-rate", "rate-above-one"],
)
def test_nonsense_economics_are_rejected(bad):
    with pytest.raises(ValueError):
        campaign_profit(10, 10, **{**ECON, **bad})


# ---------------------------------------------------------------------------
# break_even_threshold -- the closed form the grid search is compared against
# ---------------------------------------------------------------------------

def test_break_even_matches_the_documented_value():
    assert break_even_threshold(**ECON) == pytest.approx(1 / 3, abs=1e-9)


def test_break_even_is_the_indifference_point():
    """At exactly the break-even probability, contacting a customer must be
    worth zero -- that is what makes it the break-even point."""
    t = break_even_threshold(**ECON)
    expected_value = t * ECON["success_rate"] * ECON["clv"] - ECON["cost"]
    assert expected_value == pytest.approx(0.0, abs=1e-9)


def test_clv_and_success_rate_only_matter_as_a_product():
    """The sweep found clv and success_rate move the threshold identically,
    because the formula only ever multiplies them. Halving one equals
    halving the other."""
    assert break_even_threshold(clv=100, cost=20, success_rate=0.3) == pytest.approx(
        break_even_threshold(clv=200, cost=20, success_rate=0.15)
    )


def test_no_upside_means_no_threshold_justifies_the_spend():
    assert break_even_threshold(clv=0, cost=20, success_rate=0.3) == float("inf")


# ---------------------------------------------------------------------------
# confusion_at_threshold / profit_curve / best_threshold
# ---------------------------------------------------------------------------

def test_confusion_uses_greater_or_equal():
    """Both consumers decide with `>=`. A score exactly on the threshold is
    targeted, not skipped."""
    tp, fp = confusion_at_threshold([1, 0], [0.40, 0.40], 0.40)
    assert (tp, fp) == (1, 1)


def test_profit_curve_agrees_with_pointwise_computation():
    rng = np.random.default_rng(0)
    proba = rng.random(400)
    y = (rng.random(400) < proba).astype(int)
    thresholds = np.arange(0.05, 0.96, 0.01)
    curve = profit_curve(y, proba, thresholds, **ECON)
    for i in (0, 17, 45, 90):
        tp, fp = confusion_at_threshold(y, proba, thresholds[i])
        assert curve[i] == pytest.approx(campaign_profit(tp, fp, **ECON))


def test_best_threshold_finds_the_maximum_of_its_own_curve():
    rng = np.random.default_rng(1)
    proba = rng.random(500)
    y = (rng.random(500) < proba).astype(int)
    thresholds = np.arange(0.05, 0.96, 0.01)
    t, p = best_threshold(y, proba, thresholds, **ECON)
    assert p == pytest.approx(profit_curve(y, proba, thresholds, **ECON).max())
    assert t in thresholds


def test_ties_resolve_to_the_lowest_threshold():
    """The profit curve is flat near its optimum, so ties are common and the
    rule needs to be deliberate rather than incidental. A lower threshold
    targets more people, which is the conservative choice for retention."""
    y = np.array([1, 1, 0, 0])
    proba = np.array([0.9, 0.9, 0.1, 0.1])
    thresholds = np.array([0.2, 0.5, 0.8])  # all three separate the classes
    t, _ = best_threshold(y, proba, thresholds, **ECON)
    assert t == 0.2


def test_a_perfect_model_earns_the_theoretical_maximum():
    y = np.array([1] * 10 + [0] * 10)
    proba = np.array([0.99] * 10 + [0.01] * 10)
    _, p = best_threshold(y, proba, **ECON)
    assert p == pytest.approx(campaign_profit(10, 0, **ECON))


def test_all_negatives_never_beats_doing_nothing():
    """With no churners to retain, every threshold low enough to contact
    anyone loses money, so the best achievable profit is zero."""
    y = np.zeros(50, dtype=int)
    proba = np.linspace(0, 1, 50)
    _, p = best_threshold(y, proba, **ECON)
    assert p <= 0
