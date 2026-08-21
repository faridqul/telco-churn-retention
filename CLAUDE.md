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
| `feature_engineering_telco.py` | 6 derived features. Imported by the notebook, API, batch script, config, and 2 test files. **The single most load-bearing module.** |
| `config.py` | Paths, threshold loading, 3 startup validators. Shared by both consumers. |
| `api.py` | FastAPI. One customer in, one decision out. Pydantic-validated. |
| `telco_model.py` | Batch scorer. CSV in, CSV out. **No input validation** (see AUDIT.md M1). |
| `xgboost_churn_pipeline.pkl` + `model_metadata.json` | The artifact. Committed on purpose so a clone runs immediately. |
| `tests/` | 48 tests, ~1.7 s. `tests/__init__.py` is empty but **load-bearing** — deleting it breaks all 5 files at collection. |
| `AUDIT.md` | 24 known defects (10 moderate, 14 cosmetic) + roadmap. **Local-only — gitignored, not in the repo.** If present, read it before reporting a bug — it's probably already listed. |

## Notebook cell map

0–1 load + dataset hash · 3–10 cleaning · 11 splits + feature engineering ·
12 ColumnTransformer · 14–21 baselines/imbalance (marked removable) ·
22–25 RandomizedSearchCV (200 iters) · **26 threshold selection via OOF —
the heart** · 27 sensitivity sweep · 28–31 test-set scoring · 33 model
comparison · 36–37 SHAP · 38–40 save artifact.

## Invariants — don't break these

- `engineer_features()` must produce exactly the 25 columns in
  `model_metadata.json["feature_columns"]`. `config.validate_feature_schema()`
  crashes at startup if not.
- `api.py` and `telco_model.py` must make the **same** decision: same model,
  same threshold, same `>=` comparison. Divergence is silent.
- The test set is touched once, after the threshold is locked. Threshold
  selection uses out-of-fold predictions (`cross_val_predict`), never a
  reused validation split.
- Retraining rewrites `model_metadata.json` — including `library_versions`,
  which `config.validate_environment_versions()` checks at every startup.

## Facts worth not re-deriving

- Dataset: 7,043 rows, 26.54% churn, 11 blank `totalcharges` (all `tenure==0`),
  22 duplicates after dropping `customerid`. Cached at
  `~/.cache/kagglehub/datasets/blastchar/telco-customer-churn/versions/1/`
  — lets you reconstruct any split without re-downloading.
- Shipped model scores `config.DUMMY_CUSTOMER` at **0.5699995160102844**.
  Good canary that the artifact still loads and behaves.
- Test metrics reproduce exactly from the committed `.pkl`: ROC-AUC 0.8441,
  P 0.5885, R 0.6882, F1 0.6344, acc 0.7900, TP/FP/FN/TN 256/179/116/854.
- Profit-optimal threshold has a closed form: `cost / (success_rate × clv)`
  = 0.333. The grid found 0.40; the +0.046 gap is model miscalibration.
- Env: uv, Python 3.12, pandas 3.0.5. Run tests with `uv run pytest -q`.

## Conventions

- `optuna`, `lightgbm`, `pyarrow` are declared in `pyproject.toml` and used
  nowhere. Don't assume Optuna is the tuner — it's `RandomizedSearchCV`.
- The profit formula is duplicated in 5 places in the notebook (AUDIT.md C11).
- CI lives in `.github/workflows/tests.yml` — runs `uv run pytest -q` on
  every push and PR.
