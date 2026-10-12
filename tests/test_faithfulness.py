"""Tests for faithfulness.py. No API key, no network, no cost.

The harness measures the explanation layer, so a mistake in it is a wrong
measurement that looks like a right one. Weighted toward the three ways that
happens:

  1. A CHECK THAT FIRES ON SOUND TEXT, OR NOT ON UNSOUND TEXT. Every check is
     tested in both directions, as the guards are in tests/test_narrate.py: a
     check that flagged everything would pass a one-directional suite and make
     the gate fail for no reason; one that flagged nothing would make it pass
     for no reason.

  2. A JUDGE VERDICT TAKEN ON TRUST. A "found" whose quote is not in the
     summary is the judge describing some other text. It must be refused and
     counted as refused -- never as "faithful".

  3. A GATE THAT PASSES WHEN IT SHOULD NOT. Each way the baseline can fail to
     vouch for the code is produced on purpose and must be reported: a
     different prompt, a different model, too few cases, each rate over its
     limit, a missing file. And the reverse: the judge is a one-off double
     check, not a part of the product, so nothing about the judge -- its
     verdicts, its prompt, its absence -- may fail the gate.

As elsewhere in this suite, limits and counts are compared against literals,
never against the constants they test.

Tests that need the two hand-read runs in outputs/ (gitignored) skip when they
are absent; the same goes for the committed pipeline.

Run with: pytest tests/test_faithfulness.py -v
"""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import config
import explain
import faithfulness
import narrate
import narration_cache
from tests.conftest import FakeLLM

REPO_ROOT = Path(__file__).resolve().parent.parent

JUDGE_PROMPT_SHA256 = "c0aed8ce2a231d7d83fe47f225ae6d29cea493ebea3784b3b857411c6d0f7eb2"
# Kept unused: outputs/judge/judge_calibration_judge_v1.json measures it.
JUDGE_PROMPT_V1_SHA256 = "3df1e10d729ba43516ed64ec7ed8fce05bafa2573679e5dc5c27160e43f8a88d"


# ==========================================================================
# Building blocks
# ==========================================================================

_VALIDATED: dict = {}


@pytest.fixture(autouse=True)
def _check_each_distinct_case_once(monkeypatch):
    """The gate tests build baselines of 300 cases, nearly all identical.

    Both replay() and the guards are pure, so within one test an identical
    case is checked once and the result reused. Per test, never across tests:
    several tests change a guard or the prompt and must see the difference.
    Without this the file takes over a minute, most of it re-reading one
    sentence 300 times.
    """
    _VALIDATED.clear()
    real, seen = faithfulness.replay, {}

    def replay(case):
        key = json.dumps({k: v for k, v in case.items() if k != "case"}, sort_keys=True)
        if key not in seen:
            seen[key] = real(case)
        return seen[key]

    monkeypatch.setattr(faithfulness, "replay", replay)


def _validate(text, given):
    key = (text, json.dumps(given, sort_keys=True))
    if key not in _VALIDATED:
        _VALIDATED[key] = narrate.validate_narrative(text, given)
    return _VALIDATED[key]

def factor(field, direction="raises risk", value=None, comparison=None):
    entry = {"name": explain.FIELD_LABELS[field], "field": field, "direction": direction}
    if value is not None:
        entry["value"] = value
    if comparison is not None:
        entry["vs_other_customers"] = comparison
    return entry


def payload(*factors, risk_level="high"):
    return {
        "risk_level": risk_level,
        "decision": "target for retention" if "high" in risk_level else "do not target",
        "target_for_retention": "high" in risk_level,
        "factors": list(factors),
        "protected_drivers_omitted": [],
    }


# A month-to-month customer in their first month. The comparisons are the ones
# the real pipeline produces for such a customer.
RISKY = payload(
    factor("contract", value="Month-to-month"),
    factor("contractvstenure", comparison="lower than most customers"),
    factor("tenure", value=1, comparison="much lower than most customers"),
)
# A long-standing two-year customer with one factor pulling the other way.
MIXED = payload(
    factor("contract", "lowers risk", value="Two year"),
    factor("contractvstenure", "lowers risk", comparison="much higher than most customers"),
    factor("internetservice", "raises risk", value="Fiber optic"),
    risk_level="low",
)

FAITHFUL = (
    "This customer has a month-to-month contract, which raises their risk of "
    "leaving. Their overall commitment is lower than most customers, and they "
    "have been a customer for 1 month, which is much lower than most customers."
)


def answer(summary, given=RISKY, reasons=None):
    reasons = reasons if reasons is not None else [f["field"] for f in given["factors"]]
    directions = {f["field"]: f["direction"] for f in given["factors"]}
    return {
        "risk_level": given["risk_level"],
        "reasons": [{"field": field, "direction": directions.get(field, "raises risk")}
                    for field in reasons],
        "summary": summary,
    }


def types(summary, given=RISKY, reasons=None):
    return faithfulness.finding_types(given, answer(summary, given, reasons))


def gated(summary, given=RISKY, reasons=None):
    return types(summary, given, reasons) & set(faithfulness.GATED_FINDINGS)


def reply(summary=FAITHFUL, given=RISKY, reasons=None):
    return json.dumps(answer(summary, given, reasons))


# ==========================================================================
# 1. The closed sets
# ==========================================================================

def test_the_gated_findings_are_these_six():
    assert faithfulness.GATED_FINDINGS == (
        "reasons_reordered", "summary_reordered", "degree_overstated",
        "speculation", "weighing", "direction_contradicted",
    )


def test_style_findings_are_separate_from_gated_ones():
    assert faithfulness.STYLE_FINDINGS == (
        "says_risk_level", "direction_refrain", "value_unstated", "over_word_limit",
    )
    assert not set(faithfulness.GATED_FINDINGS) & set(faithfulness.STYLE_FINDINGS)


def test_a_faithful_summary_has_no_gated_finding():
    assert gated(FAITHFUL) == set()


def test_every_finding_has_a_known_type_and_a_detail():
    known = set(faithfulness.GATED_FINDINGS) | set(faithfulness.STYLE_FINDINGS)
    summary = ("Their tenure may be mainly why; a much lower overall commitment "
               "lowers their risk, contributing to their high risk level.")
    found = faithfulness.findings(RISKY, answer(summary, reasons=["tenure", "contract"]))
    assert len(found) >= 4
    for finding in found:
        assert finding["type"] in known
        assert finding["detail"]


# ==========================================================================
# 2. Order
# ==========================================================================

def test_reasons_in_the_given_order_are_fine():
    assert "reasons_reordered" not in types(FAITHFUL)


def test_a_subset_of_reasons_in_order_is_fine():
    assert "reasons_reordered" not in types(FAITHFUL, reasons=["contract", "tenure"])


def test_reasons_out_of_order_are_flagged():
    assert "reasons_reordered" in types(FAITHFUL, reasons=["tenure", "contract"])


def test_a_summary_that_names_the_factors_out_of_order_is_flagged():
    summary = ("This customer has been a customer for 1 month and is on a "
               "month-to-month contract.")
    assert "summary_reordered" in types(summary)
    # ...while the reasons, which are in order, are not blamed for it.
    assert "reasons_reordered" not in types(summary)


def test_leaving_a_factor_out_of_the_summary_is_not_a_reordering():
    summary = "This customer is on a month-to-month contract and has been a customer for 1 month."
    assert "summary_reordered" not in types(summary)


def test_a_repeated_mention_counts_from_its_first_appearance():
    summary = ("Their month-to-month contract and lower overall commitment "
               "raise their risk; the contract is month-to-month.")
    assert "summary_reordered" not in types(summary)


# ==========================================================================
# 3. Degree
# ==========================================================================

def test_much_beside_a_factor_that_is_only_lower_is_flagged():
    """The sentence the 50-customer read found five times."""
    summary = ("This customer is on a month-to-month contract and has a much "
               "lower overall commitment.")
    found = faithfulness.findings(RISKY, answer(summary))
    details = [f["detail"] for f in found if f["type"] == "degree_overstated"]
    assert details == ["'much' beside contractvstenure, which is lower than most customers"]


@pytest.mark.parametrize("summary", [
    "Their overall commitment is much lower than most customers.",
    "Their overall commitment is far lower than most customers.",
    "They have a significantly lower overall commitment.",
    "They have a very low overall commitment.",
])
def test_each_degree_word_is_recognised_before_and_after_the_mention(summary):
    assert "degree_overstated" in types(summary)


def test_much_beside_a_factor_that_really_is_much_is_fine():
    summary = "They have been a customer for 1 month, with a tenure much lower than most customers."
    assert "degree_overstated" not in types(summary)


def test_a_stronger_synonym_is_fine_when_the_comparison_says_much():
    summary = "Their overall commitment is far higher than most customers."
    assert "degree_overstated" not in types(summary, MIXED)


def test_a_degree_word_does_not_cross_a_clause_to_the_wrong_factor():
    """'much' belongs to tenure, on the other side of the 'and'."""
    summary = ("They have a lower overall commitment and a tenure much lower "
               "than most customers.")
    assert "degree_overstated" not in types(summary)


def test_a_degree_word_beside_a_factor_with_no_comparison_is_flagged():
    summary = "This customer is on a very short month-to-month contract."
    assert "degree_overstated" in types(summary)


def test_the_bands_own_name_is_not_a_degree_word():
    given = payload(factor("contract", value="Month-to-month"), risk_level="very high")
    assert "degree_overstated" not in types(
        "This customer is at very high risk because of their month-to-month contract.", given)


def test_very_high_said_of_a_merely_high_customer_is_flagged():
    given = payload(factor("contract", value="Month-to-month"), risk_level="high")
    assert "degree_overstated" in types(
        "This customer is at very high risk because of their month-to-month contract.", given)


def test_a_loose_degree_word_passes_when_some_factor_is_much():
    """It cannot be pinned to a factor, and one of them really is 'much'."""
    summary = ("They have only been with the service for one month, which is "
               "much less than most customers.")
    assert "degree_overstated" not in types(summary)


def test_a_loose_degree_word_is_flagged_when_no_factor_is_much():
    given = payload(factor("contract", value="Month-to-month"),
                    factor("contractvstenure", comparison="lower than most customers"))
    assert "degree_overstated" in types(
        "They are on a month-to-month contract, far below what others have.", given)


# ==========================================================================
# 4. Speculation
# ==========================================================================

@pytest.mark.parametrize("phrase", [
    "which may reflect dissatisfaction",
    "which might mean they are unhappy",
    "perhaps because they are new",
    "which suggests a lack of loyalty",
    "indicating a lack of established loyalty",
    "which is a sign of low engagement",
    "so they could be shopping around",
])
def test_a_guess_is_flagged(phrase):
    assert "speculation" in types(f"This customer is on a month-to-month contract, {phrase}.")


@pytest.mark.parametrize("summary", [
    FAITHFUL,
    "This customer is likely to leave because of their month-to-month contract.",
    "To their dismay, this customer is on a month-to-month contract.",   # 'may' inside a word
    "This customer is on a month-to-month contract, which raises their risk.",
])
def test_stating_what_was_given_is_not_a_guess(summary):
    assert "speculation" not in types(summary)


# ==========================================================================
# 5. Weighing
# ==========================================================================

@pytest.mark.parametrize("phrase", [
    "These factors do not outweigh their contract.",
    "This is mainly down to their contract.",
    "Their contract is the biggest reason.",
    "Their contract is more important than their tenure.",
    "Their contract is the main factor.",
    "Their contract significantly raises their risk.",
    "Their contract raises their risk considerably.",
    "The other factors significantly lower their risk.",
    # From the 300-customer run, row 27: the judge caught it, the list had not.
    "Their tenure lowers their risk, but it is not enough to offset the other factors.",
    "Their tenure does not offset their contract.",
])
def test_ranking_factors_or_stating_a_strength_is_flagged(phrase):
    assert "weighing" in types(f"This customer is on a month-to-month contract. {phrase}")


@pytest.mark.parametrize("summary", [
    FAITHFUL,
    "Their contract raises their risk, and their tenure also raises their risk.",
    "Their contract raises their risk, further raised by their tenure.",
    # A degree on a VALUE is the degree check's business, not a strength.
    "They have a much lower overall commitment.",
])
def test_listing_factors_is_not_weighing(summary):
    assert "weighing" not in types(summary)


def test_a_strength_is_counted_once_not_also_as_a_degree():
    """'significantly' describes the effect, not the contract's size."""
    summary = "Their month-to-month contract significantly raises their risk."
    found = types(summary)
    assert "weighing" in found
    assert "degree_overstated" not in found


# ==========================================================================
# 6. Direction
# ==========================================================================

def test_a_direction_stated_backwards_is_flagged():
    summary = "This customer has a month-to-month contract, which lowers their risk of leaving."
    found = faithfulness.findings(RISKY, answer(summary))
    details = [f["detail"] for f in found if f["type"] == "direction_contradicted"]
    assert details == ["says 'lowers their risk' of contract, which raises risk"]


@pytest.mark.parametrize("summary", [
    "This customer has a two-year contract, which lowers their risk of leaving.",
    "Their two-year contract reduces their risk.",
    "Their overall commitment is much higher than most customers, further lowering their risk.",
    "They use fiber optic internet, which increases their risk.",
])
def test_a_direction_stated_correctly_is_fine(summary):
    assert "direction_contradicted" not in types(summary, MIXED)


def test_both_of_which_reaches_every_factor_before_it():
    summary = ("They have a two-year contract and fiber optic internet, both of "
               "which lower their risk.")
    found = faithfulness.findings(MIXED, answer(summary))
    details = [f["detail"] for f in found if f["type"] == "direction_contradicted"]
    assert details == ["says 'lower their risk' of internetservice, which raises risk"]


def test_both_of_which_reaches_past_the_nearest_factor():
    """The factor stated backwards is the FIRST of the two, so only the
    plural reference can reach it."""
    summary = ("They have fiber optic internet and a two-year contract, both of "
               "which lower their risk.")
    found = faithfulness.findings(MIXED, answer(summary))
    details = [f["detail"] for f in found if f["type"] == "direction_contradicted"]
    assert details == ["says 'lower their risk' of internetservice, which raises risk"]


def test_a_plain_which_reaches_only_the_nearest_factor():
    """Read as about fiber optic, which does raise risk -- so nothing is wrong,
    even though the contract in the same clause lowers it."""
    summary = "They have a two-year contract and fiber optic internet, which raises their risk."
    assert "direction_contradicted" not in types(summary, MIXED)


def test_each_direction_phrase_owns_only_what_came_since_the_last_one():
    summary = ("This customer has a two-year contract, which lowers their risk. "
               "Their overall commitment is much higher than most customers, "
               "further lowering their risk, despite having fiber optic internet "
               "service, which raises their risk.")
    assert "direction_contradicted" not in types(summary, MIXED)


def test_a_concession_is_not_attached_to_the_main_clauses_verb():
    """From the real v3 run. The contract raises risk; 'lowers' is said of
    something else."""
    given = payload(
        factor("contract", "raises risk", value="Month-to-month"),
        factor("internetservice", "lowers risk", value="No"),
        factor("onlinesecurity", "lowers risk", value="No internet service"),
        risk_level="low",
    )
    summary = ("This customer has a low risk of leaving because they do not have "
               "internet service and also lack an online security add-on. Although "
               "they are on a month-to-month contract, the absence of these "
               "services lowers their risk.")
    assert "direction_contradicted" not in types(summary, given)


def test_a_concession_after_another_direction_phrase_is_still_recognised():
    summary = ("Their fiber optic internet raises their risk, while their "
               "two-year contract lowers their risk.")
    assert "direction_contradicted" not in types(summary, MIXED)


@pytest.mark.parametrize("summary", [
    "Because of their two-year contract they have a lower risk than most.",   # adjective
    "Their fiber optic internet increases the likelihood of staying.",       # inverted: unread
    "Their fiber optic internet contributes to their low risk level.",       # no direction verb
])
def test_phrases_that_are_not_a_direction_claim_are_left_alone(summary):
    assert "direction_contradicted" not in types(summary, MIXED)


def test_direction_phrases_are_read_with_their_direction():
    text = "x raises their risk. y lowers the likelihood. z reduce their overall risk."
    assert [d for _, _, d in faithfulness.direction_phrases(text)] == [
        "raises risk", "lowers risk", "lowers risk",
    ]


def test_a_decimal_point_does_not_end_a_sentence():
    """Otherwise '85.5' would cut the contract off from its own verb."""
    given = payload(factor("monthlycharges", "raises risk", value=85.5,
                           comparison="higher than most customers"))
    summary = "Their monthly bill of 85.5 lowers their risk."
    assert "direction_contradicted" in types(summary, given)


# ==========================================================================
# 7. Wording: reported, never gated
# ==========================================================================

def test_risk_level_and_the_refrain_are_style_not_faithfulness():
    summary = ("This customer has a month-to-month contract, which raises their "
               "risk, contributing to their high risk level.")
    found = types(summary)
    assert {"says_risk_level", "direction_refrain"} <= found
    assert gated(summary) == set()


@pytest.mark.parametrize("summary, unstated", [
    ("This customer is on a month-to-month contract and has been a customer for 1 month.", False),
    ("This customer is on a month-to-month contract and has been a customer for one month.", False),
    ("This customer has a contract type that raises risk and a short tenure.", True),
    ("This customer is on a month-to-month contract with a short tenure.", True),
])
def test_a_value_left_unstated_is_reported(summary, unstated):
    found = types(summary, reasons=["contract", "tenure"])
    assert ("value_unstated" in found) is unstated


def test_a_one_year_contract_does_not_state_a_tenure_of_one():
    """'one' is a number word, but in 'one-year' it is a contract term."""
    given = payload(factor("tenure", value=1, comparison="much lower than most customers"))
    for wording in ("a one-year contract", "a one year contract"):
        assert "value_unstated" in types(
            f"This customer has {wording} and a short tenure.", given, reasons=["tenure"])
    assert "value_unstated" not in types(
        "This customer has been a customer for one month.", given, reasons=["tenure"])


def test_a_yes_no_value_is_never_expected_as_a_word():
    given = payload(factor("onlinesecurity", "raises risk", value="No"))
    assert "value_unstated" not in types("They have no online security add-on.", given)


def test_a_factor_with_no_value_cannot_have_it_left_out():
    assert "value_unstated" not in types(
        "Their overall commitment is lower than most.", reasons=["contractvstenure"])


def test_the_word_limit_is_sixty():
    assert "over_word_limit" not in types(" ".join(["word"] * 60))
    assert "over_word_limit" in types(" ".join(["word"] * 61))


# ==========================================================================
# 8. The checks against the two runs that were read by hand
# ==========================================================================

def _saved(name):
    path = REPO_ROOT / "outputs" / name
    if not path.exists():
        pytest.skip(f"{path} is not present (outputs/ is not committed)")
    return json.loads(path.read_text())


def test_the_checks_reproduce_the_hand_read_of_the_v3_run():
    """Read by hand on 2026-09-28: 6 reordered, 5 'much lower' commitments,
    2 guessed motives. The hand read counted 2 strength claims; the check
    finds 5 customers, all genuine -- one sentence appears for two customers,
    'the other factors significantly lower their risk' (row 19) was missed by
    eye, and so was 'it is not enough to offset the other factors' (row 24),
    which the check itself only learned to see on 2026-10-12, from the judge."""
    counts = faithfulness.summarize(_saved("stage2_v3.json"))["findings"]
    assert counts["reasons_reordered"] == 6
    assert counts["degree_overstated"] == 5
    assert counts["speculation"] == 2
    assert counts["weighing"] == 5
    assert counts["direction_contradicted"] == 0
    assert counts["says_risk_level"] == 15


def test_the_checks_find_nothing_in_the_v5_run():
    """Read by hand on 2026-10-07: all four habits gone, 'risk level' once."""
    counts = faithfulness.summarize(_saved("stage2_v5.json"))["findings"]
    for kind in ("reasons_reordered", "summary_reordered", "degree_overstated",
                 "speculation", "weighing", "direction_contradicted"):
        assert counts[kind] == 0, kind
    assert counts["says_risk_level"] == 1


# ==========================================================================
# 9. The sample
# ==========================================================================

def _inputs(**bands):
    items = []
    for band, count in bands.items():
        for index in range(count):
            items.append({
                "key": f"{band}-{index:03d}", "position": len(items),
                "customer": {}, "risk_level": band.replace("_", " "),
            })
    return items


def _bands(sample):
    counts = {}
    for item in sample:
        counts[item["risk_level"]] = counts.get(item["risk_level"], 0) + 1
    return counts


def test_the_sample_takes_every_very_high_and_the_rest_in_proportion():
    """The real test set's numbers: 528 distinct inputs."""
    inputs = _inputs(very_high=33, high=106, moderate=142, low=247)
    sample = faithfulness.choose_sample(inputs, 300)
    assert len(sample) == 300
    assert _bands(sample) == {"very high": 33, "high": 57, "moderate": 77, "low": 133}


def test_the_sample_is_the_same_every_time_and_changes_with_the_seed():
    inputs = _inputs(very_high=5, high=40, moderate=40, low=40)
    first = [item["key"] for item in faithfulness.choose_sample(inputs, 50, seed=42)]
    again = [item["key"] for item in faithfulness.choose_sample(list(reversed(inputs)), 50, seed=42)]
    other = [item["key"] for item in faithfulness.choose_sample(inputs, 50, seed=7)]
    assert first == again
    assert first != other
    assert len(set(first)) == 50


def test_asking_for_more_than_there_are_returns_them_all():
    inputs = _inputs(very_high=2, low=5)
    assert len(faithfulness.choose_sample(inputs, 300)) == 7


def test_a_sample_smaller_than_the_very_high_band_is_still_the_size_asked():
    inputs = _inputs(very_high=10, low=10)
    sample = faithfulness.choose_sample(inputs, 4)
    assert len(sample) == 4
    assert _bands(sample) == {"very high": 4}


def test_the_sample_is_returned_in_dataset_order():
    inputs = _inputs(very_high=3, high=20, low=20)
    positions = [item["position"] for item in faithfulness.choose_sample(inputs, 15)]
    assert positions == sorted(positions)


def test_the_raw_columns_are_the_nineteen_the_api_takes():
    import api

    assert faithfulness.RAW_COLUMNS == list(api.Customer.model_fields)
    assert len(faithfulness.RAW_COLUMNS) == 19


@pytest.fixture(scope="module")
def pipeline():
    path = Path(config.MODEL_PATH)
    path = path if path.is_absolute() else REPO_ROOT / path
    if not path.exists():
        pytest.skip(f"model artifact not present at {path}")
    return explain.load_model(str(path))


@pytest.fixture(scope="module")
def simulated():
    path = REPO_ROOT / "simulated_new_customers.csv"
    if not path.exists():
        pytest.skip("simulated_new_customers.csv not present")
    return pd.read_csv(path)


def test_distinct_inputs_collapses_customers_who_get_the_same_question(
    monkeypatch, pipeline, simulated,
):
    """The 50 simulated customers stand in for the test set, so this needs no
    download. 41 distinct inputs among them was measured on 2026-09-28."""
    import fairness_analysis
    from feature_engineering_telco import engineer_features

    checked = []
    monkeypatch.setattr(fairness_analysis, "locate_dataset", lambda data: "unused.csv")
    monkeypatch.setattr(
        fairness_analysis, "build_test_split",
        lambda csv: (None, engineer_features(simulated.copy()), None, [0] * len(simulated)),
    )
    monkeypatch.setattr(
        fairness_analysis, "verify_reconstruction",
        lambda y, proba, threshold: checked.append(len(proba)),
    )
    inputs = faithfulness.distinct_inputs(pipeline=pipeline)
    assert checked == [50]            # the reconstruction gate was consulted
    assert len(inputs) == 41
    assert len({item["key"] for item in inputs}) == 41
    assert set(inputs[0]["customer"]) == set(faithfulness.RAW_COLUMNS)
    assert {item["risk_level"] for item in inputs} <= set(narrate.RISK_LEVELS)


def test_write_sample_round_trips_through_the_input_validator(tmp_path, simulated):
    sample = [{"customer": faithfulness._plain(simulated.iloc[i].to_dict())} for i in range(3)]
    sample[0]["customer"]["totalcharges"] = None
    path = tmp_path / "nested" / "sample.csv"
    faithfulness.write_sample(sample, path)
    frame = pd.read_csv(path)
    config.validate_input_frame(frame)
    assert list(frame.columns) == faithfulness.RAW_COLUMNS
    assert pd.isna(frame.loc[0, "totalcharges"])


def test_plain_turns_numpy_and_nan_into_python(simulated):
    row = simulated.iloc[0].to_dict()
    row["totalcharges"] = float("nan")
    plain = faithfulness._plain(row)
    assert plain["totalcharges"] is None
    assert type(plain["tenure"]) is int
    json.dumps(plain, allow_nan=False)


# ==========================================================================
# 10. Resumable work
# ==========================================================================

def _do(calls, fail_on=()):
    def do(item):
        calls.append(item)
        if item in fail_on:
            raise TimeoutError(f"no answer for {item}")
        return {"value": item * 10}
    return do


def test_work_writes_the_finished_file_and_removes_the_partial(tmp_path):
    out, calls, said = tmp_path / "run.json", [], []
    results = faithfulness._work([1, 2, 3], out, str, _do(calls), said.append)
    assert calls == [1, 2, 3]
    assert results == json.loads(out.read_text()) == [
        {"value": 10, "case": "1"}, {"value": 20, "case": "2"}, {"value": 30, "case": "3"},
    ]
    assert not faithfulness._partial(out).exists()


def test_an_interrupted_run_resumes_without_repeating_a_call(tmp_path):
    out, said = tmp_path / "run.json", []
    first_calls = []
    partial = faithfulness._work([1, 2, 3], out, str, _do(first_calls, fail_on={2}), said.append)
    assert first_calls == [1, 2, 3]
    assert [record["case"] for record in partial] == ["1", "3"]
    assert not out.exists()                       # not finished, so not written
    assert faithfulness._partial(out).exists()

    second_calls = []
    results = faithfulness._work([1, 2, 3], out, str, _do(second_calls), said.append)
    assert second_calls == [2]                    # only the one that failed
    assert [record["case"] for record in results] == ["1", "2", "3"]   # in order
    assert out.exists() and not faithfulness._partial(out).exists()


def test_a_finished_file_is_never_overwritten_and_nothing_is_called(tmp_path):
    out, calls = tmp_path / "run.json", []
    out.write_text("[]")
    with pytest.raises(FileExistsError, match="Nothing was sent"):
        faithfulness._work([1, 2], out, str, _do(calls), print)
    assert calls == []
    assert out.read_text() == "[]"


def test_a_partial_run_made_with_other_settings_is_not_resumed(tmp_path):
    """Finishing it would give one file measuring two prompts."""
    out, calls = tmp_path / "run.json", []

    def do(item):
        calls.append(item)
        return {"value": item, "prompt_version": "explanation_v5"}

    faithfulness._work([1, 2], out, str, lambda item: (_ for _ in ()).throw(TimeoutError())
                       if item == 2 else do(item), lambda _: None,
                       made_with={"prompt_version": "explanation_v5"})
    assert calls == [1] and faithfulness._partial(out).exists()

    with pytest.raises(ValueError, match="started with prompt_version='explanation_v5'"):
        faithfulness._work([1, 2], out, str, do, print,
                           made_with={"prompt_version": "explanation_v6"})
    assert calls == [1]                               # nothing was called
    # ...and with the settings it was started under, it finishes.
    results = faithfulness._work([1, 2], out, str, do, lambda _: None,
                                 made_with={"prompt_version": "explanation_v5"})
    assert calls == [1, 2] and len(results) == 2 and out.exists()


def test_a_half_judged_run_is_not_finished_by_a_different_judge(tmp_path, monkeypatch):
    results = [_result("a"), _result("b")]
    out = tmp_path / "judged.json"
    faithfulness.judge_run(results, out, FakeLLM([CLEAN_VERDICT, TimeoutError("down")]),
                           progress=lambda _: None)
    assert faithfulness._partial(out).exists()
    monkeypatch.setattr(faithfulness, "JUDGE_PROMPT_VERSION", "judge_v3")
    llm = FakeLLM([CLEAN_VERDICT])
    with pytest.raises(ValueError, match="judge_prompt_version"):
        faithfulness.judge_run(results, out, llm, progress=lambda _: None)
    assert llm.calls == []


def test_five_failures_in_a_row_stop_the_run(tmp_path):
    out, calls, said = tmp_path / "run.json", [], []
    items = list(range(1, 21))
    faithfulness._work(items, out, str, _do(calls, fail_on=set(items)), said.append)
    assert len(calls) == 5
    assert any("5 calls in a row failed" in line for line in said)


def test_scattered_failures_do_not_stop_the_run(tmp_path):
    out, calls = tmp_path / "run.json", []
    items = list(range(1, 21))
    faithfulness._work(items, out, str, _do(calls, fail_on={2, 4, 6, 8, 10, 12}), lambda _: None)
    assert len(calls) == 20


def _sample_csv(tmp_path, simulated, rows=3):
    path = tmp_path / "sample.csv"
    simulated.head(rows).to_csv(path, index=False)
    return path


def _good_reply_for(customer, pipeline):
    """A reply the guards accept for one real customer: every factor named by
    its own field id, and a summary that mentions none of them by alias."""
    explanation = explain.explain_customer(customer, model=pipeline, top_n=None)
    given = narrate.narration_payload(explanation)
    return json.dumps({
        "risk_level": given["risk_level"],
        "reasons": [{"field": f["field"], "direction": f["direction"]} for f in given["factors"]],
        "summary": "The listed factors are why this customer is rated this way.",
    })


def test_run_saves_what_narrate_save_would_and_uses_no_cache(tmp_path, pipeline, simulated):
    csv = _sample_csv(tmp_path, simulated)
    replies = [_good_reply_for(simulated.iloc[i].to_dict(), pipeline) for i in range(3)]
    llm = FakeLLM(replies)
    out = tmp_path / "harness.json"
    results = faithfulness.run(csv, out, llm, pipeline=pipeline, progress=lambda _: None)

    assert len(llm.calls) == 3
    saved = json.loads(out.read_text())
    assert [r["case"] for r in saved] == [f"sample.csv row {i}" for i in range(3)]
    for result in saved:
        # The keys LLMcalls.ipynb and llm_tracing's backfill read.
        assert {"payload", "structured", "attempts", "prompt_version", "model",
                "narrative", "cache_hit"} <= set(result)
        assert result["cache_hit"] is False
        assert result["prompt_version"] == "explanation_v5"
    assert narrate.rejection_rates(results)["n"] == 3
    # No cache file was created, let alone written to.
    assert not Path(narration_cache.DEFAULT_DB_PATH).exists()


def test_run_honours_a_limit(tmp_path, pipeline, simulated):
    csv = _sample_csv(tmp_path, simulated, rows=5)
    llm = FakeLLM([_good_reply_for(simulated.iloc[i].to_dict(), pipeline) for i in range(2)])
    results = faithfulness.run(csv, tmp_path / "out.json", llm, pipeline=pipeline,
                               limit=2, progress=lambda _: None)
    assert len(results) == 2 and len(llm.calls) == 2


# ==========================================================================
# 11. The judge
# ==========================================================================

def verdict(**found):
    """A judge reply. verdict(guesses_why="may reflect") finds one thing."""
    return json.dumps({
        check: {"found": check in found, "quote": found.get(check, "")}
        for check in faithfulness.JUDGE_CHECKS
    })


CLEAN_VERDICT = verdict()


def test_the_judge_prompt_is_pinned():
    digest = hashlib.sha256(faithfulness.JUDGE_PROMPT_PATH.read_bytes()).hexdigest()
    assert digest == JUDGE_PROMPT_SHA256
    assert faithfulness.JUDGE_PROMPT_VERSION == "judge_v2"


def test_the_earlier_judge_prompt_is_kept_unchanged():
    """A calibration run measures it, so it is neither edited nor deleted."""
    path = REPO_ROOT / "prompts" / "judge_v1.txt"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == JUDGE_PROMPT_V1_SHA256


def test_the_judge_answers_these_five_questions():
    assert faithfulness.JUDGE_CHECKS == (
        "adds_fact", "wrong_direction", "overstated_size", "guesses_why", "weighs_factors",
    )
    schema = faithfulness.JUDGE_RESPONSE_FORMAT["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["required"] == list(faithfulness.JUDGE_CHECKS)
    assert schema["schema"]["additionalProperties"] is False
    # The prompt names every question it is scored on.
    prompt = faithfulness.JUDGE_PROMPT_PATH.read_text()
    for check in faithfulness.JUDGE_CHECKS:
        assert check in prompt


def test_the_judge_sees_what_the_narrator_saw_and_nothing_more():
    messages = faithfulness.judge_messages(RISKY, FAITHFUL)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == faithfulness.JUDGE_PROMPT_PATH.read_text()
    sent = json.loads(messages[1]["content"])
    assert set(sent) == {"given", "summary"}
    assert set(sent["given"]) == {"risk_level", "factors"}      # no decision
    assert sent["summary"] == FAITHFUL
    assert "target" not in messages[1]["content"]


def test_a_clean_verdict_parses():
    parsed, problem = faithfulness.parse_verdict(CLEAN_VERDICT, FAITHFUL)
    assert problem is None
    assert parsed["unfaithful"] is False
    assert set(parsed["checks"]) == set(faithfulness.JUDGE_CHECKS)


def test_a_finding_with_a_real_quote_is_accepted():
    summary = "They are new, which may reflect dissatisfaction."
    parsed, problem = faithfulness.parse_verdict(
        verdict(guesses_why="which may reflect dissatisfaction"), summary)
    assert problem is None
    assert parsed["unfaithful"] is True
    assert parsed["checks"]["guesses_why"] == {
        "found": True, "quote": "which may reflect dissatisfaction",
    }


def test_a_quote_is_compared_without_case_or_punctuation():
    summary = "They are new, which may reflect dissatisfaction."
    parsed, problem = faithfulness.parse_verdict(
        verdict(guesses_why='"Which MAY reflect   dissatisfaction."'), summary)
    assert problem is None and parsed["unfaithful"] is True


def test_a_finding_whose_quote_is_not_in_the_summary_is_refused():
    """The judge describing a summary it was not given. Not a verdict."""
    parsed, problem = faithfulness.parse_verdict(
        verdict(adds_fact="they pay by electronic check"), FAITHFUL)
    assert parsed is None
    assert "not in the summary" in problem


def test_a_finding_with_no_quote_is_refused():
    reply_ = json.dumps({
        check: {"found": check == "adds_fact", "quote": "  "}
        for check in faithfulness.JUDGE_CHECKS
    })
    parsed, problem = faithfulness.parse_verdict(reply_, FAITHFUL)
    assert parsed is None and "no quote" in problem


def test_a_quote_on_something_not_found_is_ignored():
    reply_ = json.dumps({
        check: {"found": False, "quote": "stray text"} for check in faithfulness.JUDGE_CHECKS
    })
    parsed, problem = faithfulness.parse_verdict(reply_, FAITHFUL)
    assert problem is None
    assert all(entry["quote"] == "" for entry in parsed["checks"].values())


@pytest.mark.parametrize("text, why", [
    ("not json", "not valid JSON"),
    ("[]", "expected exactly the keys"),
    (json.dumps({"adds_fact": {"found": False, "quote": ""}}), "expected exactly the keys"),
    (json.dumps({c: {"found": "no", "quote": ""} for c in faithfulness.JUDGE_CHECKS}), "must be"),
    (json.dumps({c: True for c in faithfulness.JUDGE_CHECKS}), "must be"),
])
def test_a_malformed_verdict_is_refused_with_a_reason(text, why):
    parsed, problem = faithfulness.parse_verdict(text, FAITHFUL)
    assert parsed is None
    assert why in problem


def test_judge_one_asks_the_judge_model_with_the_seed_and_the_schema():
    llm = FakeLLM([CLEAN_VERDICT])
    record = faithfulness.judge_one(RISKY, FAITHFUL, llm)
    call = llm.calls[0]
    assert call["model"] == "gpt-6-luna"
    assert call["seed"] == 42
    # Room for the thinking, which counts against the cap: a verdict is ~90
    # tokens and the thinking before it was measured at ~240.
    assert call["max_tokens"] == 2000
    assert call["response_format"] is faithfulness.JUDGE_RESPONSE_FORMAT
    assert record["verdict"]["unfaithful"] is False
    assert record["error"] is None
    assert record["judge_model"] == "gpt-6-luna"
    assert record["judge_reasoning_effort"] == "low"
    assert record["judge_prompt_version"] == "judge_v2"
    assert (record["prompt_tokens"], record["completion_tokens"]) == (100, 30)
    assert record["reasoning_tokens"] is None      # a FakeLLM does no thinking


def test_the_judge_client_sends_what_the_judge_model_accepts():
    """gpt-6-luna answered 400 to temperature=0.0 on 2026-10-09: 'Only the
    default (1) value is supported.' So it must not be sent at all -- while
    the seed, the schema, the cap and the reasoning effort must be."""
    import importlib.util

    if importlib.util.find_spec("openai") is None:
        pytest.skip("openai is not installed")

    class Recorder:
        def __init__(self):
            self.kwargs = None
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            self.kwargs = kwargs

            class Details:
                reasoning_tokens = 240

            class Usage:
                prompt_tokens, completion_tokens = 1060, 330
                completion_tokens_details = Details

            class Choice:
                finish_reason = "stop"

                class message:
                    content = CLEAN_VERDICT

            class Response:
                choices = [Choice]
                usage = Usage
                system_fingerprint = None

            return Response

    client = faithfulness.JudgeClient(api_key="sk-not-a-real-key")
    client._client = recorder = Recorder()
    record = faithfulness.judge_one(RISKY, FAITHFUL, client)

    assert "temperature" not in recorder.kwargs
    assert recorder.kwargs["model"] == "gpt-6-luna"
    assert recorder.kwargs["seed"] == 42
    assert recorder.kwargs["reasoning_effort"] == "low"
    assert recorder.kwargs["max_completion_tokens"] == 2000
    assert recorder.kwargs["response_format"] is faithfulness.JUDGE_RESPONSE_FORMAT
    assert record["verdict"]["unfaithful"] is False
    assert (record["prompt_tokens"], record["completion_tokens"]) == (1060, 330)
    assert record["reasoning_tokens"] == 240
    assert record["finish_reason"] == "stop"


def test_the_judge_client_is_a_narrate_client_underneath():
    """Same key handling, same missing-SDK message: one place for both."""
    assert issubclass(faithfulness.JudgeClient, narrate.OpenAIClient)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY|openai package"):
        faithfulness.JudgeClient()      # conftest removed the key


def test_judge_one_records_an_unusable_reply_instead_of_raising():
    record = faithfulness.judge_one(RISKY, FAITHFUL, FakeLLM(["nonsense"]))
    assert record["verdict"] is None
    assert "not valid JSON" in record["error"]
    assert record["text"] == "nonsense"


def _result(case, summary=FAITHFUL, given=RISKY, attempts=None):
    """A saved result, as run() writes it, without calling anything."""
    texts = attempts if attempts is not None else [reply(summary, given)]
    records, structured = [], None
    for number, text in enumerate(texts, start=1):
        parsed, rejection, detail = _validate(text, given)
        records.append({"attempt": number, "accepted": parsed is not None,
                        "rejection_type": rejection, "rejection_detail": detail,
                        "text": text, "latency_ms": 900.0})
        structured = parsed
    return {
        "case": case, "payload": given, "attempts": records, "structured": structured,
        "narrative": structured["summary"] if structured else None,
        "prompt_version": narrate.PROMPT_VERSION, "model": narrate.DEFAULT_MODEL,
        "temperature": narrate.DEFAULT_TEMPERATURE, "seed": narrate.DEFAULT_SEED,
        "churn_probability": 0.57, "contributions": {"contract": 0.6},
    }


REJECTED = reply("This customer has a 74% chance of leaving on a month-to-month contract.")


def test_judge_run_judges_only_the_accepted_summaries(tmp_path):
    results = [_result("a"), _result("b", attempts=[REJECTED, REJECTED]), _result("c")]
    assert results[1]["structured"] is None
    llm = FakeLLM([CLEAN_VERDICT, CLEAN_VERDICT])
    judged = faithfulness.judge_run(results, tmp_path / "judged.json", llm, progress=lambda _: None)
    assert [record["case"] for record in judged] == ["a", "c"]
    assert len(llm.calls) == 2


# ==========================================================================
# 12. Calibrating the judge
# ==========================================================================

CLEAN_MIXED = (
    "This customer has a two-year contract, which lowers their risk of leaving. "
    "Their overall commitment is much higher than most customers, and they use "
    "fiber optic internet service, which raises their risk."
)
CLEAN_RISKY = (
    "This customer has a month-to-month contract, which raises their risk of "
    "leaving. They have a lower overall commitment and have been a customer "
    "for 1 month."
)


@pytest.mark.parametrize("kind, given, summary, code_check", [
    ("wrong_direction", MIXED, CLEAN_MIXED, "direction_contradicted"),
    ("overstated_size", RISKY, CLEAN_RISKY, "degree_overstated"),
    ("guesses_why", MIXED, CLEAN_MIXED, "speculation"),
    ("weighs_factors", MIXED, CLEAN_MIXED, "weighing"),
])
def test_a_planted_error_is_one_the_code_checks_can_see(kind, given, summary, code_check):
    """Each planted error is checked against an independent detector, so the
    judge is not being scored on errors that were never actually planted."""
    assert gated(summary, given) == set()
    planted = faithfulness._plant(kind, given, summary)
    assert planted and planted != summary
    assert code_check in types(planted, given)


@pytest.mark.parametrize("kind", ["adds_fact", "adds_number"])
def test_a_planted_fact_is_one_the_guards_would_refuse(kind):
    """An invented factor or number never reaches a reader -- the guards stop
    it -- which makes it a fair test of whether the judge would too."""
    planted = faithfulness._plant(kind, MIXED, CLEAN_MIXED)
    assert planted.startswith(CLEAN_MIXED)
    _, rejection, _ = narrate.validate_narrative(reply(planted, MIXED), MIXED)
    assert rejection in ("unlisted_field", "hallucinated_number")


def test_a_kind_that_does_not_apply_plants_nothing():
    assert faithfulness._plant("wrong_direction", MIXED, "They have a two-year contract.") is None
    # Every comparison in MIXED already says "much": there is nothing to overstate.
    assert faithfulness._plant("overstated_size", MIXED, CLEAN_MIXED) is None


def test_every_planted_kind_has_an_expected_judge_check():
    assert set(faithfulness.PLANTED.values()) <= set(faithfulness.JUDGE_CHECKS)
    for kind in faithfulness.PLANTED:
        faithfulness._plant(kind, MIXED, CLEAN_MIXED)   # no kind raises


def test_calibration_cases_come_in_three_kinds_with_known_answers():
    faulty = "This customer has a month-to-month contract, which may reflect a wish to leave."
    known = [_result("k0", faulty), _result("k1", FAITHFUL)]
    clean = [_result("c0", CLEAN_MIXED, MIXED), _result("c1", CLEAN_RISKY),
             _result("c2", CLEAN_MIXED, MIXED),          # a duplicate of c0
             _result("c3", attempts=[REJECTED, REJECTED])]
    cases = faithfulness.calibration_cases(known, clean)
    by_kind = {}
    for case in cases:
        by_kind.setdefault(case["kind"], []).append(case)

    assert [case["expect"] for case in by_kind["known"]] == [["guesses_why"]]
    assert len(by_kind["clean"]) == 2                    # duplicate and rejected dropped
    assert all(case["expect"] == [] for case in by_kind["clean"])
    assert len(by_kind["planted"]) == 2
    for case in by_kind["planted"]:
        assert len(case["expect"]) == 1
        assert case["summary"] not in (CLEAN_MIXED, CLEAN_RISKY)
    assert len({case["case"] for case in cases}) == len(cases)


def _judged(kind, expect, flags=(), usable=True):
    checks = {check: {"found": check in flags, "quote": "x" if check in flags else ""}
              for check in faithfulness.JUDGE_CHECKS}
    return {"kind": kind, "expect": list(expect),
            "verdict": {"checks": checks, "unfaithful": bool(flags)} if usable else None}


def test_the_calibration_summary_counts_catches_and_false_alarms():
    records = (
        [_judged("planted", ["guesses_why"], ["guesses_why"])] * 6     # caught, named
        + [_judged("planted", ["adds_fact"], ["weighs_factors"])] * 2  # caught, misnamed
        + [_judged("known", ["weighs_factors"])] * 2                   # missed
        + [_judged("clean", [])] * 18
        + [_judged("clean", [], ["adds_fact"])] * 2                    # false alarm
        + [_judged("clean", [], usable=False)] * 1                     # unusable
    )
    summary = faithfulness.calibration_summary(records)
    assert summary["faulty"] == 10 and summary["clean"] == 21
    assert summary["recall"] == pytest.approx(0.8)
    assert summary["strict_recall"] == pytest.approx(0.6)
    assert summary["false_alarm"] == pytest.approx(0.1)   # 2 of the 20 it judged
    assert summary["errors"] == 1
    assert summary["recall_by_kind"] == {"known": 0.0, "planted": 1.0}
    assert summary["caught_by_check"]["guesses_why"] == (6, 6)
    assert summary["passes"] is True


@pytest.mark.parametrize("caught, alarms, passes", [
    (8, 2, True),     # exactly on both bars: 80% and 10%
    (7, 2, False),    # 70% caught
    (8, 3, False),    # 15% false alarms
])
def test_the_bar_is_eighty_percent_caught_and_ten_percent_false_alarms(caught, alarms, passes):
    records = (
        [_judged("planted", ["adds_fact"], ["adds_fact"])] * caught
        + [_judged("planted", ["adds_fact"])] * (10 - caught)
        + [_judged("clean", [], ["adds_fact"])] * alarms
        + [_judged("clean", [])] * (20 - alarms)
    )
    assert faithfulness.calibration_summary(records)["passes"] is passes


def test_an_unusable_reply_on_a_faulty_case_counts_as_a_miss():
    records = [_judged("planted", ["adds_fact"], usable=False)] * 2 + [_judged("clean", [])] * 5
    assert faithfulness.calibration_summary(records)["recall"] == 0.0


# ==========================================================================
# 13. Scoring
# ==========================================================================

def test_the_upper_bound_says_how_little_zero_in_fifty_proves():
    assert faithfulness.upper_bound(0, 50) == pytest.approx(0.0713, abs=5e-4)
    assert faithfulness.upper_bound(0, 300) == pytest.approx(0.0126, abs=5e-4)
    assert faithfulness.upper_bound(6, 300) == pytest.approx(0.043, abs=1e-3)
    assert faithfulness.upper_bound(0, 0) is None
    assert faithfulness.upper_bound(5, 5) == 1.0


def test_replay_reads_the_saved_text_with_todays_guards():
    retried = _result("r", attempts=[REJECTED, reply()])
    item = faithfulness.replay(retried)
    assert item["first_rejected"] == "hallucinated_number"
    assert item["final_rejected"] is None
    assert item["structured"]["summary"] == FAITHFUL


def test_a_result_served_from_the_cache_is_scored_not_crashed_on():
    """`narrate.py --save` files can hold cache hits, which have no attempts
    to re-check. They were accepted once; the code checks still read them."""
    guess = "This customer has a month-to-month contract, which may be why."
    cached = {**_result("cached", guess), "attempts": [], "cache_hit": True}
    item = faithfulness.replay(cached)
    assert item["first_rejected"] is None and item["final_rejected"] is None
    assert {f["type"] for f in item["findings"]} >= {"speculation"}
    summary = faithfulness.summarize([cached, _result("live")])
    assert summary["n"] == 2 and summary["accepted"] == 2
    assert summary["first_attempt_rejected"] == 0
    assert summary["findings"]["speculation"] == 1


def test_summarize_counts_each_case_once_per_finding_type():
    twice = "Their contract may, and might, be why they leave."
    cases = [_result("a"), _result("b", twice), _result("c", attempts=[REJECTED, REJECTED]),
             _result("d", attempts=[REJECTED, reply()])]
    summary = faithfulness.summarize(cases)
    assert summary["n"] == 4
    assert summary["accepted"] == 3
    assert summary["first_attempt_rejected"] == 2
    assert summary["first_attempt_by_type"] == {"hallucinated_number": 2}
    assert summary["final_rejected"] == 1
    assert summary["findings"]["speculation"] == 1       # two words, one case
    assert summary["bands"] == {"high": 4}
    assert summary["judged"] == 0


def _with_judge(result, text=CLEAN_VERDICT):
    parsed, problem = faithfulness.parse_verdict(text, result["structured"]["summary"])
    return {**result, "judge": {"verdict": parsed, "error": problem}}


def test_summarize_counts_the_judges_verdicts_and_its_unusable_replies():
    guess = "This customer has a month-to-month contract, which may reflect a wish to leave."
    cases = [
        _with_judge(_result("a")),
        _with_judge(_result("b", guess), verdict(guesses_why="may reflect a wish to leave")),
        _with_judge(_result("c"), "nonsense"),
    ]
    summary = faithfulness.summarize(cases)
    assert summary["judged"] == 3
    assert summary["judge_errors"] == 1
    assert summary["judge_unfaithful"] == 1
    assert summary["judge_by_check"]["guesses_why"] == 1
    assert summary["judge_by_check"]["adds_fact"] == 0


def test_flagged_cases_show_what_the_code_and_the_judge_each_said():
    guess = "This customer has a month-to-month contract, which may reflect a wish to leave."
    cases = [
        _with_judge(_result("clean")),
        _with_judge(_result("both", guess), verdict(guesses_why="may reflect a wish to leave")),
        _with_judge(_result("judge only"), verdict(adds_fact="month-to-month contract")),
    ]
    rows = {row["case"]: row for row in faithfulness.flagged_cases(cases)}
    assert set(rows) == {"both", "judge only"}
    assert rows["both"]["code"] == ["speculation: says 'may'"]
    assert rows["both"]["judge"] == ["guesses_why: 'may reflect a wish to leave'"]
    assert rows["judge only"]["code"] == []


def test_the_report_states_every_limit_and_lists_the_flagged_case():
    guess = "This customer has a month-to-month contract, which may reflect a wish to leave."
    cases = [_with_judge(_result("a")), _with_judge(_result("the guess", guess))]
    text = "\n".join(faithfulness.render_report(cases, {
        **faithfulness.current_meta(), "created": "2026-10-09", "n": 2,
        "judge": faithfulness.judge_meta(),
    }))
    for expected in ("limit 5%", "limit 1%", "limit 2% each",
                     "explanation_v5", "judge_v2", "gpt-6-luna (reasoning low)", "2026-10-09",
                     "speculation", "the guess", "could be as high as"):
        assert expected in text, expected
    # The judge's numbers are shown as a second opinion, with no limit beside them.
    judge_section = text[text.index("THE JUDGE'S DOUBLE CHECK"):text.index("FLAGGED CASES")]
    assert "not gated" in judge_section
    assert "limit" not in judge_section


def test_the_report_of_an_unjudged_run_says_so():
    text = "\n".join(faithfulness.render_report(
        [_result("a")], {**faithfulness.current_meta(), "created": "2026-10-09",
                         "n": 1, "judge": None}))
    assert "not judged" in text
    assert "double check  :" not in text


# ==========================================================================
# 14. The baseline and the gate
# ==========================================================================

def _baseline(tmp_path, results=None, judge=CLEAN_VERDICT, mutate=None):
    results = results if results is not None else [_result(f"case {i}") for i in range(300)]
    judged = [
        {"case": r["case"],
         **dict(zip(("verdict", "error"),
                    faithfulness.parse_verdict(judge, r["structured"]["summary"])))}
        for r in results if r["structured"] is not None
    ]
    baseline = faithfulness.build_baseline(results, judged, created="2026-10-09")
    if mutate:
        mutate(baseline)
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline))
    return path


def test_the_limits_are_the_ones_fixed_before_the_run():
    assert faithfulness.MIN_CASES == 300
    assert faithfulness.MAX_FIRST_ATTEMPT_REJECTION == 0.05
    assert faithfulness.MAX_FINAL_REJECTION == 0.01
    assert faithfulness.MAX_FINDING_RATE == 0.02
    assert faithfulness.CALIBRATION_MIN_RECALL == 0.80
    assert faithfulness.CALIBRATION_MAX_FALSE_ALARM == 0.10


def test_a_sound_baseline_passes(tmp_path):
    assert faithfulness.check_baseline(_baseline(tmp_path)) == []


def test_a_missing_baseline_fails_rather_than_skips(tmp_path):
    problems = faithfulness.check_baseline(tmp_path / "absent.json")
    assert len(problems) == 1 and "does not exist" in problems[0]


@pytest.mark.parametrize("content", ["not json", "[]", '{"meta": {}}'])
def test_a_file_that_is_not_a_baseline_fails(tmp_path, content):
    path = tmp_path / "baseline.json"
    path.write_text(content)
    problems = faithfulness.check_baseline(path)
    assert len(problems) == 1 and "is not a baseline" in problems[0]


@pytest.mark.parametrize("key, value", [
    ("prompt_sha256", "0" * 64),
    ("prompt_version", "explanation_v3"),
    ("model", "gpt-4o"),
    ("seed", 7),
    ("temperature", 0.7),
])
def test_a_baseline_measured_with_something_else_fails(tmp_path, key, value):
    path = _baseline(tmp_path, mutate=lambda b: b["meta"].__setitem__(key, value))
    problems = faithfulness.check_baseline(path)
    assert len(problems) == 1
    assert problems[0].startswith(f"{key}:")


def test_changing_the_prompt_fails_the_gate_until_it_is_measured(tmp_path, monkeypatch):
    """The point of the gate. The baseline is untouched; the code moved."""
    path = _baseline(tmp_path)
    monkeypatch.setattr(narrate, "PROMPT_PATH", REPO_ROOT / "prompts" / "explanation_v3.txt")
    problems = faithfulness.check_baseline(path)
    assert any(problem.startswith("prompt_sha256:") for problem in problems)


def test_fewer_than_three_hundred_cases_fails(tmp_path):
    path = _baseline(tmp_path, results=[_result(f"case {i}") for i in range(299)])
    assert faithfulness.check_baseline(path) == ["299 cases, fewer than the 300 required."]


def _mixed(clean, *others):
    """300 results: `clean` faithful ones, then each (count, kwargs) group."""
    results = [_result(f"clean {i}") for i in range(clean)]
    for group, (count, kwargs) in enumerate(others):
        results += [_result(f"group {group} case {i}", **kwargs) for i in range(count)]
    assert len(results) == 300
    return results


def test_first_attempt_rejections_at_the_limit_pass_and_over_it_fail(tmp_path):
    retried = {"attempts": [REJECTED, reply()]}
    at = _baseline(tmp_path, results=_mixed(285, (15, retried)))          # 5.0%
    assert faithfulness.check_baseline(at) == []
    over = _baseline(tmp_path, results=_mixed(284, (16, retried)))        # 5.3%
    problems = faithfulness.check_baseline(over)
    assert len(problems) == 1
    assert problems[0].startswith("rejected on the first attempt by today's guards: 16 of 300")


def test_final_rejections_at_the_limit_pass_and_over_it_fail(tmp_path):
    lost = {"attempts": [REJECTED, REJECTED]}
    at = _baseline(tmp_path, results=_mixed(297, (3, lost)))              # 1.0%
    assert faithfulness.check_baseline(at) == []
    over = _baseline(tmp_path, results=_mixed(296, (4, lost)))            # 1.3%
    assert any(p.startswith("no summary after the retry") for p in faithfulness.check_baseline(over))


@pytest.mark.parametrize("kind, summary, reasons", [
    ("speculation", "This customer has a month-to-month contract, which may be why.", None),
    ("weighing", "This customer leaves mainly because of their month-to-month contract.", None),
    ("degree_overstated", "They have a month-to-month contract and a much lower overall commitment.", None),
    ("direction_contradicted", "This customer has a month-to-month contract, which lowers their risk.", None),
    ("summary_reordered", "They have been a customer for 1 month on a month-to-month contract.", None),
    ("reasons_reordered", FAITHFUL, ["tenure", "contract"]),
])
def test_each_finding_at_the_limit_passes_and_over_it_fails(tmp_path, kind, summary, reasons):
    faulty = {"summary": summary}
    if reasons:
        faulty = {"attempts": [reply(FAITHFUL, RISKY, reasons)]}
    at = _baseline(tmp_path, results=_mixed(294, (6, faulty)))            # 2.0%
    assert faithfulness.check_baseline(at) == []
    over = _baseline(tmp_path, results=_mixed(293, (7, faulty)))          # 2.3%
    problems = faithfulness.check_baseline(over)
    assert [p.split(":")[0] for p in problems] == [kind]


def test_a_guard_that_starts_refusing_sound_answers_fails_the_gate(tmp_path, monkeypatch):
    """The baseline's answers are real ones the guards accepted. A guard
    changed to refuse them is caught here, against all 300."""
    path = _baseline(tmp_path)
    monkeypatch.setattr(narrate, "MAX_SUMMARY_CHARS", 20)
    problems = faithfulness.check_baseline(path)
    assert any(p.startswith("rejected on the first attempt by today's guards: 300 of 300")
               for p in problems)


# --------------------------------------------------------------------------
# The judge is a one-off double check of one run, not a part of the product.
# So the gate must not be able to fail because of it -- whatever it said,
# whether it ran at all, and whatever has happened to its prompt since.
# --------------------------------------------------------------------------

def _judge_swap(count, text):
    """Replace the first `count` cases' verdicts with the parse of `text`."""
    def mutate(baseline):
        for case in baseline["cases"][:count]:
            summary = json.loads(case["attempts"][-1]["text"])["summary"]
            parsed, problem = faithfulness.parse_verdict(text, summary)
            case["judge"] = {"verdict": parsed, "error": problem}
    return mutate


def test_what_the_judge_said_cannot_fail_the_gate(tmp_path):
    flagged = verdict(adds_fact="month-to-month contract")
    path = _baseline(tmp_path, mutate=_judge_swap(300, flagged))    # all "unfaithful"
    assert faithfulness.summarize(json.loads(path.read_text())["cases"])["judge_unfaithful"] == 300
    assert faithfulness.check_baseline(path) == []


def test_unusable_judge_replies_cannot_fail_the_gate(tmp_path):
    path = _baseline(tmp_path, mutate=_judge_swap(300, "nonsense"))
    assert faithfulness.check_baseline(path) == []


def test_a_run_nobody_judged_passes_the_gate(tmp_path):
    results = [_result(f"case {i}") for i in range(300)]
    baseline = faithfulness.build_baseline(results, created="2026-10-09")
    assert baseline["meta"]["judge"] is None
    assert all("judge" not in case for case in baseline["cases"])
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline))
    assert faithfulness.check_baseline(path) == []


def test_changing_or_removing_the_judge_cannot_fail_the_gate(tmp_path, monkeypatch):
    """A different judge model, a different effort, and a judge prompt that
    no longer exists: the baseline still vouches for the narration."""
    path = _baseline(tmp_path)
    monkeypatch.setattr(faithfulness, "JUDGE_MODEL", "some-other-model")
    monkeypatch.setattr(faithfulness, "JUDGE_REASONING_EFFORT", "high")
    monkeypatch.setattr(faithfulness, "JUDGE_PROMPT_PATH", tmp_path / "deleted.txt")
    assert faithfulness.check_baseline(path) == []


def test_the_gates_meta_holds_nothing_about_the_judge():
    assert set(faithfulness.current_meta()) == {
        "prompt_version", "prompt_sha256", "model", "temperature", "seed",
    }
    assert set(faithfulness.judge_meta()) == {
        "judge_model", "judge_reasoning_effort", "judge_prompt_version",
        "judge_prompt_sha256",
    }


def test_the_judge_is_never_called_by_the_serving_path():
    """It is a harness tool. Neither the narration layer nor the API may
    import the harness, or the judge would be one call away from a request."""
    import ast

    for module in ("api.py", "narrate.py", "explain.py", "narration_cache.py"):
        tree = ast.parse((REPO_ROOT / module).read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "faithfulness" not in imported, module


def test_a_slim_record_keeps_what_a_replay_needs_and_drops_the_rest():
    result = _result("a", attempts=[REJECTED, reply()])
    record = faithfulness.slim(result, {"verdict": None, "error": "x", "text": "raw"})
    assert set(record) == {"case", "payload", "attempts", "judge"}
    assert set(record["attempts"][0]) == {"attempt", "accepted", "rejection_type", "text"}
    assert record["judge"] == {"verdict": None, "error": "x"}
    # Enough to replay, and it gives the same answer as the full result.
    assert faithfulness.replay(record) == faithfulness.replay(result)
    assert "churn_probability" not in record and "contributions" not in record
    assert "judge" not in faithfulness.slim(result, None)


def test_a_baseline_cannot_be_written_from_a_run_of_another_prompt():
    old = {**_result("a"), "prompt_version": "explanation_v3"}
    with pytest.raises(ValueError, match="current prompt and model"):
        faithfulness.build_baseline([old], [])


def test_a_baseline_cannot_be_written_from_cached_answers():
    cached = {**_result("a"), "attempts": [], "cache_hit": True}
    with pytest.raises(ValueError, match="served from the cache"):
        faithfulness.build_baseline([_result("b"), cached])


def test_the_baseline_is_written_one_case_per_line_and_reads_back_whole(tmp_path):
    baseline = json.loads(_baseline(tmp_path, results=[_result(f"c{i}") for i in range(3)]).read_text())
    text = faithfulness.dump_baseline(baseline)
    assert json.loads(text) == baseline
    lines = text.splitlines()
    assert sum(line.startswith('  {"case"') for line in lines) == 3
    assert text.endswith("}\n")


def test_the_baselines_meta_is_what_the_gate_compares(tmp_path):
    baseline = json.loads(_baseline(tmp_path).read_text())
    assert baseline["meta"]["n"] == 300
    assert baseline["meta"]["created"] == "2026-10-09"
    for key, value in faithfulness.current_meta().items():
        assert baseline["meta"][key] == value
    # Which judge read the run is recorded, for whoever reads the report.
    assert baseline["meta"]["judge"] == faithfulness.judge_meta()
    assert baseline["meta"]["judge"]["judge_model"] == "gpt-6-luna"
    assert baseline["meta"]["prompt_sha256"] == hashlib.sha256(
        (REPO_ROOT / "prompts" / "explanation_v5.txt").read_bytes()).hexdigest()


# ==========================================================================
# 15. The command line
# ==========================================================================

def test_default_files_are_inside_the_repository_wherever_the_command_runs():
    """A relative default would start a second paid run in another folder."""
    outputs = REPO_ROOT / "outputs"
    assert Path(faithfulness.RUN_PATH) == outputs / "harness_v5.json"
    # One folder down, so LLMcalls.ipynb -- which reads every outputs/*.json
    # as a saved run -- never opens a file of verdicts.
    assert Path(faithfulness.JUDGED_PATH) == outputs / "judge" / "harness_v5_judged.json"
    assert not list(outputs.glob("*judge*.json"))
    assert faithfulness.SAMPLE_PATH == outputs / "harness_customers.csv"
    assert faithfulness.BASELINE_PATH == REPO_ROOT / "docs" / "faithfulness_baseline.json"


def test_check_exits_non_zero_and_says_why(tmp_path, capsys):
    code = faithfulness.main(["check", "--baseline", str(tmp_path / "absent.json")])
    assert code == 1
    assert "does not exist" in capsys.readouterr().err


def test_check_exits_zero_on_a_sound_baseline(tmp_path, capsys):
    assert faithfulness.main(["check", "--baseline", str(_baseline(tmp_path))]) == 0
    assert "OK" in capsys.readouterr().out


def test_score_prints_a_report_for_a_saved_run(tmp_path, capsys):
    path = tmp_path / "run.json"
    path.write_text(json.dumps([_result("a"), _result("b")]))
    assert faithfulness.main(["score", str(path)]) == 0
    out = capsys.readouterr().out
    assert "FAITHFULNESS REPORT" in out and "not judged" in out


def test_the_paid_commands_stop_without_a_key_before_doing_anything(tmp_path, capsys, simulated):
    """conftest removes OPENAI_API_KEY for every test not marked live."""
    csv = _sample_csv(tmp_path, simulated)
    out = tmp_path / "out.json"
    assert faithfulness.main(["run", "--csv", str(csv), "--out", str(out)]) == 2
    assert not out.exists() and not faithfulness._partial(out).exists()
    printed = capsys.readouterr()
    assert "3 customers" in printed.out          # the cost is stated first
    assert "OPENAI_API_KEY" in printed.err or "openai package" in printed.err


def test_baseline_writes_both_files_and_runs_the_gate(tmp_path, capsys):
    results = [_result(f"case {i}") for i in range(300)]
    judged = [{"case": r["case"],
               **dict(zip(("verdict", "error"),
                          faithfulness.parse_verdict(CLEAN_VERDICT, FAITHFUL)))} for r in results]
    run_path, judged_path = tmp_path / "run.json", tmp_path / "judged.json"
    run_path.write_text(json.dumps(results))
    judged_path.write_text(json.dumps(judged))
    out, report = tmp_path / "baseline.json", tmp_path / "report.txt"
    code = faithfulness.main([
        "baseline", "--run", str(run_path), "--judged", str(judged_path),
        "--sample", str(tmp_path / "no-sample.csv"), "--out", str(out), "--report", str(report),
    ])
    assert code == 0
    assert faithfulness.check_baseline(out) == []
    assert "FAITHFULNESS REPORT" in report.read_text()
    assert out.stat().st_size < 300 * 2500       # slim: well under 2.5 KB a case


def test_baseline_can_be_written_without_any_judging(tmp_path):
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps([_result(f"case {i}") for i in range(300)]))
    out, report = tmp_path / "baseline.json", tmp_path / "report.txt"
    code = faithfulness.main([
        "baseline", "--run", str(run_path), "--judged", str(tmp_path / "never-judged.json"),
        "--sample", str(tmp_path / "no-sample.csv"), "--out", str(out), "--report", str(report),
    ])
    assert code == 0
    assert "not judged" in report.read_text()


# ==========================================================================
# 16. THE GATE ITSELF
#
# Everything above tests the gate against baselines built for the purpose.
# This is the one test that reads the committed one, and it is what CI runs.
# It is not skipped when the file is missing: a gate that passes once its
# evidence is deleted is not a gate.
# ==========================================================================

def test_the_committed_baseline_vouches_for_the_code_as_it_is():
    """Fails when the explanation prompt, the model, the seed or the
    temperature differs from what was measured; when a guard or a check, as
    it is today, puts the 300 saved answers over a limit; or when
    docs/faithfulness_baseline.json is gone.

    If this fails after a prompt change, that is the gate working: run
    `faithfulness.py sample`, `run` and `baseline` for the new prompt. If it
    fails after a guard change, read the message -- it names the rate that
    moved -- before deciding whether the guard or the limit is wrong.
    """
    problems = faithfulness.check_baseline()
    assert problems == [], "\n".join(problems)


def test_the_committed_baseline_is_the_300_customer_run():
    baseline = json.loads(faithfulness.BASELINE_PATH.read_text())
    assert baseline["meta"]["n"] == len(baseline["cases"]) == 300
    bands = {}
    for case in baseline["cases"]:
        bands[case["payload"]["risk_level"]] = bands.get(case["payload"]["risk_level"], 0) + 1
    assert bands == {"low": 133, "moderate": 77, "high": 57, "very high": 33}
    # No customer rows: only what the language model could be shown.
    assert all(set(case) <= {"case", "payload", "attempts", "judge"} for case in baseline["cases"])
