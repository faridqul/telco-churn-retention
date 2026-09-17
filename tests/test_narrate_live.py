"""Live tests for narrate.py: these call a real API and cost real money.

Deselected by default. `addopts = "-m 'not live'"` in pyproject.toml means a
plain `uv run pytest -q` never selects them, so a developer who has exported
OPENAI_API_KEY does not pay for an API run on every test invocation, and CI
never touches them. Run them deliberately:

    uv sync --group llm
    uv run --env-file .env pytest tests/test_narrate_live.py -m live -v -s

Expected cost at prompt v2: 10 calls (8 customers + 2 for the determinism
check), plus one per retry, at roughly $0.00015 each -- about $0.0015.

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
    frame = pd.read_csv(narrate.REPO_ROOT / "simulated_new_customers.csv")
    out = []
    for i in range(min(SAMPLE_SIZE, len(frame))):
        explanation = explain.explain_customer(
            frame.iloc[i].to_dict(), model=pipeline, top_n=None
        )
        out.append(narrate.narrate(
            explanation, client=client, tracer=tracer, trace_label=f"row {i}",
        ))
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


def test_accounting_fields_come_back_populated(results):
    for result in results:
        for attempt in result["attempts"]:
            assert attempt["latency_ms"] > 0
            assert attempt["prompt_tokens"] and attempt["prompt_tokens"] > 0
            assert attempt["completion_tokens"] and attempt["completion_tokens"] > 0


def test_temperature_zero_gives_the_same_text_twice(client, pipeline, tracer):
    """Determinism is what makes caching sound and what lets step four
    measure the prompt rather than sampling noise. Not guaranteed by the
    API, so this is a check rather than an assumption -- if it starts
    failing, the caching plan needs revisiting, not this test deleting."""
    from config import DUMMY_CUSTOMER

    explanation = explain.explain_customer(DUMMY_CUSTOMER, model=pipeline, top_n=None)
    first = narrate.narrate(explanation, client=client, tracer=tracer,
                            trace_label="DUMMY_CUSTOMER, determinism 1")
    second = narrate.narrate(explanation, client=client, tracer=tracer,
                             trace_label="DUMMY_CUSTOMER, determinism 2")
    assert first["narrative"] == second["narrative"]


def test_print_the_outputs_and_the_rates(results):
    """Not an assertion -- a report. Run with -s to see it. Each output is
    printed next to the factors the model was shown, because the guards
    cannot catch everything and every live run gets read by a human against
    its payload."""
    for i, result in enumerate(results):
        print(f"\n--- customer row {i}: {result['payload']['risk_level']}, "
              f"{result['payload']['decision']}")
        for factor in result["payload"]["factors"]:
            print(f"    shown: {factor}")
        for attempt in result["attempts"]:
            verdict = "accepted" if attempt["accepted"] else attempt["rejection_type"]
            print(f"    attempt {attempt['attempt']} ({verdict}, "
                  f"{attempt['prompt_tokens']} in / {attempt['completion_tokens']} out): "
                  f"{attempt['text']}")
    print("\n" + "\n".join(narrate.render_rates(narrate.rejection_rates(results))))
