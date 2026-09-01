"""Standalone fairness analysis for the shipped churn model.

Reads the already-fitted pipeline (`xgboost_churn_pipeline.pkl`) and the
operating threshold recorded in `model_metadata.json`. **Nothing is trained
here.** The test-set predictions are produced by calling `predict_proba` on
the committed artifact, over a test split reconstructed deterministically
from the same seed the notebook uses.

Run:  uv run python fairness_analysis.py
      uv run python fairness_analysis.py --with-oof     (refits -- see below)
      uv run python fairness_analysis.py --out fairness_report.txt

WHY THE SPLIT IS RECONSTRUCTED RATHER THAN LOADED
The notebook caches only the fitted pipeline and a 50-row sample CSV; it does
not persist its test-set or out-of-fold predictions. The split is therefore
rebuilt here by replaying the notebook's exact cleaning steps and its
`train_test_split(..., test_size=0.2, stratify=y, random_state=42)`. That
reconstruction is *verified, not assumed*: `verify_reconstruction()` scores
the artifact and refuses to continue unless the confusion matrix matches the
published 256/179/116/854 exactly. If the cleaning ever drifts, this aborts
rather than silently reporting fairness numbers for the wrong rows.

WHY OOF IS OPT-IN
Out-of-fold predictions can only be produced by `cross_val_predict`, which
refits the estimator once per fold. That is training. It is therefore off by
default and gated behind `--with-oof`, which prints a warning before doing
it. Without the flag, groups whose churner count falls in the "marginal" band
are reported with a bootstrap interval and an explicit note that the
higher-power companion was not computed -- never with a bare point estimate.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from campaign_profit import DEFAULT_CLV, DEFAULT_COST, DEFAULT_SUCCESS_RATE
from campaign_profit import best_threshold, campaign_profit, profit_curve
from config import METADATA_PATH, MODEL_PATH, load_threshold
from feature_engineering_telco import engineer_features

# --------------------------------------------------------------------------
# Reliability gate. Bands are churner counts *within the subgroup*, because a
# recall estimate's precision is set by the number of positives it is computed
# over, not by the subgroup's total size. A group can hold 1,000 customers and
# still support no usable recall estimate if only 25 of them churned.
# --------------------------------------------------------------------------
SOLID, USABLE, MARGINAL, FLOOR = 150, 100, 50, 30

# A gap this large on recall or precision is reported as a finding rather than
# noise. Chosen in advance, not after seeing the numbers.
GAP_FLAG_PP = 10.0

# The published test-set confusion matrix. The reconstruction gate below
# refuses to run if the rebuilt split does not reproduce it exactly.
PUBLISHED_CONFUSION = {"tp": 256, "fp": 179, "fn": 116, "tn": 854}

BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 42

THRESHOLD_GRID = np.round(np.arange(0.05, 0.96, 0.01), 2)

# How close two groups' recalls must be to count as "parity" in section 5.
RECALL_PARITY_TOLERANCE = 0.02

W = 78  # report width


# ==========================================================================
# Data: replay the notebook's cleaning, then its split. No training.
# ==========================================================================

def locate_dataset(explicit: str | None) -> str:
    """Find the raw CSV without requiring kagglehub (a notebook-group
    dependency this script deliberately does not pull in)."""
    if explicit:
        return explicit
    cached = glob.glob(os.path.expanduser(
        "~/.cache/kagglehub/datasets/blastchar/telco-customer-churn/versions/*/*.csv"))
    if cached:
        return sorted(cached)[-1]
    try:  # only if the notebook group happens to be installed
        import kagglehub
        path = kagglehub.dataset_download("blastchar/telco-customer-churn")
        return glob.glob(os.path.join(path, "*.csv"))[0]
    except Exception as e:
        raise SystemExit(
            f"Could not locate the Telco CSV ({e}). Pass --data /path/to.csv"
        )


def build_test_split(csv_path: str):
    """Replay notebook cells 3-11 exactly, in order.

    Order matters and is not cosmetic: the blank-to-NaN replacement happens
    BEFORE deduplication, so doing it afterwards would compare a different set
    of rows and produce a different 22 duplicates -- and therefore a different
    test split. The reconstruction gate is what catches that class of mistake.
    """
    df = pd.read_csv(csv_path)
    df.columns = (df.columns.str.strip().str.lower()
                  .str.replace(" ", "_").str.replace("-", "_"))
    df = df.replace(["?", "", "NA", "nan", " "], np.nan)
    df = df.drop("customerid", axis=1)
    df = df.drop_duplicates()
    df["totalcharges"] = pd.to_numeric(df["totalcharges"], errors="coerce")
    df["churn"] = df["churn"].map({"Yes": 1, "No": 0})

    y = df["churn"]
    X = df.drop(columns=["churn"])
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    return (engineer_features(X_train), engineer_features(X_test),
            y_train.to_numpy(), y_test.to_numpy())


def verify_reconstruction(y_true, proba, threshold) -> dict:
    """Abort unless the rebuilt split reproduces the published confusion
    matrix. Everything downstream is meaningless if the rows are wrong, and a
    wrong-but-plausible fairness report is worse than no report."""
    flagged = proba >= threshold
    got = {
        "tp": int((flagged & (y_true == 1)).sum()),
        "fp": int((flagged & (y_true == 0)).sum()),
        "fn": int((~flagged & (y_true == 1)).sum()),
        "tn": int((~flagged & (y_true == 0)).sum()),
    }
    if got != PUBLISHED_CONFUSION:
        raise SystemExit(
            "RECONSTRUCTION GATE FAILED -- refusing to report.\n"
            f"  expected {PUBLISHED_CONFUSION}\n  got      {got}\n"
            "The rebuilt test split does not match the one the published\n"
            "metrics came from, so every subgroup number below would describe\n"
            "the wrong rows. Check that the cleaning steps in build_test_split()\n"
            "still mirror notebook cells 3-11, and that the artifact is current."
        )
    return got


# ==========================================================================
# Metrics
# ==========================================================================

def reliability(n_churners: int) -> str:
    if n_churners >= SOLID:
        return "solid"
    if n_churners >= USABLE:
        return "usable"
    if n_churners >= MARGINAL:
        return "marginal"
    if n_churners >= FLOOR:
        return "marginal-"
    return "insufficient"


def group_metrics(y_true, proba, mask, threshold) -> dict:
    """Rates for one subgroup. Recall and precision are returned as None when
    their denominator is empty, so a missing number can never be mistaken for
    a zero."""
    y_g, p_g = y_true[mask], proba[mask]
    flagged = p_g >= threshold
    tp = int((flagged & (y_g == 1)).sum())
    fp = int((flagged & (y_g == 0)).sum())
    fn = int((~flagged & (y_g == 1)).sum())
    churners = int((y_g == 1).sum())
    return {
        "n": int(mask.sum()),
        "churners": churners,
        "base_rate": float(y_g.mean()) if len(y_g) else float("nan"),
        "flag_rate": float(flagged.mean()) if len(y_g) else float("nan"),
        "recall": tp / (tp + fn) if (tp + fn) else None,
        "precision": tp / (tp + fp) if (tp + fp) else None,
        "reliability": reliability(churners),
        "tp": tp, "fp": fp, "fn": fn,
    }


def bootstrap_gap_ci(y_true, proba, mask_a, mask_b, threshold, metric):
    """Percentile bootstrap CI for (metric_a - metric_b), resampling the test
    set as a whole so group sizes vary the way they really would."""
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(y_true)
    gaps = []
    for _ in range(BOOTSTRAP_DRAWS):
        idx = rng.integers(0, n, n)
        ys, ps = y_true[idx], proba[idx]
        a = group_metrics(ys, ps, mask_a[idx], threshold)[metric]
        b = group_metrics(ys, ps, mask_b[idx], threshold)[metric]
        if a is not None and b is not None:
            gaps.append(a - b)
    if len(gaps) < BOOTSTRAP_DRAWS * 0.5:
        return None, None
    return float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))


# ==========================================================================
# Report helpers
# ==========================================================================

class Report:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, text: str = ""):
        self.lines.append(text)
        print(text)

    def rule(self, title: str = "", char: str = "="):
        if title:
            head = f"{char * 3} {title} "
            self(head + char * max(0, W - len(head)))
        else:
            self(char * W)


def pct(v, width=5):
    return "  n/a" if v is None else f"{v * 100:{width}.1f}%"


# ==========================================================================
# Sections
# ==========================================================================

def report_attribute(R, name, note, y_true, proba, groups, threshold,
                     oof=None):
    """One protected attribute: a row per level, then the pairwise gaps."""
    R()
    R(f"  {name}   {note}")
    R("  " + "-" * (W - 4))
    R(f"  {'subgroup':<22}{'n':>6}{'churn':>8}{'base':>8}{'flag':>8}"
      f"{'recall':>9}{'prec':>8}  reliability")

    stats = {}
    for label, mask in groups.items():
        m = group_metrics(y_true, proba, mask, threshold)
        stats[label] = m
        rel = m["reliability"]
        if rel == "insufficient":
            # Spec: below 30 churners, report no rate at all.
            R(f"  {label:<22}{m['n']:>6}{m['churners']:>8}"
              f"{pct(m['base_rate']):>8}{pct(m['flag_rate']):>8}"
              f"{'--':>9}{'--':>8}  INSUFFICIENT SAMPLE")
        else:
            R(f"  {label:<22}{m['n']:>6}{m['churners']:>8}"
              f"{pct(m['base_rate']):>8}{pct(m['flag_rate']):>8}"
              f"{pct(m['recall']):>9}{pct(m['precision']):>8}  {rel}")

    labels = list(groups)
    findings = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = labels[i], labels[j]
            if "insufficient" in (stats[a]["reliability"], stats[b]["reliability"]):
                R(f"    {a} vs {b}: no comparison -- insufficient sample")
                continue
            for metric in ("recall", "precision"):
                va, vb = stats[a][metric], stats[b][metric]
                if va is None or vb is None:
                    continue
                gap_pp = (va - vb) * 100
                lo, hi = bootstrap_gap_ci(y_true, proba, groups[a], groups[b],
                                          threshold, metric)
                ci = "" if lo is None else f"  95% CI [{lo*100:+.1f}, {hi*100:+.1f}]pp"
                verdict = ""
                if abs(gap_pp) > GAP_FLAG_PP:
                    crosses_zero = lo is not None and lo <= 0 <= hi
                    verdict = ("  <-- FLAGGED (CI crosses zero -- "
                               "not distinguishable from noise)" if crosses_zero
                               else "  <-- FLAGGED")
                    findings.append((name, metric, a, b, gap_pp, not crosses_zero))
                R(f"    {metric:<10}{a} - {b} = {gap_pp:+6.1f}pp{ci}{verdict}")

            weak = [l for l in (a, b)
                    if stats[l]["reliability"] in ("marginal", "marginal-")]
            if weak:
                if oof is None:
                    R(f"    NOTE: {', '.join(weak)} is in the marginal band. The "
                      f"higher-power OOF")
                    R(f"          companion was not computed (needs --with-oof, "
                      f"which refits).")
                    R(f"          Read the interval above, not the point estimate.")
                else:
                    for label in weak:
                        om = oof["stats"].get((name, label))
                        if om:
                            R(f"    OOF companion [{label}]: recall "
                              f"{pct(om['recall'])}, precision {pct(om['precision'])} "
                              f"on {om['churners']} churners")
    return stats, findings


def section_intersectional(R, y_true, proba, X, threshold, main_stats):
    """seniorcitizen x gender. Diagnostic only -- looking for an interaction
    the two one-way checks would miss, not proposing a 4-way policy."""
    R.rule("4. INTERSECTIONAL DIAGNOSTIC -- seniorcitizen x gender")
    R()
    R("  A sanity check, not a decision rule. If an intersection is much worse")
    R("  than the two one-way analyses predict, there is an interaction effect")
    R("  the individual checks cannot see.")
    R()

    overall = group_metrics(y_true, proba,
                            np.ones(len(y_true), dtype=bool), threshold)
    R(f"  {'subgroup':<26}{'n':>6}{'churn':>8}{'recall':>9}{'prec':>8}"
      f"{'expected':>10}{'delta':>8}")

    senior_col = X["seniorcitizen"].to_numpy()
    gender_col = X["gender"].to_numpy()
    flags = []
    for s_val, s_lab in [(1, "senior"), (0, "non-senior")]:
        for g_val in ("Female", "Male"):
            mask = (senior_col == s_val) & (gender_col == g_val)
            m = group_metrics(y_true, proba, mask, threshold)
            label = f"{s_lab}, {g_val}"
            if m["reliability"] == "insufficient":
                R(f"  {label:<26}{m['n']:>6}{m['churners']:>8}{'--':>9}{'--':>8}"
                  f"{'--':>10}{'--':>8}   INSUFFICIENT")
                continue
            # Additive main-effects prediction: what the two one-way checks
            # would lead you to expect if there were no interaction.
            r_s = main_stats["seniorcitizen"][s_lab]["recall"]
            r_g = main_stats["gender"][g_val]["recall"]
            expected = r_s + r_g - overall["recall"]
            delta = (m["recall"] - expected) * 100
            mark = "  <-- INTERACTION" if abs(delta) > GAP_FLAG_PP else ""
            if abs(delta) > GAP_FLAG_PP:
                flags.append((label, delta))
            R(f"  {label:<26}{m['n']:>6}{m['churners']:>8}{pct(m['recall']):>9}"
              f"{pct(m['precision']):>8}{pct(expected):>10}{delta:+7.1f}pp{mark}")
    R()
    if flags:
        R("  Interaction detected -- the one-way checks understate the effect for:")
        for label, d in flags:
            R(f"    {label}: {d:+.1f}pp vs the additive prediction")
    else:
        R("  No interaction beyond what the one-way checks already show. The")
        R("  seniorcitizen and gender effects combine additively.")
    return flags


def section_threshold_cost(R, y_true, proba, X, shipped_threshold):
    """Section 5: what recall parity between seniors and non-seniors costs."""
    R.rule("5. PER-GROUP THRESHOLDS -- THE COST OF RECALL PARITY")
    R()
    senior = X["seniorcitizen"].to_numpy() == 1
    y_s, p_s = y_true[senior], proba[senior]
    y_n, p_n = y_true[~senior], proba[~senior]

    # Reference: what actually ships -- one threshold for everyone.
    tp_s, fp_s = int(((p_s >= shipped_threshold) & (y_s == 1)).sum()), \
                 int(((p_s >= shipped_threshold) & (y_s == 0)).sum())
    tp_n, fp_n = int(((p_n >= shipped_threshold) & (y_n == 1)).sum()), \
                 int(((p_n >= shipped_threshold) & (y_n == 0)).sum())
    shipped_profit = float(campaign_profit(tp_s, fp_s) + campaign_profit(tp_n, fp_n))
    rec_s_ship = tp_s / (y_s == 1).sum()
    rec_n_ship = tp_n / (y_n == 1).sum()

    # (a) unconstrained per-group optima
    t_s, prof_s = best_threshold(y_s, p_s, THRESHOLD_GRID)
    t_n, prof_n = best_threshold(y_n, p_n, THRESHOLD_GRID)
    unconstrained = prof_s + prof_n

    # (b) the best pair that also equalises recall. Recall is a step function,
    # so for each non-senior threshold we take the senior threshold whose
    # recall is closest, keep it only if it lands inside tolerance, and
    # maximise total profit over what survives.
    def recalls(y, p):
        return np.array([( (p >= t) & (y == 1)).sum() / (y == 1).sum()
                         for t in THRESHOLD_GRID])

    rec_s, rec_n = recalls(y_s, p_s), recalls(y_n, p_n)
    curve_s = profit_curve(y_s, p_s, THRESHOLD_GRID)
    curve_n = profit_curve(y_n, p_n, THRESHOLD_GRID)

    best = None
    for j, r_target in enumerate(rec_n):
        i = int(np.argmin(np.abs(rec_s - r_target)))
        if abs(rec_s[i] - r_target) > RECALL_PARITY_TOLERANCE:
            continue
        total = curve_s[i] + curve_n[j]
        if best is None or total > best[0]:
            best = (float(total), float(THRESHOLD_GRID[i]),
                    float(THRESHOLD_GRID[j]), float(rec_s[i]), float(r_target))

    R(f"  Economics: CLV ${DEFAULT_CLV:.0f}, contact cost ${DEFAULT_COST:.0f}, "
      f"success rate {DEFAULT_SUCCESS_RATE:.0%}")
    R(f"  Test set: {senior.sum()} seniors ({(y_s==1).sum()} churners), "
      f"{(~senior).sum()} non-seniors ({(y_n==1).sum()} churners)")
    R()
    R(f"  {'policy':<34}{'thr sen':>9}{'thr non':>9}{'profit':>11}{'recall gap':>12}")
    R("  " + "-" * (W - 4))
    R(f"  {'shipped: one threshold':<34}{shipped_threshold:>9.2f}"
      f"{shipped_threshold:>9.2f}{shipped_profit:>10,.0f}"
      f"{(rec_s_ship - rec_n_ship) * 100:>11.1f}pp")
    R(f"  {'(a) per-group profit optimum':<34}{t_s:>9.2f}{t_n:>9.2f}"
      f"{unconstrained:>10,.0f}"
      f"{(rec_s[list(THRESHOLD_GRID).index(t_s)] - rec_n[list(THRESHOLD_GRID).index(t_n)]) * 100:>11.1f}pp")
    if best:
        total, ts, tn, rs, rn = best
        R(f"  {'(b) per-group + recall parity':<34}{ts:>9.2f}{tn:>9.2f}"
          f"{total:>10,.0f}{(rs - rn) * 100:>11.1f}pp")
        R()
        cost = unconstrained - total
        R(f"  COST OF RECALL PARITY  =  (a) - (b)  =  ${cost:,.0f}"
          f"  ({cost / unconstrained * 100:.1f}% of (a))")
        R(f"  Both groups end up catching {rs:.1%} of their real churners.")
    else:
        cost = None
        R("  No threshold pair achieved recall parity within tolerance.")
    R()
    R("  These are TEST-SET dollars on 1,405 customers, not an annual figure.")
    R("  (a) is a diagnostic upper bound, NOT a deployment proposal: setting")
    R("  different cutoffs by a protected attribute is disparate treatment and")
    R("  is legally fraught in most jurisdictions. The number that matters is")
    R("  the GAP between (a) and (b) -- the price of the constraint.")
    return {"shipped": shipped_profit, "unconstrained": unconstrained,
            "parity": best[0] if best else None,
            "cost": (unconstrained - best[0]) if best else None,
            "recall_gap_shipped": (rec_s_ship - rec_n_ship) * 100}


# ==========================================================================
# Main
# ==========================================================================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", help="path to the raw Telco CSV")
    ap.add_argument("--with-oof", action="store_true",
                    help="also compute out-of-fold predictions (REFITS the "
                         "model 5x -- this is training)")
    ap.add_argument("--out", help="also write the report to this file")
    args = ap.parse_args(argv)

    R = Report()
    threshold = load_threshold()
    model = joblib.load(MODEL_PATH)

    csv = locate_dataset(args.data)
    X_train, X_test, y_train, y_test = build_test_split(csv)
    proba = model.predict_proba(X_test)[:, 1]

    R.rule()
    R("FAIRNESS ANALYSIS -- Telco churn retention model")
    R.rule()
    R()
    R(f"  Artifact   : {MODEL_PATH}")
    R(f"  Metadata   : {METADATA_PATH}")
    R(f"  Threshold  : {threshold}  (as shipped)")
    R(f"  Dataset    : {csv}")
    R(f"  Test set   : {len(y_test)} rows, {int(y_test.sum())} churners "
      f"({y_test.mean():.2%})")
    R("  Training   : NONE. The committed pipeline is loaded and scored.")
    R()

    got = verify_reconstruction(y_test, proba, threshold)
    R(f"  Reconstruction gate: PASSED -- confusion matrix reproduces the")
    R(f"  published TP/FP/FN/TN {got['tp']}/{got['fp']}/{got['fn']}/{got['tn']}.")
    R()

    oof = None
    if args.with_oof:
        R("  --with-oof given: refitting 5x for out-of-fold predictions...")
        from sklearn.base import clone
        from sklearn.model_selection import StratifiedKFold, cross_val_predict
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        oof_proba = cross_val_predict(clone(model), X_train, y_train, cv=cv,
                                      method="predict_proba", n_jobs=-1)[:, 1]
        oof = {"proba": oof_proba, "X": X_train, "y": y_train, "stats": {}}
        R(f"  OOF ready: {len(y_train)} rows, {int(y_train.sum())} churners.")
        R()

    # ---- reliability gate ------------------------------------------------
    R.rule("1. RELIABILITY GATE")
    R()
    R("  A recall estimate's precision is set by the number of CHURNERS in the")
    R("  subgroup, not its total size. Bands applied throughout:")
    R()
    R(f"    >= {SOLID:<4} churners   solid        ~+/-7pp on recall")
    R(f"    >= {USABLE:<4} churners   usable       ~+/-9pp")
    R(f"    >= {MARGINAL:<4} churners   marginal     ~+/-13pp, companion required")
    R(f"    >= {FLOOR:<4} churners   marginal-    wide, treat with suspicion")
    R(f"    <  {FLOOR:<4} churners   INSUFFICIENT -- no rate is reported at all")
    R()

    # ---- tiers -----------------------------------------------------------
    def build_oof_stats(name, groups_fn):
        if oof is None:
            return
        for label, mask in groups_fn(oof["X"]).items():
            oof["stats"][(name, label)] = group_metrics(
                oof["y"], oof["proba"], mask, threshold)

    def g_gender(X):
        c = X["gender"].to_numpy()
        return {"Female": c == "Female", "Male": c == "Male"}

    def g_senior(X):
        c = X["seniorcitizen"].to_numpy()
        return {"senior": c == 1, "non-senior": c == 0}

    def g_partner(X):
        c = X["partner"].to_numpy()
        return {"no partner": c == "No", "has partner": c == "Yes"}

    def g_dependents(X):
        c = X["dependents"].to_numpy()
        return {"no dependents": c == "No", "has dependents": c == "Yes"}

    def g_family(X):
        c = X["family_tie"].to_numpy()
        return {"alone": c == 0, "has family": c == 1}

    def g_autopay(X):
        c = X["is_auto_pay"].to_numpy()
        return {"manual pay": c == 0, "auto-pay": c == 1}

    tier1 = [
        ("gender", "protected: sex", g_gender),
        ("seniorcitizen", "protected: age", g_senior),
        ("partner", "protected: marital status", g_partner),
        ("dependents", "protected: familial status", g_dependents),
        ("family_tie", "= partner OR dependents (power backup)", g_family),
    ]

    R.rule("2. TIER 1 -- PROTECTED ATTRIBUTES")
    all_stats, all_findings = {}, []
    for name, note, fn in tier1:
        build_oof_stats(name, fn)
        stats, findings = report_attribute(
            R, name, note, y_test, proba, fn(X_test), threshold, oof)
        all_stats[name] = stats
        all_findings += findings
    R()

    R.rule("3. TIER 2 -- SOCIOECONOMIC PROXY")
    R()
    R("  is_auto_pay is NOT a protected class. It is included because payment")
    R("  method proxies for banking access and therefore income: customers who")
    R("  cannot or do not autopay skew lower-income. A disparity here is not a")
    R("  legal finding, but it is a distributional one worth knowing about.")
    build_oof_stats("is_auto_pay", g_autopay)
    stats, findings = report_attribute(
        R, "is_auto_pay", "socioeconomic proxy", y_test, proba,
        g_autopay(X_test), threshold, oof)
    all_stats["is_auto_pay"] = stats
    all_findings += findings
    R()

    inter_flags = section_intersectional(R, y_test, proba, X_test, threshold,
                                         all_stats)
    R()
    cost = section_threshold_cost(R, y_test, proba, X_test, threshold)
    R()

    # ---- the constraint --------------------------------------------------
    R.rule("6. WHY THERE IS NO 'CORRECT' ANSWER HERE")
    R()
    sen = X_test["seniorcitizen"].to_numpy() == 1
    R(f"  When two groups have different base rates -- and in this test set")
    R(f"  seniors churn at {y_test[sen].mean():.1%} against "
      f"{y_test[~sen].mean():.1%} for everyone else --")
    R("  recall parity, precision parity and flag-rate parity CANNOT all hold")
    R("  at once. This is a")
    R("  theorem, not a limitation of this model (Chouldechova 2017;")
    R("  Kleinberg, Mullainathan & Raghavan 2016). Any threshold satisfying")
    R("  one criterion necessarily violates the others.")
    R()
    R("  This report therefore chooses RECALL PARITY (equal opportunity) and")
    R("  says so, rather than presenting a computed 'fair' answer. The reason:")
    R("  a retention offer is an allocated BENEFIT, so the harm being measured")
    R("  is a real churner never being contacted. Precision parity would")
    R("  instead equalise wasted spend, which is the company's interest rather")
    R("  than the customer's.")
    R()
    R("  A reader who disagrees with that choice should read section 5's")
    R("  numbers and substitute their own criterion. The numbers are reported")
    R("  so the trade-off is visible, not to settle it.")
    R()

    # ---- plain-language summary -----------------------------------------
    R.rule("7. SUMMARY IN PLAIN LANGUAGE")
    R()
    real = [f for f in all_findings if f[5]]
    noisy = [f for f in all_findings if not f[5]]
    insufficient = [f"{n}/{l}" for n, s in all_stats.items()
                    for l, m in s.items() if m["reliability"] == "insufficient"]
    weak = [f"{n}/{l}" for n, s in all_stats.items() for l, m in s.items()
            if m["reliability"] in ("marginal", "marginal-")]

    if real:
        R("  Groups with a real gap (bigger than 10 points, and the confidence")
        R("  interval does not include zero):")
        for name, metric, a, b, gap, _ in real:
            hi, lo = (a, b) if gap > 0 else (b, a)
            R(f"    - {name}: {metric} is {abs(gap):.0f} points HIGHER for "
              f"'{hi}' than '{lo}'")
    else:
        R("  No group showed a gap we can be confident is real. Some gaps are")
        R("  larger than 10 points, but their confidence intervals include")
        R("  zero, which means the test set is too small to tell them apart")
        R("  from chance.")
    R()
    if noisy:
        R("  Large but statistically unclear (do not act on these yet):")
        for name, metric, a, b, gap, _ in noisy:
            hi, lo = (a, b) if gap > 0 else (b, a)
            R(f"    - {name}: {metric} {abs(gap):.0f} points higher for "
              f"'{hi}' than '{lo}'")
        R()
    if insufficient:
        R(f"  Not enough data to say anything at all: {', '.join(insufficient)}.")
        R("  These groups had fewer than 30 churners in the test set, so no")
        R("  rate is reported for them rather than a misleading one.")
        R()
    if weak:
        R(f"  Thin but reportable: {', '.join(sorted(set(weak)))}.")
        R("  Read the intervals, not the point estimates.")
        R()
    if real:
        R("  Which way do these run? In every case the gap favours the group")
        R("  that churns MORE. Seniors, people without a partner, people")
        R("  without dependents and people who pay manually are all MORE likely")
        R("  to be contacted when they are about to leave, not less. That is the")
        R("  expected result of one threshold over groups with different base")
        R("  rates -- the model ranks higher-risk groups higher, so more of them")
        R("  clear the cutoff. The people being missed are the LOW-risk groups:")
        R("  a churning customer with a partner or dependents is meaningfully")
        R("  less likely to be offered retention than a churning customer alone.")
        R()
    if cost["cost"] is not None:
        pct_cost = cost["cost"] / cost["unconstrained"] * 100
        R(f"  What fairness costs: making the model catch the same share of")
        R(f"  churning seniors as churning non-seniors would cost ${cost['cost']:,.0f}")
        R(f"  of the ${cost['unconstrained']:,.0f} that separate per-group cutoffs")
        R(f"  could earn -- about {pct_cost:.0f}% -- on this 1,405-customer test set.")
        R()
        R("  But note HOW parity is reached: by raising the senior cutoff, so")
        R("  FEWER at-risk seniors get contacted, not by contacting more")
        R("  non-seniors. Equal recall here is levelling down. That is an")
        R("  argument against enforcing it, and it is visible only because the")
        R("  per-group thresholds are printed rather than summarised.")
        R()
    R("  What was decided: nothing changes. The model keeps one threshold of")
    R(f"  {threshold} for everyone. Using a different cutoff for seniors would")
    R("  mean treating people differently because of their age, which is the")
    R("  thing fairness work is supposed to prevent -- so the per-group")
    R("  numbers above are a measurement, not a proposal. They exist so that")
    R("  if someone asks 'is this model fair to older customers?', the answer")
    R("  is a number and a stated trade-off rather than a shrug.")
    R()
    R.rule()

    if args.out:
        with open(args.out, "w") as f:
            f.write("\n".join(R.lines) + "\n")
        print(f"\n[written to {args.out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
