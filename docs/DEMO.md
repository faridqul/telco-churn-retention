# Running the project — a demo runbook

Every command needed to show this project working, in the order you would
show it. Copy-paste from a clean clone.

Each command below was run on 2026-10-06 and its output checked, except the
ones marked **costs money** (a real API call) and the two marked **slow**.
Section 5c was added and run on 2026-10-09.

Three things to know before you start:

- **`uv sync` replaces the environment, it does not add to it.** Asking for
  one dependency group removes the others. See [Setup](#0-setup-once).
- **Nothing here retrains the model.** The trained model is committed, so a
  clone works immediately. Re-running `telco_customer_churn.ipynb` would
  overwrite it — don't do that during a demo.
- **Only the LLM narration costs money.** Everything else is free and offline.

---

## 0. Setup (once)

```bash
uv sync                                     # 32 packages: serving, scoring, tests
uv sync --group llm --group notebook        # + the LLM layer and Jupyter
```

Pick the second line if you want the whole demo, including the explanation
layer and the notebooks. **Name every group you want in one command** —
`uv sync --group llm` on its own removes Jupyter, and `uv sync --group
notebook` on its own removes the OpenAI client.

Check what you have: `uv pip list | wc -l`.

The LLM parts also need an API key in `.env` at the repo root:

```
OPENAI_API_KEY=sk-...
```

It is never read from a file by the code — each command loads it explicitly
with `uv run --env-file .env`.

---

## 1. The API (the main demo)

```bash
uv run uvicorn api:app --port 8000
```

Then, in another terminal:

```bash
curl -s http://127.0.0.1:8000/health
```
```json
{"status":"ok","model_loaded":true,"explain_available":true,"narration_available":false}
```

`explain_available` and `narration_available` describe `/explain`
([section 5c](#5c-the-explanation-over-http--explain)). Started this way, with
no API key, the second is `false`: reasons are served, written summaries are
not.

```bash
curl -s -X POST http://127.0.0.1:8000/predict \
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
{"churn_probability":0.7443000078201294,"target_for_retention":true,"threshold_used":0.4}
```

That exact number is pinned by the test suite and by the CI container smoke
test, so it is the same on any machine.

**Interactive docs:** <http://127.0.0.1:8000/docs> — good for a live demo,
since you can edit a customer and re-send without leaving the browser.

**Worth showing: a rejected input.** Change `"contract"` to `"Three year"`
and the API answers `422` before the model is touched. The point: an unknown
category would otherwise score silently and wrongly (0.5700 becomes 0.1017 on
the sample customer), so the categories are validated, not trusted.

---

## 2. The browser page

`frontend/index.html` is a single static page that calls `/predict`. Serve it
from its own port — **not 8000, which the API is using**:

```bash
python3 -m http.server 5500 --directory frontend
```

Open <http://localhost:5500>. The "API base URL" field at the top defaults to
`http://localhost:8000`, which is where step 1 is listening. The API allows
any origin, so the page works from any port.

The page has a card reading "AI explanation — coming soon". The `/explain`
endpoint behind it exists ([section 5c](#5c-the-explanation-over-http--explain));
the card is not wired to it yet.

---

## 3. Batch scoring

```bash
uv run python telco_model.py
```
```
Loading model...
...
Success! 15 of 50 customers flagged for retention.
```

Reads `simulated_new_customers.csv`, writes
`retention_campaign_targets.csv`. Override with the `INPUT_PATH` and
`OUTPUT_PATH` environment variables.

The point to make out loud: this path and the API make the **same** decision —
same model, same threshold, same comparison. A test pins that.

---

## 4. Why a customer was flagged (free, no API key)

```bash
uv run python explain.py --dummy
```

Prints the probability, the decision, and the five features that moved it
most, with their contributions and the baseline they are measured from. The
contributions are reconstructed exactly: the report shows the reconstruction
error against its tolerance.

Other forms:

```bash
uv run python explain.py --csv simulated_new_customers.csv --row 7
uv run python explain.py --csv simulated_new_customers.csv --all --top 3
```

---

## 5. The same thing in English — **costs money**

Each customer is one API call to `gpt-4o-mini`, about **$0.0002**. Keep an eye
on the project's budget note before running these.

```bash
uv run --env-file .env python narrate.py --dummy
```

The full report: the drivers from step 4, then a checked summary written by
the language model, then which prompt version and how many attempts it took.

Shorter forms for a demo:

```bash
uv run --env-file .env python narrate.py --dummy --style short
uv run --env-file .env python narrate.py --dummy --style bullets
```

`bullets` is worth showing: every word of it comes from the model's own data,
not from the language model — the model only chose which factors to name.

A whole batch, saved for later reading (**50 customers, about $0.009**):

```bash
uv run --env-file .env python narrate.py --csv simulated_new_customers.csv \
  --all --quiet --rates --save outputs/stage2_v3.json
```

`--save` refuses to overwrite an existing file, and refuses before making any
call, so a repeat run cannot destroy a batch you already paid for.

---

## 5b. The cache (why the second run is free)

`narrate.py` caches accepted explanations in `data/narration.sqlite3`, keyed by
exactly what was sent to the model. Run the same customer twice and the second
answer is instant and costs nothing:

```bash
uv run --env-file .env python narrate.py --dummy --style short     # one call
uv run --env-file .env python narrate.py --dummy --style short     # free
```

The second run prints `1 of 1 served from cache`.

Entries live a week while a prompt is the one you are using. Two things cut
that short: anything stored in a prompt's **first day** lives only a day (that
is when you are still judging it), and when you **switch prompt or model** the
one you left keeps its entries for 24 more hours, so a quick rollback is still
free. `--stats` shows which is which, and `--ttl` overrides the lot.

Fill it from runs you have already paid for, with no API calls at all:

```bash
uv run python narration_cache.py --import-all
uv run python narration_cache.py --stats
```

**Measuring a prompt? Pass `--no-cache`.** A rejection rate computed over
cached answers is not a measurement of the model.

## 5c. The explanation over HTTP — `/explain`

`/explain` takes exactly the body `/predict` takes and returns `/predict`'s
three fields plus the reasons. Start the API as in step 1 — no key needed for
this first part — and send the same customer to the other path:

```bash
curl -s -X POST http://127.0.0.1:8000/explain \
  -H "Content-Type: application/json" \
  -d '{
    "gender": "Female", "seniorcitizen": 0, "partner": "Yes", "dependents": "No",
    "tenure": 3, "phoneservice": "Yes", "multiplelines": "No",
    "internetservice": "Fiber optic", "onlinesecurity": "No", "onlinebackup": "No",
    "deviceprotection": "No", "techsupport": "No", "streamingtv": "Yes",
    "streamingmovies": "Yes", "contract": "Month-to-month", "paperlessbilling": "Yes",
    "paymentmethod": "Electronic check", "monthlycharges": 85.5, "totalcharges": 256.5
  }' | python3 -m json.tool
```

Trimmed to one driver, the answer is:

```json
{
    "churn_probability": 0.7443000078201294,
    "target_for_retention": true,
    "threshold_used": 0.4,
    "risk_level": "very high",
    "drivers": [
        {
            "field": "tenure",
            "label": "months as a customer",
            "value": 3,
            "vs_other_customers": "much lower than most customers",
            "direction": "raises risk",
            "contribution": 0.22714783251285553
        }
    ],
    "explanation": null,
    "meta": {
        "status": "unavailable",
        "detail": "OPENAI_API_KEY is not set. Export it; it is never read from a file in the repo and never has a default.",
        "rejection_type": null,
        "prompt_version": "explanation_v5",
        "model": "gpt-4o-mini",
        "cache_hit": false,
        "attempts": 0,
        "protected_drivers_omitted": []
    }
}
```

Three things to say out loud:

- **The first three fields are `/predict`'s**, the same number to the last
  digit. The two endpoints cannot disagree about a customer.
- **`drivers` is the model's own arithmetic**, five strongest first. It needed
  no key, no network and about 50 ms.
- **`explanation` is `null` and that is a 200, not an error.** `meta.status`
  says why: `unavailable` here, because no key reached the process.

Now the written summary — **costs money**, about $0.0002 for each customer not
seen before. Stop the API and restart it with the key:

```bash
uv run --env-file .env uvicorn api:app --port 8000
```

The startup log now says `/explain is on.` and `/health` reports
`"narration_available":true`. Send the same `curl` twice. The first takes
about two seconds and returns `"status": "ok"` with an `explanation` holding
`risk_level`, `reasons` and `summary`; the second is instant and reports
`"cache_hit": true`. It is the same cache as step 5b, so anything `narrate.py`
already paid for is free here, and the other way round.

The four values of `meta.status`:

| `status` | `explanation` | what happened |
|---|---|---|
| `ok` | present | written, and passed every check |
| `rejected` | `null` | the model answered and every attempt was refused; `rejection_type` names the check |
| `unavailable` | `null` | no call could be made — no key, or `uv sync --group llm` was not run |
| `error` | `null` | the call was made and failed (network, rate limit) |

A started API with no key still serves any summary already in the cache, so
"leave the key out" doubles as a mode that cannot spend anything.

The Docker image does not contain the explanation layer: there `/explain`
answers 503 and `/health` reports `"explain_available":false`. `/predict` is
unaffected.

## 6. Reading saved LLM runs (free, no API calls)

```bash
uv run --group notebook --group llm jupyter lab LLMcalls.ipynb
```

Reads whatever is in `outputs/*.json` — newest by default. Shows cost and
token totals, the exact prompt used, one card per customer with the input
beside the answer, every summary in one table, charts, and a comparison of all
saved runs.

It never calls the API, so re-run it as often as you like.

---

## 7. Tests

```bash
uv run pytest -q
```
```
599 passed, 1 skipped, 10 deselected
```

The 10 deselected are the live tests that cost money. They are excluded by
default and only run deliberately:

```bash
# costs money: ~15 calls, ~$0.0025
uv run --env-file .env pytest tests/test_narrate_live.py -m live -v -s
```

---

## 8. Docker — one image, both entrypoints

**slow:** about two minutes the first time.

```bash
docker build -t telco-churn .
```

The build verifies itself twice as the unprivileged user: library versions
must match the ones the model was trained with, and the sample customer must
still score the exact value recorded in the model's metadata.

```bash
# The API
docker run -p 8000:8000 telco-churn

# Batch scoring, against the sample CSV baked into the image
docker run telco-churn python telco_model.py

# Batch scoring, against your own CSV in ./data
mkdir -p data && cp simulated_new_customers.csv data/
docker run -v "$PWD/data:/data" telco-churn python telco_model.py
```

Mounting a directory at `/data` hides the sample file inside the image, so the
mounted directory must contain the input. `/data` is also the only place the
container can write.

Health, while the API container runs:

```bash
docker ps        # STATUS shows "healthy" after ~20s
```

The health check asserts the model actually loaded, not merely that the
service answers.

---

## 9. Extras worth a mention

```bash
uv run python check_model_environment.py       # the version gate CI runs
uv run python fairness_analysis.py             # error rates by group
```

The fairness report compares selection and error rates across gender, senior
citizen, partner and dependents, at the shipped threshold. A committed copy
is at `docs/fairness_report.txt`, so you can show the numbers without
re-running it.

---

## 10. If something goes wrong

**"Address already in use" on 8000.** Something else is on that port — often a
`python -m http.server` left running. Either stop it, or start the API on
another port and change the API URL field on the web page to match.

**`ImportError` / no kernel in a notebook.** The environment was re-synced
without the `notebook` group. Fix with
`uv sync --group llm --group notebook`, then restart the kernel and make sure
it points at `.venv`.

**A matplotlib "backend is not a valid value" error.** Same cause: the
notebook stack is missing, and the editor's inline backend cannot be
imported. Same fix.

**`RuntimeError` about `OPENAI_API_KEY`.** Either `.env` has no key, or the
command was run without `--env-file .env`.

**The openai package is not installed.** Run
`uv sync --group llm --group notebook`; it is deliberately absent from the
default install, so that serving a prediction can never depend on a
third-party network call.

**On Windows, use Docker.** The committed model cannot be loaded by native
Windows Python — the file arrives intact and the library refuses it. The
container is Linux, so everything above works there.

**Type-checker warnings in the editor.** `pyright` reports around 150
findings on a fully passing tree; almost all are type-stub artefacts. Nothing
in CI or the build runs it.
