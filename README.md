# Telco Customer Churn — Profit-Optimized Retention Targeting

[![tests](https://github.com/faridqul/telco-churn-retention/actions/workflows/tests.yml/badge.svg)](https://github.com/faridqul/telco-churn-retention/actions/workflows/tests.yml)

Predicts which customers are likely to churn, and — more importantly — decides
*which of them are worth targeting with a retention campaign*, given the real
economics of that campaign. The operating threshold isn't chosen by accuracy
or F1; it's chosen by maximizing expected campaign profit on held-out data.

## Dataset

[Telco Customer Churn](https://www.kaggle.com/datasets/blastchar/telco-customer-churn)
— 7,043 customers, ~26% churn rate. Imbalance is handled via `scale_pos_weight`
in XGBoost (tuned as part of the hyperparameter search, not hand-picked — see
below) and stratified train/validation/test splits throughout.

The notebook downloads the dataset automatically via `kagglehub` on first
run — no manual download needed, but it does require a (free) Kaggle
account and API credentials configured locally
([instructions here](https://github.com/Kaggle/kagglehub)).

## Approach

1. **Cleaning** — placeholder values normalized to `NaN`, `totalcharges`
   coerced to numeric, duplicates dropped. 22 exact-duplicate rows (0.3%)
   removed — verified as duplicates across every remaining column (customer
   ID excluded, since it's dropped earlier), not coincidental categorical
   collisions.
2. **Feature engineering** (`feature_engineering_telco.py`, shared by the
   notebook, the batch script, and the API — one source of truth):
   - `total_services` — count of active add-on services
   - `is_auto_pay` — automatic vs. manual payment method
   - `family_tie` — has a partner and/or dependents
   - `contractvstenure` — contract length (encoded 1/2/3) × tenure. Unlike
     the two ratio features below, this one isn't closing a capability gap —
     a tree can already recover the same interaction for free via two
     sequential splits (`contract` is 3-valued, so branching on it first
     costs nothing, then `tenure` splits independently within each branch).
     The actual reason to keep it is XGBoost's per-tree column subsampling
     (`colsample_bytree`): if a given tree happens to drop `contract` or
     `tenure` for that round, this column preserves the interaction anyway.
     The 1/2/3 encoding also assumes the churn-risk gap between
     month-to-month → one-year is comparable to one-year → two-year, which
     isn't verified — a real but untested assumption baked into the feature.
   - `average_monthly_charges` — actual historical spend rate (`totalcharges / tenure`)
   - `charge_change_ratio` — current rate vs. historical average, capturing a
     *proportional* bill change rather than a flat dollar amount

   The last two (not `contractvstenure`, see above) exist because tree
   models can't synthesize a ratio between two columns on their own — they
   can only threshold individual features.
3. **Modeling** — XGBoost tuned via `RandomizedSearchCV` (200 iterations,
   5-fold stratified CV), compared against Logistic Regression and Random
   Forest under the same search budget and data split. `scale_pos_weight` is
   included as one of the 7 tuned hyperparameters (searched over
   `[1.0, 1 + 2×spw]`, where `spw` is the neg/pos class ratio on the training
   fold) rather than fixed to a single hand-computed value — a fixed value
   from one split doesn't necessarily generalize, so it's treated as
   something to search like any other hyperparameter instead of assumed.
   `n_iter=200` isn't an arbitrary round number: a convergence check
   (best-score-so-far vs. iteration) showed the search plateaus around
   iteration ~125–130 and stays flat to 200, confirming the budget is
   sufficient rather than cutting the search off early.
4. **Threshold selection** — a coarse-then-fine grid search over decision
   thresholds using out-of-fold (5-fold CV) predictions on `X_train`,
   optimizing:

   `Profit = TP × success_rate × CLV − (TP + FP) × cost`

   i.e., revenue only from customers actually retained, cost charged to
   everyone targeted — not just the successes. The test set is touched
   exactly once, after the threshold and hyperparameters are both locked in.
5. **Feature schema validation** — `config.validate_feature_schema()` runs
   at startup in both `api.py` and `telco_model.py`. It runs a dummy row
   through `engineer_features()` and diffs the resulting columns against
   `model_metadata.json["feature_columns"]`, refusing to start if they
   don't match. This exists to catch the specific failure mode where
   `feature_engineering_telco.py` changes but the notebook isn't rerun, so
   the saved model/metadata silently fall out of sync with the code — it
   turns that into an immediate, readable startup error instead of a
   confusing failure (or worse, a silently wrong prediction) at request
   time. Covered by `test_config.py`.
6. **Dataset drift detection** — the notebook downloads "latest" from
   `kagglehub` with no version pin, so nothing stops the underlying Kaggle
   dataset from changing under a future rerun without anyone noticing. A
   SHA-256 hash of the raw CSV is computed right after loading and compared
   against `dataset_baseline.json` (committed to git, unlike
   `model_metadata.json`, specifically so there's something stable across
   runs months apart to compare against). First run writes the baseline;
   every run after that prints a warning if the hash no longer matches. The
   current hash is also written into `model_metadata.json` for traceability
   between a saved model and the exact data it was trained on.

## Results

| Metric | Value |
|---|---|
| CV ROC-AUC (train) | 0.8491 ± 0.0175 |
| Test ROC-AUC | 0.8441 |
| Operating threshold | 0.40 (profit-optimized via 5-fold OOF on `X_train`, not the default 0.5) |
| Test precision / recall / F1 (churn class) | 0.59 / 0.69 / 0.63 |
| Test accuracy | 79% |
| Test confusion matrix | TP 256, FP 179, FN 116, TN 854 |
| Test campaign profit @ threshold | $6,660 |

*Note: the operating threshold dropped from 0.66 to 0.44 once `scale_pos_weight`
moved into the hyperparameter search. The search found `scale_pos_weight ≈ 1.19`
— much lower than the ~2.77 the original hand-computed value would have given
— so the model's raw probabilities skew less aggressively toward the positive
class, and the profit-optimal cutoff shifts down to compensate. This is a real,
explainable consequence of the change, not noise: model, threshold, and profit
all moved together and are consistent with each other, not left over from the
old configuration.*

*A second, unrelated change moved the threshold again, from 0.44 to 0.40:
threshold selection now runs on 5-fold out-of-fold (OOF) predictions across all
of `X_train`, instead of a plain validation split scored by a differently-fit
model (see "Threshold selection" above). Note that `Test ROC-AUC` (0.8441) is
*unchanged* by this — ROC-AUC is threshold-independent and the final deployed
model is the same either way, so it only measures whether the model's
probability rankings are good, which this fix didn't touch. What changed is
which cutoff gets applied to those same probabilities: 0.40 trades a bit of
precision for more recall (more customers correctly flagged as churners, a few
more false alarms too), which nets a higher profit under the stated cost
assumptions.*

**Model comparison** — XGBoost, Logistic Regression, and Random Forest
converge to statistically indistinguishable ROC-AUC (0.845812 / 0.843897 /
0.844126, each well within one standard deviation of the others). Rather than
read this as "the model choice didn't matter," I read it as evidence the
dataset itself has an information ceiling around ROC-AUC ≈ 0.845 — churn here
is partly driven by factors outside the data (competitor offers, individual
service interactions), and no algorithm can learn around that. A simpler,
more interpretable Logistic Regression would be a defensible choice over
XGBoost for this specific dataset. Note the comparison still isn't perfectly
apples-to-apples: XGBoost searches its own `scale_pos_weight`, while Logistic
Regression and Random Forest use `class_weight='balanced'` — each model's
native imbalance mechanism, not a controlled variable.

Since ROC-AUC alone doesn't say much about the business outcome this project
actually optimizes for, each model was also given its own profit-maximizing
threshold (same method as XGBoost's: a scan over 5-fold OOF predictions on
`X_train`, using the same `clv`/`cost`/`success_rate` constants):

| Model | Mean ROC-AUC | Std Dev | Best Threshold | Accuracy @ Threshold | Profit @ Threshold ($) |
|---|---|---|---|---|---|
| XGBoost (Tuned) | 0.845812 | 0.019575 | 0.40 | 0.7876 | 26,640 |
| Random Forest | 0.844126 | 0.016803 | 0.58 | 0.7810 | 27,000 |
| Logistic Regression | 0.843897 | 0.018890 | 0.58 | 0.7762 | 26,240 |

Random Forest edges out XGBoost on profit here (\$27,000 vs. \$26,640), but at
a ROC-AUC gap of just 0.0017 — an order of magnitude smaller than the ~0.02
fold-to-fold CV std above — this \$360 (1.3%) difference isn't distinguishable
from noise without a proper significance test (see Known limitations). It
isn't a reason to switch models.

The more interesting pattern is the **threshold split**: XGBoost's optimum
(0.40) sits well below Random Forest's and Logistic Regression's (0.58, for
both). This is a real, structural effect, not a coincidence: boosted trees
build up probability estimates additively across rounds, which tends to push
them toward the extremes (more separated between classes), while averaging
many trees (Random Forest) or fitting a single smooth sigmoid (Logistic
Regression) both produce softer, more centrally-clustered probabilities.
Different probability shapes need different cutoffs to hit the same
precision/recall trade-off — which is exactly why this project never
hardcodes a threshold and always derives one per model instead.

### How stable is the profit-optimized threshold?

The `Profit` formula above depends on three business constants that aren't
empirically derived — they're informed guesses: `CLV=$200` (value of a
retained customer), `cost=$20` (cost of targeting one customer), and
`success_rate=0.3` (fraction of targeted churners actually retained). To
check how much the recommended threshold depends on those specific guesses,
I swept each one independently by ±25% and ±50% and re-ran the threshold
search on the same out-of-fold predictions (`X_train`). Note these profit
figures are summed over all ~5,616 `X_train` customers (the OOF population),
not the 1,405-customer `X_test` set the Results table above uses — compare
the **threshold** column across the two, not the raw dollar amounts:

| Varied Param | % Change | Value | Best Threshold | Profit at Best Threshold ($) |
|---|---|---|---|---|
| clv | -50% | 100.00 | 0.75 | 1,720 |
| clv | -25% | 150.00 | 0.47 | 12,255 |
| clv | +0% | 200.00 | 0.40 | 26,640 |
| clv | +25% | 250.00 | 0.29 | 44,280 |
| clv | +50% | 300.00 | 0.27 | 62,840 |
| cost | -50% | 10.00 | 0.21 | 50,420 |
| cost | -25% | 15.00 | 0.27 | 37,785 |
| cost | +0% | 20.00 | 0.40 | 26,640 |
| cost | +25% | 25.00 | 0.46 | 18,880 |
| cost | +50% | 30.00 | 0.53 | 12,180 |
| success_rate | -50% | 0.15 | 0.75 | 1,720 |
| success_rate | -25% | 0.22 | 0.47 | 12,255 |
| success_rate | +0% | 0.30 | 0.40 | 26,640 |
| success_rate | +25% | 0.38 | 0.29 | 44,280 |
| success_rate | +50% | 0.45 | 0.27 | 62,840 |

**Takeaway: the threshold is still not stable.** Across a plausible ±50%
range on these assumptions, the optimal threshold swings from 0.21 to 0.75,
and profit at that optimum swings roughly 36x ($1,720 to $62,840).
`success_rate` and `clv` still move the result identically, since they only
ever appear multiplied together in the formula (`success_rate × CLV`) —
there are really two independent levers here, not three. The reported
$6,660 test-set profit and the 0.40 threshold should be read as directionally
correct given the current assumptions, not as precise figures — replacing
`clv`, `cost`, and `success_rate` with real historical campaign data would be
the single highest-value next step before trusting this model's threshold in
production.

## Interpretability

SHAP (`TreeExplainer`) is used against the final refit model to surface which
features drive individual predictions, not just aggregate feature importance.

## Repo structure

```
telco_customer_churn.ipynb    # full analysis: cleaning → modeling → SHAP → threshold sensitivity
feature_engineering_telco.py  # shared feature logic (single source of truth)
telco_model.py                # batch scoring script (CSV in, CSV out)
api.py                        # FastAPI service (POST /predict)
config.py                     # shared config: threshold loading, feature-schema
                               # validation, artifact paths (env-var overridable)
tests/
  test_feature_engineering.py # unit tests for feature_engineering_telco.py
  test_api.py                 # smoke tests for the FastAPI service
  test_config.py              # unit tests for validate_feature_schema and load_threshold
  test_telco_model.py         # smoke tests for the batch scoring script
  test_integration.py         # fits the real pipeline (no mocks) on synthetic data
  test_artifact.py            # loads the committed .pkl and pins its prediction
  test_input_validation.py    # batch-input domain checks + API non-finite handling
pyproject.toml                # dependencies (managed with uv)
.github/workflows/tests.yml   # CI: runs the test suite on every push and PR

verify_version_check.sh       # integration check: builds two throwaway venvs and
                               # verifies the version-drift warning actually fires

# regenerated by running the notebook end to end, but committed anyway so
# the API and batch script run straight after a clone:
xgboost_churn_pipeline.pkl    # trained pipeline (preprocessing + model)
model_metadata.json           # operating threshold + CV scores + feature schema + dataset hash
simulated_new_customers.csv   # sample input for telco_model.py

# the one fixed point a dataset-hash comparison can check against across
# runs, unlike model_metadata.json above, which is rewritten on retrain:
dataset_baseline.json         # SHA-256 hash of the raw Kaggle CSV, recorded once

# not committed — regenerated on every scoring run:
retention_campaign_targets.csv
```

## Running it

**Batch scoring:**
```
python telco_model.py
```
Reads `simulated_new_customers.csv`, writes `retention_campaign_targets.csv`.
Validates the current feature schema against `model_metadata.json` before
loading the model; fails fast with a clear error if they've drifted apart
(e.g. `feature_engineering_telco.py` changed but the notebook wasn't rerun).

**Configuration:**
`MODEL_PATH` and `METADATA_PATH` (in `config.py`) default to
`xgboost_churn_pipeline.pkl` and `model_metadata.json` in the working
directory, but can be overridden per-environment without a code change:
```
MODEL_PATH=/path/to/model.pkl METADATA_PATH=/path/to/metadata.json uvicorn api:app
```
Both the API and the batch script load the model via `joblib.load`, which
deserializes a pickle — only ever point these at an artifact you trust,
since pickle deserialization executes arbitrary code on load.

**API:**
```
uv sync
uvicorn api:app --reload
```
Interactive docs at `http://127.0.0.1:8000/docs`. `POST /predict` with a raw
customer record; feature engineering runs server-side automatically. Same
startup schema check as the batch script above.

```
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "gender": "Female", "seniorcitizen": 0, "partner": "Yes", "dependents": "No",
    "tenure": 3, "phoneservice": "Yes", "multiplelines": "No",
    "internetservice": "Fiber optic", "onlinesecurity": "No", "onlinebackup": "No",
    "deviceprotection": "No", "techsupport": "No", "streamingtv": "Yes",
    "streamingmovies": "Yes", "contract": "Month-to-month", "paperlessbilling": "Yes",
    "paymentmethod": "Electronic check", "monthlycharges": 85.5, "totalcharges": 256.5
  }'
```

```json
{
  "churn_probability": 0.81,
  "target_for_retention": true,
  "threshold_used": 0.40
}
```
*(illustrative — run it yourself to get a real prediction)*

**Tests:**
```
pytest -v
```
Covers feature engineering edge cases, API request/response contracts, the
feature-schema validation guard, `load_threshold`'s fallback behavior
(missing file, missing key, bad value), and the batch scoring script's I/O
contract. Most of these mock the model out entirely, so they run fast with
no trained `.pkl` or `model_metadata.json` on disk. `test_integration.py` is
the exception: it fits the real preprocessing pipeline + `XGBClassifier`
(no mocks) on a small synthetic sample, so the actual sklearn/XGBoost
plumbing gets exercised end to end, not just each piece's wiring in
isolation. Either way, a fresh clone can run `pytest -v` immediately, before
ever running the notebook.

## Known limitations / what I'd add for production

- **Threshold sensitivity is confirmed against the current model** (see
  sweep above), not just checked once and forgotten. `clv`, `cost`, and
  `success_rate` are still hardcoded placeholders, not measured values, and
  remain the single biggest source of uncertainty in the whole pipeline —
  bigger than model choice.
- **Model comparison has no formal significance test.** The ROC-AUC and
  profit gaps between XGBoost, Random Forest, and Logistic Regression (see
  above) are all smaller than the ~0.02 fold-to-fold CV std — "probably not
  distinguishable from noise" by eye, but never actually tested. A paired
  Wilcoxon signed-rank test on the per-fold CV scores (`cv_results_` already
  has these) would turn that into a real yes/no instead of an eyeball call.
- **ROC-AUC is the only ranking metric reported.** With ~26% churn, PR-AUC is
  arguably more informative — it's more sensitive to minority-class
  (churner) performance than ROC-AUC under imbalance, and costs almost
  nothing to add (`average_precision_score` alongside the existing
  `roc_auc_score` calls).
- No auth on the API — fine for a local demo, not for anything exposed
  publicly.
- No monitoring or drift detection — churn drivers shift over time in
  practice; a deployed version of this would need to track prediction
  distribution and periodically retrain. The feature-schema check catches
  *code/model* drift, not *data* drift (e.g. the input population changing
  over time).
- Would containerize with Docker for consistent deployment across
  environments.
- Hyperparameter search is currently `RandomizedSearchCV`; a Bayesian search
  (Optuna) would likely reach the same ~0.845 plateau with fewer iterations,
  though the convergence check suggests there isn't much headroom left to
  find either way.
- `simulated_new_customers.csv` is sampled from the held-out test set for
  demo convenience, not genuinely unseen data.

## Stack

Python, pandas, scikit-learn, XGBoost, SHAP, FastAPI, uv.

## License

MIT — see [LICENSE](LICENSE).
