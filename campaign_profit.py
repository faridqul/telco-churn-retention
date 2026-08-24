"""The campaign profit formula, in one place.

Every threshold decision in this project is scored with the same arithmetic:
a retained churner is worth `success_rate * clv`, and every customer you
contact costs `cost` whether the retention works or not. Written out:

    profit = TP * success_rate * clv - (TP + FP) * cost

That expression was previously retyped in five places in the notebook, in
three different shapes (a pandas column, a scalar, and a loop body). Retyping
arithmetic is how a sign or a parenthesis quietly diverges between the number
you tune on and the number you report, so it lives here instead, imported by
the notebook and covered by tests/test_campaign_profit.py.

Note what is deliberately absent: false negatives carry no explicit term.
A churner you fail to contact costs you nothing *in this model* -- the lost
customer is already priced into the counterfactual, and adding a penalty for
them would double-count. True negatives are free for the same reason.
"""

from __future__ import annotations

import numpy as np

# The economics the project ships with. Illustrative, not measured -- see the
# sensitivity sweep in the notebook, which is the honest treatment of that.
DEFAULT_CLV = 200.0
DEFAULT_COST = 20.0
DEFAULT_SUCCESS_RATE = 0.3


def _validate(clv: float, cost: float, success_rate: float) -> None:
    if clv < 0:
        raise ValueError(f"clv must be non-negative, got {clv}")
    if cost < 0:
        raise ValueError(f"cost must be non-negative, got {cost}")
    if not 0.0 <= success_rate <= 1.0:
        raise ValueError(
            f"success_rate is a fraction of targeted churners retained and "
            f"must lie in [0, 1], got {success_rate}"
        )


def campaign_profit(
    true_positives,
    false_positives,
    *,
    clv: float = DEFAULT_CLV,
    cost: float = DEFAULT_COST,
    success_rate: float = DEFAULT_SUCCESS_RATE,
):
    """Expected campaign profit for a confusion-matrix slice.

    Works elementwise, so `true_positives` and `false_positives` may be
    scalars, numpy arrays or pandas Series -- the notebook needs all three.

    The economics are keyword-only on purpose. `campaign_profit(tp, fp, 200,
    20, 0.3)` and `campaign_profit(tp, fp, 20, 200, 0.3)` would both run and
    differ by a factor of a hundred; forcing the names makes that misordering
    impossible to write.
    """
    _validate(clv, cost, success_rate)
    # Coerce only plain sequences. numpy arrays and pandas Series are left
    # alone so a Series in gives a Series out -- cell 26 assigns the result
    # straight back onto a DataFrame, and keeping the index means that
    # assignment aligns rather than relying on positional order.
    if isinstance(true_positives, (list, tuple)):
        true_positives = np.asarray(true_positives)
    if isinstance(false_positives, (list, tuple)):
        false_positives = np.asarray(false_positives)
    revenue = true_positives * success_rate * clv
    spend = (true_positives + false_positives) * cost
    return revenue - spend


def break_even_threshold(
    *,
    clv: float = DEFAULT_CLV,
    cost: float = DEFAULT_COST,
    success_rate: float = DEFAULT_SUCCESS_RATE,
) -> float:
    """The probability at which contacting a customer breaks even.

    Contacting is worth it when `p * success_rate * clv > cost`, so the
    closed-form optimum is `cost / (success_rate * clv)` -- 0.333 at the
    default constants. The grid search lands above this because the model's
    probabilities run hot near the boundary; see the calibration cells.

    Returns inf when the upside is zero, which is the honest answer: no
    probability justifies the spend.
    """
    _validate(clv, cost, success_rate)
    upside = success_rate * clv
    return float("inf") if upside == 0 else cost / upside


def confusion_at_threshold(y_true, proba, threshold):
    """(true_positives, false_positives) at one cutoff, using `>=` -- the
    same comparison api.py and telco_model.py use to make a decision."""
    y_true = np.asarray(y_true)
    predicted = np.asarray(proba) >= threshold
    return int((predicted & (y_true == 1)).sum()), int((predicted & (y_true == 0)).sum())


def profit_curve(
    y_true,
    proba,
    thresholds,
    *,
    clv: float = DEFAULT_CLV,
    cost: float = DEFAULT_COST,
    success_rate: float = DEFAULT_SUCCESS_RATE,
) -> np.ndarray:
    """Profit at every candidate threshold at once.

    Vectorised across thresholds rather than looped: the bootstrap in the
    threshold-stability appendix calls this thousands of times, and the loop
    version turned a 2-second cell into a multi-minute one.
    """
    y_true = np.asarray(y_true)
    proba = np.asarray(proba)
    thresholds = np.asarray(thresholds)
    flags = proba[:, None] >= thresholds[None, :]
    tp = (flags & (y_true == 1)[:, None]).sum(axis=0)
    fp = (flags & (y_true == 0)[:, None]).sum(axis=0)
    return campaign_profit(tp, fp, clv=clv, cost=cost, success_rate=success_rate)


def best_threshold(
    y_true,
    proba,
    thresholds=None,
    *,
    clv: float = DEFAULT_CLV,
    cost: float = DEFAULT_COST,
    success_rate: float = DEFAULT_SUCCESS_RATE,
) -> tuple[float, float]:
    """(threshold, profit) at the profit-maximising cutoff.

    Ties go to the LOWEST threshold. The profit curve is flat near its
    optimum -- the appendix measures the plateau at roughly 0.11 wide -- so
    ties are common and `argmax`'s first-wins behaviour needs to be a stated
    rule rather than an accident of implementation.
    """
    if thresholds is None:
        thresholds = np.arange(0.05, 0.96, 0.01)
    thresholds = np.asarray(thresholds)
    curve = profit_curve(y_true, proba, thresholds,
                         clv=clv, cost=cost, success_rate=success_rate)
    best = int(np.argmax(curve))
    return float(thresholds[best]), float(curve[best])
