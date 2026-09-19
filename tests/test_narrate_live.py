"""Live tests for narrate.py: these call a real API and cost real money.

Deselected by default. `addopts = "-m 'not live'"` in pyproject.toml means a
plain `uv run pytest -q` never selects them, so a developer who has exported
OPENAI_API_KEY does not pay for an API run on every test invocation, and CI
never touches them. Run them deliberately:

    uv sync --group llm
    uv run --env-file .env pytest tests/test_narrate_live.py -m live -v -s

Expected cost at prompt v3: 15 calls (8 sampled rows + 5 edge cases + 2 for
the determinism check), plus one per retry, at roughly $0.00016 each -- about
$0.0025. Past 20 calls needs explicit go-ahead under the project's budget
rules, so don't grow EDGE_CASES without re-costing.

If LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are in .env, every call is also
traced to Langfuse under one session per run (llm_tracing.py). Tracing adds no
model calls.

Set NARRATE_RESULTS=outputs/<name>.json to save every result, payloads and
attempts included, so the run can be reviewed again without paying for it.

WHAT THESE CAN AND CANNOT CHECK
They cannot assert what the model wrote -- that is the point of the guards,
which tests/test_narrate.py covers exhaustively with a fake. What they check
is that the real thing is wired up: that a real response passes the real
guards often enough to be useful, that temperature=0 actually produces stable
text, and that the accounting fields come back populated rather than None.

The rejection-rate assertion is deliberately loose. A tight bound here would
be a flaky test that fails on a model update, and the number that matters is
recorded in CHANGELOG.md from a full 50-customer run rather than asserted on
a sample of eight.
"""

import json
import os

import pandas as pd
import pytest

import explain
import llm_tracing
import narrate

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY is not set",
    ),
]

SAMPLE_SIZE = 8

# Hand-built customers that aim at the traps the guards were written for, run
# after the 8 sampled rows (which stay the same across prompt versions, so runs
# remain comparable). Each is DUMMY_CUSTOMER with overrides; the comment says
# what its payload contains, as computed offline on 2026-09-17. No sampled or
# hand-built customer has a protected driver in its top three -- that path is
# covered offline only.
EDGE_CASES = {
    # tenure 0, blank total: commitment "lower" (not much), tenure "much lower".
    # Where v3 overstated a degree (not guarded; read the output).
    "edge: brand new, blank total": dict(tenure=0, totalcharges=None, monthlycharges=20.0),
    # A low-risk customer with a factor that RAISES risk (fiber), and a
    # commitment only "higher". Tests mixed directions.
    "edge: typical values, one year": dict(
        internetservice="Fiber optic", monthlycharges=70.0, totalcharges=2000.0,
        tenure=29, contract="One year", paperlessbilling="Yes",
        paymentmethod="Bank transfer (automatic)"),
    # internetservice value "No": "no internet" must still read as the field.
    "edge: no internet, long tenure": dict(tenure=50, monthlycharges=20.0, totalcharges=1000.0),
    # A numeric value (110.0) the summary may quote, "much higher".
    "edge: high bill, fiber": dict(
        tenure=12, internetservice="Fiber optic", monthlycharges=110.0,
        totalcharges=800.0, streamingtv="Yes", streamingmovies="Yes"),
    # Partner and dependents set: protected fields present in the row, must
    # not surface in the text.
    "edge: family, short tenure": dict(
        partner="Yes", dependents="Yes", tenure=5, internetservice="DSL",
        monthlycharges=50.0, totalcharges=250.0),
}


@pytest.fixture(scope="module")
def client():
    return narrate.OpenAIClient()


@pytest.fixture(scope="module")
def pipeline():
    return explain.load_model()


@pytest.fixture(scope="module")
def tracer():
    """Langfuse when its keys are set, otherwise a tracer that does nothing.
    Flushed at the end, or a short test run can exit before traces are sent."""
    tracer = llm_tracing.from_env(
        session_id=llm_tracing.session_id(f"live-{narrate.PROMPT_VERSION}")
    )
    yield tracer
    tracer.flush()


@pytest.fixture(scope="module")
def results(client, pipeline, tracer):
    """One narration per sampled customer. Module-scoped so the whole file
    costs one batch of calls rather than one per test."""
    from config import DUMMY_CUSTOMER

    frame = pd.read_csv(narrate.REPO_ROOT / "simulated_new_customers.csv")
    customers = [(f"row {i}", frame.iloc[i].to_dict())
                 for i in range(min(SAMPLE_SIZE, len(frame)))]
    customers += [(name, {**DUMMY_CUSTOMER, **overrides})
                  for name, overrides in EDGE_CASES.items()]
    out = []
    for label, customer in customers:
        explanation = explain.explain_customer(customer, model=pipeline, top_n=None)
        result = narrate.narrate(
            explanation, client=client, tracer=tracer, trace_label=label,
        )
        # Not part of narrate()'s result: which customer this was, so a saved
        # run (and LLMcalls.ipynb) can name the edge cases.
        result["case"] = label
        out.append(result)
    if os.environ.get("NARRATE_RESULTS"):
        with open(os.environ["NARRATE_RESULTS"], "w") as handle:
            json.dump(out, handle, indent=2)
    return out


def test_most_customers_get_a_narrative(results):
    """Loose on purpose. The measured rate belongs in CHANGELOG.md from a
    full run; this only catches a layer that is broken outright."""
    narrated = [r for r in results if r["narrative_available"]]
    assert len(narrated) >= len(results) * 0.5, (
        f"only {len(narrated)}/{len(results)} narrated: "
        f"{narrate.rejection_rates(results)}"
    )


def test_accepted_narratives_pass_the_guards_again(results):
    """Re-validating an accepted narrative must accept it. Catches a guard
    whose verdict depends on state rather than on the text."""
    for result in results:
        if not result["narrative_available"]:
            continue
        payload = narrate.narration_payload(result)
        # The raw JSON reply, not result["narrative"]: since prompt v2 the
        # narrative is only the summary field, which isn't valid input to the
        # guards on its own. Checking it failed every accepted result.
        accepted_text = result["attempts"][-1]["text"]
        assert narrate.validate_narrative(accepted_text, payload)[1] is None


def test_every_accepted_output_repeats_the_payloads_risk_level(results):
    for result in results:
        if result["narrative_available"]:
            assert result["structured"]["risk_level"] == result["payload"]["risk_level"]


def test_no_reply_was_cut_off_by_the_token_cap(results):
    """A "length" finish means MAX_OUTPUT_TOKENS is too tight for real
    replies, which would show up as malformed_output and blame the prompt."""
    for result in results:
        for attempt in result["attempts"]:
            assert attempt["finish_reason"] == "stop", attempt


def test_no_accepted_narrative_mentions_a_protected_attribute(results):
    """The guarantee that matters most, checked against real output rather
    than a scripted fake."""
    for result in results:
        if not result["narrative_available"]:
            continue
        mentioned = narrate.fields_mentioned(result["narrative"])
        assert not mentioned & narrate.PROTECTED_FIELDS, result["narrative"]


def test_accepted_summaries_keep_to_sixty_words(results):
    """The prompt asks for 60; MAX_SUMMARY_CHARS is only a backstop at 400
    characters. A few words over is a prompt-quality finding to record, so
    this allows a margin and fails only on a limit plainly ignored."""
    for result in results:
        if result["narrative_available"]:
            assert len(result["narrative"].split()) <= 65, result["narrative"]


def test_accepted_reasons_are_all_named_in_the_summary(results):
    """The prompt asks the summary to name the same factors as reasons, so
    the bullets view and the short view agree. Reported, not asserted: the
    alias map can miss a fair paraphrase, and a miss here is a reading aid."""
    for result in results:
        if not result["narrative_available"]:
            continue
        named = narrate.fields_mentioned(result["narrative"])
        missing = [r["field"] for r in result["structured"]["reasons"]
                   if r["field"] not in named]
        if missing:
            print(f"\n  {result['case']}: reasons not found in summary: {missing}")


def test_accounting_fields_come_back_populated(results):
    for result in results:
        for attempt in result["attempts"]:
            assert attempt["latency_ms"] > 0
            assert attempt["prompt_tokens"] and attempt["prompt_tokens"] > 0
            assert attempt["completion_tokens"] and attempt["completion_tokens"] > 0


def test_the_same_request_gives_the_same_structured_answer(client, pipeline, tracer):
    """Determinism is what makes caching sound and what lets step four
    measure the prompt rather than sampling noise.

    Asserted on the structured part only. v3's live run got two different
    summaries for DUMMY_CUSTOMER at temperature 0, so requests now carry
    a seed -- which OpenAI documents as best effort. The risk level and the
    reasons are what a decision would be cached on; the wording is printed,
    with each attempt's system_fingerprint, so a difference can be told apart
    from a backend change. If the structured part starts differing, the
    caching plan needs revisiting, not this test deleting."""
    from config import DUMMY_CUSTOMER

    explanation = explain.explain_customer(DUMMY_CUSTOMER, model=pipeline, top_n=None)
    first = narrate.narrate(explanation, client=client, tracer=tracer,
                            trace_label="DUMMY_CUSTOMER, determinism 1")
    second = narrate.narrate(explanation, client=client, tracer=tracer,
                             trace_label="DUMMY_CUSTOMER, determinism 2")
    assert first["narrative_available"] and second["narrative_available"]
    assert first["structured"]["risk_level"] == second["structured"]["risk_level"]
    assert first["structured"]["reasons"] == second["structured"]["reasons"]
    same = first["narrative"] == second["narrative"]
    print(f"\n  determinism: summary text identical: {same}")
    for label, result in (("first", first), ("second", second)):
        attempt = result["attempts"][-1]
        print(f"    {label} ({attempt['system_fingerprint']}): {result['narrative']}")


def test_print_the_outputs_and_the_rates(results):
    """Not an assertion -- a report. Run with -s to see it. Each output is
    printed next to the factors the model was shown, because the guards
    cannot catch everything and every live run gets read by a human against
    its payload."""
    for i, result in enumerate(results):
        print(f"\n--- {result['case']}: {result['payload']['risk_level']}, "
              f"{result['payload']['decision']}")
        for factor in result["payload"]["factors"]:
            print(f"    shown: {factor}")
        for attempt in result["attempts"]:
            verdict = "accepted" if attempt["accepted"] else attempt["rejection_type"]
            print(f"    attempt {attempt['attempt']} ({verdict}, "
                  f"{attempt['prompt_tokens']} in / {attempt['completion_tokens']} out): "
                  f"{attempt['text']}")
        print("    as bullets:")
        for line in narrate.format_explanation(result, "bullets").splitlines():
            print(f"      {line}")
    print("\n" + "\n".join(narrate.render_rates(narrate.rejection_rates(results))))
