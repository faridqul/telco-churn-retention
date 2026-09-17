"""Per-customer attribution for the shipped churn model.

Reads the already-fitted pipeline (`xgboost_churn_pipeline.pkl`) and the
operating threshold recorded in `model_metadata.json`. **Nothing is trained
here and nothing is written.** The prediction being explained is produced by
calling `predict_proba` on the committed artifact -- the same call `api.py`
and `telco_model.py` make -- so an explanation can never describe a different
number from the one the service reports.

Run:  uv run python explain.py --dummy
      uv run python explain.py --csv simulated_new_customers.csv --row 0
      uv run python explain.py --csv simulated_new_customers.csv --all --top 3

WHY NOT THE `shap` PACKAGE
The notebook's cells 39-40 use `shap.TreeExplainer`, which is right for
producing beeswarm plots during training. Here the attribution comes from
XGBoost's own `Booster.predict(..., pred_contribs=True)`, which computes the
identical exact tree-SHAP values. The reason is dependency placement: `shap`
sits in the `notebook` group and is deliberately absent from both `uv sync`'s
default set and the production image. This module is meant to be importable
by the serving path later without changing a single line of `pyproject.toml`
or the Dockerfile, so it uses the library that is already a runtime
dependency.

WHY THE ENGINEERED FEATURES GET THEIR OWN ROWS
`engineer_features()` derives six columns from the raw ones, and the model
splits credit across the whole set. `contract` and `contractvstenure`
therefore both appear in a typical explanation, which reads as
near-duplication to a human -- the same fact stated twice. The tempting fix is
to fold each derived feature's contribution back into the raw fields it was
computed from. That is not done here, on purpose: any such split (half to
`contract`, half to `tenure`, or any other ratio) is a reporting choice
invented after the fact, and the model never attributed credit that way. What
this module reports is exactly what the model computed. The derived rows are
labelled in plain English instead, so a reader can see why the same fact
appears twice rather than being quietly shown a number nobody calculated.

WHAT THE GATE IS FOR
Tree SHAP is additive: the contributions plus a bias term sum to the model's
margin, and the sigmoid of that margin is the predicted probability. That
identity is checked on every single explanation by `verify_attribution()`,
which refuses to return a driver list that does not reconstruct the model's
own prediction. The failure this exists to stop is not a crash -- it is a
plausible, well-formatted list of reasons for a customer whose prediction
actually came from somewhere else.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost

from config import (
    DUMMY_CUSTOMER,
    METADATA_PATH,
    MODEL_PATH,
    load_threshold,
    validate_input_frame,
)
from feature_engineering_telco import engineer_features

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# How far sigmoid(sum of contributions) may sit from predict_proba before the
# attribution is rejected. This is float32 round-tripping room, not modelling
# slack: the pipeline predicts in float32 while the contributions are summed
# in float64, and the observed gap on the shipped artifact is ~6e-08. A
# genuine breakage -- a changed objective, a reordered preprocessor, a model
# that is not the one being scored -- moves this by orders of magnitude, not
# by rounding. Same tolerance and same reasoning as tests/test_artifact.py.
RECONSTRUCTION_TOLERANCE = 1e-6

# The six columns engineer_features() derives. Flagged in the output so a
# reader can tell a raw customer fact from a computed one.
ENGINEERED_FEATURES = frozenset({
    "total_services",
    "is_auto_pay",
    "family_tie",
    "contractvstenure",
    "average_monthly_charges",
    "charge_change_ratio",
})

# Plain-English name for every one of the 25 feature columns. Sourced from
# docs/DATA_DICTIONARY.txt, but deliberately restated here rather than parsed from
# it at runtime: that file is a human-readable report, not a data structure,
# and reformatting it should never be able to break an explanation.
#
# tests/test_explain.py asserts this covers model_metadata.json's
# "feature_columns" exactly, so a new engineered feature cannot ship without
# a label -- it would otherwise surface to a reader as a raw column name.
FIELD_LABELS: dict[str, str] = {
    # Raw customer fields, in the order api.Customer declares them.
    "gender": "gender",
    "seniorcitizen": "senior citizen",
    "partner": "has a partner",
    "dependents": "has dependents",
    "tenure": "months as a customer",
    "phoneservice": "phone service",
    "multiplelines": "multiple phone lines",
    "internetservice": "internet service type",
    "onlinesecurity": "online security add-on",
    "onlinebackup": "online backup add-on",
    "deviceprotection": "device protection add-on",
    "techsupport": "tech support add-on",
    "streamingtv": "streaming TV",
    "streamingmovies": "streaming movies",
    "contract": "contract type",
    "paperlessbilling": "paperless billing",
    "paymentmethod": "payment method",
    "monthlycharges": "current monthly bill",
    "totalcharges": "total charged to date",
    # Derived by engineer_features().
    "total_services": "number of add-on services taken",
    "is_auto_pay": "pays automatically",
    "family_tie": "has a partner or dependents",
    # A product, not a ratio: contract rank (1 month-to-month, 2 one year,
    # 3 two year) times months as a customer. Labelled "contract length
    # weighted by tenure" until 2026-09-17, which the language model read as
    # "contract length compared to tenure" in 4 of 8 live outputs.
    "contractvstenure": "overall commitment (contract term × months as a customer)",
    "average_monthly_charges": "average monthly bill across their whole tenure",
    "charge_change_ratio": "current bill vs. their historical average",
}

# Report width, matching fairness_analysis.py so the two modules' output
# looks like it came from the same project.
W = 78

REPO_ROOT = Path(__file__).resolve().parent


class UnexplainableModelError(TypeError):
    """The loaded object is not a pipeline this module can attribute.

    Raised rather than returning an empty or a best-effort explanation.
    A caller that cannot get real drivers must find out immediately: the
    whole point of this module is that its numbers are the model's, and a
    graceful degradation here would produce a driver list with no model
    behind it.
    """


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _anchor(path_str: str) -> Path:
    """Resolve a config path against the repo root when it's relative.

    config.MODEL_PATH defaults to a bare filename, so importing this module
    from another directory would otherwise fail to find the artifact. An
    absolute override (the MODEL_PATH / METADATA_PATH env vars) is honoured
    as-is. Same trick, and same reason, as tests/test_artifact.py.
    """
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


# joblib.load of the real pipeline takes appreciably longer than scoring a
# customer, and the CLI's --all path explains 50 of them. Keyed by resolved
# path so pointing MODEL_PATH somewhere else gets a different object rather
# than a stale one.
_MODEL_CACHE: dict[str, object] = {}


def load_model(path: str | None = None):
    """The fitted pipeline, cached per resolved path."""
    resolved = str(_anchor(path or MODEL_PATH))
    if resolved not in _MODEL_CACHE:
        _MODEL_CACHE[resolved] = joblib.load(resolved)
    return _MODEL_CACHE[resolved]


def _split_pipeline(model):
    """(preprocessor, classifier), or raise UnexplainableModelError.

    Checked explicitly, with a message naming what was actually found,
    because the alternative is an AttributeError from inside a library call
    that says nothing about which object was wrong.
    """
    steps = getattr(model, "named_steps", None)
    if steps is None:
        raise UnexplainableModelError(
            f"Cannot explain a {type(model).__name__}: it has no "
            f"named_steps, so it is not the sklearn Pipeline this project "
            f"ships. Attribution needs the fitted preprocessor to map "
            f"transformed columns back to customer fields."
        )
    missing = [name for name in ("preprocessor", "classifier") if name not in steps]
    if missing:
        raise UnexplainableModelError(
            f"Pipeline is missing the step(s) {missing}. Found: "
            f"{sorted(steps)}. This module expects the two-step pipeline "
            f"the notebook builds ('preprocessor' then 'classifier')."
        )
    classifier = steps["classifier"]
    if not hasattr(classifier, "get_booster"):
        raise UnexplainableModelError(
            f"Cannot explain a {type(classifier).__name__} classifier: it "
            f"exposes no get_booster(), so exact tree contributions are not "
            f"available. Only the gradient-boosted tree model this project "
            f"ships can be attributed this way."
        )
    return steps["preprocessor"], classifier


# --------------------------------------------------------------------------
# Mapping transformed columns back to customer fields
# --------------------------------------------------------------------------

def _encoder_of(transformer):
    """The fitted one-hot encoder inside a transformer, or None if it is a
    numeric branch. Located by looking for `categories_` rather than by step
    name, so renaming a step in the notebook doesn't silently produce a
    numeric-looking map for categorical columns."""
    if hasattr(transformer, "categories_"):
        return transformer
    for _, step in getattr(transformer, "steps", []):
        if hasattr(step, "categories_"):
            return step
    return None


def build_column_map(preprocessor) -> list[tuple[str, str | None]]:
    """(raw_field, category_or_None) for each transformed column, in order.

    Built from `transformers_` and the fitted encoder's `categories_`, never
    by parsing the strings `get_feature_names_out()` produces. Parsing looks
    simpler -- split 'cat__contract_Month-to-month' on the underscore -- and
    is correct here only by luck: it works because no raw field name happens
    to contain an underscore, and would start mangling fields silently the
    day one did. Reading the fitted objects cannot drift from what
    transform() actually emits.

    verify_column_map() then checks this against get_feature_names_out()
    anyway, which turns two independent derivations into a mutual check.
    """
    column_map: list[tuple[str, str | None]] = []
    for name, transformer, columns in preprocessor.transformers_:
        if transformer == "drop" or transformer is None:
            continue
        encoder = _encoder_of(transformer)
        if encoder is None:
            column_map.extend((column, None) for column in columns)
        else:
            for column, categories in zip(columns, encoder.categories_):
                column_map.extend((column, str(category)) for category in categories)
    return column_map


def verify_column_map(column_map, feature_names) -> None:
    """Raise unless the map reconstructs sklearn's own column names.

    Guards the case that would otherwise be invisible: a map whose length is
    right but whose entries are offset, which attributes every contribution
    to the wrong field while producing a perfectly well-formed report.
    """
    if len(column_map) != len(feature_names):
        raise RuntimeError(
            f"Column map has {len(column_map)} entries but the preprocessor "
            f"emits {len(feature_names)} columns. The map is derived from "
            f"transformers_, so this means the fitted preprocessor's "
            f"structure changed."
        )
    for position, ((field, category), actual) in enumerate(zip(column_map, feature_names)):
        expected = f"num__{field}" if category is None else f"cat__{field}_{category}"
        if expected != actual:
            raise RuntimeError(
                f"Column map disagrees with the preprocessor at position "
                f"{position}.\n"
                f"  map says:        {expected}\n"
                f"  preprocessor says: {actual}\n"
                f"Every contribution from here on would be attributed to the "
                f"wrong customer field."
            )


def collapse_contributions(contributions, column_map) -> dict[str, float]:
    """Sum each field's transformed columns into one number per field.

    A categorical field spreads across several one-hot columns and the model
    assigns a contribution to every one of them, including the columns that
    are zero for this customer -- a tree can split on 'contract is not Two
    year' and that split's credit lands on the Two-year column. Summing the
    group is therefore not an approximation; it is the field's total, and it
    preserves additivity exactly, which is what makes verify_attribution()
    able to check the whole thing at once.
    """
    aggregated: dict[str, float] = {}
    for (field, _), value in zip(column_map, contributions):
        aggregated[field] = aggregated.get(field, 0.0) + float(value)
    return aggregated


def reference_points(preprocessor) -> dict[str, dict[str, float]]:
    """{numeric_field: {"median": ..., "spread": ...}} from the TRAINING data.

    Read from the fitted pipeline itself, not from a dataset: the numeric
    branch's median imputer stores each column's training median, and its
    StandardScaler stores the training standard deviation. So "above typical"
    always means above the customers this exact model was fitted on, with no
    extra file to go stale on a retrain.

    This exists for narrate.py. Given a bare "total charged: 5762.95", a
    language model guessed "a lower total charged" (live stage 1, 2026-09-17);
    handed "well above typical" as well, it has nothing left to guess.

    Raises UnexplainableModelError when a numeric branch lacks either step.
    A narrative with no reference point is exactly the one that invents
    adjectives, so failing loudly beats quietly leaving the comparison out.
    """
    reference: dict[str, dict[str, float]] = {}
    for name, transformer, columns in preprocessor.transformers_:
        if transformer == "drop" or transformer is None:
            continue
        if _encoder_of(transformer) is not None:
            continue
        steps = [step for _, step in getattr(transformer, "steps", [])]
        imputers = [
            s for s in steps
            if hasattr(s, "statistics_") and getattr(s, "strategy", None) == "median"
        ]
        scalers = [s for s in steps if hasattr(s, "scale_")]
        if not imputers or not scalers:
            raise UnexplainableModelError(
                f"The numeric branch {name!r} has no fitted median imputer "
                f"and scaler, so there are no training medians to compare a "
                f"customer against."
            )
        for column, median, spread in zip(
            columns, imputers[0].statistics_, scalers[0].scale_
        ):
            reference[column] = {"median": float(median), "spread": float(spread)}
    return reference


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    """Logistic function, written in the branch-stable form so a large
    negative margin doesn't overflow np.exp on the way to an answer that is
    numerically zero anyway."""
    if x >= 0:
        return float(1.0 / (1.0 + np.exp(-x)))
    exponent = np.exp(x)
    return float(exponent / (1.0 + exponent))


def verify_attribution(probability: float, margin: float) -> float:
    """Return the reconstruction error, or raise if it exceeds tolerance.

    The contributions are in margin (log-odds) space and the model's link is
    the logistic function, so sigmoid(sum of contributions + bias) must equal
    what predict_proba returned. Three real breakages fail here rather than
    producing a confident wrong answer:

      1. A retrain under a different objective, where the sigmoid link no
         longer applies at all.
      2. A preprocessor whose column order no longer matches the booster's,
         so contributions land against the wrong features.
      3. Explaining one model while scoring another -- the case that looks
         most convincing and is hardest to spot by eye.

    Reports both numbers, because whoever reads this message will be doing
    so long after the change that caused it.
    """
    reconstructed = _sigmoid(margin)
    error = abs(reconstructed - probability)
    if error > RECONSTRUCTION_TOLERANCE:
        raise RuntimeError(
            f"Attribution does not reconstruct the model's own prediction.\n"
            f"  predict_proba                        : {probability!r}\n"
            f"  sigmoid(contributions + bias)        : {reconstructed!r}\n"
            f"  difference                           : {error:.3e}\n"
            f"  tolerance                            : {RECONSTRUCTION_TOLERANCE:.0e}\n"
            f"The driver list would describe a prediction other than the one "
            f"being reported, so no explanation is returned. Check whether "
            f"the artifact was retrained under a different objective, or "
            f"whether the preprocessor and the booster still agree on column "
            f"order."
        )
    return error


# --------------------------------------------------------------------------
# The public entry point
# --------------------------------------------------------------------------

def _py(value):
    """numpy scalar -> plain Python, so the result is JSON-serialisable."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def explain_customer(
    customer: dict,
    model=None,
    threshold: float | None = None,
    top_n: int | None = 5,
) -> dict:
    """Attribute one customer's churn probability to their fields.

    `churn_probability` is taken from predict_proba, never from the summed
    contributions. The reported number has to be the same one /predict would
    report for this customer; the reconstruction is a check on the drivers,
    not the source of the probability.

    Contributions are returned at full precision and are NOT rounded --
    rounding belongs to the renderer. This matches the repo-wide rule that
    the serving paths round nothing, and it keeps the additivity identity
    exact enough to assert on.

    `drivers` is the top_n by absolute contribution (top_n=None for all);
    `contributions` is always the complete per-field mapping, so a caller
    checking additivity has the untruncated set to work with.
    """
    model = load_model() if model is None else model
    if threshold is None:
        threshold = load_threshold(str(_anchor(METADATA_PATH)))

    preprocessor, classifier = _split_pipeline(model)

    frame = engineer_features(pd.DataFrame([customer]))
    transformed = preprocessor.transform(frame)
    feature_names = list(preprocessor.get_feature_names_out())

    column_map = build_column_map(preprocessor)
    verify_column_map(column_map, feature_names)

    matrix = xgboost.DMatrix(transformed, feature_names=feature_names)
    row = classifier.get_booster().predict(matrix, pred_contribs=True)[0]

    # Widened to float64 before summing. The booster returns float32, and a
    # float32 accumulation over 52 terms drifts from the float64 sum the
    # collapse below produces by ~3e-07 -- enough to blunt the additivity
    # assertion in the tests into something that could no longer tell a
    # dropped column from rounding. Summing both sides in float64 leaves the
    # two paths agreeing to ~1e-15, so the check stays sharp. It does not
    # make the *model* more precise; predict_proba is still float32, which is
    # why the gate below keeps its 1e-6 tolerance.
    wide = row.astype(np.float64)
    bias = float(wide[-1])
    margin = float(wide.sum())
    aggregated = collapse_contributions(wide[:-1], column_map)

    probability = float(model.predict_proba(frame)[:, 1][0])
    error = verify_attribution(probability, margin)

    values = frame.iloc[0]
    drivers = [
        {
            "field": field,
            "label": FIELD_LABELS.get(field, field),
            "value": _py(values[field]),
            "contribution": contribution,
            "direction": (
                "increases" if contribution > 0
                else "decreases" if contribution < 0
                else "neutral"
            ),
            "engineered": field in ENGINEERED_FEATURES,
        }
        for field, contribution in aggregated.items()
    ]
    # Sorted by magnitude: the strongest reason first regardless of whether it
    # pushed the customer toward churning or away from it. A driver that
    # strongly *lowers* risk is as much a part of the explanation as one that
    # raises it, so signed sorting would bury it.
    drivers.sort(key=lambda driver: abs(driver["contribution"]), reverse=True)

    return {
        # Full precision, and compared at full precision, matching api.py and
        # telco_model.py -- the same `>=` with no rounding on either side.
        "churn_probability": probability,
        "target_for_retention": probability >= threshold,
        "threshold_used": threshold,
        "drivers": drivers if top_n is None else drivers[:top_n],
        "contributions": aggregated,
        "bias": bias,
        "margin": margin,
        "reconstruction_error": error,
        # Training medians and spreads for the numeric fields. Not used by
        # anything in this module; carried so narrate.py can say "well above
        # typical" without being handed the pipeline separately.
        "reference": reference_points(preprocessor),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def render(explanation: dict, title: str) -> list[str]:
    """The explanation as report lines. Returned rather than printed so the
    formatting is testable without capturing stdout."""
    probability = explanation["churn_probability"]
    decision = (
        "TARGET FOR RETENTION" if explanation["target_for_retention"]
        else "leave alone"
    )
    lines = [
        "=" * W,
        title,
        "=" * W,
        f"  churn probability : {probability:.4f}"
        f"   (threshold {explanation['threshold_used']:.2f} -> {decision})",
        "",
        f"  {'DRIVER':<46}{'VALUE':<18}{'CONTRIB':>8}",
        f"  {'-' * 46}{'-' * 18}{'-' * 8}",
    ]
    for driver in explanation["drivers"]:
        label = driver["label"] + (" (E)" if driver["engineered"] else "")
        value = str(driver["value"])
        lines.append(
            f"  {label[:45]:<46}{value[:17]:<18}{driver['contribution']:>+8.4f}"
        )
    lines += [
        f"  {'-' * 46}{'-' * 18}{'-' * 8}",
        f"  {'baseline (all customers)':<46}{'':<18}{explanation['bias']:>+8.4f}",
        "",
        f"  reconstruction error: {explanation['reconstruction_error']:.2e}"
        f"   (tolerance {RECONSTRUCTION_TOLERANCE:.0e})",
        "",
    ]
    return lines


def _customers_from_csv(path: str, row: int | None, every: bool):
    """Rows from a CSV, validated before any of them is scored.

    validate_input_frame() is the batch path's existing check and is reused
    rather than reimplemented. It matters here for the same reason it matters
    in telco_model.py: the encoder uses handle_unknown='ignore', so a casing
    slip in a category is not an error -- it silently becomes an all-zeros
    block and the customer gets a different probability, and therefore a
    different and entirely plausible explanation.
    """
    frame = pd.read_csv(path)
    validate_input_frame(frame)
    if every:
        return [(i, frame.iloc[i].to_dict()) for i in range(len(frame))]
    index = 0 if row is None else row
    if not 0 <= index < len(frame):
        raise SystemExit(
            f"--row {index} is out of range: {path} has {len(frame)} rows "
            f"(0-{len(frame) - 1})."
        )
    return [(index, frame.iloc[index].to_dict())]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Explain the shipped churn model's prediction for one "
                    "customer, or for every row of a CSV."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--dummy", action="store_true",
        help="explain config.DUMMY_CUSTOMER, the row the test suite pins",
    )
    source.add_argument("--csv", help="a CSV with the 19 raw customer columns")
    parser.add_argument("--row", type=int, help="which CSV row (default 0)")
    parser.add_argument(
        "--all", action="store_true", help="explain every row of the CSV",
    )
    parser.add_argument(
        "--top", type=int, default=5, help="drivers to show per customer (default 5)",
    )
    args = parser.parse_args(argv)

    if args.dummy:
        customers = [("config.DUMMY_CUSTOMER", DUMMY_CUSTOMER)]
    else:
        customers = [
            (f"{args.csv} row {i}", customer)
            for i, customer in _customers_from_csv(args.csv, args.row, args.all)
        ]

    model = load_model()
    threshold = load_threshold(str(_anchor(METADATA_PATH)))

    for name, customer in customers:
        explanation = explain_customer(
            customer, model=model, threshold=threshold, top_n=args.top
        )
        print("\n".join(render(explanation, f"EXPLANATION -- {name}")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
