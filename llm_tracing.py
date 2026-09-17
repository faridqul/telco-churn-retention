"""Optional Langfuse tracing for the narration layer.

Run:  uv run --env-file .env python llm_tracing.py --check
      uv run --env-file .env python llm_tracing.py --backfill outputs/stage1_v3.json

Needs:  uv sync --group llm
        LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL in .env

WHAT GETS RECORDED
One narrate() call becomes one trace:

    trace "narrate"            input: exactly what the model was sent
    │                          output: the accepted JSON, or why there is none
    │                          scores: first_attempt_accepted, final_accepted,
    │                                  first_attempt_verdict, attempts
    ├─ generation "attempt 1"  messages, reply, tokens, latency, finish reason
    │                          score: guard_verdict (accepted or rejection type)
    └─ generation "attempt 2"  only when the first was rejected

Tagged with the prompt version and model, grouped by a session id (one per
CLI run, live-test run or backfilled file), so the Langfuse UI can filter "every
misstated_factor on explanation_v3" and total the cost of a run.

THREE RULES THIS MODULE KEEPS

  1. OFF UNLESS ASKED. narrate() traces only when handed a tracer, and
     from_env() returns a do-nothing tracer unless both Langfuse keys are set.
     The offline test suite never sends anything, even with keys exported.

  2. TRACING CAN NEVER CHANGE OR BREAK A NARRATION. Every call into the SDK is
     wrapped: if Langfuse is down, misconfigured or changes its API, a warning
     is printed and the narration carries on untraced. An error from the
     language model itself still propagates exactly as before.

  3. NOTHING NEW LEAVES THE MACHINE. A trace holds the same payload the model
     already receives -- no raw customer row, no protected fields, no
     probability.

The `langfuse` package is imported lazily, like `openai`, so this module and
narrate.py import on a plain `uv sync` without it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Both are required; LANGFUSE_BASE_URL is optional and defaults to the EU cloud.
REQUIRED_ENV = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def _warn(action: str, error: Exception) -> None:
    warnings.warn(
        f"Langfuse tracing failed while trying to {action} "
        f"({type(error).__name__}: {error}). The narration is unaffected.",
        RuntimeWarning,
        stacklevel=3,
    )


# --------------------------------------------------------------------------
# The do-nothing tracer
# --------------------------------------------------------------------------

class _NoopObservation:
    """Accepts every call and does nothing. Shared by the no-op tracer and by
    the Langfuse tracer whenever the SDK fails."""

    def update(self, **_):
        pass

    def score(self, *_, **__):
        pass

    def finish(self, **_):
        pass

    @contextmanager
    def generation(self, **_):
        yield self


_NOOP = _NoopObservation()


class NoopTracer:
    """The default. `enabled` is False so callers can say whether they traced."""

    enabled = False

    def __init__(self, reason: str = "tracing not configured"):
        self.reason = reason

    @contextmanager
    def trace(self, **_):
        yield _NOOP

    def flush(self):
        pass


# --------------------------------------------------------------------------
# The Langfuse tracer
# --------------------------------------------------------------------------

@contextmanager
def _safely(action, open_cm, wrap):
    """Enter an SDK context manager without letting the SDK break the caller.

    If entering fails, the body still runs, with a no-op observation. If the
    body raises (say, the language-model call failed), the SDK is told and
    the exception propagates unchanged. If exiting fails, that is only
    warned about.
    """
    try:
        cm = open_cm()
        raw = cm.__enter__()
    except Exception as error:  # noqa: BLE001 -- see rule 2
        _warn(action, error)
        yield _NOOP
        return
    handle = wrap(raw)
    exc_info = (None, None, None)
    try:
        yield handle
    except BaseException:
        exc_info = sys.exc_info()
        raise
    finally:
        try:
            cm.__exit__(*exc_info)
        except Exception as error:  # noqa: BLE001
            # Some context managers re-raise the body's own exception from
            # __exit__. That one is already propagating; only a new error from
            # the SDK is worth a warning.
            if error is not exc_info[1]:
                _warn(f"close {action}", error)


class _Observation:
    """A generation, wrapped so every call is safe."""

    def __init__(self, raw):
        self._raw = raw

    def update(self, *, output=None, usage=None, metadata=None, level=None,
               status_message=None):
        try:
            kwargs = {"output": output, "metadata": metadata}
            if usage:
                kwargs["usage_details"] = {k: v for k, v in usage.items() if v is not None}
            if level:
                kwargs["level"] = level
            if status_message:
                kwargs["status_message"] = status_message
            self._raw.update(**kwargs)
        except Exception as error:  # noqa: BLE001
            _warn("update an attempt", error)

    def score(self, name, value, data_type, comment=None):
        try:
            self._raw.score(name=name, value=value, data_type=data_type, comment=comment)
        except Exception as error:  # noqa: BLE001
            _warn(f"score {name}", error)


class _GenerationScope:
    """Starts a generation under the trace and always ends it. If the model
    call inside raised, the generation is marked ERROR with the message, and
    the exception carries on (returning False)."""

    def __init__(self, parent, kwargs, duration_ms):
        self._parent, self._kwargs, self._duration_ms = parent, kwargs, duration_ms

    def __enter__(self):
        self._started_ns = time.time_ns()
        self.raw = self._parent.start_observation(**self._kwargs)
        return self.raw

    def __exit__(self, exc_type, exc, _tb):
        if exc is not None:
            self.raw.update(level="ERROR", status_message=f"{exc_type.__name__}: {exc}")
        if self._duration_ms is None:
            self.raw.end()
        else:
            self.raw.end(end_time=self._started_ns + int(self._duration_ms * 1_000_000))
        return False


class _Trace:
    """The root observation of one narration."""

    def __init__(self, raw, tracer):
        self._raw = raw
        self._tracer = tracer

    def generation(self, *, name, model, input, model_parameters=None, duration_ms=None):
        """One API attempt. `duration_ms` is for backfilling saved results:
        the observation is then ended that long after it started, so the UI
        shows the latency that was measured at the time."""
        kwargs = dict(name=name, as_type="generation", model=model, input=input,
                      model_parameters=model_parameters)
        return _safely(
            "record an attempt",
            lambda: _GenerationScope(self._raw, kwargs, duration_ms),
            _Observation,
        )

    def score(self, name, value, data_type, comment=None):
        try:
            self._raw.score_trace(name=name, value=value, data_type=data_type, comment=comment)
        except Exception as error:  # noqa: BLE001
            _warn(f"score {name}", error)

    def finish(self, *, output):
        # Langfuse shows the root observation's input and output as the
        # trace's; the SDK's separate trace-level setter is deprecated in v4.
        try:
            self._raw.update(output=output)
        except Exception as error:  # noqa: BLE001
            _warn("finish the trace", error)


class LangfuseTracer:
    """Sends traces to Langfuse. Build it with from_env(); the constructor
    takes the SDK objects directly so tests can hand it fakes."""

    enabled = True

    def __init__(self, client, propagate_attributes, session_id: str | None = None):
        self._client = client
        self._propagate = propagate_attributes
        self.session_id = session_id

    @contextmanager
    def trace(self, *, name, input, tags=(), metadata=None):
        # Langfuse coerces metadata values to strings of at most 200
        # characters and uses them for filtering, so only short labels go here.
        meta = {k: str(v)[:200] for k, v in (metadata or {}).items() if v is not None}
        with _safely(
            "start a trace",
            lambda: self._client.start_as_current_observation(name=name, as_type="chain", input=input),
            lambda raw: _Trace(raw, self),
        ) as root:
            with _safely(
                "set the session and tags",
                lambda: self._propagate(session_id=self.session_id, tags=list(tags),
                                        metadata=meta, trace_name=name),
                lambda _raw: None,
            ):
                yield root

    def flush(self):
        try:
            self._client.flush()
        except Exception as error:  # noqa: BLE001
            _warn("flush", error)


def from_env(session_id: str | None = None):
    """A LangfuseTracer if both keys are set and the SDK is installed,
    otherwise a NoopTracer that says why. Never raises."""
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        return NoopTracer(f"{', '.join(missing)} not set")
    try:
        from langfuse import Langfuse, propagate_attributes
    except ImportError:
        warnings.warn(
            "Langfuse keys are set but the langfuse package is not installed "
            "(`uv sync --group llm`). Continuing without tracing.",
            RuntimeWarning,
            stacklevel=2,
        )
        return NoopTracer("langfuse package not installed")
    try:
        client = Langfuse()
    except Exception as error:  # noqa: BLE001
        _warn("connect", error)
        return NoopTracer(f"Langfuse client failed: {error}")
    return LangfuseTracer(client, propagate_attributes, session_id=session_id)


def session_id(prefix: str) -> str:
    """A readable, unique-enough session id: prefix plus local time."""
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"


# --------------------------------------------------------------------------
# What narrate() records: one place, shared by live narration and backfill
# --------------------------------------------------------------------------

def attempt_metadata(attempt: dict) -> dict:
    return {
        "latency_ms": attempt["latency_ms"],
        "finish_reason": attempt.get("finish_reason"),
        "rejection_detail": attempt["rejection_detail"],
    }


def score_attempt(observation, attempt: dict) -> None:
    observation.score(
        "guard_verdict",
        "accepted" if attempt["accepted"] else attempt["rejection_type"],
        "CATEGORICAL",
        comment=attempt["rejection_detail"],
    )


def score_result(trace, result: dict) -> None:
    first = result["attempts"][0]
    trace.score("first_attempt_accepted", 1 if first["accepted"] else 0, "BOOLEAN")
    trace.score("final_accepted", 1 if result["narrative_available"] else 0, "BOOLEAN")
    trace.score("first_attempt_verdict",
                "accepted" if first["accepted"] else first["rejection_type"], "CATEGORICAL")
    trace.score("attempts", len(result["attempts"]), "NUMERIC")


def trace_output(result: dict) -> dict:
    if result["structured"] is not None:
        return result["structured"]
    return {"narrative": None, "final_rejection_type": result["final_rejection_type"]}


# --------------------------------------------------------------------------
# Backfill: send saved results to Langfuse without calling the model again
# --------------------------------------------------------------------------

def backfill(results: list[dict], tracer, source: str) -> int:
    """Replay saved narrate() results as traces. No API calls, no cost.

    Messages are rebuilt exactly: the system prompt from the result's own
    prompt file, the user turn from its saved payload, and for a retry the
    rejected reply plus the correction narrate.py would have sent. Timestamps
    are the time of the backfill; durations are the latencies measured at the
    time, and every trace is tagged `backfilled`.
    """
    import narrate

    for index, result in enumerate(results):
        payload = result["payload"]
        prompt = (REPO_ROOT / "prompts" / f"{result['prompt_version']}.txt").read_text()
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(
                narrate.sent_payload(payload, result["prompt_version"]), indent=2)},
        ]
        sent = json.loads(messages[1]["content"])
        with tracer.trace(
            name="narrate",
            input=sent,
            tags=[result["prompt_version"], result["model"], "backfilled"],
            metadata={"customer": f"#{index}", "source": source,
                      "risk_level": payload["risk_level"]},
        ) as trace:
            for attempt in result["attempts"]:
                with trace.generation(
                    name=f"attempt {attempt['attempt']}",
                    model=result["model"],
                    input=messages,
                    model_parameters={"temperature": narrate.DEFAULT_TEMPERATURE,
                                      "max_tokens": narrate.MAX_OUTPUT_TOKENS},
                    duration_ms=attempt["latency_ms"],
                ) as generation:
                    generation.update(
                        output=attempt["text"],
                        usage={"input": attempt["prompt_tokens"],
                               "output": attempt["completion_tokens"]},
                        metadata=attempt_metadata(attempt),
                        level=None if attempt["accepted"] else "WARNING",
                    )
                score_attempt(generation, attempt)
                if not attempt["accepted"]:
                    messages = messages + [
                        {"role": "assistant", "content": attempt["text"]},
                        {"role": "user", "content": narrate._correction(
                            attempt["rejection_type"], attempt["rejection_detail"])},
                    ]
            trace.finish(output=trace_output(result))
            score_result(trace, result)
    tracer.flush()
    return len(results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Langfuse tracing for narrate.py.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true",
                        help="check the keys and connection, send nothing")
    action.add_argument("--backfill", metavar="RESULTS_JSON",
                        help="send a saved results file (outputs/*.json) as traces")
    args = parser.parse_args(argv)

    if args.backfill:
        path = Path(args.backfill)
        tracer = from_env(session_id=f"backfill-{path.stem}")
    else:
        tracer = from_env()
    if not tracer.enabled:
        print(f"Langfuse tracing is off: {tracer.reason}.", file=sys.stderr)
        return 2

    if args.check:
        ok = tracer._client.auth_check()
        print("Langfuse keys accepted." if ok else "Langfuse rejected the keys.")
        return 0 if ok else 1

    count = backfill(json.loads(path.read_text()), tracer, source=path.name)
    print(f"Sent {count} traces from {path} to Langfuse, session "
          f"'{tracer.session_id}'. No model calls were made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
