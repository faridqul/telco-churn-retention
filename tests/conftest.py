"""Fixtures and stand-ins shared by more than one test module.

pytest imports this automatically; nothing needs to import it by name.
"""
from dataclasses import dataclass

import numpy as np

DUMMY_CHURN_PROBABILITY = 0.8


class DummyModel:
    """Deterministic stand-in for the real XGBoost pipeline. Always predicts
    the same churn probability regardless of input -- enough to test that the
    API and the batch script are wired correctly, not to test model quality.

    Lives here because both test_api.py and test_telco_model.py need it, and
    the two consumers are supposed to behave identically: one shared fake
    makes a divergence between them show up as a test failure rather than as
    a difference between two copies of the fake.
    """

    def predict_proba(self, X):
        n = len(X)
        return np.column_stack([
            np.full(n, 1.0 - DUMMY_CHURN_PROBABILITY),
            np.full(n, DUMMY_CHURN_PROBABILITY),
        ])


class _FakeJoblib:
    """Stands in for the `joblib` module inside one module under test.

    The alternative -- monkeypatching `joblib.load` -- mutates the single
    joblib module object that api.py, telco_model.py and the test process
    all share, so it reaches far beyond the module being tested. Replacing
    the module *reference* instead keeps the patch scoped to one importer.
    """

    @staticmethod
    def load(path):
        return DummyModel()


@dataclass
class FakeCompletion:
    """One scripted model response.

    Deliberately not narrate.Completion. Importing narrate here would pull
    explain, joblib and xgboost into conftest, which pytest loads for every
    test module in the suite -- and a fake that shares the real type is a
    weaker fake anyway. narrate only reads these four attributes, so
    duck-typing is both cheaper and a better test of the boundary.
    """
    text: str
    prompt_tokens: int | None = 100
    completion_tokens: int | None = 30
    finish_reason: str | None = "stop"


class FakeLLM:
    """Scriptable stand-in for a language model client.

    Hand it a list of responses -- strings, or exceptions to raise -- and it
    returns them in order, recording every call. That makes the retry path
    testable exactly: `FakeLLM(["bad text", "good text"])` is a first attempt
    that gets rejected and a second that passes, with no network and no key.

    Lives here rather than in tests/test_narrate.py because step four's
    faithfulness harness will need the same stand-in. One shared fake means a
    divergence between the narration layer and the harness fails a test
    instead of hiding in two copies -- the same reason DummyModel is shared
    between test_api.py and test_telco_model.py.
    """

    def __init__(self, responses, prompt_tokens=100, completion_tokens=30):
        self.responses = list(responses)
        self.calls = []
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens

    def complete(self, messages, *, model, temperature, max_tokens=None,
                 response_format=None, seed=None):
        self.calls.append({
            "messages": messages, "model": model, "temperature": temperature,
            "max_tokens": max_tokens, "response_format": response_format,
            "seed": seed,
        })
        if not self.responses:
            raise AssertionError(
                f"FakeLLM was called {len(self.calls)} time(s) but was only "
                f"scripted with fewer responses. An unexpected extra call "
                f"usually means the retry loop ran when it should not have."
            )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeCompletion(
            text=response,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
        )
