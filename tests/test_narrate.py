"""Tests for narrate.py. No API key, no network, no cost.

The narration layer is the first part of this project whose output cannot be
checked by assertion -- an LLM writes it. What CAN be checked is everything
around it, and that is what this file does: the payload the model is shown,
the guards its output must pass, the retry bookkeeping, and the three rates.
The model itself is a `FakeLLM` from tests/conftest.py, scripted with canned
responses, so every path including "both attempts rejected" is exercised
deterministically.

Weighted toward the failures the module exists to stop, all silent:

  1. AN INVENTED DRIVER. Every guard is tested in both directions -- output
     that names an unlisted factor must be rejected, and output that names a
     listed factor by a paraphrase must NOT be. A guard that rejects
     everything would pass a one-directional suite and make the feature
     useless.

  2. A PROTECTED ATTRIBUTE AS A REASON. Tested at both layers: absent from
     the payload (the control) and rejected in the output anyway (the
     backstop), in both the structured reasons and the prose summary.

  3. A MISDESCRIBED VALUE. The failure the first live run found (customer row
     7, "a lower total charged" for $5,762.95). Pinned as a regression test
     below, along with the three v1 guard false positives ("unlikely to
     churn", "not at risk of leaving", "a single month").

As in tests/test_explain.py: never phrase an assertion in terms of the
constant it is testing. MAX_ATTEMPTS, MAX_SUMMARY_CHARS, NARRATION_TOP_N and
the prompt hash are compared against literals.

Run with: pytest tests/test_narrate.py -v
"""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

import explain
import narrate
import narration_cache
from tests.conftest import FakeLLM

# The prompt this suite was written against. Pinned so that editing the
# wording without bumping PROMPT_VERSION fails here: every rejection rate ever
# recorded is a measurement OF a specific prompt.
PROMPT_SHA256 = "fac2052f60a23383f90da374aa3e34ef6d80a4f6f98145f020e9a12d7eb9a89e"

# Earlier versions, kept unused because live results measure them: v1 in
# CHANGELOG.md, v2 in CHANGELOG.md and outputs/stage1_v2.json.
PROMPT_V1_SHA256 = "00d47880a6d95a9792b3c89bc89725d46cd14d3b6b19467290f149763cdd941f"
PROMPT_V2_SHA256 = "b1f98f68c418440b559d5e23f3e24b47adfb4ba0256cf81f26464d4d678c595d"
# v3 shipped from 2026-09-17 to 2026-10-07; stage1_v3.json and stage2_v3.json
# (50 customers) measure it.
PROMPT_V3_SHA256 = "65b5fb869bdd43b41a425daa18045edddcb8cc188d499cbc088541915f47e168"

GOOD_SUMMARY = (
    "This customer is on a month-to-month contract and has been with us only "
    "a short time, so there is little holding them."
)


def reply(summary=GOOD_SUMMARY, risk_level="high",
          reasons=(("contract", "raises risk"), ("tenure", "raises risk"))):
    """A model response in v2's JSON shape."""
    return json.dumps({
        "risk_level": risk_level,
        "reasons": [{"field": f, "direction": d} for f, d in reasons],
        "summary": summary,
    })


GOOD = reply()


# ==========================================================================
# Synthetic explanations
#
# Hand-built rather than produced from the real pickle, so these tests are
# fast. The shape matches explain.explain_customer()'s output; REFERENCE uses
# the shipped model's real training medians and spreads (pinned separately in
# tests/test_explain.py), so the comparisons below are the ones production
# would make.
# ==========================================================================

REFERENCE = {
    "seniorcitizen": {"median": 0.0, "spread": 0.369},
    "tenure": {"median": 29.0, "spread": 24.517},
    "monthlycharges": {"median": 70.45, "spread": 30.053},
    "totalcharges": {"median": 1396.0, "spread": 2273.855},
    "total_services": {"median": 2.0, "spread": 1.845},
    "is_auto_pay": {"median": 0.0, "spread": 0.496},
    "family_tie": {"median": 1.0, "spread": 0.499},
    "contractvstenure": {"median": 37.0, "spread": 71.418},
    "average_monthly_charges": {"median": 70.499, "spread": 30.173},
    "charge_change_ratio": {"median": 1.0, "spread": 0.052},
}

DEFAULT_DRIVERS = [
    ("contract", "Month-to-month", 0.5953),
    ("tenure", 1, 0.4312),
    ("seniorcitizen", 1, 0.3100),
    ("internetservice", "Fiber optic", 0.2456),
    ("totalcharges", 210.5, -0.1200),
    ("techsupport", "No", 0.0900),
]


def make_explanation(drivers=None, probability=0.57, threshold=0.4):
    drivers = DEFAULT_DRIVERS if drivers is None else drivers
    return {
        "churn_probability": probability,
        "target_for_retention": probability >= threshold,
        "threshold_used": threshold,
        "drivers": [
            {
                "field": field,
                "label": explain.FIELD_LABELS[field],
                "value": value,
                "contribution": contribution,
                "direction": (
                    "increases" if contribution > 0
                    else "decreases" if contribution < 0 else "neutral"
                ),
                "engineered": field in explain.ENGINEERED_FEATURES,
            }
            for field, value, contribution in drivers
        ],
        "contributions": {f: c for f, _, c in drivers},
        "bias": -0.8718,
        "margin": 0.2818,
        "reconstruction_error": 5.1e-08,
        "reference": REFERENCE,
    }


def payload_for(drivers, probability=0.57):
    return narrate.narration_payload(make_explanation(drivers, probability=probability))


@pytest.fixture
def explanation():
    return make_explanation()


@pytest.fixture
def payload(explanation):
    return narrate.narration_payload(explanation)


def verdict(output, payload):
    """Just the rejection type (None when accepted)."""
    return narrate.validate_narrative(output, payload)[1]


# Customer row 7 of simulated_new_customers.csv, as the stage-1 live run saw
# it: total charged $5,762.95, which lowered their risk.
ROW_7_DRIVERS = [
    ("contract", "Two year", -0.9000),
    ("totalcharges", 5762.95, -0.3000),
    ("tenure", 68, -0.2000),
]


# ==========================================================================
# 1. The payload: what the model is allowed to see
# ==========================================================================

def test_protected_drivers_are_absent_from_the_payload(payload):
    """The control. A rule in a prompt is a request; removing the
    information is the thing that actually works."""
    fields = {factor["field"] for factor in payload["factors"]}
    assert not fields & narrate.PROTECTED_FIELDS


def test_protected_drivers_are_still_in_the_explanation(explanation):
    fields = {driver["field"] for driver in explanation["drivers"]}
    assert "seniorcitizen" in fields


def test_omitted_protected_drivers_are_named(payload):
    assert payload["protected_drivers_omitted"] == ["seniorcitizen"]


def test_only_protected_drivers_that_outranked_a_shown_factor_are_omitted():
    """v1 listed every protected driver in the explanation, and with the full
    25-driver list that was all five on every customer -- no information. A
    protected driver ranked below the last shown factor would not have been
    shown anyway, so it was not withheld."""
    drivers = DEFAULT_DRIVERS + [("gender", "Female", 0.0010)]
    assert payload_for(drivers)["protected_drivers_omitted"] == ["seniorcitizen"]


def test_top_n_is_applied_after_protected_filtering():
    """A protected driver must not consume one of the slots."""
    payload = payload_for(DEFAULT_DRIVERS)
    assert [f["field"] for f in payload["factors"]] == [
        "contract", "tenure", "internetservice",
    ]


def test_the_model_is_shown_three_factors_by_default():
    assert narrate.NARRATION_TOP_N == 3


def test_a_zero_contribution_driver_is_not_shown():
    """It has no direction to state."""
    drivers = [("contract", "Month-to-month", 0.5), ("techsupport", "No", 0.0),
               ("tenure", 1, 0.2)]
    assert [f["field"] for f in payload_for(drivers)["factors"]] == ["contract", "tenure"]


def test_the_payload_has_exactly_these_keys(payload):
    assert set(payload) == {
        "risk_level", "decision", "target_for_retention", "factors",
        "protected_drivers_omitted",
    }


def test_factor_directions_are_stated_in_words(payload):
    assert {f["direction"] for f in payload["factors"]} == {"raises risk"}
    lowered = payload_for(ROW_7_DRIVERS, probability=0.05)
    assert {f["direction"] for f in lowered["factors"]} == {"lowers risk"}


def test_messages_carry_no_probability_weight_or_protected_field(payload):
    """v1 sent the raw score and the model quoted it as "61.51%". v2 sends a
    band. Weights are not sent either -- the order of the list is the
    ranking. Checked in the user turn: the system prompt itself says "never
    mention weights"."""
    rendered = narrate.build_messages(payload)[1]["content"]
    for forbidden in ("0.57", "churn_risk", "0.5953", "weight",
                      "protected_drivers_omitted", "seniorcitizen",
                      "target_for_retention", "decision", "target for retention"):
        assert forbidden not in rendered, forbidden


def test_the_user_turn_is_the_sent_part_of_the_payload(payload):
    sent = json.loads(narrate.build_messages(payload)[1]["content"])
    assert sent == {"risk_level": "high", "factors": payload["factors"]}


def test_the_decision_is_kept_in_the_payload_but_not_sent(payload):
    """Since v3. The band already agrees with the decision by construction,
    and v2, which was sent the decision, commented on it in 7 of 8 live
    outputs. The payload keeps it for the guards and for reviewers."""
    assert payload["decision"] == "target for retention"
    assert "decision" not in json.loads(narrate.build_messages(payload)[1]["content"])


def test_payload_states_the_decision_both_ways():
    assert payload_for(DEFAULT_DRIVERS, 0.9)["decision"] == "target for retention"
    assert payload_for(DEFAULT_DRIVERS, 0.1)["decision"] == "do not target"


@pytest.mark.parametrize("probability, expected", [
    (0.0, "low"), (0.1999, "low"), (0.20, "moderate"), (0.3999, "moderate"),
    (0.40, "high"), (0.6999, "high"), (0.70, "very high"), (1.0, "very high"),
])
def test_risk_bands_at_the_shipped_threshold(probability, expected):
    assert narrate.risk_level(probability, 0.4) == expected


@pytest.mark.parametrize("threshold", [0.25, 0.4, 0.55])
def test_a_band_can_never_disagree_with_the_decision(threshold):
    """High bands are exactly the targeted customers, at any threshold."""
    for i in range(1001):
        probability = i / 1000
        band = narrate.risk_level(probability, threshold)
        assert (band in {"high", "very high"}) == (probability >= threshold)


@pytest.mark.parametrize("value, expected", [
    (29, "similar to most customers"), (35, "similar to most customers"),
    (40, "higher than most customers"), (60, "much higher than most customers"),
    (20, "lower than most customers"), (1, "much lower than most customers"),
])
def test_compare_to_typical_uses_training_spreads(value, expected):
    """tenure: median 29, spread 24.5 -- a quarter spread is ~6 months."""
    assert narrate.compare_to_typical(value, 29.0, 24.517) == expected


def test_compare_to_typical_survives_a_zero_spread():
    assert narrate.compare_to_typical(5, 5, 0) == "similar to most customers"


def test_row_7s_total_charged_is_described_as_much_higher_than_most():
    """The stage-1 regression. The model called $5,762.95 "lower" because it
    had nothing to compare it with; now the comparison is in the payload."""
    factors = {f["field"]: f for f in payload_for(ROW_7_DRIVERS, 0.05)["factors"]}
    assert factors["totalcharges"]["value"] == 5762.95
    assert factors["totalcharges"]["vs_other_customers"] == "much higher than most customers"
    assert factors["tenure"]["vs_other_customers"] == "much higher than most customers"


def test_categorical_factors_get_no_comparison(payload):
    contract = payload["factors"][0]
    assert contract == {
        "name": "contract type", "field": "contract",
        "direction": "raises risk", "value": "Month-to-month",
    }


def test_a_yes_no_flag_is_sent_as_words_without_a_comparison():
    """A median of 0 would make every autopay customer "much higher than most"."""
    factor = payload_for([("is_auto_pay", 1, -0.3)])["factors"][0]
    assert factor["value"] == "yes"
    assert "vs_other_customers" not in factor


def test_a_meaningless_engineered_value_is_compared_but_not_sent():
    factor = payload_for([("contractvstenure", 136, -0.3)])["factors"][0]
    assert "value" not in factor
    assert factor["vs_other_customers"] == "much higher than most customers"


def test_float_values_are_rounded_for_the_model():
    factor = payload_for([("average_monthly_charges", 84.749265, 0.1)])["factors"][0]
    assert factor["value"] == 84.75


def test_the_real_dummy_customer_payload():
    """End to end from the shipped artifact: the reference points reach the
    payload, and no protected field is reported as withheld when none
    outranked the shown factors."""
    import config

    real = explain.explain_customer(config.DUMMY_CUSTOMER, top_n=None)
    payload = narrate.narration_payload(real)
    assert payload["risk_level"] == "high"
    assert payload["protected_drivers_omitted"] == []
    by_field = {f["field"]: f for f in payload["factors"]}
    assert list(by_field) == ["contract", "contractvstenure", "tenure"]
    assert by_field["tenure"]["vs_other_customers"] == "much lower than most customers"


# ==========================================================================
# 2. The prompt and the request
# ==========================================================================

def test_prompt_file_exists_and_is_not_empty():
    assert narrate.PROMPT_PATH.exists()
    assert narrate.load_prompt().strip()


def test_prompt_version_is_the_prompt_filename():
    assert narrate.PROMPT_VERSION == narrate.PROMPT_PATH.stem


def test_prompt_text_is_pinned():
    """Editing the prompt without bumping PROMPT_VERSION fails here. To change
    the prompt: write a new versioned file, update PROMPT_SHA256, and
    re-measure."""
    actual = hashlib.sha256(narrate.PROMPT_PATH.read_bytes()).hexdigest()
    assert actual == PROMPT_SHA256, (
        f"prompts/{narrate.PROMPT_VERSION}.txt has changed.\n"
        f"  expected {PROMPT_SHA256}\n"
        f"  actual   {actual}\n"
        f"Bump the prompt version, update PROMPT_SHA256, and re-measure the "
        f"rejection rates -- the old ones no longer describe this prompt."
    )


@pytest.mark.parametrize("version, sha", [
    ("explanation_v1", PROMPT_V1_SHA256), ("explanation_v2", PROMPT_V2_SHA256),
    ("explanation_v3", PROMPT_V3_SHA256),
])
def test_earlier_prompts_are_kept_unchanged(version, sha):
    """Live results in CHANGELOG.md and outputs/ are measurements of these."""
    path = narrate.REPO_ROOT / "prompts" / f"{version}.txt"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha


def test_messages_are_a_system_turn_then_a_user_turn(payload):
    messages = narrate.build_messages(payload)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == narrate.load_prompt()


def test_the_prompt_version_travels_with_every_result(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    assert result["prompt_version"] == "explanation_v5"


def test_the_request_asks_for_strict_json_and_caps_output_tokens(explanation):
    client = FakeLLM([GOOD])
    narrate.narrate(explanation, client=client)
    call = client.calls[0]
    assert call["max_tokens"] == 250
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["strict"] is True


def test_the_schema_enums_match_the_guards_vocabulary():
    """The API enforces the schema and the guard enforces its own lists; if
    they drift, the API could force an answer the guard always rejects."""
    schema = narrate.RESPONSE_FORMAT["json_schema"]["schema"]
    assert schema["properties"]["risk_level"]["enum"] == [
        "low", "moderate", "high", "very high",
    ]
    item = schema["properties"]["reasons"]["items"]
    assert item["properties"]["direction"]["enum"] == ["raises risk", "lowers risk"]
    assert set(schema["required"]) == {"risk_level", "reasons", "summary"}
    assert schema["additionalProperties"] is False
    assert item["additionalProperties"] is False


# ==========================================================================
# 3. Field aliases
# ==========================================================================

def test_every_feature_column_has_aliases():
    missing = set(explain.FIELD_LABELS) - set(narrate.FIELD_ALIASES)
    assert not missing, f"no aliases for: {sorted(missing)}"


def test_no_alias_maps_to_two_fields():
    seen = {}
    for field, aliases in narrate.FIELD_ALIASES.items():
        for alias in aliases:
            assert alias not in seen, (
                f"{alias!r} is claimed by both {seen[alias]} and {field}"
            )
            seen[alias] = field


def test_aliases_are_lowercase_and_stripped():
    for field, aliases in narrate.FIELD_ALIASES.items():
        for alias in aliases:
            assert alias == alias.lower().strip(), f"{field}: {alias!r}"


def test_every_protected_field_has_aliases():
    assert narrate.PROTECTED_FIELDS <= set(narrate.FIELD_ALIASES)


def test_matching_is_case_insensitive():
    assert narrate.fields_mentioned("Month-to-Month CONTRACT") == {"contract"}


def test_the_longest_alias_wins_an_overlapping_span():
    assert narrate.fields_mentioned("their average monthly bill") == {
        "average_monthly_charges"
    }


def test_an_alias_does_not_match_inside_a_longer_word():
    assert narrate.fields_mentioned("the backups are fine") == set()
    assert narrate.fields_mentioned("their backup service") == {"onlinebackup"}


def test_unrelated_prose_names_no_fields():
    assert narrate.fields_mentioned("Worth an early call from the team.") == set()


def test_the_commitment_label_says_it_is_a_product():
    """v2's label, "contract length weighted by tenure", was retold live as
    "contract length compared to tenure" in 4 of 8 outputs. The feature is
    contract rank times months, and the label now says so."""
    label = explain.FIELD_LABELS["contractvstenure"]
    assert "×" in label and "commitment" in label


def test_commitment_phrases_name_the_engineered_feature_not_the_contract():
    assert narrate.fields_mentioned("their overall commitment is low") == {"contractvstenure"}
    assert narrate.fields_mentioned("their commitment level is low") == {"contractvstenure"}
    assert narrate.fields_mentioned("they have no commitment") == {"contract"}


def test_bare_commitment_names_no_field():
    """v3 live false positive: "commitment" alone mapped to contractvstenure,
    so a sentence about the contract was rejected as naming an unlisted
    factor."""
    assert narrate.fields_mentioned("which offers less commitment") == set()


def test_less_commitment_from_a_contract_is_accepted():
    """The v3 live reply's own wording, for a payload without contractvstenure."""
    payload = payload_for([("contract", "Month-to-month", 0.6), ("tenure", 1, 0.4)])
    output = reply(
        summary="This customer is on a month-to-month contract, which offers less "
                "commitment, and has been a customer for 1 month.",
    )
    assert verdict(output, payload) is None


def test_a_single_month_is_not_a_marital_status():
    """v1 false positive: the bare alias "single" mapped to partner."""
    assert narrate.fields_mentioned("after a single month") == set()


def test_being_single_is_still_a_marital_status():
    assert narrate.fields_mentioned("this customer is single") == {"partner"}


# ==========================================================================
# 4. Parsing: malformed output
# ==========================================================================

@pytest.mark.parametrize("output, detail", [
    ("This customer is on a month-to-month contract.", "not valid JSON"),
    ("```json\n" + GOOD + "\n```", "not valid JSON"),
    ("[1, 2]", "expected a JSON object"),
    (json.dumps({"risk_level": "high", "summary": "x"}), "keys were"),
    (json.dumps({**json.loads(GOOD), "confidence": 0.9}), "keys were"),
    (reply(risk_level="extreme"), "risk_level"),
    (reply(summary="   "), "summary is missing or blank"),
    (reply(reasons=()), "non-empty list"),
    (reply(reasons=(("contract", "raises risk"), ("tenure", "raises risk"),
                    ("internetservice", "raises risk"), ("techsupport", "raises risk"))),
     "4 reasons given for 3 factors"),
    (reply(reasons=(("contract", "up"),)), "direction"),
    (reply(reasons=(("contract", "raises risk"), ("contract", "raises risk"))), "repeated"),
    (json.dumps({"risk_level": "high", "summary": "x",
                 "reasons": [{"field": "contract"}]}), "exactly field and direction"),
    (json.dumps({"risk_level": "high", "summary": "x",
                 "reasons": [{"field": 3, "direction": "raises risk"}]}), "not a string"),
])
def test_malformed_output_is_rejected_with_a_reason(output, detail, payload):
    _, rejection_type, message = narrate.validate_narrative(output, payload)
    assert rejection_type == "malformed_output"
    assert detail in message


def test_a_reply_truncated_by_the_token_cap_is_malformed(payload):
    assert verdict(GOOD[:40], payload) == "malformed_output"


# ==========================================================================
# 5. The guards, in both directions
# ==========================================================================

def test_accepts_a_faithful_output(payload):
    parsed, rejection_type, _ = narrate.validate_narrative(GOOD, payload)
    assert rejection_type is None
    assert parsed == json.loads(GOOD)


def test_the_accepted_summary_is_stripped(payload):
    parsed, _, _ = narrate.validate_narrative(reply(summary=f"  {GOOD_SUMMARY}  "), payload)
    assert parsed["summary"] == GOOD_SUMMARY


def test_accepts_a_subset_of_the_factors_as_reasons(payload):
    assert verdict(reply(reasons=(("contract", "raises risk"),)), payload) is None


def test_accepts_a_factor_value_quoted_verbatim(payload):
    summary = "This customer has been with us for 1 month on a month-to-month contract."
    assert verdict(reply(summary=summary), payload) is None


def test_accepts_a_rounded_factor_value():
    payload = payload_for([("totalcharges", 4863.85, 0.3)])
    output = reply(summary="They have paid $4,864 in total charges.",
                   reasons=(("totalcharges", "raises risk"),))
    assert verdict(output, payload) is None


def test_rejects_an_unlisted_field_in_the_reasons(payload):
    """Exact, not alias-matched: this is what the structured output buys."""
    output = reply(reasons=(("contract", "raises risk"), ("monthlycharges", "raises risk")))
    _, rejection_type, detail = narrate.validate_narrative(output, payload)
    assert rejection_type == "unlisted_field"
    assert "monthlycharges" in detail


def test_rejects_an_unlisted_field_in_the_summary(payload):
    output = reply(summary="Their lack of tech support and high monthly bill drive the risk.")
    _, rejection_type, detail = narrate.validate_narrative(output, payload)
    assert rejection_type == "unlisted_field"
    assert "monthlycharges" in detail


def test_rejects_a_protected_field_in_the_reasons(payload):
    """Also unlisted by construction; must be bucketed as protected."""
    output = reply(reasons=(("seniorcitizen", "raises risk"),))
    assert verdict(output, payload) == "protected_attribute"


def test_rejects_a_protected_attribute_in_the_summary(payload):
    output = reply(summary="This senior citizen is on a month-to-month contract.")
    _, rejection_type, detail = narrate.validate_narrative(output, payload)
    assert rejection_type == "protected_attribute"
    assert "seniorcitizen" in detail


def test_rejects_a_gendered_pronoun(payload):
    output = reply(summary="She is on a month-to-month contract and should be called.")
    assert verdict(output, payload) == "protected_attribute"


def test_neutral_pronouns_are_accepted(payload):
    output = reply(summary="They are on a month-to-month contract and joined a short time ago.")
    assert verdict(output, payload) is None


def test_a_pronoun_inside_a_longer_word_is_not_a_mention():
    assert narrate.fields_mentioned("there is this shelf and other history") == set()


def test_the_protected_check_runs_before_the_unlisted_check(payload):
    output = reply(summary="This senior citizen has a high monthly bill.")
    assert verdict(output, payload) == "protected_attribute"


def test_a_field_named_inside_a_factors_own_label_is_licensed():
    """The average_monthly_charges label says 'tenure'. Echoing a label it
    was handed cannot be a hallucination."""
    payload = payload_for([
        ("contract", "Month-to-month", 0.5900),
        ("average_monthly_charges", 105.7, 0.2500),
    ])
    output = reply(
        summary="Their average monthly bill across their whole tenure is high, "
                "alongside a month-to-month contract.",
        reasons=(("contract", "raises risk"), ("average_monthly_charges", "raises risk")),
    )
    assert verdict(output, payload) is None


def test_licensing_extends_only_to_what_the_labels_actually_say(payload):
    output = reply(summary="Their lack of online security is what drives this.")
    assert verdict(output, payload) == "unlisted_field"


def test_rejects_the_probability_as_a_percentage(payload):
    """v1 allowed it and the model wrote "61.51%" for an uncalibrated score.
    v2 never sends the probability, so any percentage is invented."""
    output = reply(summary="At 57% risk, this month-to-month customer is worth a call.")
    assert verdict(output, payload) == "hallucinated_number"


def test_rejects_a_number_that_is_nowhere_in_the_payload(payload):
    output = reply(summary="This month-to-month customer has churned 3 times before.")
    _, rejection_type, detail = narrate.validate_narrative(output, payload)
    assert rejection_type == "hallucinated_number"
    assert "3" in detail


def test_rejects_empty_output(payload):
    assert verdict("", payload) == "empty_output"
    assert verdict("   \n ", payload) == "empty_output"


def test_rejects_an_overlong_summary(payload):
    output = reply(summary="They are on a month-to-month contract. " * 12)
    assert verdict(output, payload) == "overlong_output"


def test_the_summary_limit_is_four_hundred_characters():
    assert narrate.MAX_SUMMARY_CHARS == 400


def test_rejects_a_risk_level_that_differs_from_the_payload(payload):
    assert verdict(reply(risk_level="very high"), payload) == "decision_contradiction"


def test_rejects_prose_that_contradicts_a_flagged_decision(payload):
    output = reply(summary="This month-to-month customer is unlikely to churn.")
    assert verdict(output, payload) == "decision_contradiction"


UNFLAGGED_REASONS = (("contract", "raises risk"),)


def test_rejects_prose_that_contradicts_an_unflagged_decision():
    payload = payload_for(DEFAULT_DRIVERS, probability=0.1)
    output = reply(summary="This month-to-month customer is likely to churn.",
                   risk_level="low", reasons=UNFLAGGED_REASONS)
    assert verdict(output, payload) == "decision_contradiction"


@pytest.mark.parametrize("summary", [
    "Despite a month-to-month contract, this customer is unlikely to churn.",
    "Despite a month-to-month contract, this customer is not at risk of leaving.",
    "This month-to-month customer is low risk and needs no call.",
])
def test_low_risk_language_is_fine_for_a_customer_left_alone(summary):
    """v1 false positives, the first two: "unlikely to churn" contains
    "likely to churn" and "not at risk of leaving" contains "at risk of
    leaving", and a substring check rejected both as contradictions."""
    payload = payload_for(DEFAULT_DRIVERS, probability=0.1)
    output = reply(summary=summary, risk_level="low", reasons=UNFLAGGED_REASONS)
    assert verdict(output, payload) is None


@pytest.mark.parametrize("summary, said", [
    # Verbatim endings from v2's live run (outputs/stage1_v2.json).
    ("They are on a month-to-month contract. Therefore, I agree with the decision to not target them.", "i"),
    ("They are on a month-to-month contract. Therefore, the decision to not target them is appropriate.", "decision"),
    ("They are on a month-to-month contract. Targeting them for retention is a suitable decision.", "suitable"),
    ("We should reach out, given their month-to-month contract.", "we"),
])
def test_commentary_on_the_decision_is_rejected(summary, said, payload):
    _, rejection_type, detail = narrate.validate_narrative(reply(summary=summary), payload)
    assert rejection_type == "commentary"
    assert repr(said) in detail


@pytest.mark.parametrize("summary", [
    "They have been with us only a short time on a month-to-month contract.",
    "This customer has had a month-to-month contract for a single month.",
    "Their month-to-month contract gives them little reason to stay.",
])
def test_explaining_why_is_not_commentary(summary, payload):
    """The other direction: "with us", "stay" and pronoun-like fragments
    inside words must not trip the check."""
    assert verdict(reply(summary=summary), payload) is None


def test_a_contradiction_is_reported_before_commentary(payload):
    """A flagged customer called unlikely to churn is the worse failure."""
    output = reply(summary="This month-to-month customer is unlikely to churn, so I agree.")
    assert verdict(output, payload) == "decision_contradiction"


def test_rejects_a_reason_whose_direction_is_wrong(payload):
    output = reply(reasons=(("contract", "lowers risk"),))
    _, rejection_type, detail = narrate.validate_narrative(output, payload)
    assert rejection_type == "misstated_factor"
    assert "contract" in detail


ROW_7_REASONS = (("contract", "lowers risk"), ("totalcharges", "lowers risk"))


def test_row_7_lower_total_charged_is_rejected():
    """The stage-1 regression, verbatim phrasing from the live run."""
    payload = payload_for(ROW_7_DRIVERS, probability=0.05)
    output = reply(
        summary="This customer is on a two-year contract, and the fact that they "
                "have a lower total charged to date also reduces their risk.",
        risk_level="low", reasons=ROW_7_REASONS,
    )
    _, rejection_type, detail = narrate.validate_narrative(output, payload)
    assert rejection_type == "misstated_factor"
    assert "totalcharges" in detail and "lower" in detail


@pytest.mark.parametrize("summary, expected", [
    ("Their high total charges and two-year contract keep them loyal.", None),
    ("They have substantial total charges on a two-year contract.", None),
    ("Their total charges are low on a two-year contract.", "misstated_factor"),
    ("A small total spend and a two-year contract keep them.", "misstated_factor"),
])
def test_size_words_must_agree_with_the_comparison(summary, expected):
    payload = payload_for(ROW_7_DRIVERS, probability=0.05)
    output = reply(summary=summary, risk_level="low", reasons=ROW_7_REASONS)
    assert verdict(output, payload) == expected


BILL_AND_TENURE = [("monthlycharges", 105.0, 0.4), ("tenure", 1, 0.3)]
BILL_AND_TENURE_REASONS = (("monthlycharges", "raises risk"), ("tenure", "raises risk"))


@pytest.mark.parametrize("summary, expected", [
    ("A high monthly bill and a short tenure drive their risk.", None),
    ("A low monthly bill and a long tenure drive their risk.", "misstated_factor"),
    # Each adjective is pinned to its own field across "and".
    ("A high monthly bill and low tenure drive their risk.", None),
    # A size word about the RISK is not about the field.
    ("Their short tenure means high risk, as does their monthly bill.", None),
    ("Their tenure makes them more likely to leave, as does their monthly bill.", None),
])
def test_size_words_are_read_only_near_their_own_field(summary, expected):
    payload = payload_for(BILL_AND_TENURE, probability=0.8)
    output = reply(summary=summary, risk_level="very high",
                   reasons=BILL_AND_TENURE_REASONS)
    assert verdict(output, payload) == expected


def test_an_about_typical_value_is_not_size_checked():
    """No comparison claim to contradict -- left to the prompt."""
    payload = payload_for([("tenure", 30, 0.3)], probability=0.8)
    output = reply(summary="Their long tenure is the main factor.",
                   risk_level="very high", reasons=(("tenure", "raises risk"),))
    assert verdict(output, payload) is None


# Customer row 5 of simulated_new_customers.csv as v3's live run saw it:
# overall commitment "lower than most customers", tenure "much lower".
ROW_5_DRIVERS = [
    ("contract", "Month-to-month", 0.5),
    ("contractvstenure", 1, 0.3),
    ("tenure", 1, 0.2),
]
ROW_5_REASONS = (
    ("contract", "raises risk"), ("contractvstenure", "raises risk"),
    ("tenure", "raises risk"),
)


def test_an_overstated_degree_is_not_rejected():
    """v3's live row 5 said "much lower" for a commitment that is only
    "lower", and 5 of 50 did the same in stage 2. **v5 forbids it in the
    prompt, and nothing checks it here.** A degree guard was built and removed
    on 2026-09-17: it rejects text that states no falsehood, which costs a
    retry and a summary for a wording preference. Pinned so that re-adding the
    guard is a decision rather than an accident."""
    payload = payload_for(ROW_5_DRIVERS, probability=0.3)
    assert payload["factors"][1]["vs_other_customers"] == "lower than most customers"
    output = reply(
        summary="This customer is on a month-to-month contract. Additionally, they "
                "have a much lower overall commitment and have only been a customer "
                "for 1 month.",
        risk_level="moderate", reasons=ROW_5_REASONS,
    )
    assert verdict(output, payload) is None


def test_a_hedged_guess_is_not_rejected(payload):
    """No speculation guard, for the same reason. **v5's prompt forbids
    guessing why a factor matters; the guards still accept it.** Pinned so
    re-adding one is a decision, not an accident."""
    output = reply(summary="Their month-to-month contract may indicate they are "
                           "shopping around.")
    assert verdict(output, payload) is None


def test_every_rejection_type_is_reachable_and_from_the_closed_set(payload):
    """Step four buckets by these. Each type must be producible, or a bucket
    is dead code; and nothing outside the set may be produced."""
    bad = [
        "",
        "not json",
        reply(summary="They are on a month-to-month contract. " * 12),
        reply(summary="This senior citizen will leave."),
        reply(summary="Their monthly bill is high."),
        reply(summary="Their contract adds 0.5953."),
        reply(summary="This month-to-month customer is unlikely to churn."),
        reply(summary="Their month-to-month contract makes a retention call worthwhile."),
        reply(reasons=(("contract", "lowers risk"),)),
    ]
    produced = {verdict(output, payload) for output in bad}
    assert produced == set(narrate.REJECTION_TYPES)


# ==========================================================================
# 6. Retry bookkeeping
# ==========================================================================

BAD_PROTECTED = reply(summary="This senior citizen will leave.")
BAD_UNLISTED = reply(summary="Their monthly bill is high.")


def test_a_good_first_attempt_makes_exactly_one_call(explanation):
    client = FakeLLM([GOOD])
    result = narrate.narrate(explanation, client=client)
    assert len(client.calls) == 1
    assert len(result["attempts"]) == 1
    assert result["narrative"] == GOOD_SUMMARY
    assert result["structured"] == json.loads(GOOD)
    assert result["narrative_available"] is True
    assert result["final_rejection_type"] is None


def test_the_result_carries_the_payload_the_model_was_shown(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    assert result["payload"] == narrate.narration_payload(explanation)


def test_a_rejected_first_attempt_is_retried_once(explanation):
    client = FakeLLM([BAD_PROTECTED, GOOD])
    result = narrate.narrate(explanation, client=client)
    assert len(client.calls) == 2
    assert result["narrative"] == GOOD_SUMMARY


def test_the_two_attempts_are_recorded_separately(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([BAD_PROTECTED, GOOD]))
    first, second = result["attempts"]
    assert first["attempt"] == 1
    assert first["accepted"] is False
    assert first["rejection_type"] == "protected_attribute"
    assert first["text"] == BAD_PROTECTED
    assert second["attempt"] == 2
    assert second["accepted"] is True
    assert second["rejection_type"] is None
    assert second["text"] == GOOD


def test_two_rejections_leave_no_narrative_but_keep_the_drivers(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([BAD_PROTECTED, BAD_UNLISTED]))
    assert result["narrative"] is None
    assert result["structured"] is None
    assert result["narrative_available"] is False
    assert result["final_rejection_type"] == "unlisted_field"
    assert len(result["drivers"]) == len(explanation["drivers"])
    assert result["churn_probability"] == explanation["churn_probability"]


def test_malformed_then_good_is_retried(explanation):
    result = narrate.narrate(explanation, client=FakeLLM(["{not json", GOOD]))
    assert result["attempts"][0]["rejection_type"] == "malformed_output"
    assert result["narrative_available"] is True


def test_at_most_two_attempts_are_ever_made(explanation):
    client = FakeLLM(["", ""])
    narrate.narrate(explanation, client=client)
    assert len(client.calls) == 2


def test_the_attempt_cap_is_two():
    assert narrate.MAX_ATTEMPTS == 2


def test_the_retry_turn_carries_the_rejected_text_and_the_rule(explanation):
    client = FakeLLM([BAD_PROTECTED, GOOD])
    narrate.narrate(explanation, client=client)
    retry_messages = client.calls[1]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": BAD_PROTECTED}
    assert retry_messages[-1]["role"] == "user"
    assert "never allowed" in retry_messages[-1]["content"]


def test_the_correction_names_a_rule_for_every_rejection_type():
    for rejection_type in narrate.REJECTION_TYPES:
        correction = narrate._correction(rejection_type, "detail")
        assert correction.strip()
        assert "Try again." in correction


def test_api_errors_propagate_rather_than_becoming_rejections(explanation):
    client = FakeLLM([RuntimeError("rate limited")])
    with pytest.raises(RuntimeError, match="rate limited"):
        narrate.narrate(explanation, client=client)


def test_temperature_is_zero_by_default(explanation):
    client = FakeLLM([GOOD])
    narrate.narrate(explanation, client=client)
    assert client.calls[0]["temperature"] == 0.0


def test_a_fixed_seed_is_sent_and_recorded(explanation):
    """temperature=0 alone gave two texts for one customer in v3's live run."""
    client = FakeLLM([GOOD])
    result = narrate.narrate(explanation, client=client)
    assert client.calls[0]["seed"] == 42
    assert result["seed"] == 42


def test_the_seed_can_be_turned_off(explanation):
    client = FakeLLM([GOOD])
    narrate.narrate(explanation, client=client, seed=None)
    assert client.calls[0]["seed"] is None


def test_the_default_model_is_recorded_in_the_result(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    assert result["model"] == "gpt-4o-mini"


def test_attempt_records_carry_latency_tokens_and_finish_reason(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    attempt = result["attempts"][0]
    assert attempt["latency_ms"] >= 0
    assert attempt["prompt_tokens"] == 100
    assert attempt["completion_tokens"] == 30
    assert attempt["finish_reason"] == "stop"


def test_the_result_is_json_serialisable(explanation):
    json.dumps(narrate.narrate(explanation, client=FakeLLM([GOOD])))


# ==========================================================================
# 7. The three rates
# ==========================================================================

def _result(attempt_types, narrative="text"):
    """A minimal narrate() result. `attempt_types` is one entry per attempt:
    None for accepted, a rejection type otherwise."""
    return {
        "narrative": narrative,
        "attempts": [
            {"attempt": i + 1, "accepted": t is None, "rejection_type": t}
            for i, t in enumerate(attempt_types)
        ],
    }


def test_first_attempt_rate_is_over_all_results():
    results = [
        _result([None]),
        _result([None]),
        _result(["unlisted_field", None]),
        _result(["protected_attribute", None]),
    ]
    rates = narrate.rejection_rates(results)
    assert rates["n"] == 4
    assert rates["first_attempt_rejection_rate"] == 0.5


def test_second_attempt_rate_is_over_retries_issued_not_over_all_results():
    """Four customers, two retries, one of which failed again: 1/2, not 1/4."""
    results = [
        _result([None]),
        _result([None]),
        _result(["unlisted_field", None]),
        _result(["unlisted_field", "unlisted_field"], narrative=None),
    ]
    rates = narrate.rejection_rates(results)
    assert rates["retries_issued"] == 2
    assert rates["second_attempt_rejection_rate"] == 0.5
    assert rates["final_rejection_rate"] == 0.25


def test_second_attempt_rate_is_none_when_no_retry_was_ever_issued():
    rates = narrate.rejection_rates([_result([None]), _result([None])])
    assert rates["second_attempt_rejection_rate"] is None
    assert rates["retries_issued"] == 0


def test_final_rate_counts_results_with_no_narrative():
    results = [
        _result([None]),
        _result(["empty_output", "empty_output"], narrative=None),
    ]
    assert narrate.rejection_rates(results)["final_rejection_rate"] == 0.5


def test_buckets_sum_to_the_rejection_counts():
    results = [
        _result(["unlisted_field", None]),
        _result(["unlisted_field", None]),
        _result(["protected_attribute", "unlisted_field"], narrative=None),
        _result([None]),
    ]
    rates = narrate.rejection_rates(results)
    assert rates["first_attempt_by_type"] == {
        "unlisted_field": 2, "protected_attribute": 1,
    }
    assert rates["second_attempt_by_type"] == {"unlisted_field": 1}


def test_rates_of_an_empty_batch_are_none_rather_than_zero():
    rates = narrate.rejection_rates([])
    assert rates["n"] == 0
    assert rates["first_attempt_rejection_rate"] is None
    assert rates["final_rejection_rate"] is None


def test_rates_are_computed_from_real_narrate_results(explanation):
    results = [
        narrate.narrate(explanation, client=FakeLLM([GOOD])),
        narrate.narrate(explanation, client=FakeLLM([BAD_UNLISTED, GOOD])),
    ]
    rates = narrate.rejection_rates(results)
    assert rates["first_attempt_rejection_rate"] == 0.5
    assert rates["second_attempt_rejection_rate"] == 0.0
    assert rates["final_rejection_rate"] == 0.0


# ==========================================================================
# 8. The client boundary
# ==========================================================================

def test_narrate_does_not_import_the_sdk_at_module_scope():
    tree = ast.parse(Path(narrate.__file__).read_text())
    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
    assert "openai" not in top_level


def test_constructing_a_real_client_explains_how_to_install_the_sdk():
    if importlib.util.find_spec("openai") is not None:
        pytest.skip("openai is installed; the missing-SDK path cannot be reached")
    with pytest.raises(RuntimeError, match="uv sync --group llm"):
        narrate.OpenAIClient()


def test_constructing_a_real_client_without_a_key_says_which_variable(monkeypatch):
    if importlib.util.find_spec("openai") is None:
        pytest.skip("openai is not installed")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        narrate.OpenAIClient()


def test_the_real_client_sends_the_schema_and_the_token_cap():
    """Through OpenAIClient.complete with the SDK object swapped for a
    recorder -- no network, no key used. Catches the request quietly losing
    response_format, which would turn every reply back into free prose."""
    if importlib.util.find_spec("openai") is None:
        pytest.skip("openai is not installed")

    class Recorder:
        def __init__(self):
            self.kwargs = None
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            self.kwargs = kwargs

            class Usage:
                prompt_tokens, completion_tokens = 400, 70

            class Choice:
                finish_reason = "stop"

                class message:
                    content = GOOD

            class Response:
                choices = [Choice]
                usage = Usage
                system_fingerprint = "fp_test"

            return Response

    client = narrate.OpenAIClient(api_key="sk-not-a-real-key")
    client._client = recorder = Recorder()
    completion = client.complete(
        [{"role": "user", "content": "x"}], model="gpt-4o-mini", temperature=0.0,
        max_tokens=250, response_format=narrate.RESPONSE_FORMAT, seed=42,
    )
    assert recorder.kwargs["response_format"] is narrate.RESPONSE_FORMAT
    assert recorder.kwargs["max_completion_tokens"] == 250
    assert recorder.kwargs["seed"] == 42
    assert completion.system_fingerprint == "fp_test"

    client.complete(
        [{"role": "user", "content": "x"}], model="gpt-4o-mini", temperature=0.0,
        max_tokens=250, response_format=narrate.RESPONSE_FORMAT, seed=None,
    )
    assert "seed" not in recorder.kwargs
    assert completion.text == GOOD
    assert completion.finish_reason == "stop"
    assert (completion.prompt_tokens, completion.completion_tokens) == (400, 70)


# ==========================================================================
# 9. Rendering
# ==========================================================================

def test_render_includes_the_structured_output(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    text = "\n".join(narrate.render(result, "TEST"))
    assert "risk level: high" in text
    assert "- contract (raises risk)" in text
    assert "month-to-month contract" in text
    assert "explanation_v5" in text


def test_render_reports_a_missing_narrative_with_its_reason(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([BAD_PROTECTED, BAD_UNLISTED]))
    text = "\n".join(narrate.render(result, "TEST"))
    assert "no narrative" in text
    assert "unlisted_field" in text


def test_render_names_the_protected_omissions(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    text = "\n".join(narrate.render(result, "TEST"))
    assert "protected" in text
    assert "seniorcitizen" in text


def test_render_rates_labels_the_first_attempt_rate_as_the_measure():
    rates = narrate.rejection_rates([_result([None]), _result(["unlisted_field", None])])
    text = "\n".join(narrate.render_rates(rates))
    assert "first-attempt rejection rate" in text
    assert "the measure of the prompt" in text


def test_render_rates_reports_an_absent_second_attempt_rate_as_na():
    rates = narrate.rejection_rates([_result([None])])
    assert "n/a" in "\n".join(narrate.render_rates(rates))


# ==========================================================================
# 10. Explanation styles: views over one accepted reply
# ==========================================================================

def test_short_style_is_the_accepted_summary(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    assert narrate.format_explanation(result, "short") == GOOD_SUMMARY


def test_bullets_are_worded_from_the_payload_not_the_model(explanation):
    """Every word of a bullet is payload data: the model only chose which
    factors, and that choice already passed the guards."""
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    assert narrate.format_explanation(result, "bullets").splitlines() == [
        "Risk level: high",
        "- contract type: Month-to-month (raises risk)",
        "- months as a customer: 1, much lower than most customers (raises risk)",
    ]


def test_bullets_follow_the_models_reasons_not_every_factor(explanation):
    """The payload has three factors; this reply gave one reason."""
    output = reply(reasons=(("contract", "raises risk"),),
                   summary="Their month-to-month contract drives their risk.")
    result = narrate.narrate(explanation, client=FakeLLM([output]))
    bullets = narrate.format_explanation(result, "bullets").splitlines()
    assert len(bullets) == 2 and "contract type" in bullets[1]


def test_detailed_is_the_summary_then_the_bullets(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    detailed = narrate.format_explanation(result, "detailed")
    assert detailed == "\n".join([
        GOOD_SUMMARY, "", narrate.format_explanation(result, "bullets"),
    ])


def test_a_value_without_a_number_still_gets_its_comparison():
    """contractvstenure is compared but its value is never shown."""
    payload = payload_for(ROW_5_DRIVERS, probability=0.3)
    line = narrate._reason_line(payload["factors"][1])
    assert line == ("overall commitment (contract term × months as a customer), "
                    "lower than most customers (raises risk)")


@pytest.mark.parametrize("style", ["short", "bullets", "detailed"])
def test_no_narrative_falls_back_to_the_payload_factors(style, explanation):
    """Degraded, not failed: the reader still gets the reasons."""
    result = narrate.narrate(
        explanation, client=FakeLLM([BAD_PROTECTED, BAD_PROTECTED]))
    text = narrate.format_explanation(result, style)
    assert text.startswith("Risk level: high (no written summary)")
    assert len(text.splitlines()) == 1 + len(result["payload"]["factors"])
    assert "senior" not in text


def test_an_unknown_style_is_refused(explanation):
    result = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    with pytest.raises(ValueError, match="bullets"):
        narrate.format_explanation(result, "haiku")


def test_formatting_makes_no_call(explanation):
    client = FakeLLM([GOOD])
    result = narrate.narrate(explanation, client=client)
    for style in narrate.EXPLANATION_STYLES:
        narrate.format_explanation(result, style)
    assert len(client.calls) == 1


def test_the_styles_are_these_three():
    assert narrate.EXPLANATION_STYLES == ("short", "bullets", "detailed")


def test_the_cli_prints_only_the_chosen_style(monkeypatch, capsys):
    """`narrate.py --dummy --style bullets`, with the real churn model and a
    fake language model: prints the bullets, not the full report."""
    monkeypatch.setattr(narrate, "OpenAIClient", lambda: FakeLLM([
        reply(risk_level="high", reasons=(("contract", "raises risk"),),
              summary="Their month-to-month contract drives their risk."),
    ]))
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert narrate.main(["--dummy", "--style", "bullets"]) == 0
    out = capsys.readouterr().out
    assert "--- config.DUMMY_CUSTOMER" in out
    assert "- contract type: Month-to-month (raises risk)" in out
    assert "EXPLANATION --" not in out


# ==========================================================================
# 11. --save: keeping a paid batch
# ==========================================================================

def _cli(monkeypatch, responses, *args):
    """Run main() with a scripted fake model, Langfuse off and the cache off.

    The CLI caches by default; these tests are about saving, so they opt out
    rather than measuring a cache by accident. The cache's own CLI behaviour is
    tested in tests/test_narration_cache.py.
    """
    args = ("--no-cache",) + args
    client = FakeLLM(responses)
    monkeypatch.setattr(narrate, "OpenAIClient", lambda: client)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    return narrate.main(list(args)), client


def test_save_writes_one_entry_per_customer(monkeypatch, tmp_path, capsys):
    target = tmp_path / "run.json"
    code, _ = _cli(monkeypatch, [GOOD], "--dummy", "--quiet", "--save", str(target))
    assert code == 0
    saved = json.loads(target.read_text())
    assert len(saved) == 1
    assert saved[0]["narrative"] == GOOD_SUMMARY
    # The keys LLMcalls.ipynb reads.
    for key in ("payload", "attempts", "structured", "prompt_version", "model"):
        assert key in saved[0]


def test_save_labels_each_result_with_its_customer(monkeypatch, tmp_path):
    target = tmp_path / "run.json"
    _cli(monkeypatch, [GOOD], "--dummy", "--quiet", "--save", str(target))
    assert json.loads(target.read_text())[0]["case"] == "config.DUMMY_CUSTOMER"


def test_save_refuses_an_existing_file_before_calling_the_api(monkeypatch, tmp_path, capsys):
    """The check that matters: overwriting a saved run destroys a measurement
    that cost money, and a batch that dies at the end would have to be paid
    for twice. The fake is scripted with nothing, so any call would raise."""
    target = tmp_path / "run.json"
    target.write_text("[]")
    code, client = _cli(monkeypatch, [], "--dummy", "--quiet", "--save", str(target))
    assert code == 2
    assert client.calls == []
    assert target.read_text() == "[]"
    assert "already exists" in capsys.readouterr().err


def test_a_partial_batch_is_still_saved(monkeypatch, tmp_path):
    """One customer's call raising must not discard the ones already paid
    for. Row 0 is answered; every later row's call raises."""
    target = tmp_path / "run.json"
    csv = narrate.REPO_ROOT / "simulated_new_customers.csv"
    row_0 = reply(
        risk_level="high", reasons=(("contract", "raises risk"),),
        summary="Their month-to-month contract drives their risk.",
    )
    code, _ = _cli(
        monkeypatch, [row_0, RuntimeError("boom")],
        "--csv", str(csv), "--all", "--quiet", "--save", str(target),
    )
    assert code == 0
    saved = json.loads(target.read_text())
    assert len(saved) == 1 and saved[0]["case"].endswith("row 0")


def test_without_save_nothing_is_written(monkeypatch, tmp_path):
    target = tmp_path / "run.json"
    _cli(monkeypatch, [GOOD], "--dummy", "--quiet")
    assert not target.exists()


# ==========================================================================
# 12. The cache, through narrate()
# ==========================================================================

@pytest.fixture
def cache(tmp_path):
    cache = narration_cache.from_env(str(tmp_path / "narration.sqlite3"))
    yield cache
    cache.close()


def test_without_a_cache_every_call_reaches_the_model(explanation):
    """The library default. A measurement run must meet the real model."""
    client = FakeLLM([GOOD, GOOD])
    first = narrate.narrate(explanation, client=client)
    second = narrate.narrate(explanation, client=client)
    assert len(client.calls) == 2
    assert first["cache_hit"] is False and second["cache_hit"] is False


def test_an_identical_second_request_is_served_from_the_cache(explanation, cache):
    client = FakeLLM([GOOD])  # one response only: a second call would raise
    first = narrate.narrate(explanation, client=client, cache=cache)
    second = narrate.narrate(explanation, client=client, cache=cache)
    assert len(client.calls) == 1
    assert second["narrative"] == first["narrative"]
    assert second["structured"] == first["structured"]


def test_a_cached_result_says_so_and_records_no_attempts(explanation, cache):
    narrate.narrate(explanation, client=FakeLLM([GOOD]), cache=cache)
    second = narrate.narrate(explanation, client=FakeLLM([]), cache=cache)
    assert second["cache_hit"] is True
    assert second["attempts"] == [], "no call was made, so there is nothing to record"
    assert second["cached_attempts"] == 1
    assert second["narrative_available"] is True
    assert second["final_rejection_type"] is None


def test_a_cached_result_keeps_the_whole_attribution(explanation, cache):
    """The drivers are the part that survives everything; a cache hit must not
    return less than a live call."""
    live = narrate.narrate(explanation, client=FakeLLM([GOOD]), cache=cache)
    cached = narrate.narrate(explanation, client=FakeLLM([]), cache=cache)
    for key in ("drivers", "contributions", "churn_probability", "payload",
                "prompt_version", "model", "seed", "protected_drivers_omitted"):
        assert cached[key] == live[key], key


def test_a_different_customer_is_not_served_the_first_ones_answer(explanation, cache):
    other = make_explanation([("contract", "Two year", -0.9), ("tenure", 70, -0.3)],
                             probability=0.05)
    narrate.narrate(explanation, client=FakeLLM([GOOD]), cache=cache)
    low = reply(risk_level="low", reasons=(("contract", "lowers risk"),),
                summary="Their two-year contract holds them.")
    client = FakeLLM([low])
    result = narrate.narrate(other, client=client, cache=cache)
    assert len(client.calls) == 1 and result["cache_hit"] is False


def test_a_rejected_narration_is_not_cached(explanation, cache):
    narrate.narrate(explanation, client=FakeLLM([BAD_PROTECTED, BAD_PROTECTED]),
                    cache=cache)
    client = FakeLLM([GOOD])
    result = narrate.narrate(explanation, client=client, cache=cache)
    assert len(client.calls) == 1, "the next caller deserves a real attempt"
    assert result["narrative_available"]


def test_a_changed_seed_misses_the_cache(explanation, cache):
    narrate.narrate(explanation, client=FakeLLM([GOOD]), cache=cache)
    client = FakeLLM([GOOD])
    narrate.narrate(explanation, client=client, cache=cache, seed=7)
    assert len(client.calls) == 1


class HostileCache:
    """Everything it is asked to do, it refuses."""

    enabled = True

    def get(self, *_, **__):
        raise RuntimeError("get exploded")

    def put(self, *_, **__):
        raise RuntimeError("put exploded")


def test_a_cache_that_raises_cannot_change_a_narration(explanation):
    """The llm_tracing rule, applied to the cache: optional comfort must never
    cost an explanation."""
    plain = narrate.narrate(explanation, client=FakeLLM([GOOD]))
    with pytest.warns(RuntimeWarning, match="narration cache failed"):
        hostile = narrate.narrate(explanation, client=FakeLLM([GOOD]),
                                  cache=HostileCache())
    assert hostile["narrative"] == plain["narrative"]
    assert hostile["structured"] == plain["structured"]
    assert hostile["cache_hit"] is False


def test_rates_count_live_results_only(explanation, cache):
    """Two customers, one of them answered twice: the rates describe the two
    calls that happened, and the hit is reported on its own."""
    narrate.narrate(explanation, client=FakeLLM([GOOD]), cache=cache)
    results = [
        narrate.narrate(explanation, client=FakeLLM([]), cache=cache),
        narrate.narrate(explanation, client=FakeLLM([BAD_UNLISTED, GOOD]), cache=None),
    ]
    rates = narrate.rejection_rates(results)
    assert rates["n"] == 1
    assert rates["cached"] == 1
    assert rates["first_attempt_rejection_rate"] == 1.0
    assert rates["final_rejection_rate"] == 0.0


def test_rates_of_an_all_cached_batch_are_none_rather_than_zero(explanation, cache):
    narrate.narrate(explanation, client=FakeLLM([GOOD]), cache=cache)
    cached = [narrate.narrate(explanation, client=FakeLLM([]), cache=cache)]
    rates = narrate.rejection_rates(cached)
    assert rates["n"] == 0 and rates["cached"] == 1
    assert rates["first_attempt_rejection_rate"] is None


def test_render_says_when_an_explanation_came_from_the_cache(explanation, cache):
    narrate.narrate(explanation, client=FakeLLM([GOOD]), cache=cache)
    cached = narrate.narrate(explanation, client=FakeLLM([]), cache=cache)
    text = "\n".join(narrate.render(cached, "TEST"))
    assert "from cache" in text
    assert "1 attempt(s) when first made" in text


def test_render_rates_mentions_cache_hits():
    rates = {"n": 2, "cached": 3, "retries_issued": 0,
             "first_attempt_rejection_rate": 0.0,
             "second_attempt_rejection_rate": None, "final_rejection_rate": 0.0,
             "first_attempt_by_type": {}, "second_attempt_by_type": {}}
    assert "3 more served from cache" in "\n".join(narrate.render_rates(rates))


def test_the_cli_caches_by_default(monkeypatch, tmp_path, capsys):
    """Opposite default from the library: a person running the same customer
    twice should not pay twice."""
    db = str(tmp_path / "cli.sqlite3")
    client = FakeLLM([GOOD])  # one response for two runs
    monkeypatch.setattr(narrate, "OpenAIClient", lambda: client)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert narrate.main(["--dummy", "--quiet", "--cache-path", db]) == 0
    assert narrate.main(["--dummy", "--quiet", "--cache-path", db]) == 0
    assert len(client.calls) == 1
    assert "1 of 1 served from cache" in capsys.readouterr().err


def test_the_cli_can_be_told_not_to_cache(monkeypatch, tmp_path):
    db = str(tmp_path / "cli.sqlite3")
    client = FakeLLM([GOOD, GOOD])
    monkeypatch.setattr(narrate, "OpenAIClient", lambda: client)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    narrate.main(["--dummy", "--quiet", "--no-cache", "--cache-path", db])
    narrate.main(["--dummy", "--quiet", "--no-cache", "--cache-path", db])
    assert len(client.calls) == 2
    assert not Path(db).exists(), "--no-cache must not even open the database"
