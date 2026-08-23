# ml_projects_4 — telco churn, profit-optimised retention targeting

Predicts churn and decides **who is worth targeting** given campaign economics.
The model produces a ranking; a separately-chosen threshold (0.40, in
`model_metadata.json`) turns that ranking into a decision. Those are two
independent steps — that separation is the point of the project.

## Read this before opening files

**Never `Read` the notebook directly.** `telco_customer_churn.ipynb` is 800 KB
(~200k tokens) because it stores plot images. The code is ~29 KB (~7k tokens).
Extract it:

```bash
python3 -c "
import json; nb=json.load(open('telco_customer_churn.ipynb'))
for i,c in enumerate(nb['cells']):
    print(f'--- [{i}] {c[\"cell_type\"]} ---'); print(''.join(c['source']))"
```

Reading everything else (4 source files + 5 test files + README) is ~16k tokens.

## Layout

| File | Role |
|---|---|
| `telco_customer_churn.ipynb` | 41 cells. Training only. Produces the artifact. |
| `feature_engineering_telco.py` | 6 derived features. Imported by the notebook, API, batch script, config, and 2 test files. **The single most load-bearing module.** Guards its own `.str` use — an all-blank `paymentmethod` degrades to `is_auto_pay=0` instead of raising (AUDIT.md M9). |
| `campaign_profit.py` | The profit formula, once. `campaign_profit()`, `break_even_threshold()`, `profit_curve()`, `best_threshold()`. Imported by the notebook in 7 places; economics are keyword-only so `clv`/`cost` can't be swapped (AUDIT.md C11). |
| `config.py` | Paths, threshold loading, 3 startup validators. Shared by both consumers. Missing/corrupt metadata is **fatal**; a bad value inside readable metadata **degrades**. |
| `api.py` | FastAPI. One customer in, one decision out. Pydantic-validated. |
| `telco_model.py` | Batch scorer. CSV in, CSV out. Validates the frame via `config.validate_input_frame()` before scoring (AUDIT.md M1, fixed). |
| `xgboost_churn_pipeline.pkl` + `model_metadata.json` | The artifact. Committed on purpose so a clone runs immediately. |
| `check_model_environment.py` | CI's hard version gate. Fails the build when installed libraries differ from `model_metadata.json["library_versions"]`. The strict counterpart to `config.validate_environment_versions()`. Also runs as a `docker build` step. |
| `Dockerfile` | Production image. One image, both entrypoints (`uvicorn api:app` by default, `python telco_model.py` for batch). Multi-stage, non-root, `uv sync --no-dev`. Verifies itself at build time — see the Docker section below. |
| `.dockerignore` | Keeps the local `.venv` (1.2 GB) and the notebook out of the build context. Without it every build uploads both to the daemon. |
| `tests/` | 166 tests, a few seconds. `tests/__init__.py` is empty but **load-bearing** — deleting it breaks all 9 test files at collection. |
| `tests/conftest.py` | Shared `DummyModel` and `_FakeJoblib`. Imported explicitly (`from tests.conftest import ...`) — pytest auto-loads fixtures, not plain names. One shared fake is deliberate: it makes an API/batch divergence fail a test instead of hiding in two copies. |
| `tests/test_artifact.py` | The only tests that open the real `.pkl`. Pins `DUMMY_CUSTOMER`'s score against `model_metadata.json["dummy_customer_score"]`. |
| `tests/test_input_validation.py` | `validate_input_frame()` + the API's non-finite handling. Asserts `api.Customer`'s Literals and `config.CATEGORICAL_DOMAINS` agree. |
| `AUDIT.md` | 24 known defects (10 moderate, 14 cosmetic) + roadmap. **Local-only — gitignored, not in the repo.** If present, read it before reporting a bug — it's probably already listed. |

## Notebook cell map

51 cells. 0–1 load + dataset hash · 3–10 cleaning · 11 splits + feature
engineering · 12 `make_preprocessor()` · 14–21 baselines/imbalance (marked
removable) · 22–25 RandomizedSearchCV (200 iters) · **26 threshold selection
via OOF — the heart** · 27 sensitivity sweep · 28–29 calibration curve ·
30–33 test-set scoring · 35 model comparison · 36–37 the user's own notes ·
39–40 SHAP · 41–43 save artifact · 44–45 appendix: display-only Platt scaling
+ score→risk table · 46–48 appendix: cross-model error-overlap analysis ·
49–50 appendix: threshold plateau + selection-leakage check.

Indices above 37 shifted +1 when a markdown note was added at 37; anything
citing the older numbering is off by one there (SHAP was 38–39, save 40–42).

**44–50 save nothing.** They fit a calibrator for display and are appended
*after* the save cells on purpose, so the artifact, the metadata and the 0.40
threshold are unaffected by them. Don't move them above cell 43, and don't
wire their calibrator into the pipeline without reading the note in
`README.md` about why the shipped model is deliberately uncalibrated. Cell 47
needs `tuned_estimators`, which cell 35 fills — running 47 alone after a
kernel restart won't work.

Numbering has shifted twice: +2 above cell 27 when the calibration cells were
added, then +1 above cell 37 when a note was added there. `AUDIT.md` predates
both and uses the oldest numbering (its "cell 33" is now 35, its "cell 38" is
now 41).

## Invariants — don't break these

- `engineer_features()` must produce exactly the 25 columns in
  `model_metadata.json["feature_columns"]`. `config.validate_feature_schema()`
  crashes at startup if not.
- `api.py` and `telco_model.py` must make the **same** decision: same model,
  same threshold, same `>=` comparison. Divergence is silent. **Neither path
  rounds.** `/predict` reports the raw probability; rounding it to 4dp before
  comparing would flag customers at 0.39995 that the batch script leaves
  alone. `tests/test_api.py` pins this at the boundary.
- Both must also **accept the same inputs**. `config.CATEGORICAL_DOMAINS` is
  the batch path's copy of `api.Customer`'s `Literal` types;
  `tests/test_input_validation.py` asserts they agree. The encoder uses
  `handle_unknown='ignore'`, so an unvalidated bad category scores silently
  (0.5700 → 0.1017 on `DUMMY_CUSTOMER`) rather than erroring.
- The test set is touched once, after the threshold is locked. Threshold
  selection uses out-of-fold predictions (`cross_val_predict`), never a
  reused validation split.
- `feature_schema_version` is a **gate**, not a label:
  `config.SUPPORTED_FEATURE_SCHEMA_VERSION` must equal the string the notebook
  stamps, or startup raises. Bump both together when `engineer_features()`
  changes meaning without changing column names — the column check can't see
  that case.
- Retraining rewrites `model_metadata.json` — including `library_versions`,
  which `config.validate_environment_versions()` checks at every startup.
- Missing-metadata policy, applied by all three `config.py` entry points:
  a missing or unparseable metadata **file** raises `RuntimeError` with a
  readable message; a malformed **value** in a readable file degrades
  (`load_threshold` → `DEFAULT_THRESHOLD`). `validate_environment_versions()`
  never raises at all — it's a detection control, and
  `validate_feature_schema()` runs first in both consumers.

## Facts worth not re-deriving

- Dataset: 7,043 rows, 26.54% churn, 11 blank `totalcharges` (all `tenure==0`),
  22 duplicates after dropping `customerid`. Cached at
  `~/.cache/kagglehub/datasets/blastchar/telco-customer-churn/versions/1/`
  — lets you reconstruct any split without re-downloading.
- Shipped model scores `config.DUMMY_CUSTOMER` at **0.5699995160102844**.
  Recorded as `dummy_customer_score` in `model_metadata.json` and asserted
  by `tests/test_artifact.py`; the notebook's save cell rewrites both
  together on retrain, so the pin can't go stale.
- Test metrics reproduce exactly from the committed `.pkl`: ROC-AUC 0.8441,
  PR-AUC 0.6610, P 0.5885, R 0.6882, F1 0.6344, acc 0.7900,
  TP/FP/FN/TN 256/179/116/854.
- **PR-AUC's baseline is the churn rate (0.2648), not 0.5.** Always report it
  against that floor — 0.6610 is 2.50x random. CV PR-AUC is 0.6643 ± 0.0374,
  i.e. more than twice ROC-AUC's 0.0175 spread: fewer positives per fold, so
  the estimate is noisier. OOF PR-AUC by model: XGB 0.6603, LR 0.6548,
  RF 0.6532 — note this **reverses** RF and LR relative to ROC-AUC, but by
  0.0016, far inside the noise. Model selection still runs on
  `scoring='roc_auc'`; PR-AUC is reported, never optimised. Don't "fix" the
  search to maximise it — that would change which model ships.
- Extreme *numbers* are safe: the tree ensemble saturates, so `tenure=10**15`
  scores identically to `tenure=1000`. There is deliberately no range check.
  Unknown *categories* are the real hazard — hence the domain validation.
- The threshold is a **plateau, not a point**: everything in 0.35–0.46 is
  within 1% of peak profit, bootstrap spread ±0.047, so the README reports
  0.40 ± 0.05. M6's selection leakage shifts it +0.029 with a 95% CI of
  [−0.19, +0.18] — real in mechanism, unmeasurable in size. Checked, not fixed.
- Profit-optimal threshold has a closed form: `cost / (success_rate × clv)`
  = 0.333. The grid found 0.40. The gap is miscalibration, now measured in
  cells 28–29: the mean offset across the 15 sweep rows is **+0.046**
  (15/15 positive) and the calibration gap in the `[0.30, 0.50)` band where
  the decision is made is **+0.051** — they agree to 0.004. The gap is *not*
  uniform: only +0.022 averaged over all bins, roughly double that in the
  band that matters. Brier 0.1342.
- Env: uv, Python 3.12, pandas 3.0.5. Run tests with `uv run pytest -q`.

## After re-executing the notebook

Re-running it end to end rewrites `xgboost_churn_pipeline.pkl`,
`model_metadata.json` and `simulated_new_customers.csv`, and re-prints every
number the README publishes. Check these, in order:

1. **`git diff model_metadata.json`.** If only `trained_at` and `git_commit`
   moved, the artifact reproduced and nothing downstream needs touching. If
   `threshold`, `cv_roc_auc_*`, `cv_pr_auc_*`, `dummy_customer_score` or
   `hash` moved, the model genuinely changed — every README figure is now
   suspect. On the *first* run after PR-AUC was added, `cv_pr_auc_mean`,
   `cv_pr_auc_std` and `churn_rate_train` appear as new keys; that is the
   expected one-off, not a model change.
2. **`uv run pytest -q`.** `tests/test_artifact.py` re-pins itself against the
   rewritten metadata, so it passing does *not* prove the model is unchanged —
   step 1 is what proves that.
3. **Compare the README against the notebook's real outputs**, not against a
   reconstruction. Extract them with the cell-source snippet at the top of
   this file, substituting `c.get('outputs')`. The figures the README
   publishes live in cells 26 and 30–33 (Results table), 27 (sensitivity
   sweep), 29 (calibration) and 35 (model comparison).
4. **Watch the Logistic Regression row in cell 35 specifically.** Its ROC-AUC
   surface is flat, so the winning `C` — and therefore its best threshold —
   slides between near-tied draws from run to run. It has legitimately been
   both 0.58 and 0.62. Never publish that row from anything but a real run.
5. **Check the prose, not just the tables.** The threshold-split paragraph in
   the README quotes per-model thresholds inline and has gone stale this way
   before.

## Conventions

- `make_preprocessor()` (cell 12) returns a **fresh** ColumnTransformer per
  pipeline. Don't hoist it back to a shared object: `Pipeline.fit()` fits in
  place, so one shared instance means fitting any pipeline silently re-fits
  the scaler/encoder every other pipeline holds.
- The tuner is `RandomizedSearchCV`, not Optuna. (`optuna`, `lightgbm` and
  `pyarrow` used to be declared in `pyproject.toml` and imported nowhere;
  they were removed when dependencies were split into groups.)
- `pyproject.toml` is split three ways: `[project.dependencies]` is the
  runtime set a container installs, the `dev` group adds pytest/httpx, and
  the `notebook` group (jupyter, matplotlib, seaborn, shap, kagglehub, scipy)
  is **not installed by default**. `uv sync` gives 32 packages; re-running
  the notebook needs `uv sync --group notebook`. Don't add a training-only
  package to `[project.dependencies]`.
- Notebook cell 2 uses `warnings.simplefilter('once')`, not a blanket
  `ignore` — don't restore the catch-all (AUDIT.md M5). Lifting it exposed
  ~1,457 deprecation warnings in the model-comparison cell, now fixed: it searches
  `l1_ratio: [1.0, 0.0]` instead of the `penalty` argument scikit-learn
  removes in 1.10. Same search space, but the code paths aren't
  bit-identical — the LR row's ROC-AUC moved 0.843897 → 0.843891. That cell
  now runs warning-free.
- The profit formula lives in `campaign_profit.py` and nowhere else. Don't
  retype `tp * success_rate * clv - (tp + fp) * cost` in a new cell — it was
  duplicated 7 times before (AUDIT.md C11).
- `tests/test_integration.py`'s fixture forces the first `N_ZERO_TENURE_ROWS`
  (3) rows to `tenure=0` so the missing-`totalcharges` rows are exact for
  every seed — it used to leave that to chance and 21 of 40 seeds produced
  none (AUDIT.md M7).
- CI lives in `.github/workflows/tests.yml` — runs `check_model_environment.py`
  and then `uv run pytest -q`, on every push and PR.
- Two version checks exist and are deliberately different.
  `config.validate_environment_versions()` warns and never raises (live
  service: an outage is worse than a maybe-broken pickle);
  `check_model_environment.py` exits non-zero (CI: no uptime to protect, so
  "can't tell" fails). Both resolve versions through
  `config._current_library_versions()` — keep it that way, or CI and
  production can disagree about what's installed.

## Docker

One image, both entrypoints. `CMD` is `uvicorn api:app`; batch scoring is
`docker run -v "$PWD/data:/data" telco-churn python telco_model.py` — that
mount shadows the sample CSV baked into the image, so the mounted directory
must contain the input. Don't split this into two images: `api.py` and
`telco_model.py` have an identical dependency set, and the "both paths make
the same decision" invariant above is exactly what two independently-built
images would erode.

- **Never train in the build.** The artifact is committed and
  byte-reproducible; it is `COPY`d in. Training needs the `notebook` group,
  which the image deliberately doesn't install.
- **`uv sync --frozen --no-dev`** — 24 installed distributions on Linux, vs 32
  for a plain `uv sync`. `--no-dev` verified safe by import audit: no runtime
  module imports pytest or httpx. `--frozen` makes lockfile drift a build
  failure, matching CI.
- **The nvidia trim is deliberate and load-bearing.** `xgboost` hard-depends
  on `nvidia-nccl-cu13` on Linux — 288 MB of GPU training libraries a CPU
  inference container never calls. The builder stage deletes the payload,
  taking the image from 858 MB to 570 MB. It **fails the build if it finds
  nothing to delete**, so the trim can never silently become a no-op. Don't
  "fix" this by switching to `xgboost-cpu`: `check_model_environment.py`
  resolves via `importlib.metadata.version("xgboost")`, which raises
  `PackageNotFoundError` under that distribution and fails the gate. Don't
  move it into `pyproject.toml` either — it's a property of the image, and
  keeping it here leaves `uv.lock`, CI and local `uv sync` untouched.
- **`COPY --chmod=0644` is not cosmetic.** Several source files are `0600` in
  the working tree from a restrictive umask, and `COPY` preserves host modes.
  Without the explicit mode the image builds clean and dies on first request
  with `PermissionError` on `config.py`.
- **Two build-time verifications, both after `USER appuser`** so they also
  prove the unprivileged user can read the artifact: `check_model_environment.py`
  (versions match the artifact) and an inline load-and-score check
  (`DUMMY_CUSTOMER` still scores `dummy_customer_score`). The first is the
  version gate's third home; per AUDIT.md item 4, pinning from `uv.lock` is
  what demotes `validate_environment_versions()` from primary control to
  cheap assertion.
- **`/app` is read-only to `appuser`; `/data` is the only writable path.**
  (`/app` is root-owned, dir 0755 and files 0644 — not a read-only mount, so
  say "to appuser" rather than "read-only" flatly.) `INPUT_PATH` and
  `OUTPUT_PATH` (new in `telco_model.py`, mirroring `config.py`'s `MODEL_PATH`
  handling) default to `/data` **inside the image only** — the module defaults
  remain the repo-relative filenames. Mounting a host dir at `/data` shadows
  the sample CSV baked in; that's intended.
- **`campaign_profit.py` is deliberately not in the image.** Neither entrypoint
  imports it; the threshold its formula chose is already in
  `model_metadata.json`. If an endpoint ever needs `break_even_threshold()`,
  add it to the `COPY` line.
- **The `HEALTHCHECK` asserts `model_loaded`, not just a 200.** `/health`
  returns 200 unconditionally — `model_loaded` is a field in the body — so a
  status-only probe would call a model-less process healthy, which is the
  state `/predict` answers with a 503. Don't simplify it back to a status
  check.
- CI's `docker` job runs **parallel to** `test`, not after it. It builds the
  image and smoke-tests the running container: `/predict` pinned at
  `0.7443000078201294`, an unknown category rejected with 422, and the batch
  scorer writing through a mounted `/data` as non-root.

## CHANGELOG.md — mandatory, every session

`CHANGELOG.md` in the repo root is an append-only record of every file
change an assistant makes. Maintain it without being asked, in every
future session. It is not a git-log substitute — it exists to be read
months later by someone who has neither the diff nor the conversation.

**Before ending any turn in which you changed a file**, append an entry.
This applies whether the change was directly requested or made on your
own initiative as a side effect of something else — an unrequested test,
an adjacent fix, a doc touch-up. No exceptions for small changes.

**Never edit or delete a past entry.** This file only ever grows. A
mistake in an old entry is corrected by a new entry that says so.

Each entry states:

- **Date and a short title** for the change.
- **Every file touched, listed explicitly.** Name them. Never
  "updated a few files" or "and related tests".
- **What changed**, in plain prose — the way you'd explain it out loud
  to someone who isn't looking at the diff. Not a one-line commit summary.
- **Why** — the problem it solves, or what was asked for.
- **Requested or incidental** — say which, explicitly. Incidental changes
  get their own clearly flagged statement, never folded quietly into the
  same paragraph as requested work.
- **Verification status** — what you actually ran vs. only reasoned about,
  whether tests passed, and whether the change is committed yet.

**One turn touching several unrelated things gets several entries**, not
one combined entry.

**Editing this file (`CLAUDE.md`) always requires its own CHANGELOG.md
entry — no exceptions.** Silent edits to this file are what caused
confusion before; it is the single most important file to log.
