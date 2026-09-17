"""Tests for llm_tracing.py. No network, no Langfuse account, no cost.

Two kinds of stand-in:

  * The REAL Langfuse SDK, pointed at an in-memory span exporter instead of
    the cloud, with score uploads captured instead of sent. This checks that
    the calls llm_tracing.py makes match the installed SDK's actual API --
    names, arguments, parent/child structure, session and tags -- which a
    hand-written fake could only assume. Skipped when `langfuse` isn't
    installed (plain `uv sync`, and CI).

  * A deliberately broken client whose every method raises. That checks the
    rule that matters most: tracing can never change or break a narration.

Run with: pytest tests/test_llm_tracing.py -v
"""

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

import llm_tracing
import narrate
from tests.conftest import FakeLLM
from tests.test_narrate import BAD_PROTECTED, GOOD, make_explanation

needs_sdk = pytest.mark.skipif(
    importlib.util.find_spec("langfuse") is None,
    reason="langfuse is not installed (uv sync --group llm)",
)


# ==========================================================================
# Fixtures: the real SDK, offline
# ==========================================================================

@pytest.fixture(scope="module")
def sdk():
    """One Langfuse client for the module: the SDK holds global OpenTelemetry
    state, so building a fresh client per test would leak spans between
    them. Unroutable base URL, in-memory exporter, scores intercepted."""
    if importlib.util.find_spec("langfuse") is None:
        pytest.skip("langfuse is not installed")
    from langfuse import Langfuse, propagate_attributes
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key="pk-lf-offline-test", secret_key="sk-lf-offline-test",
        base_url="http://127.0.0.1:9", span_exporter=exporter, timeout=1,
    )
    scores = []
    client.create_score = lambda **kwargs: scores.append(kwargs)
    return client, propagate_attributes, exporter, scores


@pytest.fixture
def traced(sdk):
    """A tracer on the offline SDK plus accessors for what it recorded."""
    client, propagate, exporter, scores = sdk
    exporter.clear()
    scores.clear()
    tracer = llm_tracing.LangfuseTracer(client, propagate, session_id="test-session")

    def spans():
        tracer.flush()
        return {s.name: s for s in exporter.get_finished_spans()}

    return tracer, spans, scores


def _attrs(span):
    return dict(span.attributes)


# ==========================================================================
# 1. Off unless asked
# ==========================================================================

def test_from_env_without_keys_is_a_noop_that_says_why(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracer = llm_tracing.from_env()
    assert tracer.enabled is False
    assert "LANGFUSE_PUBLIC_KEY" in tracer.reason


def test_from_env_with_keys_but_no_sdk_warns_and_does_not_trace(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setitem(sys.modules, "langfuse", None)  # makes the import fail
    with pytest.warns(RuntimeWarning, match="not installed"):
        tracer = llm_tracing.from_env()
    assert tracer.enabled is False


def test_narrate_traces_nothing_unless_handed_a_tracer(explanation_pair):
    """The default is the no-op tracer, so the offline suite never sends
    anything even when keys are exported in the shell."""
    untraced, noop = explanation_pair
    assert untraced["narrative"] == noop["narrative"]


@pytest.fixture
def explanation_pair():
    plain = narrate.narrate(make_explanation(), client=FakeLLM([GOOD]))
    noop = narrate.narrate(make_explanation(), client=FakeLLM([GOOD]),
                           tracer=llm_tracing.NoopTracer())
    return plain, noop


def test_neither_module_imports_the_sdk_at_module_scope():
    for module in (llm_tracing, narrate):
        tree = ast.parse(Path(module.__file__).read_text())
        top = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top.add(node.module.split(".")[0])
        assert "langfuse" not in top, module.__name__


def test_cli_without_keys_exits_2_and_sends_nothing(monkeypatch, capsys):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert llm_tracing.main(["--check"]) == 2
    assert "tracing is off" in capsys.readouterr().err


# ==========================================================================
# 2. Tracing can never change or break a narration
# ==========================================================================

class _Explodes:
    """Every attribute is a function that raises."""

    def __getattr__(self, name):
        def boom(*_, **__):
            raise ConnectionError(f"langfuse is down ({name})")
        return boom


def _comparable(result):
    return {k: v for k, v in result.items() if k != "attempts"} | {
        "attempts": [{k: v for k, v in a.items() if k != "latency_ms"} for a in result["attempts"]]
    }


def test_a_broken_tracer_only_warns_and_the_result_is_unchanged():
    broken = llm_tracing.LangfuseTracer(_Explodes(), _Explodes().propagate, session_id="x")
    expected = narrate.narrate(make_explanation(), client=FakeLLM([BAD_PROTECTED, GOOD]))
    with pytest.warns(RuntimeWarning, match="narration is unaffected"):
        actual = narrate.narrate(make_explanation(), client=FakeLLM([BAD_PROTECTED, GOOD]),
                                 tracer=broken, trace_label="row 0")
    assert _comparable(actual) == _comparable(expected)


class _BrokenObservation(_Explodes):
    """Starts and ends fine; every update and score raises."""

    def start_observation(self, **_):
        return _BrokenObservation()

    def end(self, **_):
        pass


class _HalfBrokenClient:
    """Traces open normally, but everything recorded into them fails -- the
    case a broken trace start can't reach, because then nothing is recorded."""

    def start_as_current_observation(self, **_):
        from contextlib import nullcontext
        return nullcontext(_BrokenObservation())

    def flush(self):
        pass


def test_failures_inside_an_open_trace_only_warn_and_the_result_is_unchanged():
    from contextlib import nullcontext
    half = llm_tracing.LangfuseTracer(_HalfBrokenClient(), lambda **_: nullcontext())
    expected = narrate.narrate(make_explanation(), client=FakeLLM([BAD_PROTECTED, GOOD]))
    with pytest.warns(RuntimeWarning) as caught:
        actual = narrate.narrate(make_explanation(), client=FakeLLM([BAD_PROTECTED, GOOD]),
                                 tracer=half)
    assert _comparable(actual) == _comparable(expected)
    messages = " ".join(str(w.message) for w in caught)
    assert "update an attempt" in messages and "score guard_verdict" in messages


def test_a_model_error_still_propagates_through_a_broken_tracer():
    broken = llm_tracing.LangfuseTracer(_Explodes(), _Explodes().propagate)
    with pytest.warns(RuntimeWarning), pytest.raises(RuntimeError, match="rate limited"):
        narrate.narrate(make_explanation(), client=FakeLLM([RuntimeError("rate limited")]),
                        tracer=broken)


# ==========================================================================
# 3. What reaches Langfuse (real SDK, offline)
# ==========================================================================

@needs_sdk
def test_one_trace_with_a_generation_per_attempt(traced):
    tracer, spans, _ = traced
    narrate.narrate(make_explanation(), client=FakeLLM([BAD_PROTECTED, GOOD]),
                    tracer=tracer, trace_label="row 0")
    recorded = spans()
    assert set(recorded) == {"narrate", "attempt 1", "attempt 2"}
    root = recorded["narrate"]
    for name in ("attempt 1", "attempt 2"):
        assert recorded[name].parent.span_id == root.context.span_id
        assert _attrs(recorded[name])["langfuse.observation.type"] == "generation"


@needs_sdk
def test_the_trace_carries_session_tags_and_labels(traced):
    tracer, spans, _ = traced
    narrate.narrate(make_explanation(), client=FakeLLM([GOOD]), tracer=tracer, trace_label="row 3")
    attrs = _attrs(spans()["narrate"])
    assert attrs["session.id"] == "test-session"
    assert tuple(attrs["langfuse.trace.tags"]) == ("explanation_v3", "gpt-4o-mini")
    assert attrs["langfuse.trace.metadata.customer"] == "row 3"
    assert attrs["langfuse.trace.metadata.risk_level"] == "high"


@needs_sdk
def test_the_trace_input_is_exactly_what_the_model_was_sent(traced):
    """Rule 3: nothing leaves the machine that the model didn't already get.
    No probability, no protected field, no raw row."""
    tracer, spans, _ = traced
    explanation = make_explanation()
    narrate.narrate(explanation, client=FakeLLM([GOOD]), tracer=tracer)
    root_input = _attrs(spans()["narrate"])["langfuse.observation.input"]
    sent = narrate.build_messages(narrate.narration_payload(explanation))[1]["content"]
    assert json.loads(root_input) == json.loads(sent)
    for forbidden in ("seniorcitizen", "churn_probability", "0.57"):
        assert forbidden not in root_input


@needs_sdk
def test_a_generation_records_the_reply_usage_and_a_rejection_as_a_warning(traced):
    tracer, spans, _ = traced
    narrate.narrate(make_explanation(), client=FakeLLM([BAD_PROTECTED, GOOD]), tracer=tracer)
    recorded = spans()
    first, second = _attrs(recorded["attempt 1"]), _attrs(recorded["attempt 2"])
    assert first["langfuse.observation.output"] == BAD_PROTECTED
    assert json.loads(first["langfuse.observation.usage_details"]) == {"input": 100, "output": 30}
    assert first["langfuse.observation.model.name"] == "gpt-4o-mini"
    assert first["langfuse.observation.level"] == "WARNING"
    assert "langfuse.observation.level" not in second
    # The retry's input includes the rejected reply and the correction.
    retry_messages = json.loads(second["langfuse.observation.input"])
    assert retry_messages[-2] == {"role": "assistant", "content": BAD_PROTECTED}


@needs_sdk
def test_scores_record_each_verdict_and_the_outcome(traced):
    tracer, _, scores = traced
    narrate.narrate(make_explanation(), client=FakeLLM([BAD_PROTECTED, GOOD]), tracer=tracer)
    by_name = {}
    for score in scores:
        by_name.setdefault(score["name"], []).append((score["value"], score["data_type"]))
    assert by_name["guard_verdict"] == [
        ("protected_attribute", "CATEGORICAL"), ("accepted", "CATEGORICAL"),
    ]
    assert by_name["first_attempt_accepted"] == [(0, "BOOLEAN")]
    assert by_name["final_accepted"] == [(1, "BOOLEAN")]
    assert by_name["first_attempt_verdict"] == [("protected_attribute", "CATEGORICAL")]
    assert by_name["attempts"] == [(2, "NUMERIC")]


@needs_sdk
def test_a_failed_model_call_is_recorded_as_an_error_and_still_raises(traced):
    tracer, spans, _ = traced
    with pytest.raises(RuntimeError, match="rate limited"):
        narrate.narrate(make_explanation(), client=FakeLLM([RuntimeError("rate limited")]),
                        tracer=tracer)
    attrs = _attrs(spans()["attempt 1"])
    assert attrs["langfuse.observation.level"] == "ERROR"
    assert "rate limited" in attrs["langfuse.observation.status_message"]


# ==========================================================================
# 4. Backfill
# ==========================================================================

@needs_sdk
def test_backfill_rebuilds_the_traces_without_calling_a_model(traced):
    tracer, spans, scores = traced
    saved = json.loads(json.dumps(narrate.narrate(
        make_explanation(), client=FakeLLM([BAD_PROTECTED, GOOD]))))
    saved["attempts"][0]["latency_ms"] = 1500.0

    assert llm_tracing.backfill([saved], tracer, source="unit.json") == 1
    recorded = spans()
    assert set(recorded) == {"narrate", "attempt 1", "attempt 2"}
    root = _attrs(recorded["narrate"])
    assert "backfilled" in root["langfuse.trace.tags"]
    assert root["langfuse.trace.metadata.source"] == "unit.json"

    first = recorded["attempt 1"]
    duration_ms = (first.end_time - first.start_time) / 1_000_000
    assert duration_ms == pytest.approx(1500.0, abs=1.0)

    retry = json.loads(_attrs(recorded["attempt 2"])["langfuse.observation.input"])
    live = narrate.narrate(make_explanation(), client=(fake := FakeLLM([BAD_PROTECTED, GOOD])))
    assert retry == fake.calls[1]["messages"], "backfilled retry messages differ from the real ones"
    assert live["narrative_available"]
    assert {s["name"] for s in scores} >= {"guard_verdict", "final_accepted"}


@needs_sdk
def test_backfill_sends_each_prompt_versions_own_input(traced):
    """v2 was still sent the decision; v3 isn't. A backfilled v2 trace built
    with today's keys would show an input the model never received -- the
    first real backfill did exactly that."""
    tracer, spans, _ = traced
    saved = json.loads(json.dumps(narrate.narrate(make_explanation(), client=FakeLLM([GOOD]))))
    saved["prompt_version"] = "explanation_v2"
    llm_tracing.backfill([saved], tracer, source="v2.json")
    recorded = spans()
    root_input = json.loads(_attrs(recorded["narrate"])["langfuse.observation.input"])
    assert root_input["decision"] == "target for retention"
    user_turn = json.loads(json.loads(_attrs(recorded["attempt 1"])["langfuse.observation.input"])[1]["content"])
    assert user_turn == root_input


def test_an_unknown_prompt_version_cannot_be_replayed():
    with pytest.raises(ValueError, match="explanation_v1"):
        narrate.sent_payload({"risk_level": "high"}, "explanation_v1")
