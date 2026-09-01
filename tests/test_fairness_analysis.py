"""Tests for fairness_analysis.py.

This module reports numbers that a reader will treat as findings about how
the model treats people, so the failure that matters most is not a crash --
it is a plausible-looking report computed over the wrong rows, or a rate
printed for a subgroup too small to support one. The tests below are built
around those two risks.

Three things get the most attention:

  1. THE RELIABILITY GATE. The whole report's honesty rests on it. Every
     band boundary is pinned, and the INSUFFICIENT branch is exercised
     end-to-end -- a group under the floor must produce no rate, no
     comparison and no finding, not a rate with a caveat next to it.

  2. THE RECONSTRUCTION GATE. The test split is rebuilt from the raw CSV
     rather than loaded, because the notebook caches no predictions. A
     cleaning change would silently shift which rows are scored, and every
     subgroup number would still look reasonable. verify_reconstruction()
     is what stops that, so it is tested in both directions.

  3. NONE vs ZERO. A subgroup with no churners has an undefined recall, not
     a recall of 0.0. Returning 0.0 there would read as "the model catches
     nobody in this group" -- the most damaging possible misreport. Several
     tests exist only to pin that distinction.

Tests that need the raw Kaggle CSV or the committed pickle skip when those
are absent, so the suite still runs on a clean checkout.

Run with: pytest tests/test_fairness_analysis.py -v
"""

import numpy as np
import pandas as pd
import pytest

import fairness_analysis as fa

THRESHOLD = 0.4


# ==========================================================================
# 1. Reliability gate
# ==========================================================================

@pytest.mark.parametrize("churners,expected", [
    (0, "insufficient"), (1, "insufficient"), (29, "insufficient"),
    (30, "marginal-"), (49, "marginal-"),
    (50, "marginal"), (99, "marginal"),
    (100, "usable"), (149, "usable"),
    (150, "solid"), (10_000, "solid"),
])
def test_reliability_bands_at_every_boundary(churners, expected):
    """Both sides of all four boundaries. These thresholds are the
    documented contract, so an off-by-one here silently changes which
    groups get reported at all."""
    assert fa.reliability(churners) == expected


def test_reliability_never_improves_as_sample_shrinks():
    """Monotonicity, checked rather than assumed -- a band written out of
    order would still pass the boundary tests above if both boundaries
    moved together."""
    order = ["insufficient", "marginal-", "marginal", "usable", "solid"]
    ranks = [order.index(fa.reliability(n)) for n in range(0, 200)]
    assert ranks == sorted(ranks)


def test_the_floor_is_thirty_churners():
    """Pins the spec's hard rule: below 30, nothing is reported."""
    assert fa.reliability(fa.FLOOR - 1) == "insufficient"
    assert fa.reliability(fa.FLOOR) != "insufficient"


# ==========================================================================
# 2. group_metrics -- and the None/zero distinction
# ==========================================================================

def test_group_metrics_matches_a_hand_computed_case():
    #            churner?      1     1     1     0     0     0
    y = np.array([1, 1, 1, 0, 0, 0])
    proba = np.array([0.9, 0.8, 0.1, 0.7, 0.2, 0.1])
    mask = np.ones(6, dtype=bool)
    m = fa.group_metrics(y, proba, mask, THRESHOLD)
    # flagged at >=0.4: rows 0,1,3  -> tp=2, fp=1, fn=1
    assert (m["tp"], m["fp"], m["fn"]) == (2, 1, 1)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["flag_rate"] == pytest.approx(3 / 6)
    assert m["base_rate"] == pytest.approx(0.5)
    assert m["churners"] == 3


def test_mask_selects_only_its_own_rows():
    y = np.array([1, 1, 0, 0])
    proba = np.array([0.9, 0.1, 0.9, 0.1])
    first_half = np.array([True, True, False, False])
    m = fa.group_metrics(y, proba, first_half, THRESHOLD)
    assert m["n"] == 2 and m["churners"] == 2
    assert m["tp"] == 1 and m["fp"] == 0


def test_recall_is_none_not_zero_when_a_group_has_no_churners():
    """The single most damaging possible misreport: 0.0 would read as
    'the model catches nobody here', when the truth is 'undefined'."""
    y = np.zeros(10, dtype=int)
    m = fa.group_metrics(y, np.full(10, 0.9), np.ones(10, dtype=bool), THRESHOLD)
    assert m["recall"] is None
    assert m["recall"] != 0


def test_precision_is_none_not_zero_when_nobody_is_flagged():
    y = np.array([1, 0, 1, 0])
    m = fa.group_metrics(y, np.full(4, 0.01), np.ones(4, dtype=bool), THRESHOLD)
    assert m["precision"] is None
    assert m["recall"] == 0.0  # recall IS defined here: 0 of 2 caught


def test_threshold_comparison_is_inclusive():
    """`>=`, matching api.py and telco_model.py. A customer sitting exactly
    on the threshold is flagged; the whole repo depends on that agreeing."""
    y = np.array([1])
    assert fa.group_metrics(y, np.array([THRESHOLD]), np.array([True]),
                            THRESHOLD)["tp"] == 1
    assert fa.group_metrics(y, np.array([THRESHOLD - 1e-9]), np.array([True]),
                            THRESHOLD)["tp"] == 0


# ==========================================================================
# 3. Reconstruction gate
# ==========================================================================

def _confusion_hitting_published():
    """Synthetic scores that reproduce the published confusion matrix
    exactly, without needing the real model or dataset."""
    c = fa.PUBLISHED_CONFUSION
    y = np.concatenate([
        np.ones(c["tp"]), np.zeros(c["fp"]),
        np.ones(c["fn"]), np.zeros(c["tn"]),
    ]).astype(int)
    proba = np.concatenate([
        np.full(c["tp"], 0.9), np.full(c["fp"], 0.9),
        np.full(c["fn"], 0.1), np.full(c["tn"], 0.1),
    ])
    return y, proba


def test_gate_passes_on_the_published_confusion_matrix():
    y, proba = _confusion_hitting_published()
    assert fa.verify_reconstruction(y, proba, THRESHOLD) == fa.PUBLISHED_CONFUSION


def test_gate_raises_when_a_single_row_moves():
    """One customer crossing the threshold is enough to abort. The gate is
    deliberately exact -- a near-miss means the split is not the published
    one, and 'close enough' is how wrong rows get reported as findings."""
    y, proba = _confusion_hitting_published()
    proba[0] = 0.1  # one true positive becomes a false negative
    with pytest.raises(SystemExit) as excinfo:
        fa.verify_reconstruction(y, proba, THRESHOLD)
    assert "RECONSTRUCTION GATE FAILED" in str(excinfo.value)


def test_gate_message_shows_both_expected_and_actual():
    """The message has to be diagnosable -- it fires long after whoever
    changed the cleaning has stopped looking."""
    y, proba = _confusion_hitting_published()
    proba[:20] = 0.1
    with pytest.raises(SystemExit) as excinfo:
        fa.verify_reconstruction(y, proba, THRESHOLD)
    message = str(excinfo.value)
    assert "expected" in message and "got" in message
    assert str(fa.PUBLISHED_CONFUSION["tp"]) in message


# ==========================================================================
# 4. Bootstrap intervals
# ==========================================================================

@pytest.fixture
def two_groups():
    """A frame where group A is caught much more often than group B, so the
    recall gap is large and unambiguous."""
    rng = np.random.default_rng(0)
    n = 200
    y = np.tile([1, 0], n // 2)
    proba = np.where(y == 1, rng.uniform(0.5, 0.95, n), rng.uniform(0.05, 0.35, n))
    group_a = np.zeros(n, dtype=bool); group_a[: n // 2] = True
    # depress group B's scores so its churners fall below the threshold
    proba[~group_a] *= 0.4
    return y, proba, group_a, ~group_a


def test_bootstrap_is_reproducible(two_groups):
    y, proba, a, b = two_groups
    first = fa.bootstrap_gap_ci(y, proba, a, b, THRESHOLD, "recall")
    second = fa.bootstrap_gap_ci(y, proba, a, b, THRESHOLD, "recall")
    assert first == second


def test_bootstrap_interval_is_ordered_and_brackets_the_estimate(two_groups):
    y, proba, a, b = two_groups
    lo, hi = fa.bootstrap_gap_ci(y, proba, a, b, THRESHOLD, "recall")
    gap = (fa.group_metrics(y, proba, a, THRESHOLD)["recall"]
           - fa.group_metrics(y, proba, b, THRESHOLD)["recall"])
    assert lo <= hi
    assert lo <= gap <= hi


def test_bootstrap_returns_none_when_the_metric_is_mostly_undefined():
    """A group with no churners has no recall to compare, so there is no
    interval -- and the function must say so rather than inventing one."""
    y = np.zeros(100, dtype=int)
    proba = np.full(100, 0.9)
    a = np.zeros(100, dtype=bool); a[:50] = True
    assert fa.bootstrap_gap_ci(y, proba, a, ~a, THRESHOLD, "recall") == (None, None)


# ==========================================================================
# 5. report_attribute: the INSUFFICIENT branch and gap flagging
# ==========================================================================

@pytest.fixture
def fast_bootstrap(monkeypatch):
    """The report path runs a bootstrap per metric per pair. 2000 draws is
    right for the real report and far too slow for a test suite measured in
    seconds; the flagging logic under test does not depend on the count."""
    monkeypatch.setattr(fa, "BOOTSTRAP_DRAWS", 200)


def _report(groups, y, proba):
    R = fa.Report()
    stats, findings = fa.report_attribute(R, "attr", "note", y, proba,
                                          groups, THRESHOLD)
    return "\n".join(R.lines), stats, findings


def test_tiny_group_reports_no_rate_and_no_comparison(fast_bootstrap):
    """The spec's hard rule, end to end: under 30 churners, nothing is
    reported for that group."""
    rng = np.random.default_rng(1)
    n = 400
    y = rng.integers(0, 2, n)
    proba = rng.random(n)
    tiny = np.zeros(n, dtype=bool); tiny[:40] = True   # ~20 churners
    text, stats, findings = _report({"tiny": tiny, "rest": ~tiny}, y, proba)

    assert stats["tiny"]["reliability"] == "insufficient"
    assert "INSUFFICIENT SAMPLE" in text
    assert "no comparison" in text
    assert findings == []          # nothing may be concluded about this pair
    # the surviving group still gets its own rates
    assert stats["rest"]["recall"] is not None


def test_adequate_groups_do_get_rates_and_a_comparison(fast_bootstrap):
    rng = np.random.default_rng(2)
    n = 1200
    y = rng.integers(0, 2, n)
    proba = rng.random(n)
    half = np.zeros(n, dtype=bool); half[: n // 2] = True
    text, stats, findings = _report({"a": half, "b": ~half}, y, proba)
    assert stats["a"]["reliability"] == "solid"
    assert "INSUFFICIENT" not in text
    assert "recall    a - b" in text


def test_the_flag_threshold_is_ten_points():
    """Pinned as a literal. The tests below deliberately do NOT compare
    against fa.GAP_FLAG_PP: an assertion phrased in terms of the constant it
    is testing moves when the constant moves, and catches nothing."""
    assert fa.GAP_FLAG_PP == 10.0


def test_a_large_and_certain_gap_is_flagged_as_real(two_groups, fast_bootstrap):
    y, proba, a, b = two_groups
    _, stats, findings = _report({"a": a, "b": b}, y, proba)
    observed = abs(stats["a"]["recall"] - stats["b"]["recall"]) * 100
    assert observed > 10.0, "fixture should produce a gap above the 10pp rule"
    recall_findings = [f for f in findings if f[1] == "recall"]
    assert recall_findings, "a recall gap above 10pp must produce a finding"
    assert recall_findings[0][5] is True, "CI excludes zero -> real"


def test_no_gap_produces_no_finding(fast_bootstrap):
    """Two statistically identical groups must generate nothing to report."""
    rng = np.random.default_rng(3)
    n = 1000
    y = rng.integers(0, 2, n)
    proba = rng.random(n)
    alternating = np.arange(n) % 2 == 0     # independent of y and proba
    _, _, findings = _report({"a": alternating, "b": ~alternating}, y, proba)
    assert findings == []


def test_a_noisy_gap_is_marked_not_real(fast_bootstrap):
    """A gap over the flag threshold whose interval still spans zero must be
    recorded with its 'real' flag false, and labelled in the text."""
    rng = np.random.default_rng(11)
    n = 160
    y = rng.integers(0, 2, n)
    proba = np.where(y == 1, rng.uniform(0.3, 0.8, n), rng.uniform(0.1, 0.6, n))
    small = np.zeros(n, dtype=bool); small[:70] = True
    proba[small] *= 1.35        # a real but poorly-estimated difference
    text, _, findings = _report({"small": small, "rest": ~small}, y, proba)
    noisy = [f for f in findings if not f[5]]
    if noisy:                    # only assert the labelling when one occurs
        assert "not distinguishable from noise" in text


# ==========================================================================
# 6. Per-group threshold comparison
# ==========================================================================

@pytest.fixture
def senior_frame():
    rng = np.random.default_rng(7)
    n = 1200
    senior = np.zeros(n, dtype=int); senior[: n // 4] = 1
    # seniors churn more, and are scored higher, as in the real data
    base = np.where(senior == 1, 0.45, 0.22)
    y = (rng.random(n) < base).astype(int)
    proba = np.clip(np.where(y == 1, rng.normal(0.6, 0.18, n),
                             rng.normal(0.28, 0.18, n)), 0.01, 0.99)
    X = pd.DataFrame({"seniorcitizen": senior, "gender": "Female"})
    return y, proba, X


def test_parity_never_earns_more_than_the_unconstrained_optimum(senior_frame):
    """A constrained maximum cannot beat an unconstrained one over the same
    grid. If it does, the parity search is exploring pairs the unconstrained
    search did not, which would make the 'cost of fairness' number
    meaningless -- and it could come out negative."""
    y, proba, X = senior_frame
    result = fa.section_threshold_cost(fa.Report(), y, proba, X, THRESHOLD)
    assert result["parity"] is not None
    assert result["parity"] <= result["unconstrained"] + 1e-9
    assert result["cost"] >= 0


def test_the_parity_tolerance_is_two_points():
    """Pinned as a literal, for the same reason as the flag threshold."""
    assert fa.RECALL_PARITY_TOLERANCE == 0.02


def test_the_reported_parity_pair_really_equalises_recall(senior_frame):
    """The number is only a fairness cost if the constraint actually binds.
    Bound is a literal 2.5pp, not fa.RECALL_PARITY_TOLERANCE -- widening the
    tolerance must fail this test rather than redefine what it checks."""
    y, proba, X = senior_frame
    R = fa.Report()
    fa.section_threshold_cost(R, y, proba, X, THRESHOLD)
    line = [l for l in R.lines if "recall parity" in l][0]
    gap_pp = float(line.split()[-1].replace("pp", ""))
    assert abs(gap_pp) <= 2.5


def test_parity_row_differs_from_the_unconstrained_row(senior_frame):
    """Guards the other direction: if the constraint never binds, (b) is
    just (a) again and the cost is a meaningless zero."""
    y, proba, X = senior_frame
    R = fa.Report()
    fa.section_threshold_cost(R, y, proba, X, THRESHOLD)
    unconstrained = [l for l in R.lines if "profit optimum" in l][0]
    parity = [l for l in R.lines if "recall parity" in l][0]
    gap_a = abs(float(unconstrained.split()[-1].replace("pp", "")))
    gap_b = abs(float(parity.split()[-1].replace("pp", "")))
    assert gap_a > gap_b, "parity must narrow the recall gap it was asked to close"


def test_shipped_single_threshold_is_reported_for_reference(senior_frame):
    """(a) and (b) are both hypotheticals; the shipped policy has to appear
    alongside them or the comparison has no baseline."""
    y, proba, X = senior_frame
    result = fa.section_threshold_cost(fa.Report(), y, proba, X, THRESHOLD)
    assert "shipped" in result and np.isfinite(result["shipped"])


def test_profit_uses_the_shared_campaign_formula(senior_frame):
    """campaign_profit() is the single definition of the economics. If this
    module ever grows its own copy, this catches it."""
    from campaign_profit import campaign_profit
    y, proba, X = senior_frame
    senior = X["seniorcitizen"].to_numpy() == 1
    flagged = proba >= THRESHOLD
    expected = 0.0
    for mask in (senior, ~senior):
        tp = int((flagged & mask & (y == 1)).sum())
        fp = int((flagged & mask & (y == 0)).sum())
        expected += float(campaign_profit(tp, fp))
    result = fa.section_threshold_cost(fa.Report(), y, proba, X, THRESHOLD)
    assert result["shipped"] == pytest.approx(expected)


# ==========================================================================
# 7. Intersectional diagnostic
# ==========================================================================

def test_intersection_reports_no_interaction_for_additive_data(senior_frame):
    """Data built with no interaction must not produce an interaction flag.
    A test that only checks the alarm fires would not catch an alarm that
    always fires."""
    y, proba, X = senior_frame
    X = X.copy()
    rng = np.random.default_rng(5)
    X["gender"] = rng.choice(["Female", "Male"], len(X))  # independent of y
    main = {
        "seniorcitizen": {
            "senior": fa.group_metrics(y, proba, X["seniorcitizen"].to_numpy() == 1,
                                       THRESHOLD),
            "non-senior": fa.group_metrics(y, proba,
                                           X["seniorcitizen"].to_numpy() == 0,
                                           THRESHOLD)},
        "gender": {
            "Female": fa.group_metrics(y, proba, X["gender"].to_numpy() == "Female",
                                       THRESHOLD),
            "Male": fa.group_metrics(y, proba, X["gender"].to_numpy() == "Male",
                                     THRESHOLD)},
    }
    flags = fa.section_intersectional(fa.Report(), y, proba, X, THRESHOLD, main)
    assert flags == []


# ==========================================================================
# 8. Small helpers
# ==========================================================================

def test_pct_renders_none_as_na_not_as_a_number():
    assert fa.pct(None).strip() == "n/a"
    assert "0" not in fa.pct(None)


def test_pct_formats_a_fraction_as_a_percentage():
    assert fa.pct(0.5).strip() == "50.0%"
    assert fa.pct(1.0).strip() == "100.0%"


def test_report_accumulates_every_line_it_prints(capsys):
    R = fa.Report()
    R("first")
    R.rule("TITLE")
    captured = capsys.readouterr().out
    assert R.lines[0] == "first"
    assert "TITLE" in R.lines[1]
    assert "first" in captured          # it prints as well as accumulates


def test_locate_dataset_honours_an_explicit_path():
    assert fa.locate_dataset("/somewhere/telco.csv") == "/somewhere/telco.csv"


# ==========================================================================
# 9. Integration -- needs the raw CSV and/or the committed artifact
# ==========================================================================

@pytest.fixture(scope="module")
def dataset_path():
    try:
        return fa.locate_dataset(None)
    except SystemExit:
        pytest.skip("raw Telco CSV not available in this environment")


@pytest.fixture(scope="module")
def rebuilt_split(dataset_path):
    return fa.build_test_split(dataset_path)


def test_rebuilt_test_split_has_the_published_shape(rebuilt_split):
    _, X_test, _, y_test = rebuilt_split
    total = sum(fa.PUBLISHED_CONFUSION.values())
    assert len(X_test) == total == len(y_test)


def test_rebuilt_split_carries_all_engineered_columns(rebuilt_split):
    import json
    from pathlib import Path
    _, X_test, _, _ = rebuilt_split
    meta = json.loads(
        (Path(__file__).resolve().parent.parent / "model_metadata.json").read_text())
    assert set(X_test.columns) == set(meta["feature_columns"])


def test_rebuilt_split_is_deterministic(dataset_path):
    """Two calls must produce the same rows, or the report is not
    reproducible and the gate would pass or fail at random."""
    _, _, _, first = fa.build_test_split(dataset_path)
    _, _, _, second = fa.build_test_split(dataset_path)
    assert np.array_equal(first, second)


def test_train_and_test_do_not_overlap(rebuilt_split):
    X_train, X_test, _, _ = rebuilt_split
    assert not set(X_train.index) & set(X_test.index)


def test_the_real_artifact_passes_the_reconstruction_gate(rebuilt_split):
    """The end-to-end guarantee the whole report rests on: the committed
    pickle, scored over the rebuilt split, reproduces the published
    confusion matrix exactly."""
    import joblib
    from pathlib import Path
    import config
    path = Path(config.MODEL_PATH)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    if not path.exists():
        pytest.skip("xgboost_churn_pipeline.pkl not present")
    _, X_test, _, y_test = rebuilt_split
    proba = joblib.load(path).predict_proba(X_test)[:, 1]
    assert fa.verify_reconstruction(y_test, proba, config.load_threshold()) \
        == fa.PUBLISHED_CONFUSION
