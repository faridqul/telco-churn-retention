"""Turn explain.py's driver list into a short, checked explanation in English.

Run:  uv run python narrate.py --dummy
      uv run python narrate.py --csv simulated_new_customers.csv --row 0
      uv run python narrate.py --csv simulated_new_customers.csv --all --rates

Needs an API key:  export OPENAI_API_KEY=...   (or `uv run --env-file .env ...`)
Needs the client:  uv sync --group llm

THE SHAPE OF THIS MODULE
    narration_payload()  ->  the LLM  ->  validate_narrative()
      deterministic          one call      deterministic

The language model occupies only the middle. It is handed what the churn
model found and is permitted to phrase it; it never sees the customer's raw
row, never computes anything, and every claim it makes is checked against the
payload before the text is allowed out. `explain.py` stays free of any network
dependency, which is what keeps it importable by the serving path.

THE FAILURES THIS EXISTS TO STOP
All are silent, and none looks wrong on the page.

  1. AN INVENTED DRIVER. A language model knows telco churn priors and will
     write "high monthly charges and no tech support" whether or not those are
     what this model actually used. Guarded by checking every field the output
     names against the payload's own factor list, via FIELD_ALIASES.

  2. A PROTECTED ATTRIBUTE GIVEN AS A REASON. gender, seniorcitizen, partner,
     dependents and the derived family_tie are real features and can be real
     top drivers -- but "she is a senior citizen, so she will churn" must
     never reach a human as a retention rationale. Those drivers are removed
     from the payload before the prompt is built (the control), and the
     output is checked for them anyway (the backstop). explain_customer()'s
     own driver list still reports them -- that is the honest attribution.

  3. A MISDESCRIBED VALUE. Found in the first live run (prompt v1,
     2026-09-17): a customer who had paid $5,762.95 -- about 4x the training
     median -- was described as having "a lower total charged to date". The
     name and the direction were right; the adjective was invented. Prompt v2
     hands the model the comparison ("well above typical"), so there is
     nothing to guess, and the misstated_factor guard rejects an adjective
     that disagrees with it.

PROMPT v2: STRUCTURED OUTPUT
The model returns JSON -- risk_level, reasons[{field, direction}], summary --
rather than free prose. The structured parts are checked exactly (a field id
is either in the payload or not; a direction either matches or not), with no
alias guessing. The summary is still prose, so the prose guards still run on
it. v2 also stops sending the raw probability: the scores are uncalibrated
(README), and v1 quoted them as "61.51%". The model gets a risk band instead,
and the only numbers it may write are factor values.

RETRY POLICY
One retry, two attempts maximum. Both attempts are recorded separately and are
never merged: each keeps its own text, its own verdict and its own rejection
type. The number that measures prompt quality is the FIRST-attempt rejection
rate, and rejection_rates() reports it separately for exactly that reason. The
correction sent with a retry names only the rule that was broken, never a
suggested fix -- telling the model what to say would let a retry launder a
hallucination into an accepted answer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

import explain
from config import DUMMY_CUSTOMER, validate_input_frame

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent

# v1 (prompts/explanation_v1.txt) is kept in the repo, unused, because the
# stage-1 live results in CHANGELOG.md are a measurement of that exact file.
PROMPT_PATH = REPO_ROOT / "prompts" / "explanation_v2.txt"

# The prompt's identity, carried in every result so a logged explanation can be
# traced back to the exact text that produced it. tests/test_narrate.py pins
# the prompt file's sha256, so editing the wording without bumping this fails
# a test rather than silently invalidating everything measured before it.
PROMPT_VERSION = PROMPT_PATH.stem

DEFAULT_MODEL = "gpt-4o-mini"

# Zero, so the same customer yields the same output. Needed for caching, and
# so that step four's harness measures the prompt rather than sampling noise.
DEFAULT_TEMPERATURE = 0.0

# Two attempts: the first, and one retry. Pinned by test against a literal.
MAX_ATTEMPTS = 2

# How many factors the model is shown, applied AFTER protected fields are
# filtered out -- filtering first would let a protected driver consume one of
# the slots and silently shorten the explanation. Three, not five: fewer facts
# means fewer chances to misstate one, and the manager needs the top reasons,
# not an inventory.
NARRATION_TOP_N = 3

# About 60 words, which is what the prompt asks for. The backstop for a model
# that ignores it, bucketed separately because it is a different failure from
# a wrong summary.
MAX_SUMMARY_CHARS = 400

# Hard cap on what the API may generate. Valid v2 output is ~60-100 tokens; a
# truncated reply is invalid JSON and lands in malformed_output, so a runaway
# response costs at most this and is still counted.
MAX_OUTPUT_TOKENS = 250

# Attributes that must never be given to a human as a reason to target someone,
# even when the model genuinely used them. family_tie is derived from partner
# and dependents, so it carries the same information and belongs here too.
PROTECTED_FIELDS = frozenset({
    "gender", "seniorcitizen", "partner", "dependents", "family_tie",
})

# Bands instead of a probability. Relative to the threshold, so a band can never
# disagree with the decision: "high" and "very high" are exactly the targeted
# customers. The raw score is uncalibrated, so a band is also the more honest
# thing to show a reader.
RISK_LEVELS = ("low", "moderate", "high", "very high")

DIRECTIONS = ("raises risk", "lowers risk")

# The closed set of reasons an output can be refused. Closed on purpose: step
# four buckets by these, and a free-text reason would make the buckets
# uncountable. A failed API call is NOT in here -- that is an exception, not a
# verdict on the text, and it propagates.
REJECTION_TYPES = (
    "empty_output",
    "malformed_output",
    "overlong_output",
    "protected_attribute",
    "unlisted_field",
    "hallucinated_number",
    "decision_contradiction",
    "misstated_factor",
)

# Yes/no flags stored as 0/1. A median of 0 makes "well above typical" true of
# every customer who has the flag, which says nothing, so these get "yes"/"no"
# and no comparison.
_BINARY_FIELDS = frozenset({"is_auto_pay", "seniorcitizen", "family_tie"})

# Engineered values with no meaning to a reader ("contract length weighted by
# tenure: 136"). The comparison is sent; the number is not, so it cannot be
# quoted.
_UNQUOTED_VALUE_FIELDS = frozenset({"contractvstenure", "charge_change_ratio"})

# The JSON shape the API is asked to return. Strict mode makes the API itself
# enforce keys and enums; validate_narrative() checks all of it again, because
# a fake, a different provider, or a truncated reply is not bound by this.
# Array length limits are left to the guard rather than the schema.
RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "churn_explanation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "risk_level": {"type": "string", "enum": list(RISK_LEVELS)},
                "reasons": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "direction": {"type": "string", "enum": list(DIRECTIONS)},
                        },
                        "required": ["field", "direction"],
                        "additionalProperties": False,
                    },
                },
                "summary": {"type": "string"},
            },
            "required": ["risk_level", "reasons", "summary"],
            "additionalProperties": False,
        },
    },
}

W = 78  # report width, matching explain.py and fairness_analysis.py


# --------------------------------------------------------------------------
# Field aliases
#
# The phrases a language model actually reaches for when it means one of the
# 25 feature columns. This is the asset that makes the "did it name a factor
# the model didn't use" check possible for prose, and step four's faithfulness
# metrics score against the same map -- one copy, so the endpoint and the
# harness cannot disagree about what counts as a mention.
#
# Every alias string is globally unique across fields, asserted by test. Where
# two fields could plausibly claim a phrase, the more specific field keeps it
# ('automatic payment' belongs to is_auto_pay, not paymentmethod) and matching
# runs longest-alias-first so the specific one wins the span.
# --------------------------------------------------------------------------

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    # Protected. Listed so the guard can NAME them, not so they can be used.
    # Pronouns included deliberately. The payload carries no gender, so a
    # narrative saying "she" has asserted one the model was never given --
    # an invented protected attribute, which is worse than a quoted one.
    "gender": (
        "gender", "male", "female", "man", "woman",
        "she", "he", "her", "his", "him", "hers", "herself", "himself",
    ),
    "seniorcitizen": ("senior citizen", "senior", "elderly", "older customer", "age"),
    # Not bare "single": "a single month" is not a marital status, and the bare
    # word rejected it as one. Only the phrasings that are about a person.
    "partner": (
        "partner", "spouse", "married", "is single", "are single",
        "single person", "single customer",
    ),
    "dependents": ("dependents", "children", "kids"),
    "family_tie": ("family status", "family ties", "household", "family"),
    # Tenure and contract.
    "tenure": (
        "tenure", "months as a customer", "months with", "how long",
        "new customer", "recently joined", "length of time", "customer for",
        "signed up recently", "short time",
    ),
    "contract": (
        "contract", "month-to-month", "month to month", "monthly plan",
        "one year", "one-year", "two year", "two-year", "annual plan",
        "no commitment", "rolling plan",
    ),
    "contractvstenure": ("contract length weighted by tenure", "contract weighted"),
    # Services.
    "phoneservice": ("phone service",),
    "multiplelines": ("multiple lines", "multiple phone lines", "additional lines"),
    "internetservice": (
        "internet service", "internet", "fiber optic", "fibre optic",
        "fiber", "fibre", "dsl",
    ),
    "onlinesecurity": ("online security", "security add-on", "security service"),
    "onlinebackup": ("online backup", "backup service", "backup"),
    "deviceprotection": ("device protection", "protection plan"),
    "techsupport": ("tech support", "technical support", "support plan"),
    "streamingtv": ("streaming tv", "tv streaming"),
    "streamingmovies": ("streaming movies", "movie streaming"),
    "total_services": (
        "add-on services", "number of services", "services taken",
        "bundled services", "add-ons", "few services", "extra services",
    ),
    # Billing.
    "paperlessbilling": ("paperless billing", "paperless", "electronic billing"),
    "paymentmethod": (
        "payment method", "electronic check", "mailed check", "bank transfer",
        "credit card", "how they pay", "pays by check",
    ),
    "is_auto_pay": (
        "automatic payment", "autopay", "auto-pay", "pays automatically",
        "automatic billing", "direct debit",
    ),
    "monthlycharges": (
        "monthly bill", "monthly charges", "monthly charge", "current bill",
        "what they pay each month", "monthly cost",
    ),
    "totalcharges": (
        "total charges", "total charged", "total spend", "lifetime spend",
        "total billed", "spent with us",
    ),
    "average_monthly_charges": (
        "average monthly bill", "average monthly charges", "historical average",
        "average bill", "typical monthly",
    ),
    "charge_change_ratio": (
        "bill compared", "charge change", "bill increase", "bill has risen",
        "paying more than", "bill went up",
    ),
}

# Phrases that claim a level of risk. Matched as whole phrases, longest first,
# with each matched span consumed -- so "unlikely to churn" and "not at risk
# of leaving" are read as the low-risk claims they are, and no longer also
# match the high-risk phrases they contain ("likely to churn", "at risk of
# leaving"). Under v1's plain substring check both were rejected as
# contradictions for customers who were correctly left alone.
_LOW_RISK_PHRASES = (
    "unlikely to churn", "unlikely to leave", "not likely to churn",
    "not likely to leave", "low risk", "moderate risk", "not at risk",
    "not at risk of leaving", "no action", "leave alone",
    "not worth targeting", "likely to stay", "no need to",
)
_HIGH_RISK_PHRASES = (
    "likely to churn", "likely to leave", "high risk", "should be targeted",
    "at risk of leaving", "urgent", "immediate action", "act now",
)

# Size words, for the misstated_factor check. A word from the wrong list near a
# field whose value is above (or below) typical is a misdescription.
_LOW_WORDS = frozenset({
    "low", "lower", "lowest", "small", "smaller", "little", "short", "shorter",
    "few", "fewer", "minimal", "modest", "cheap", "cheaper",
})
_HIGH_WORDS = frozenset({
    "high", "higher", "highest", "large", "larger", "big", "bigger", "long",
    "longer", "many", "substantial", "considerable", "expensive",
    "steep", "hefty",
})

# How far from a field mention a size word still counts as describing it: two
# words before ("a lower total charged") and three after ("total charges are
# low"), never across punctuation or a conjunction, so "high total charges and
# low tenure" pins each adjective to its own field.
_WORDS_BEFORE = 2
_WORDS_AFTER = 3
_CLAUSE_BREAK = re.compile(r"[.,;:!?()]|\b(?:and|but|while|whereas|although|though|or)\b")
# "more" and "less" are left out of the size words: "their tenure makes them
# more likely to leave" is about likelihood, not tenure. For the same reason a
# size word directly before a risk noun ("means high risk") is removed from the
# window before looking.
_ABOUT_RISK = re.compile(r"\b[a-z]+ (?:risk|chance|likelihood|probability)\b")


# --------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------

def risk_level(probability: float, threshold: float) -> str:
    """The band shown to the model instead of the probability.

    At or above the threshold is "high", or "very high" past halfway to 1.
    Below it is "moderate", or "low" under half the threshold. With the
    shipped 0.40 that is 0-0.20-0.40-0.70-1. Same `>=` as the decision, so a
    band and a decision cannot disagree.
    """
    if probability >= threshold:
        return "very high" if probability >= (1 + threshold) / 2 else "high"
    return "moderate" if probability >= threshold / 2 else "low"


def compare_to_typical(value: float, median: float, spread: float) -> str:
    """Where a value sits against the training median, in words.

    Distance measured in training standard deviations: within a quarter is
    "about typical", past one is "well above/below". Words only, so there is
    no number here for the model to quote.
    """
    if spread <= 0:
        return "about typical"
    z = (value - median) / spread
    if z >= 1:
        return "well above typical"
    if z >= 0.25:
        return "above typical"
    if z <= -1:
        return "well below typical"
    if z <= -0.25:
        return "below typical"
    return "about typical"


def _factor(driver: dict, reference: dict) -> dict:
    field, value = driver["field"], driver["value"]
    factor = {
        "name": driver["label"],
        "field": field,
        "direction": "raises risk" if driver["contribution"] > 0 else "lowers risk",
    }
    if field in _BINARY_FIELDS:
        factor["value"] = "yes" if value else "no"
        return factor
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if field not in _UNQUOTED_VALUE_FIELDS:
        factor["value"] = round(value, 2) if isinstance(value, float) else value
    if numeric and field in reference:
        factor["compared_to_typical"] = compare_to_typical(
            value, reference[field]["median"], reference[field]["spread"],
        )
    return factor


def narration_payload(explanation: dict, top_n: int = NARRATION_TOP_N) -> dict:
    """What the language model is allowed to see.

    Deliberately smaller than the explanation. The raw customer row is absent
    -- there is nothing the model could do with `streamingtv = Yes` except
    speculate about whether it matters. The probability is absent too: the
    model gets a risk band. Protected drivers are removed here, before the
    prompt is built, rather than being forbidden afterwards: a rule in a
    prompt is a request, and removing the information is a control. Drivers
    with exactly zero contribution are dropped, since they have no direction.

    `protected_drivers_omitted` names only the protected drivers that ranked
    above the last factor shown -- the ones that would have been in the
    explanation had they been allowed. Listing every protected field the
    model has (v1 did) put all five on every customer and told a reader
    nothing.
    """
    reference = explanation["reference"]
    kept, omitted = [], []
    for driver in explanation["drivers"]:
        if len(kept) >= top_n:
            break
        if driver["contribution"] == 0:
            continue
        if driver["field"] in PROTECTED_FIELDS:
            omitted.append(driver["field"])
        else:
            kept.append(_factor(driver, reference))
    return {
        "risk_level": risk_level(
            explanation["churn_probability"], explanation["threshold_used"]
        ),
        "decision": (
            "target for retention" if explanation["target_for_retention"]
            else "do not target"
        ),
        "target_for_retention": explanation["target_for_retention"],
        "factors": kept,
        "protected_drivers_omitted": omitted,
    }


# Keys of the payload that are sent to the model. target_for_retention repeats
# `decision`; protected_drivers_omitted would reintroduce exactly what
# filtering removed.
_SENT_KEYS = ("risk_level", "decision", "factors")


def load_prompt() -> str:
    """The system prompt. Read from disk rather than embedded in this file so
    it can be diffed, versioned and hashed on its own."""
    return PROMPT_PATH.read_text()


def build_messages(payload: dict) -> list[dict]:
    """The system turn plus one user turn rendering the payload as JSON."""
    sendable = {key: payload[key] for key in _SENT_KEYS}
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": json.dumps(sendable, indent=2)},
    ]


# --------------------------------------------------------------------------
# Phrase matching
# --------------------------------------------------------------------------

def _phrase_spans(text: str, phrases) -> list[tuple[int, int, str]]:
    """(start, end, label) for each whole-phrase match of `phrases`, an
    iterable of (phrase, label).

    Longest phrase first, with each matched span consumed, so a specific
    phrase beats a general one that overlaps it. Lookarounds rather than \\b
    so that hyphenated phrases ('month-to-month') behave, while 'backup' still
    refuses to match inside 'backups'.
    """
    lowered = text.lower()
    consumed = [False] * len(lowered)
    spans = []
    for phrase, label in sorted(phrases, key=lambda pair: len(pair[0]), reverse=True):
        pattern = re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)")
        for match in pattern.finditer(lowered):
            start, end = match.span()
            if any(consumed[start:end]):
                continue
            for position in range(start, end):
                consumed[position] = True
            spans.append((start, end, label))
    return sorted(spans)


_ALIAS_PAIRS = [
    (alias, field) for field, aliases in FIELD_ALIASES.items() for alias in aliases
]


def fields_mentioned(text: str) -> set[str]:
    """Which feature columns this text refers to.

    'average monthly bill' is scored as average_monthly_charges and does not
    also register as monthlycharges via 'monthly bill'. Without span
    consumption every compound phrase would fire two fields and the
    unlisted-field guard would reject correct narratives.
    """
    return {field for _, _, field in _phrase_spans(text, _ALIAS_PAIRS)}


def risk_claims(text: str) -> set[str]:
    """{"low", "high"}: which levels of risk the text claims."""
    pairs = [(p, "low") for p in _LOW_RISK_PHRASES] + [(p, "high") for p in _HIGH_RISK_PHRASES]
    return {label for _, _, label in _phrase_spans(text, pairs)}


def size_words_near(text: str, start: int, end: int) -> set[str]:
    """Words within the window around a mention, stopping at a clause break."""
    before = _ABOUT_RISK.sub(" ", _CLAUSE_BREAK.split(text[:start].lower())[-1])
    after = _ABOUT_RISK.sub(" ", _CLAUSE_BREAK.split(text[end:].lower())[0])
    words = (
        re.findall(r"[a-z]+", before)[-_WORDS_BEFORE:]
        + re.findall(r"[a-z]+", after)[:_WORDS_AFTER]
    )
    return set(words)


_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def numbers_in(text: str) -> list[float]:
    """Every number in the text, as a value. A percentage is divided by 100,
    so '57%' and '0.57' are the same claim."""
    values = []
    for match in _NUMBER_RE.finditer(text):
        token = match.group()
        is_percent = token.endswith("%")
        try:
            value = float(token.rstrip("%").replace(",", ""))
        except ValueError:  # pragma: no cover -- the regex cannot produce this
            continue
        values.append(value / 100 if is_percent else value)
    return values


def allowed_numbers(payload: dict) -> list[float]:
    """Numbers the summary may state: each factor's own numeric value.

    Nothing else. v1 also allowed the churn probability, and the model quoted
    it as "61.51%" -- an uncalibrated score presented to a reader as a precise
    likelihood. v2 does not send it, so stating any percentage fails here.
    """
    allowed = []
    for factor in payload["factors"]:
        value = factor.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            allowed.append(float(value))
    return allowed


def _is_allowed(value: float, allowed: list[float]) -> bool:
    """Rounding a real value is not a hallucination, so membership is
    tolerant: within half a percent, or 0.005 absolute for small numbers.
    '$4,864' passes for 4863.85."""
    return any(
        abs(value - candidate) <= max(0.005, abs(candidate) * 0.005)
        for candidate in allowed
    )


# --------------------------------------------------------------------------
# The guards
# --------------------------------------------------------------------------

def parse_output(text: str, payload: dict) -> tuple[dict | None, str | None]:
    """(parsed, None) or (None, why it is malformed).

    Checks shape only -- keys, types, enums, lengths, duplicates. Whether the
    content is TRUE is validate_narrative()'s job.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return None, f"not valid JSON ({error.msg})"
    if not isinstance(data, dict):
        return None, f"expected a JSON object, got {type(data).__name__}"
    expected = {"risk_level", "reasons", "summary"}
    if set(data) != expected:
        return None, f"keys were {sorted(data)}, expected {sorted(expected)}"
    if data["risk_level"] not in RISK_LEVELS:
        return None, f"risk_level {data['risk_level']!r} is not one of {list(RISK_LEVELS)}"
    if not isinstance(data["summary"], str) or not data["summary"].strip():
        return None, "summary is missing or blank"
    reasons = data["reasons"]
    if not isinstance(reasons, list) or not reasons:
        return None, "reasons must be a non-empty list"
    if len(reasons) > len(payload["factors"]):
        return None, (
            f"{len(reasons)} reasons given for {len(payload['factors'])} factors"
        )
    for reason in reasons:
        if not isinstance(reason, dict) or set(reason) != {"field", "direction"}:
            return None, f"reason {reason!r} must have exactly field and direction"
        if not isinstance(reason["field"], str):
            return None, f"reason field {reason['field']!r} is not a string"
        if reason["direction"] not in DIRECTIONS:
            return None, f"direction {reason['direction']!r} is not one of {list(DIRECTIONS)}"
    fields = [reason["field"] for reason in reasons]
    if len(set(fields)) != len(fields):
        return None, f"a field is repeated in reasons: {fields}"
    return {
        "risk_level": data["risk_level"],
        "reasons": reasons,
        "summary": data["summary"].strip(),
    }, None


def validate_narrative(
    text: str, payload: dict,
) -> tuple[dict | None, str | None, str | None]:
    """(parsed_output, rejection_type, detail). Exactly one of the first two
    is None.

    Check order is deliberate. A protected attribute is also, by
    construction, an unlisted field -- it was filtered out of the payload --
    so the protected check runs first and gets the more meaningful label.
    Bucketing a fairness failure as a generic 'unlisted_field' would hide it
    in step four's report.
    """
    if not text or not text.strip():
        return None, "empty_output", "the model returned nothing"

    parsed, problem = parse_output(text, payload)
    if parsed is None:
        return None, "malformed_output", problem

    summary = parsed["summary"]
    if len(summary) > MAX_SUMMARY_CHARS:
        return None, "overlong_output", (
            f"summary is {len(summary)} characters, limit {MAX_SUMMARY_CHARS}"
        )

    reason_fields = [reason["field"] for reason in parsed["reasons"]]
    mentioned = fields_mentioned(summary)

    protected = sorted((mentioned | set(reason_fields)) & PROTECTED_FIELDS)
    if protected:
        return None, "protected_attribute", f"named {', '.join(protected)}"

    factors = {factor["field"]: factor for factor in payload["factors"]}
    unlisted_reasons = [field for field in reason_fields if field not in factors]
    if unlisted_reasons:
        return None, "unlisted_field", (
            f"reasons name {', '.join(unlisted_reasons)}, which is not among "
            f"the factors given"
        )
    # A factor's own label can name a different field: the label for
    # average_monthly_charges is "average monthly bill across their whole
    # tenure", which says 'tenure'. A summary that echoes a label it was
    # handed cannot be hallucinating, so whatever the labels say is licensed
    # alongside the fields they belong to.
    listed = set(factors)
    for factor in payload["factors"]:
        listed |= fields_mentioned(factor["name"])
    unlisted = sorted(mentioned - listed)
    if unlisted:
        return None, "unlisted_field", (
            f"summary names {', '.join(unlisted)}, which is not among the "
            f"factors given"
        )

    allowed = allowed_numbers(payload)
    for value in numbers_in(summary):
        if not _is_allowed(value, allowed):
            return None, "hallucinated_number", (
                f"stated {value:g}, which is not in the payload"
            )

    if parsed["risk_level"] != payload["risk_level"]:
        return None, "decision_contradiction", (
            f"risk_level {parsed['risk_level']!r}, but the payload says "
            f"{payload['risk_level']!r}"
        )
    contradicting = "low" if payload["target_for_retention"] else "high"
    if contradicting in risk_claims(summary):
        return None, "decision_contradiction", (
            f"summary claims {contradicting} risk for a customer the model "
            f"decided to {payload['decision']}"
        )

    for reason in parsed["reasons"]:
        expected = factors[reason["field"]]["direction"]
        if reason["direction"] != expected:
            return None, "misstated_factor", (
                f"{reason['field']} {reason['direction']}, but the payload "
                f"says it {expected}"
            )
    for start, end, field in _phrase_spans(summary, _ALIAS_PAIRS):
        comparison = factors.get(field, {}).get("compared_to_typical", "")
        if "above" in comparison:
            wrong = size_words_near(summary, start, end) & _LOW_WORDS
        elif "below" in comparison:
            wrong = size_words_near(summary, start, end) & _HIGH_WORDS
        else:
            continue
        if wrong:
            return None, "misstated_factor", (
                f"called {field} {', '.join(sorted(wrong))}, but it is "
                f"{comparison}"
            )

    return parsed, None, None


def _correction(rejection_type: str, detail: str) -> str:
    """The retry turn. Names the rule that was broken and nothing else.

    Deliberately does not suggest a replacement. A correction that says what
    to write instead would let the retry launder a hallucination into an
    accepted answer, and the second attempt would stop measuring the model.
    """
    rules = {
        "empty_output": "You returned nothing. Return the JSON object.",
        "malformed_output": (
            "That was not a JSON object with exactly risk_level, reasons and "
            "summary in the required form."
        ),
        "overlong_output": "The summary was too long. At most 60 words.",
        "protected_attribute": (
            "That mentioned age, gender, marital status or family status, "
            "which is never allowed."
        ),
        "unlisted_field": (
            "That named a factor you were not given. Use only the factors in "
            "the list."
        ),
        "hallucinated_number": (
            "That stated a number you were not given. The only numbers "
            "allowed are factor values."
        ),
        "decision_contradiction": (
            "That contradicted the risk level or decision you were given."
        ),
        "misstated_factor": (
            "That described a factor's direction or size differently from "
            "what you were given."
        ),
    }
    return f"{rules[rejection_type]} ({detail}) Try again."


# --------------------------------------------------------------------------
# The client
# --------------------------------------------------------------------------

@dataclass
class Completion:
    """One model response, provider-independent."""
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # "stop" normally; "length" when MAX_OUTPUT_TOKENS cut the reply off,
    # which is the first thing to check when malformed_output appears.
    finish_reason: str | None = None


class LLMClient(Protocol):
    """One method, so a fake is trivial and swapping providers is one class."""

    def complete(
        self, messages, *, model: str, temperature: float,
        max_tokens: int, response_format: dict,
    ) -> Completion:
        ...


class OpenAIClient:
    """The real client.

    The SDK is imported inside __init__, not at module scope, so `import
    narrate` works on a plain `uv sync` with no `openai` installed and only
    constructing a real client fails. That is what lets the entire non-live
    test suite run on a clean checkout, and it is why openai sits in the `llm`
    dependency group rather than in the runtime set.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        try:
            from openai import OpenAI
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "The openai package is not installed. It is deliberately not "
                "part of the runtime dependency set -- install it with "
                "`uv sync --group llm`."
            ) from e
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it; it is never read from "
                "a file in the repo and never has a default."
            )
        kwargs = {"api_key": key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def complete(
        self, messages, *, model: str, temperature: float,
        max_tokens: int, response_format: dict,
    ) -> Completion:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            response_format=response_format,
        )
        usage = getattr(response, "usage", None)
        choice = response.choices[0]
        return Completion(
            text=choice.message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            finish_reason=getattr(choice, "finish_reason", None),
        )


# --------------------------------------------------------------------------
# Narration
# --------------------------------------------------------------------------

def narrate(
    explanation: dict,
    client: LLMClient | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_attempts: int = MAX_ATTEMPTS,
    top_n: int = NARRATION_TOP_N,
) -> dict:
    """Add a validated explanation to an attribution.

    `narrative` is the accepted summary sentence(s); `structured` is the whole
    accepted output (risk_level, reasons, summary), which is what a renderer
    should build from. The drivers survive whatever happens to the text. If
    every attempt is rejected, both are None, `narrative_available` is False,
    and the caller still has the full attribution -- a numbers-only answer is
    a degraded response, not a failed one.

    Attempt records are never merged. A failing API call raises rather than
    being recorded as a rejection: it is not a verdict on the text.
    """
    payload = narration_payload(explanation, top_n=top_n)
    messages = build_messages(payload)
    client = client if client is not None else OpenAIClient()

    attempts: list[dict] = []
    structured: dict | None = None

    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        completion = client.complete(
            messages, model=model, temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS, response_format=RESPONSE_FORMAT,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        text = completion.text or ""
        parsed, rejection_type, detail = validate_narrative(text, payload)

        attempts.append({
            "attempt": attempt,
            "accepted": parsed is not None,
            "rejection_type": rejection_type,
            "rejection_detail": detail,
            "text": text,
            "latency_ms": round(latency_ms, 1),
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
            "finish_reason": getattr(completion, "finish_reason", None),
        })

        if parsed is not None:
            structured = parsed
            break

        if attempt < max_attempts:
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": _correction(rejection_type, detail)},
            ]

    return {
        **explanation,
        "narrative": structured["summary"] if structured else None,
        "structured": structured,
        "narrative_available": structured is not None,
        "payload": payload,
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "protected_drivers_omitted": payload["protected_drivers_omitted"],
        "attempts": attempts,
        "final_rejection_type": (
            None if structured is not None else attempts[-1]["rejection_type"]
        ),
    }


def narrate_customer(
    customer: dict,
    client: LLMClient | None = None,
    pipeline=None,
    **kwargs,
) -> dict:
    """Explain and narrate one customer in a single call.

    `pipeline` is the fitted churn model (passed straight to
    explain_customer); `client` is the language model. Two different things
    called 'model' in two different libraries, kept apart here by name.
    """
    explanation = explain.explain_customer(customer, model=pipeline, top_n=None)
    return narrate(explanation, client=client, **kwargs)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def rejection_rates(results: list[dict]) -> dict:
    """The three rates, computed once so the CLI and step four's harness
    cannot grow separate copies.

    The denominators differ on purpose, and the middle one is the subtle one:

      first_attempt_rejection_rate  -- over ALL results. The measure of the
          prompt itself, and the only one worth gating on.
      second_attempt_rejection_rate -- over the RETRIES ISSUED, not over all
          results. None when no retry was ever issued, because 0.0 would read
          as "retries always worked".
      final_rejection_rate          -- over ALL results. What a caller
          actually experiences.
    """
    n = len(results)
    first_rejections = [
        r["attempts"][0] for r in results
        if r["attempts"] and not r["attempts"][0]["accepted"]
    ]
    retried = [r for r in results if len(r["attempts"]) >= 2]
    second_rejections = [
        r["attempts"][1] for r in retried if not r["attempts"][1]["accepted"]
    ]
    final_rejected = [r for r in results if r["narrative"] is None]

    return {
        "n": n,
        "retries_issued": len(retried),
        "first_attempt_rejection_rate": len(first_rejections) / n if n else None,
        "second_attempt_rejection_rate": (
            len(second_rejections) / len(retried) if retried else None
        ),
        "final_rejection_rate": len(final_rejected) / n if n else None,
        "first_attempt_by_type": dict(
            Counter(a["rejection_type"] for a in first_rejections)
        ),
        "second_attempt_by_type": dict(
            Counter(a["rejection_type"] for a in second_rejections)
        ),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def render(result: dict, title: str) -> list[str]:
    """The explanation's own report, with the checked output appended."""
    lines = explain.render(result, title)
    structured = result["structured"]
    if structured is not None:
        lines.append(f"  risk level: {structured['risk_level']}")
        for reason in structured["reasons"]:
            lines.append(f"    - {reason['field']} ({reason['direction']})")
        lines += ["  " + line for line in _wrap(structured["summary"], W - 4)]
    else:
        lines += [
            f"  (no narrative: {result['final_rejection_type']} -- "
            f"{result['attempts'][-1]['rejection_detail']})"
        ]
    if result["protected_drivers_omitted"]:
        lines += [
            "",
            f"  not shown to the model (protected): "
            f"{', '.join(result['protected_drivers_omitted'])}",
        ]
    lines += [
        "",
        f"  prompt {result['prompt_version']} / {result['model']} / "
        f"{len(result['attempts'])} attempt(s)",
        "",
    ]
    return lines


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def render_rates(rates: dict) -> list[str]:
    def pct(value):
        return "  n/a" if value is None else f"{value * 100:5.1f}%"

    lines = [
        "=" * W,
        "REJECTION RATES",
        "=" * W,
        f"  customers narrated            : {rates['n']}",
        f"  retries issued                : {rates['retries_issued']}",
        f"  first-attempt rejection rate  : {pct(rates['first_attempt_rejection_rate'])}"
        f"   <- the measure of the prompt",
        f"  second-attempt rejection rate : {pct(rates['second_attempt_rejection_rate'])}"
        f"   (of retries issued)",
        f"  final rejection rate          : {pct(rates['final_rejection_rate'])}",
    ]
    for label, key in (
        ("first attempt", "first_attempt_by_type"),
        ("second attempt", "second_attempt_by_type"),
    ):
        buckets = rates[key]
        lines.append(f"  {label} rejections by type:")
        if not buckets:
            lines.append("      (none)")
        for reason, count in sorted(buckets.items(), key=lambda kv: -kv[1]):
            lines.append(f"      {reason:<26} {count}")
    lines.append("")
    return lines


def _customers(args) -> list[tuple[str, dict]]:
    if args.dummy:
        return [("config.DUMMY_CUSTOMER", DUMMY_CUSTOMER)]
    frame = pd.read_csv(args.csv)
    validate_input_frame(frame)
    if args.all:
        return [(f"{args.csv} row {i}", frame.iloc[i].to_dict()) for i in range(len(frame))]
    index = args.row or 0
    if not 0 <= index < len(frame):
        raise SystemExit(f"--row {index} is out of range: {args.csv} has {len(frame)} rows.")
    return [(f"{args.csv} row {index}", frame.iloc[index].to_dict())]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Explain a churn prediction and narrate it in English."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dummy", action="store_true", help="explain config.DUMMY_CUSTOMER")
    source.add_argument("--csv", help="a CSV with the 19 raw customer columns")
    parser.add_argument("--row", type=int, help="which CSV row (default 0)")
    parser.add_argument("--all", action="store_true", help="every row of the CSV")
    parser.add_argument("--top", type=int, default=NARRATION_TOP_N,
                        help=f"factors shown to the model (default {NARRATION_TOP_N})")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"default {DEFAULT_MODEL}")
    parser.add_argument("--rates", action="store_true",
                        help="print the three rejection rates for the batch")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress per-customer reports; use with --rates")
    args = parser.parse_args(argv)

    customers = _customers(args)
    pipeline = explain.load_model()
    try:
        client = OpenAIClient()
    except RuntimeError as error:
        # The two setup mistakes -- no key, or the group not installed -- are
        # ordinary and both have a one-line fix, so they get a readable line
        # rather than a traceback through the SDK.
        print(f"{error}", file=sys.stderr)
        return 2

    results, failures = [], []
    for name, customer in customers:
        explanation = explain.explain_customer(customer, model=pipeline, top_n=None)
        try:
            result = narrate(
                explanation, client=client, model=args.model, top_n=args.top,
            )
        except Exception as error:  # noqa: BLE001 -- one bad call must not
            # discard the calls already paid for. The library lets this
            # propagate; the CLI is where a partial batch is still useful.
            failures.append((name, f"{type(error).__name__}: {error}"))
            continue
        results.append(result)
        if not args.quiet:
            print("\n".join(render(result, f"EXPLANATION -- {name}")))

    if args.rates and results:
        print("\n".join(render_rates(rejection_rates(results))))

    for name, error in failures:
        print(f"FAILED {name}: {error}", file=sys.stderr)
    return 1 if failures and not results else 0


if __name__ == "__main__":
    sys.exit(main())
