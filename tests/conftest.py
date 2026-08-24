"""Fixtures and stand-ins shared by more than one test module.

pytest imports this automatically; nothing needs to import it by name.
"""
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
