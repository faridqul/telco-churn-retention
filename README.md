# Telco Customer Churn — Profit-Optimized Retention Targeting

[![tests](https://github.com/faridqul/telco-churn-retention/actions/workflows/tests.yml/badge.svg)](https://github.com/faridqul/telco-churn-retention/actions/workflows/tests.yml)

Predicts which customers are likely to churn, and — more importantly — decides
*which of them are worth targeting with a retention campaign*, given the real
economics of that campaign. The operating threshold isn't chosen by accuracy
or F1; it's chosen by maximizing expected campaign profit on held-out data.

Each decision can also be explained in plain English: the model's own drivers
for that customer, put into two or three sentences by a language model whose
every reply is checked against what it was given before anyone sees it, and
whose faithfulness is measured on 300 customers and gated in CI.

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
| CV PR-AUC (train) | 0.6643 ± 0.0374 |
| Test ROC-AUC | 0.8441 |
| Test PR-AUC | 0.6610 (random baseline 0.2648 → **2.50x**) |
| Operating threshold | **0.40 ± 0.05** (profit-optimized via 5-fold OOF on `X_train`, not the default 0.5) |
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

**Why both ranking metrics.** ROC-AUC is reported by convention, but it
counts true negatives, and 74% of these customers don't churn — so it stays
comfortable even when the ranking of actual churners degrades. PR-AUC
(average precision) ignores true negatives entirely and tracks only the class
the campaign spends money on, which makes it the more sensitive read under
this imbalance. Its baseline is not 0.5: a model ranking at random scores the
churn rate itself, 0.2648. Against that floor, 0.6610 is **2.50x better than
random**, which is the honest statement of ranking quality here — 0.8441
sounds stronger than the model is, because a large part of it is earned on
the easy majority class.

Both are threshold-independent, so neither is affected by the 0.40 operating
threshold, and adding PR-AUC changed no model, no threshold and no shipped
artifact. Worth noting that PR-AUC is also the noisier of the two: its
fold-to-fold std is 0.0374 against ROC-AUC's 0.0175, more than double.
Sensitivity to the minority class cuts both ways — there are simply fewer
positives for each fold's estimate to rest on.

**Model comparison** — XGBoost, Logistic Regression, and Random Forest
converge to statistically indistinguishable ROC-AUC (0.845812 / 0.843894 /
0.844126, each well within one standard deviation of the others). Rather than
read this as "the model choice didn't matter," I read it as evidence the
dataset itself has an information ceiling around ROC-AUC ≈ 0.845 — churn here
is partly driven by factors outside the data (competitor offers, individual
service interactions), and no algorithm can learn around that.

Three matching scores are only circumstantial evidence for that, though —
models can reach the same accuracy while being wrong about entirely different
customers, and if they were, pooling them would beat any of them alone. So I
checked the errors rather than stopping at the scores (final appendix in the
notebook). They are wrong about the *same* people:

| | Value |
|---|---|
| Error correlation `corr(y − p)` between the three | 0.964 – 0.980 |
| Errors shared by all three models | **65%** |
| Pairwise error overlap (Jaccard) | 0.73 – 0.78 |
| Best single model, OOF profit | $27,000 (Random Forest) |
| Average of all three, OOF profit | $26,780 |

Averaging them nudges OOF ROC-AUC from 0.8492 to 0.8505 — inside the ~0.019
fold-to-fold std — and *loses* to Random Forest alone on profit. Three
structurally different algorithms (boosted trees, bagged trees, a linear
model) failing on the same 65% of customers is what an information ceiling
looks like when you measure it instead of inferring it, and it's the reason
there's no stacking or blending here: there is no independent signal to pool.

A simpler,
more interpretable Logistic Regression would be a defensible choice over
XGBoost for this specific dataset. Note the comparison still isn't perfectly
apples-to-apples: XGBoost searches its own `scale_pos_weight`, while Logistic
Regression and Random Forest use `class_weight='balanced'` — each model's
native imbalance mechanism, not a controlled variable.

Since ROC-AUC alone doesn't say much about the business outcome this project
actually optimizes for, each model was also given its own profit-maximizing
threshold (same method as XGBoost's: a scan over 5-fold OOF predictions on
`X_train`, using the same `clv`/`cost`/`success_rate` constants):

| Model | Mean ROC-AUC | Std Dev | PR-AUC (OOF) | Best Threshold | Accuracy @ Threshold | Profit @ Threshold ($) |
|---|---|---|---|---|---|---|
| XGBoost (Tuned) | 0.845812 | 0.019575 | 0.6603 | 0.40 | 0.7876 | 26,640 |
| Random Forest | 0.844126 | 0.016803 | 0.6532 | 0.58 | 0.7810 | 27,000 |
| Logistic Regression | 0.843894 | 0.018894 | 0.6548 | 0.62 | 0.7867 | 26,200 |

PR-AUC is computed on the same out-of-fold predictions as the threshold and
profit columns, so every column shares one basis. Note it **reorders the two
runners-up**: Random Forest is ahead of Logistic Regression on ROC-AUC and
behind it on PR-AUC. That is the metric doing exactly what it is there for —
ROC-AUC's true-negative credit flatters the model that is better at the
majority class, and 74% of these customers don't churn. It is not a reason to
change anything, though: the 0.0016 gap is a twentieth of PR-AUC's own 0.037
fold-to-fold std, so it is noise, and XGBoost leads on both metrics either
way. Selection still runs on ROC-AUC (`scoring='roc_auc'`); PR-AUC is
reported, not optimized, because changing the search metric would change
which model ships and that is a different decision from measuring one more
thing.

*For several runs this row refused to reproduce: its best threshold alternated
between 0.58 and 0.62, accuracy between 0.7758 and 0.7869, profit between
$26,200 and $26,240, while ROC-AUC moved in the fifth decimal. It was written
off as an inherently flat optimisation surface. That was the wrong diagnosis,
and the right one is worth recording.*

*`LogisticRegression` was the only one of the three estimators without a
`random_state`. Nothing about it looks stochastic — but with
`solver='liblinear'`, scikit-learn uses `random_state` to shuffle the data, so
an unseeded estimator scores the **same** candidate differently on every run.
Measured spread across five runs at a fixed `C`: 2.3e-05, versus 0.0 once
seeded. And the top five candidates in this search sit within 1.0e-05 of each
other — half the noise. The argmax was selecting noise, a different `C` won
each time, and the profit-optimal threshold followed it. The flat surface was
real; it was the amplifier, not the cause.*

*Seeded now, matching XGBoost and Random Forest, both of which carried
`random_state=42` from the start. The row is reproducible. The lesson
generalises past this project: an unseeded estimator inside a seeded search is
not obviously wrong when you read it, and only shows up as numbers that will
not sit still.*

Random Forest edges out XGBoost on profit here (\$27,000 vs. \$26,640), but at
a ROC-AUC gap of just 0.0017 — an order of magnitude smaller than the ~0.02
fold-to-fold CV std above. That gap is *not* noise: a paired Wilcoxon over 25
repeated CV folds separates the two at p = 0.0003 (appendix below). But
detectable is not the same as material. The effect is +0.0023 ROC-AUC, a sixth
of one fold's standard deviation, and it points the wrong way for the metric
that pays: Random Forest wins on profit while losing on ROC-AUC. So it still
isn't a reason to switch models — now for a measured reason rather than an
assumed one.

### Are the model differences significant?

Paired Wilcoxon signed-rank on per-fold CV ROC-AUC. The pairing is sound: all
three searches ran the same `StratifiedKFold(shuffle=True, random_state=42)`
over the same `X_tr`/`y_tr`, so fold *k* is the identical split for every
model — the notebook asserts this rather than assuming it.

| Pair | p (5 folds) | p (25 folds) | Mean diff (25 folds) |
|---|---|---|---|
| XGBoost vs Random Forest | 0.6250 | **0.0003** | +0.0023 |
| XGBoost vs Logistic Regression | 0.4375 | 0.1073 | +0.0016 |
| Logistic Regression vs Random Forest | 1.0000 | 0.6528 | +0.0006 |

Both columns are now reproducible run to run — see the note on seeding above.
The XGBoost-vs-Random-Forest result reproduced at 0.0003 across four runs.

**The 5-fold column is worthless, and that is worth saying.** With 5 pairs
there are 2⁵ = 32 equally likely sign patterns under the null, so the smallest
two-sided p the test can return is 2/32 = **0.0625**. No 5-fold result can
ever clear 0.05. Reporting "not significant" from it would have been a
statement about the sample size dressed up as a statement about the models.
The 25-fold column comes from 5×5 repeated CV on the same tuned estimators,
which has the power the 5-fold version structurally lacks.

**Result: one pair separates.** XGBoost beats Random Forest at p = 0.0003,
comfortably past the Bonferroni threshold of 0.0167 for three comparisons.
The other two pairs do not. So the blanket "information ceiling" reading needs
qualifying: the models are not interchangeable, and the difference between the
best and worst here is measurable.

It is also **too small to act on**: +0.0023 ROC-AUC is a sixth of one fold's
own standard deviation, and Random Forest still earns more campaign profit
than XGBoost at its own threshold. The practical conclusion survives; the
reasoning behind it was wrong. One caveat kept in view: repeated CV reuses
overlapping training data, so these p-values are optimistic in the
Nadeau–Bengio sense — p = 0.0003 has room to be wrong by a lot and still be
under 0.0167, but it is not the clean independent-sample number it looks
like.

The more interesting pattern is the **threshold split**: XGBoost's optimum
(0.40) sits well below Random Forest's (0.58) and Logistic Regression's (0.62).
This is a real, structural effect, not a coincidence: boosted trees
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

### How precise is 0.40, and is it optimistic?

The threshold is the argmax of a profit curve over ~90 candidates, and near
an optimum a curve is flat by definition — so an argmax picks the peak of the
noise as much as the peak of the signal. The sweep above measures uncertainty
in the *assumptions*; this measures uncertainty in the *estimate*.

| | Value |
|---|---|
| Per-fold argmax (5 folds) | 0.404 ± 0.036 |
| Bootstrap over customers (500 resamples) | 0.400 ± 0.047, 95% interval [0.29, 0.46] |
| Thresholds within 1% of peak profit | **0.35 – 0.46** |
| Cost of being anywhere in that band | ≤ $260 of $26,640 |

So the optimum is a plateau about 0.11 wide, not a point, which is why the
Results table reports **0.40 ± 0.05**. Anything in 0.35–0.46 is the same
decision in every way that matters.

That number also settles a leakage question worth being explicit about. The
threshold comes from out-of-fold predictions over `X_train`, but the
hyperparameters were chosen on `X_tr` — 80% of those same rows. Refitting per
fold removes parameter leakage, not *selection* leakage, so the scores could
be mildly optimistic on most rows. `X_val` is the clean control, since the
search never touched it:

| Rows | Threshold |
|---|---|
| `X_tr` — hyperparameters did see them (n=4,492) | 0.38 ± 0.051 |
| `X_val` — hyperparameters never saw them (n=1,124) | 0.43 ± 0.077 |
| Difference | +0.029, 95% CI **[−0.19, +0.18]** |

The interval straddles zero. The leakage is real as a mechanism but shifts the
threshold by less than the estimator's own resampling noise, so it isn't
measurable at this sample size — and nested CV would buy precision the profit
curve can't use, given the whole plateau is worth $260. Documented as checked
rather than fixed.

### Why the searched threshold sits above the closed form

The profit formula has an exact optimum. Targeting a customer pays off when
`p x success_rate x clv > cost`, so the break-even probability is
`cost / (success_rate x clv)` — 0.333 at the baseline constants. The grid
chose 0.40, and **every** row of the sweep above sits above its own
closed-form value: mean offset **+0.046**, 15 of 15 rows positive. A
consistent one-directional gap isn't search noise, so it's worth explaining
rather than shrugging at.

It's calibration. The closed form assumes the model's output *is* a
probability; the grid doesn't have to. Measured on the same out-of-fold
predictions:

| Quantity | Value |
|---|---|
| Brier score | 0.1342 |
| Mean calibration gap, all bins | +0.022 |
| Calibration gap in `[0.30, 0.50)` — where the threshold sits | **+0.051** |
| Mean threshold offset across the 15 sweep rows | **+0.046** |

Those last two agree to within 0.004, which is the whole explanation: the
model's probabilities run hot near the decision boundary, so the
profit-maximizing cutoff moves up to compensate. Note the gap is *not*
uniform — averaged across all bins the model is only 0.022 hot, roughly half
what it is in the band that actually matters, so a single global "the model
is X points optimistic" would understate the effect exactly where it counts.

Two practical consequences. First, a raw score isn't a churn probability: a
customer scored 0.45 by this model churns about 38% of the time, worth
saying before anyone quotes a score to a stakeholder. The notebook's final
appendix prints a full translation table for this, and shows the two
reliability curves side by side.

Second, this is the honest justification for searching the threshold
empirically instead of computing it — the closed form can't absorb
miscalibration, so the grid is earning its keep.

**The shipped model is deliberately left uncalibrated.** Fitting a Platt
scaler does move the profit-optimal threshold onto the closed form (0.32
against a predicted 0.333), which is a satisfying confirmation that the gap
really was miscalibration. But Platt scaling is monotonic: it cannot reorder
customers, so it cannot pick a better set to target. Measured on the same
out-of-fold predictions, it changes the targeting decision for 0.2% of
customers and moves campaign profit by $40 on $26,640. It buys a readable
number, not a better campaign — so it lives in the appendix as a lookup
table rather than in the artifact, and the deployed threshold stays 0.40 on
raw scores.

## Interpretability

SHAP (`TreeExplainer`) is run against the final refit model on the held-out
test set, so these are attributions for the model that actually ships. Mean
|SHAP| across the 51 encoded features, in log-odds units:

| Feature | Mean \|SHAP\| | Direction |
|---|---|---|
| `contract = Month-to-month` | 0.589 | ↑ churn |
| `contractvstenure` *(engineered)* | 0.282 | ↓ churn |
| `internetservice = Fiber optic` | 0.272 | ↑ churn |
| `tenure` | 0.211 | ↓ churn |
| `onlinesecurity = No` | 0.197 | ↑ churn |
| `monthlycharges` | 0.154 | ↑ churn |
| `techsupport = No` | 0.142 | ↑ churn |
| `paymentmethod = Electronic check` | 0.126 | ↑ churn |

**Contract type dominates.** Being month-to-month carries more than twice the
attribution of the next feature and roughly a fifth of all 51 features
combined; `contract = Two year` shows up separately at 0.126 pulling the other
way. The top five features account for **53.6%** of total attribution, so this
is a model driven by a handful of things rather than a broad blend.

Three findings worth drawing out:

- **The commitment story is the whole story.** Contract type, `tenure`, and
  the engineered interaction between them occupy three of the top four slots.
  Customers who haven't committed and haven't been around long are the
  churners, which is intuitive — the useful part is that the model says so
  loudly rather than spreading attribution thinly.
- **Of the six engineered features, one is excellent and two are dead.**
  Their ranks out of 51:

  | Engineered feature | Rank | Mean \|SHAP\| |
  |---|---|---|
  | `contractvstenure` | **2** | 0.2821 |
  | `average_monthly_charges` | 10 | 0.1092 |
  | `charge_change_ratio` | 17 | 0.0328 |
  | `total_services` | 20 | 0.0234 |
  | `is_auto_pay` | 50 | **0.0000** |
  | `family_tie` | 51 | **0.0000** |

  `contractvstenure` — contract length ordinal × tenure — ranks second
  overall, above raw `tenure` itself, because the interaction carries what
  neither parent has alone: two years on a month-to-month contract means
  something different from two years on a two-year contract.

  The two zeros are exact, not rounded — the trained booster contains **no
  split on either feature**, so they contribute nothing to any prediction.
  They are computed on every request and every batch row for no effect. The
  six together carry 15.5% of total attribution, essentially all of it from
  one feature. Dropping the two dead ones is a safe simplification; it is
  left in place here only because removing a column changes the feature
  schema and so requires a retrain. (Worth noting `is_auto_pay` is the
  feature whose `.str` handling `feature_engineering_telco.py` guards most
  carefully — that guard is protecting the pipeline's column contract, not
  the model's accuracy.)
- **Two drivers are directly actionable, and the campaign ignores them.**
  `onlinesecurity = No` (0.197) and `techsupport = No` (0.142) together carry
  more attribution than `tenure`. Unlike contract type or tenure, these are
  add-ons the business can simply *give* someone. The retention campaign
  modelled here spends a flat $20 per targeted customer on an unspecified
  intervention — the notebook's own note calls it "a discount/incentive, or
  agent outreach time" — applied uniformly. SHAP suggests
  targeting that spend specifically at the add-on someone is missing may beat
  spending it undifferentiated. That is a hypothesis this data cannot
  confirm — it is correlational, and customers who decline add-ons may differ
  in ways the model can't see — but it is the kind of lead worth an A/B test,
  and it is a more specific next step than "improve the model."

`Fiber optic` at 0.272 with `monthlycharges` at 0.154, both pushing toward
churn, is the familiar pattern of a premium tier that costs more and
under-delivers; worth flagging to whoever owns that product line.

## Explaining one customer in plain English

The Interpretability section describes the model as a whole. A retention
agent about to call someone needs the reasons for *that* customer, in words.
`POST /explain` returns the same decision as `/predict`, the model's five
strongest drivers for this customer, and a two-to-three sentence summary
written by a language model (`gpt-4o-mini`). Because a language model writes
it, most of this section is about what it is *not* allowed to do.

```
explain.py     →  narration_payload()  →  language model  →  validate_narrative()
exact SHAP        what it may be told       one call          nine checks on
                                                              every reply
```

Everything except the middle step is deterministic code. The language model
never sees the customer's row and never computes anything, and nothing it
writes reaches a reader until it has been checked against what it was given.

**The reasons come from the churn model, not the language model.**
`explain.py` takes XGBoost's own `pred_contribs`, the same exact tree-SHAP
values the notebook gets from `shap.TreeExplainer`. It uses XGBoost rather
than `shap` because XGBoost is already a runtime dependency, so the serving
path gained no new package. Tree SHAP is additive: the contributions plus a bias
term sum to the model's margin. That identity is checked on every
explanation, and a driver list that does not reconstruct the model's own
probability is refused. `/explain` then compares the probability and decision
against `/predict`'s own scoring with `==`, and returns a 500 rather than
reasons for a different number.

**What the language model is told is deliberately less than it could be:**

- **Three factors, chosen after protected attributes are removed.**
  `gender`, `seniorcitizen`, `partner`, `dependents` and `family_tie` (derived
  from the last two) can be genuine top drivers, and the attribution still
  reports them. But "she is a senior citizen" must never reach a person as a
  reason to make a call. Filtering happens before the top three are picked,
  so a protected driver cannot use up a slot, and `/explain` names anything
  it left out.
- **A risk band, not the probability.** The bands are low, moderate, high and
  very high, cut at 0.20 / 0.40 / 0.70. They are set relative to the
  threshold with the same `>=`, so "high" and "very high" are exactly the
  targeted customers. The score is uncalibrated (see above), and the first
  prompt version quoted it back as "61.51%".
- **Each value with a comparison in words**, such as "much lower than most
  customers", measured in training standard deviations from the median. The
  first live run described a customer who had paid $5,762.95, about four
  times the median, as having "a lower total charged to date". Given the
  comparison, the model has nothing left to guess. Engineered values like
  `contractvstenure` get the comparison and never the number, so there is no
  meaningless figure to quote.

It replies in strict JSON (`risk_level`, `reasons[{field, direction}]`,
`summary`), so the structured part is checked exactly, with no text matching.

**Nine checks run before a summary is shown.** Any one rejects the reply.
One retry is allowed. The correction names the rule that was broken and never
suggests wording: telling the model what to say would let a retry turn an
invented reason into an accepted answer.

| Check | Rejects |
|---|---|
| `empty_output`, `malformed_output` | no reply, or not the JSON shape asked for |
| `overlong_output` | a summary over 400 characters (about 60 words are asked for) |
| `protected_attribute` | a protected attribute named anywhere, gendered pronouns included |
| `unlisted_field` | a reason or a mention of any field outside the three given |
| `hallucinated_number` | a number that is not one of the given values (rounding allowed) |
| `decision_contradiction` | a risk level, or "low/high risk" wording, that disagrees with the band |
| `commentary` | remarks on the decision itself, or speaking in the first person |
| `misstated_factor` | a direction, or a higher/lower, that disagrees with what was given |

### How the prompt got to v5

Each version answers something a live run found, and each run's result is a
measurement of a specific, hash-pinned prompt file. Editing a prompt in place
fails a test, so every number below still refers to the exact text that
produced it.

| Version | What the run before it found | Change |
|---|---|---|
| v1 | — | free prose, raw probability included |
| v2 | quoted the uncalibrated score as "61.51%"; called a total 4× the median "lower" | strict JSON; a band instead of the probability; comparisons sent as words |
| v3 | 6 of 8 summaries copied "well above typical" verbatim; 7 of 8 commented on the decision ("I agree with the decision") | plainer comparison phrases; the decision is no longer sent, and commenting on it is rejected |
| v4 | — | written, measured once, deleted: v3 had not been judged yet |
| v5 | 50 customers on v3, all accepted, read by hand: degrees, motives and weightings it was never given, and factors reordered | four "say only what you were given" rules |

The v3 run is the useful one to look at. All 50 summaries passed every check,
with not one false statement, and reading them still found the model saying
more than it was handed. Same 50 customers, same model and seed, only the
prompt changed:

| Habit | v3 | v5 |
|---|---|---|
| a degree it was not given ("*much* lower commitment" when the data said "lower") | 5/50 | **0/50** |
| a guessed motive ("indicating a lack of loyalty") | 2/50 | **0/50** |
| weighing factors ("significantly lowers", "outweigh") | 1/50 | **0/50** |
| factors reordered | 6/50 | **0/50** |

None of the four rules is checked at run time. A degree check and a
speculation check were built in September and then removed. They rejected
text that stated nothing false, which cost a retry and sometimes the summary
itself, over a wording preference. They are measured afterwards instead,
below.

### How faithful is it, measured on 300 customers?

0 problems in 50 still allows a true rate of about 7% (95% upper bound). So `faithfulness.py`
measures prompt v5 on 300 inputs instead. The test set's 1,405 customers
produce only 528 distinct inputs for the language model, because it sees
three worded factors and a band rather than the whole row. The sample takes
all 33 very-high-risk inputs and a stratified 267 of the rest. It ran with
no cache: 302 calls, $0.054, about 13 minutes.

Six code checks then read every accepted summary. They are measurements, not
guards: nothing is rejected because of them. The limits were fixed from the
50-customer result before the run existed:

| | Result | Limit |
|---|---|---|
| rejected on the first attempt | 0 of 300 | 5% |
| no summary after the retry | 0 of 300 | 1% |
| reasons reordered | 0 of 300 | 2% |
| summary reordered | 2 | 2% |
| degree overstated | 0 | 2% |
| speculation | 0 | 2% |
| weighing | 2 | 2% |
| direction contradicted | 0 | 2% |

On the day, the checks rejected 2 first answers and left one customer with
no summary. All three were the same false alarm, and so was the only
rejection in each 50-customer run. A value can name a different field from
its own: `multiplelines` = "No phone service", or an add-on = "No internet
service". The `unlisted_field` check took a correct "they do not have phone
service" for an invented fact. The fix allows exactly those two values, and
only when they were given. A test fails if any other value in the data ever
names a different field. Re-checked against the saved replies, rejections
fell to 0 in all three runs at no cost, because nothing had to be
generated again.

Two wording habits are counted and deliberately left alone, because neither
is false. 237 of 300 summaries (79%) use the refrain "which raises their
risk". 193 (64%) leave at least one factor's value out of the sentence, or
word it in a way a text match cannot confirm ("a contract type that reduces
their risk" instead of "a two-year contract"). Both arrived with v5 as the
cost of the four rules above, and they are what a v6 would address.

**A second model as a cross-check, and how much it was worth.** A stronger
model (`gpt-6-luna`) also read the 299 accepted summaries once, answering a fixed
checklist and quoting the words it objected to. Before that it was scored on
103 cases with known answers: it caught 55 of 55 planted or known problems
and flagged 2 of 48 clean summaries. On the real run it flagged 17, which
were read by hand:

- 2 real, both already counted by the code checks
- 3 arguable
- 12 false alarms, 11 of them "due to" taken for a guess

It did find one phrasing the checks had missed ("not enough to offset the
other factors"), which is now on the weighing list. It is not part of the
product or the gate: a judge that is wrong in 12 of 17 flags is a second
opinion, not a test.

**The measurement is a CI gate.** The 300 saved answers and their results
are committed (`docs/faithfulness_baseline.json`, with the readable
`docs/faithfulness_report.txt`). A test in the ordinary suite fails in any of
these cases:
- the prompt's hash, the model, the seed or the temperature differs from what
  was measured
- re-checking the saved answers with today's checks puts any rate over its
  limit
- the baseline file is missing

So a prompt change cannot ship unmeasured: CI stays red until it is measured
again (about $0.05). A change to a check is re-scored against the same 300
real answers for free.

**Repeats are free.** Accepted summaries are cached in SQLite, keyed by
exactly what the model was sent plus the model, temperature and seed, with
one table per prompt version so an old prompt's answer can never be served to
a new one. Measured in the container: 3.8 s for a new customer, 0.03 s for
the repeat. A process with no API key still serves what is cached, and
otherwise returns the drivers with `explanation: null`. The numbers never
depend on the language model being reachable.

A summary costs about $0.0002. The whole project's live calls (every prompt
version, the 300-customer run and the judge) came to about $0.18.

## Fairness

`fairness_analysis.py` asks whether the shipped model catches churners
equally well across groups. Missing a churner is the harm being measured,
because a retention offer is a benefit. The full output is committed as
`docs/fairness_report.txt`.

**Nothing is retrained.** The committed pipeline is scored on the test set,
rebuilt by replaying the notebook's cleaning and split. That rebuild is
checked rather than assumed: the script refuses to report anything unless the
confusion matrix reproduces the published 256/179/116/854 exactly. Every gap
comes with a 95% bootstrap interval (2,000 resamples of the test set). A
recall estimate's precision depends on how many *churners* a group has, not
how many customers, so groups are graded by that count. Below 30 churners, no
rate is reported at all.

| Group | Churn rate | Recall | Gap in recall (95% CI) |
|---|---|---|---|
| senior / non-senior | 38.9% / 24.1% | 86.5% / 63.3% | **+23.3 pts** [+14.1, +31.6] |
| no partner / has partner | 33.0% / 19.3% | 75.3% / 56.6% | **+18.7 pts** [+8.5, +28.8] |
| no dependents / has dependents | 30.7% / 16.9% | 72.6% / 53.4% | **+19.2 pts** [+6.4, +30.8] |
| female / male | 28.3% / 24.8% | 70.0% / 67.6% | +2.4 pts [−6.9, +12.4] |
| manual pay / auto-pay *(income proxy, not protected)* | 34.8% / 16.0% | 76.8% / 47.0% | **+29.8 pts** [+19.1, +40.1] |

Precision shows no significant gap for any group. Senior × gender combines
additively, with no interaction the one-way checks miss.

**Every gap runs the same way: the group that churns more is caught more.**
Seniors, customers without a partner or dependents, and manual payers are
*more* likely to be contacted before they leave, not less. That is what one
threshold does to groups with different base rates: the model ranks
higher-risk groups higher, so more of them clear 0.40. The customers being
missed are churners from the low-risk groups. A churning customer with a
family is meaningfully less likely to get the offer than one living alone.

**Closing the senior gap costs $220 and gains nothing worth having.** With a
separate profit-optimal threshold for each group, the test set earns $6,680.
Adding equal recall drops that to $6,460, and both groups then catch 67.4% of
their churners. That is $220, 3.3% of the profit. How parity is reached
matters more than the price: it comes from *raising* the seniors' cutoff from
0.40 to 0.56, so fewer at-risk seniors get contacted. Equal recall here is
levelling down.

**Decision: one threshold for everyone, unchanged.** A different cutoff by
age is treating people differently because of their age, which is what this
check exists to prevent. The per-group thresholds are a measurement of the
trade-off, not a proposal. When two groups churn at different rates, equal
recall, equal precision and equal flag rates cannot all hold at once
(Chouldechova 2017; Kleinberg, Mullainathan & Raghavan 2016). The report picks
recall parity and says why, and prints the numbers so that someone who would
choose differently can.

The same attributes are kept out of the written explanations: they are
removed before the language model sees anything, and any mention of them is
rejected (see the explanation section above). The model may use age; a
summary may never give it as a reason to call someone.

## Repo structure

```
telco_customer_churn.ipynb    # full analysis: cleaning → modeling → SHAP → threshold sensitivity
feature_engineering_telco.py  # shared feature logic (single source of truth)
campaign_profit.py            # the campaign profit formula + break-even threshold,
                               # in one place (was retyped in 7 notebook cells)
telco_model.py                # batch scoring script (CSV in, CSV out)
api.py                        # FastAPI service (POST /predict, POST /explain)
explain.py                    # per-customer drivers: exact tree SHAP from the shipped model
narrate.py                    # the language-model step: payload, prompt, nine checks, retry
narration_cache.py            # SQLite cache of accepted summaries, one table per prompt
llm_tracing.py                # optional Langfuse tracing for command-line narration runs
faithfulness.py               # the 300-customer measurement and the CI gate on it
fairness_analysis.py          # per-group recall/precision with bootstrap intervals
prompts/                      # versioned system prompts, each pinned by its sha256
LLMcalls.ipynb                # read-only viewer for saved language-model runs
frontend/index.html           # single static page: /predict, and /explain on a button
docs/                         # data dictionary, fairness and faithfulness reports,
                               # the committed faithfulness baseline, a demo script
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
  test_campaign_profit.py     # unit tests for the profit arithmetic
  test_check_model_environment.py  # unit tests for the CI version gate
  test_explain.py             # attribution reconstructs the model's own probability
  test_narrate.py             # payload, every check in both directions, retry policy
  test_explain_api.py         # /explain against the real pipeline and a scripted model
  test_faithfulness.py        # the harness offline, and the gate on the committed baseline
  test_narration_cache.py     # keys, expiry, and per-prompt tables
  test_llm_tracing.py         # tracing against the real SDK, with an in-memory exporter
  test_fairness_analysis.py   # the fairness report's arithmetic and split reconstruction
  test_narrate_live.py        # the only tests that call a real model; deselected by default
  conftest.py                 # DummyModel + _FakeJoblib, shared by the API and
                               # batch-script tests so they can't drift apart
check_model_environment.py    # CI gate: fails the build if installed library versions
                               # don't match the ones that trained the artifact
pyproject.toml                # dependencies (managed with uv), split into runtime /
                               # dev / explain / llm / notebook groups
.github/workflows/tests.yml   # CI: version gate + test suite, and a parallel job that
                               # builds the image and smoke-tests it, on every push and PR
Dockerfile                    # production image: API + batch scorer, one image, non-root
.dockerignore                 # keeps the 1.2 GB local .venv and the notebook out of the
                               # build context

verify_version_check.sh       # integration check: builds two throwaway venvs and
                               # verifies the version-drift warning actually fires

# regenerated by running the notebook end to end, but committed anyway so
# the API and batch script run straight after a clone:
xgboost_churn_pipeline.pkl    # trained pipeline (preprocessing + model)
model_metadata.json           # operating threshold + CV scores + feature schema + dataset
                               # hash + library versions + pinned reference prediction
simulated_new_customers.csv   # sample input for telco_model.py

# the one fixed point a dataset-hash comparison can check against across
# runs, unlike model_metadata.json above, which is rewritten on retrain:
dataset_baseline.json         # SHA-256 hash of the raw Kaggle CSV, recorded once

# not committed — regenerated on every scoring run:
retention_campaign_targets.csv
outputs/                      # saved language-model runs
data/narration.sqlite3        # the summary cache
```

## Running it

**Installing:** dependencies are split by what you actually intend to do.
```
uv sync                        # serve or score: the runtime set, plus test tooling
uv sync --group llm            # additionally: written summaries on /explain
uv sync --group notebook       # additionally: re-train by running the notebook
```
The default set is deliberately small — 32 packages rather than 142 — because
it is what a deployed container installs, and Jupyter, SHAP, matplotlib and
seaborn are needed only to *produce* the model, never to *use* it. Splitting
them out cuts the installed environment from roughly 1.4 GB to 675 MB. If an
import fails while running the notebook, the `notebook` group is what's
missing. The `llm` group is the OpenAI SDK plus the optional Langfuse tracing
SDK; without it `/explain` still answers, with drivers and no summary. (`uv sync`
replaces the environment, so name every group you want in one command:
`uv sync --group llm --group notebook`.)

**Batch scoring:**
```
python telco_model.py
```
Reads `simulated_new_customers.csv`, writes `retention_campaign_targets.csv`.

Two checks run before anything is scored. First, the current feature schema
is validated against `model_metadata.json`, failing fast with a clear error
if they've drifted apart (e.g. `feature_engineering_telco.py` changed but the
notebook wasn't rerun). Second, the input frame itself is validated against
the categories the model was trained on — this matters because the pipeline's
OneHotEncoder is configured with `handle_unknown='ignore'`, so an
unrecognized category is silently encoded as all-zeros rather than raising.
A single casing difference (`month-to-month` instead of `Month-to-month`)
moves a customer's score from 0.5700 to 0.1017 — a flipped retention
decision, with no error anywhere. The API never had this problem because
Pydantic rejects those values outright; the batch path needed it added.

Validation reports every problem at once rather than the first, and names
rows by file line number so they can be fixed in one pass:

```
Input validation failed -- refusing to score. ...

  contract: 2 row(s) with a value outside the trained categories.
      found:   'Two Year', 'month-to-month'
      allowed: 'Month-to-month', 'One year', 'Two year'
      rows:    5, 9
  monthlycharges: 1 row(s) are negative. ...
      rows:    13
```

Note what is deliberately *not* checked: plausible numeric ranges. The model
is a tree ensemble, so out-of-range values saturate rather than extrapolate —
`tenure=1000` and `tenure=10^15` both score 0.1201. A range check would
reject inputs the model already handles correctly, so membership and
finiteness are checked and magnitude is not.

**Configuration:**
`MODEL_PATH` and `METADATA_PATH` (in `config.py`) default to
`xgboost_churn_pipeline.pkl` and `model_metadata.json` in the working
directory, but can be overridden per-environment without a code change:
```
MODEL_PATH=/path/to/model.pkl METADATA_PATH=/path/to/metadata.json uvicorn api:app
```
`telco_model.py` reads `INPUT_PATH` and `OUTPUT_PATH` the same way, defaulting
to `simulated_new_customers.csv` and `retention_campaign_targets.csv` in the
working directory:
```
INPUT_PATH=/data/new.csv OUTPUT_PATH=/data/targets.csv python telco_model.py
```
That is what lets the container score a mounted volume without a code change —
the image ships the script and the model, and the data arrives from outside.

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
  "churn_probability": 0.7443000078201294,
  "target_for_retention": true,
  "threshold_used": 0.4
}
```
*(the real response for the payload above)* — the probability is reported
unrounded on purpose. The decision is `churn_probability >= threshold_used`
evaluated at full precision, and `telco_model.py` compares the same way, so
rounding for display would let a response show `0.4 >= 0.4` next to `false`,
and rounding before the comparison would flag customers the batch script
skips.

Invalid input is rejected with a `422` before the model is touched: an
unknown category, a negative charge, or a non-finite number (`Infinity`,
`NaN` — accepted by Python's JSON parser, and `inf >= 0` is `True`, so a
bare `ge=0` bound does not catch them). The allowed values are the same ones
the batch path checks against — `config.CATEGORICAL_DOMAINS` mirrors this
model's `Literal` types, and a test asserts the two agree so the two
consumers cannot drift into accepting different inputs.

**Explanations:** `POST /explain` takes the same body. For a written summary
the process needs the OpenAI key, which is passed per command and never read
from a file by the code:
```
uv sync --group llm
uv run --env-file .env uvicorn api:app
```
```json
{
  "churn_probability": 0.7443000078201294,
  "target_for_retention": true,
  "threshold_used": 0.4,
  "risk_level": "very high",
  "drivers": [
    {"field": "contract", "label": "contract type", "value": "Month-to-month",
     "vs_other_customers": null, "direction": "raises risk", "contribution": 0.6179567351937294},
    ...four more
  ],
  "explanation": {
    "risk_level": "very high",
    "reasons": [
      {"field": "contract", "direction": "raises risk"},
      {"field": "contractvstenure", "direction": "raises risk"},
      {"field": "internetservice", "direction": "raises risk"}
    ],
    "summary": "This customer has a very high risk of leaving due to their month-to-month contract, which raises their risk. Their overall commitment is lower than most customers, which also raises their risk. Additionally, they use fiber optic internet service, contributing further to their risk."
  },
  "meta": {"status": "ok", "detail": null, "rejection_type": null,
           "prompt_version": "explanation_v5", "model": "gpt-4o-mini",
           "cache_hit": true, "attempts": 0, "protected_drivers_omitted": []}
}
```
*(the real response for the same payload as above, served from the cache;
four of the five drivers left out)* — the first three fields are `/predict`'s,
by construction: both endpoints score through one function, and `/explain`
returns a 500 rather than reasons for a different number. `drivers` are five
where the language model was shown three, so every field in `reasons` can be
looked up in them.

A missing summary is still a `200`. `meta.status` says why:

| `status` | `explanation` | Meaning |
|---|---|---|
| `ok` | the summary | accepted by every check, live or from the cache |
| `rejected` | `null` | both attempts were refused; `rejection_type` names the check |
| `unavailable` | `null` | no key, or the `llm` group isn't installed |
| `error` | `null` | the call was made and failed (network, rate limit, the 15 s timeout) |

The drivers and the decision are present in all four. Only a missing model,
or a build without the explanation layer, answers `503`.

**Docker:**
```
docker build -t telco-churn .

# API (drivers on /explain, no summaries: there is no key)
docker run -p 8000:8000 telco-churn

# API with written summaries. The key comes from .env on the host, never the image.
uv run --no-sync --env-file .env -- \
  docker run -p 8000:8000 -e OPENAI_API_KEY -v telco-cache:/data telco-churn

# Batch scoring, against the sample CSV shipped in the image
docker run telco-churn python telco_model.py

# Batch scoring, against your own CSV: put it in ./data and name it
docker run -v "$PWD/data:/data" -e INPUT_PATH=/data/new_customers.csv \
  telco-churn python telco_model.py
```
Mounting a directory at `/data` shadows the sample CSV baked into the image —
intended, since you are supplying your own data, but it does mean an empty
mount has nothing to score. `INPUT_PATH` defaults to
`/data/simulated_new_customers.csv`, so a file at that exact name needs no
`-e` flag. Output lands at `/data/retention_campaign_targets.csv` unless
`OUTPUT_PATH` says otherwise. (`-v "$PWD/data:/data"` rather than
`-v ./data:/data` only for portability — relative bind sources need Docker
23 or newer.)

The key goes through `uv run --env-file` rather than `docker run --env-file`
because Docker's own parser keeps quotes as part of the value, so a quoted key
arrives as `"sk-..."` and every call fails. `telco-cache` is a named volume
holding the summary cache (`NARRATION_DB=/data/narration.sqlite3`). A bind
mount of the repo's `data/` would not work here: that folder belongs to the
host user, and the container's user can read the cache there but never write
to it.

One image serves both entrypoints, on purpose. The API and the batch script
have an identical dependency set and share `config.py` and
`feature_engineering_telco.py`, and the invariant that matters most here is
that the two paths reach the *same* decision — same model, same threshold,
same `>=` comparison. Two images would duplicate every layer for no benefit
while creating exactly the divergence that invariant exists to prevent. Both
were checked against a local run: the container's
`retention_campaign_targets.csv` is byte-identical to the host's, and
`/predict` returns the same `0.7443000078201294` documented above.

The model is copied in, never trained during the build. The artifact is
committed and byte-reproducible, and training needs the `notebook` dependency
group, which the image deliberately does not install.

**What the build verifies.** Three checks run as build steps, so a broken image
fails `docker build` instead of failing at the first request in production:

- `check_model_environment.py` — the same hard version gate CI runs. Because
  the image installs from `uv.lock`, its library set is a build artifact
  rather than a hope, and this asserts that set matches
  `model_metadata.json["library_versions"]`.
- A load-and-score check of the committed `.pkl`, asserting `DUMMY_CUSTOMER`
  still scores the `dummy_customer_score` recorded in the metadata. The
  version gate proves the versions match; this proves the pickle actually
  loads and reproduces its prediction, which version equality alone cannot
  show.
- The explanation layer is present: `api.py` imports it, the prompt file reads
  and the OpenAI SDK is installed. `api.py` imports the layer optionally, so
  without this check a missing piece would show up as a quiet `503` on
  `/explain` at run time.

All three run *after* `USER appuser`, which is how they also confirm the
unprivileged user can read the artifact. That is not hypothetical — it caught
a real defect on the first build: several source files are `0600` in the
working tree from a restrictive umask, `COPY` preserves host modes, and the
image would otherwise have built clean and died on its first request with
`PermissionError` on `config.py`. The `COPY --chmod=0644` in the Dockerfile is
the fix. The third check caught the same class of defect on its own first
build: copying the prompt into a new `prompts/` folder created the folder with
the file's mode, `0644`, which the unprivileged user cannot enter. The image
built, started and passed its health check, and every `/explain` would have
failed reading the prompt.

**Size.** 593 MB. Dependencies come from the runtime group plus `--no-dev`
and the `explain` group (the OpenAI SDK alone, for `/explain`), so neither the
training stack (jupyter, matplotlib, seaborn, shap, kagglehub, scipy), the
tracing SDK nor the test runner ships — 30 installed distributions, against
the 32 that `uv sync` gives a developer. Before the explanation layer was
added on 2026-10-15 it was 570 MB and 24. The single largest remaining item was not a
project dependency at all: `xgboost` hard-depends on
`nvidia-nccl-cu13` on Linux, 288 MB of GPU distributed-training libraries a
CPU inference container never calls. Removing that payload in the builder
stage took the image (as it was then) from 858 MB to 570 MB. It is done there rather than by
switching to the `xgboost-cpu` distribution because `check_model_environment.py`
resolves versions through `importlib.metadata.version("xgboost")`, which
raises `PackageNotFoundError` under that package and would fail the gate — and
rather than in `pyproject.toml` because it is a property of the image, not of
the project, leaving `uv.lock`, CI and a local `uv sync` untouched.

**Security.** The container runs as `appuser` (uid 10001), not root, because
`api.py` loads a pickle and `joblib.load` executes arbitrary code on
deserialization. `/app` is read-only to that user; `/data` is the only
writable path, which is where the batch scorer reads its input and writes its
output, and where the summary cache lives. `INPUT_PATH` and `OUTPUT_PATH` default to `/data` inside the image, so
mounting a host directory there is the entire interface — the mount shadows
the sample CSV baked in, which is intended: the shipped sample exists only so
a bare `docker run` still demonstrates the batch path.

**Tests:**
```
uv run pytest -q
```
788 tests, about 30 seconds. They cover feature engineering edge cases, API
request/response contracts, the feature-schema validation guard,
`load_threshold`'s behavior on malformed metadata, batch-input validation,
the batch scoring script's I/O contract, and, in 577 of them, the explanation
layer: every check in both directions, the retry policy, the cache, `/explain`
and the faithfulness gate.

No test reaches a real language model unless it asks to. The explanation
tests drive a scripted fake model, and a shared fixture removes
`OPENAI_API_KEY` from the environment, because the app builds a client at
startup when the key is set. The ten tests in `test_narrate_live.py` call the
real API and spend money, so they are deselected by default and run only with
`uv run pytest -m live`.

Several test files are deliberately not mocked, among them:

- `test_integration.py` fits the real preprocessing pipeline +
  `XGBClassifier` on a small synthetic sample, so the actual
  sklearn/XGBoost plumbing is exercised end to end rather than each
  piece's wiring in isolation. It needs no trained artifact.
- `test_artifact.py` loads the committed `xgboost_churn_pipeline.pkl`
  itself and pins its prediction — see "Artifact pinning" below.
- `test_input_validation.py` drives the real FastAPI app and the real
  domain checks.
- `test_explain.py` and `test_explain_api.py` use the committed pipeline,
  because an attribution needs its real preprocessor and booster. The second
  also pins `/explain`'s probability and decision to `/predict`'s on all 50
  simulated customers.

Everything else mocks the model out and runs without a trained `.pkl` on
disk. A fresh clone can run the full suite immediately, before ever opening
the notebook, because the artifact and its metadata are committed.

**Artifact pinning:** `test_artifact.py` asserts that the committed pickle
still scores a fixed reference customer at the value recorded in
`model_metadata.json["dummy_customer_score"]`. The notebook's save cell
writes that number at the same moment it writes the pickle, so retraining
updates both together and the pin cannot go stale — it only fails when the
artifact and the environment around it disagree. That covers the case
`verify_version_check.sh` states it cannot detect: a library version that
unpickles cleanly but predicts differently.

**Version drift:** `model_metadata.json` records the exact
scikit-learn/XGBoost/numpy/pandas versions that produced the pickle, and
`config.validate_environment_versions()` compares them against the running
environment at startup. It warns rather than blocking, deliberately —
neither library guarantees pickle compatibility across releases, but turning
a possibly-harmless patch bump into a guaranteed outage is worse than
surfacing it for a human to judge. `verify_version_check.sh` builds two
throwaway virtualenvs and confirms that warning actually fires.

That leniency is only defensible if something stricter runs before deploy, so
the hard gate lives in CI: `check_model_environment.py` compares the same
versions and **exits non-zero**, failing the build. The two checks differ
deliberately in what they do with ignorance. At runtime, unreadable metadata
or an untracked library is a shrug — the service keeps serving. In CI it is a
failure, because there is no uptime to protect there, only the question of
whether this environment matches the artifact, and "can't tell" is not a yes.
The gate resolves versions through the same `config._current_library_versions()`
the service uses rather than keeping its own list: a gate that checks something
different from what production checks is worse than no gate. It runs before
the test suite, so a version skew reports itself as a version problem instead
of as a cryptic pinned-prediction failure in `test_artifact.py`.

The same gate runs a third time, as a `docker build` step, and that is where
it changes character. In CI it answers "does this checkout match the
artifact?" — a question about a machine that will be thrown away. In the image
it answers "does this artifact match the dependency set that was just pinned
from `uv.lock`?", and the answer is baked in permanently. The runtime check
stops being the primary defence against version drift and becomes a cheap
assertion that the image is the one it claims to be — which is the real
argument for containerizing this project, more than deployment convenience.

**Missing metadata is fatal.** If `model_metadata.json` is absent or
unparseable, both consumers stop at startup with a message naming the file
and how to regenerate it — the artifact records the threshold, the feature
schema and the library versions, so without it there is no way to confirm
the pickle beside it is the one the code expects. A *malformed value inside
a readable file* is treated differently: `load_threshold` falls back to
`DEFAULT_THRESHOLD` with a warning, since the model itself is probably fine
and a sane default beats an outage.

## Known limitations / what I'd add for production

- **Threshold sensitivity is confirmed against the current model** (see
  sweep above), not just checked once and forgotten. `clv`, `cost`, and
  `success_rate` are still hardcoded placeholders, not measured values, and
  remain the single biggest source of uncertainty in the whole pipeline —
  bigger than model choice.
- **The model gaps were tested, and one of them is real** — see the
  significance appendix. XGBoost beats Random Forest on ROC-AUC at
  p = 0.0003, which survives Bonferroni correction for the three pairwise
  comparisons. That contradicts the earlier eyeball call of "all noise", so
  it is recorded here rather than quietly dropped. It does not change the
  recommendation: the effect is +0.0023 ROC-AUC, about a sixth of one fold's
  own standard deviation, and Random Forest still returns more campaign
  profit ($27,000 vs. $26,640) at its own threshold. A difference can be
  reliably detectable and still be too small to act on — that is the
  distinction the original note was missing in both directions.
- No auth on the API — fine for a local demo, not for anything exposed
  publicly.
- No monitoring or drift detection — churn drivers shift over time in
  practice; a deployed version of this would need to track prediction
  distribution and periodically retrain. The feature-schema check catches
  *code/model* drift, not *data* drift (e.g. the input population changing
  over time).
- Hyperparameter search is currently `RandomizedSearchCV`; a Bayesian search
  (Optuna) would likely reach the same ~0.845 plateau with fewer iterations,
  though the convergence check suggests there isn't much headroom left to
  find either way.
- `simulated_new_customers.csv` is sampled from the held-out test set for
  demo convenience, not genuinely unseen data.
- **`/explain` spends money on every new customer, and nothing limits who
  asks.** That is fine on a laptop. Exposed publicly, anyone could run up the
  OpenAI bill. It would need auth or a rate limit first, along with the auth
  the API is already missing.
- **The same customer can be worded differently on a fresh call.**
  Temperature 0 and a fixed seed narrow the variation, but OpenAI documents
  `seed` as best-effort. Re-asked days to weeks later, 11 of 15 customers got
  different (still accepted) wording. The cache keeps a repeat identical; the
  measurement is over 300 customers for the same reason.
- **The faithfulness numbers describe one prompt on one model.** Switching
  `gpt-4o-mini` for anything else fails the CI gate until it is measured
  again. That is intended: the 300-customer result says nothing about a
  different model.
- **`/explain` is not traced.** Langfuse tracing exists for command-line runs
  only.

## Stack

Python, pandas, scikit-learn, XGBoost, SHAP, FastAPI, OpenAI API
(`gpt-4o-mini`), SQLite, Langfuse (optional), uv, Docker.

## License

MIT — see [LICENSE](LICENSE).
