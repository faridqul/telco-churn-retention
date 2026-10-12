"""Faithfulness harness for the explanation layer.

narrate.py's guards reject a bad answer at run time. This module measures the
answers that got through: how often a summary says something the model's own
numbers do not support. It is step four of the GenAI plan, and it exists
because the only evidence so far was 50 summaries read by hand -- and a
problem seen 0 times in 50 can still be happening 6% of the time.

Run:  uv run python faithfulness.py sample                       (free)
      uv run python faithfulness.py score outputs/stage2_v5.json (free)
      uv run --env-file .env python faithfulness.py calibrate    (costs money)
      uv run --env-file .env python faithfulness.py run          (costs money)
      uv run --env-file .env python faithfulness.py judge        (costs money)
      uv run python faithfulness.py baseline                     (free)
      uv run python faithfulness.py check                        (free; the CI gate)

FIVE PARTS
  1. THE SAMPLE. The held-out test set, rebuilt exactly the way
     fairness_analysis.py rebuilds it and verified the same way. 1,405
     customers produce only 528 distinct inputs to the language model, so the
     sample is drawn from distinct inputs: asking the same question twice
     measures nothing.

  2. THE CODE CHECKS. Pure functions over (payload, accepted answer) that count
     what the guards do not look at -- reasons reordered, a degree the payload
     never gave, a guessed motive, factors weighed against each other, a
     direction stated backwards. They share narrate.py's alias map and its
     clause-bounded window, so the guards and the harness cannot disagree
     about what counts as a mention.

  3. THE JUDGE. A second model answers a fixed yes/no checklist about the same
     input and summary. Two things keep its verdicts checkable: every "yes"
     must quote the words it objects to and the quote is verified to be in the
     summary, and the judge is scored on cases with known answers before it is
     used on anything. **It is a one-off double check of one run, not a part
     of the product** -- see below.

  4. THE RUN. Resumable to the single call, because it is paid for.

  5. THE BASELINE AND THE GATE. A slim, committed copy of the run -- what was
     sent and what came back, no customer rows -- which CI re-checks with
     today's guards and today's checks on every push.

THE JUDGE IS NOT A PART OF THE PRODUCT
Nothing at run time asks it anything: narrate() and /explain never call it,
and a summary shown to a user has been through the guards and nothing else.
Nothing in CI depends on it either. It read the 300 summaries of one run,
once, as a second opinion on the code checks; its verdicts are kept beside
the cases they are about, as a record of that reading, and the gate does not
look at them. Changing the explanation prompt therefore means re-running the
300 customers, not re-running the judge.

THESE ARE MEASUREMENTS, NOT GUARDS
Nothing here rejects an answer at run time. A degree guard and a speculation
guard both existed briefly in September and were removed, because they cost a
retry and a summary for a wording preference. Counting the same things after
the fact costs nothing and still tells you whether the prompt is holding.

WHAT THE GATE CAN AND CANNOT DO
CI has no API key, so it cannot measure a prompt. What it can do is refuse a
prompt that has no measurement: the baseline records the hash of the prompt it
measured, and a different prompt fails the gate until someone runs the harness
again. It also re-checks every saved answer, so a guard changed to be
over-eager fails against 300 real answers rather than passing a handful of
hand-written ones.

The limits were fixed on 2026-10-09 from the 50-customer result (2% rejected
on the first attempt, 0 of 50 findings), before the 300-customer run existed,
so that they are not fitted to it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

import config
import explain
import narrate
import narration_cache

REPO_ROOT = Path(__file__).resolve().parent
W = 78  # report width, matching explain.py, narrate.py and fairness_analysis.py

# --------------------------------------------------------------------------
# The gate's limits. Literal numbers, compared against literals in the tests.
# --------------------------------------------------------------------------

# Fewer than this and "0 seen" says too little: 0 in 300 puts the true rate
# under about 1.3% (95%), where 0 in 50 only puts it under about 7%.
MIN_CASES = 300

# Rejected on the first attempt, re-checked with today's guards. 2% measured
# on 50 customers; the limit leaves room for sampling noise, not for a guard
# that has started refusing sound answers.
MAX_FIRST_ATTEMPT_REJECTION = 0.05

# No summary at all after the retry. What a reader actually experiences.
MAX_FINAL_REJECTION = 0.01

# Each gated code finding, separately.
MAX_FINDING_RATE = 0.02

# What the judge has to manage on cases with known answers before its verdicts
# on unknown ones are worth recording.
CALIBRATION_MIN_RECALL = 0.80
CALIBRATION_MAX_FALSE_ALARM = 0.10

BASELINE_PATH = REPO_ROOT / "docs" / "faithfulness_baseline.json"
REPORT_PATH = REPO_ROOT / "docs" / "faithfulness_report.txt"
SAMPLE_PATH = REPO_ROOT / "outputs" / "harness_customers.csv"

SAMPLE_SEED = 42

# "v5": names the files a run of the current prompt writes.
PROMPT_TAG = narrate.PROMPT_VERSION.rsplit("_", 1)[-1]
# Anchored to the repository, like SAMPLE_PATH, so a command run from another
# directory still finds a paid run rather than starting a second one there.
RUN_PATH = str(REPO_ROOT / "outputs" / f"harness_{PROMPT_TAG}.json")

# The judge's files live one folder down. LLMcalls.ipynb reads every
# outputs/*.json as a saved run and opens the newest; a file of verdicts
# there is not a run, and the notebook fails on it.
JUDGE_DIR = REPO_ROOT / "outputs" / "judge"
JUDGED_PATH = str(JUDGE_DIR / f"harness_{PROMPT_TAG}_judged.json")

# The 19 raw columns, in the order api.Customer and the sample CSV use.
RAW_COLUMNS = list(config.DUMMY_CUSTOMER)

# USD per million tokens, for the estimates this module prints. An estimate
# only: the provider's invoice is the record.
PRICE_PER_M = {
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-6-luna": {"in": 0.10, "out": 0.50},
}


# --------------------------------------------------------------------------
# The code checks
# --------------------------------------------------------------------------

# A statement the payload does not support, or one of prompt v5's four rules
# broken. Each is counted separately and each has its own limit.
GATED_FINDINGS = (
    "reasons_reordered",
    "summary_reordered",
    "degree_overstated",
    "speculation",
    "weighing",
    "direction_contradicted",
)

# Wording, not truth. Reported so a change of habit is visible; never gated.
STYLE_FINDINGS = (
    "says_risk_level",
    "direction_refrain",
    "value_unstated",
    "over_word_limit",
)

# Prompt v5 names four; the rest are the same claim in other words.
_DEGREE_WORDS = frozenset({
    "much", "far", "very", "significantly", "considerably", "substantially",
    "extremely", "greatly", "vastly", "dramatically", "markedly",
})

# Prompt v5 names may, might, perhaps, suggests, indicates and "a sign of".
# Not "likely": "likely to leave" is a statement about risk, which is given.
_SPECULATION = (
    "may", "might", "perhaps", "possibly", "maybe", "presumably", "probably",
    "could", "suggest", "suggests", "suggesting", "indicate", "indicates",
    "indicating", "imply", "implies", "implying", "a sign of", "sign that",
    "signals", "appears to", "seems to",
)

# One factor ranked against another. The payload never says how strong a
# factor is, so every one of these is a claim the model cannot support.
_WEIGHING = (
    "outweigh", "outweighs", "outweighed", "outweighing", "mainly",
    "primarily", "chiefly", "largely", "mostly", "biggest reason",
    "biggest factor", "main reason", "main factor", "main driver",
    "primary reason", "primary factor", "primary driver", "key reason",
    "key factor", "key driver", "most important", "more important",
    "most significant", "more significant", "strongest", "above all",
    # Added 2026-10-12 after reading the 300-customer run: row 27 said a long
    # tenure "is not enough to offset the other factors", which the judge
    # caught and this list did not.
    "offset", "offsets", "offsetting", "not enough to",
)

_RAISE = (r"(?:raise[sd]?|raising|increase[sd]?|increasing|heighten(?:s|ed|ing)?"
          r"|elevate[sd]?|elevating|add(?:s|ed|ing)? to)")
_LOWER = (r"(?:lower(?:s|ed|ing)?|reduce[sd]?|reducing|decrease[sd]?|decreasing"
          r"|lessen(?:s|ed|ing)?|diminish(?:es|ed|ing)?|mitigat(?:e|es|ed|ing))")
_DEGREE_ALTERNATION = "|".join(sorted(_DEGREE_WORDS))

# "raises their risk", "lower the likelihood", "reduces their overall risk".
# A determiner is required, which is what tells the verb "lower their risk"
# from the adjective in "a lower risk".
_RISK_OBJECT = (r"(?:\s+(?:their|the|this customer's|its|that|his|her|overall|own)){1,3}"
                r"\s+(?:risk|likelihood|chance|chances|probability)")
_DIRECTION = re.compile(
    rf"\b(?:(?P<raise>{_RAISE})|(?P<lower>{_LOWER})){_RISK_OBJECT}\b"
)

# "significantly lowers their risk", "lowers their risk considerably": a
# strength the payload never stated. The risk object is required here too, or
# "a much lower overall commitment" would be read as a verb with an adverb.
_EFFECT_DEGREE = re.compile(
    rf"\b(?P<degree>{_DEGREE_ALTERNATION})\s+"
    rf"(?:(?:{_RAISE}|{_LOWER}){_RISK_OBJECT}|contribut\w+|affect\w*|impact\w*|influenc\w+)\b"
    rf"|\b(?:{_RAISE}|{_LOWER}){_RISK_OBJECT}\s+(?P<after>{_DEGREE_ALTERNATION})\b"
)

# "...the likelihood of staying" turns the direction round. Rare, and not worth
# guessing at: such a phrase is left unread.
_INVERTED = re.compile(r"\b(?:stay|staying|stays|remain|remaining|remains|loyal|retention)\b")

_CONCESSIVE = re.compile(r"^\W*(?:although|even though|though|while|whereas|despite|in spite of)\b")
_PLURAL_REFERENCE = re.compile(r"\b(?:both|all|each)\b")

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

# The word limit prompt v5 states. The guard's own backstop is characters.
WORD_LIMIT = 60


def _finding(kind: str, detail: str) -> dict:
    return {"type": kind, "detail": detail}


def _mask(text: str, start: int, end: int) -> str:
    """Blank a span without moving anything after it."""
    return text[:start] + " " * (end - start) + text[end:]


def _mask_band(lowered: str, risk_level: str) -> str:
    """Remove the risk band's own name, so the 'very' of a customer who really
    is 'very high' risk is not read as a degree word. Only the band the
    payload gave: 'very high risk' written about a 'high' customer stays."""
    for match in list(re.finditer(r"(?<!\w)" + re.escape(risk_level) + r"(?!\w)", lowered)):
        lowered = _mask(lowered, match.start(), match.end())
    return lowered


def _window(lowered: str, start: int, end: int) -> list[tuple[int, str]]:
    """(position, word) for the words that describe a mention.

    The same window narrate.size_words_near() uses -- same word counts, same
    clause breaks, same removal of a word that is about risk rather than about
    the field -- but keeping positions, so a degree word can be attributed to
    one mention and not counted again.
    """
    breaks = [m.end() for m in narrate._CLAUSE_BREAK.finditer(lowered[:start])]
    clause_start = breaks[-1] if breaks else 0
    following = narrate._CLAUSE_BREAK.search(lowered, end)
    clause_end = following.start() if following else len(lowered)

    masked = lowered
    for match in narrate._ABOUT_RISK.finditer(lowered):
        masked = _mask(masked, match.start(), match.end())

    def words(low, high):
        return [(m.start(), m.group()) for m in re.finditer(r"[a-z]+", masked[:high])
                if m.start() >= low]

    return (words(clause_start, start)[-narrate._WORDS_BEFORE:]
            + words(end, clause_end)[:narrate._WORDS_AFTER])


def _mentions(lowered: str, factors: dict) -> list[tuple[int, int, str]]:
    """Alias spans that name one of this payload's factors."""
    return [span for span in narrate._phrase_spans(lowered, narrate._ALIAS_PAIRS)
            if span[2] in factors]


def _order_findings(payload: dict, structured: dict, mentions: list) -> list[dict]:
    given = [factor["field"] for factor in payload["factors"]]
    found = []

    reasons = [reason["field"] for reason in structured["reasons"]]
    expected = [field for field in given if field in reasons]
    if [field for field in reasons if field in given] != expected:
        found.append(_finding(
            "reasons_reordered", f"reasons are {reasons}; given order was {given}",
        ))

    first = {}
    for start, _, field in mentions:
        first.setdefault(field, start)
    mentioned = sorted(first, key=lambda field: first[field])
    if mentioned != [field for field in given if field in first]:
        found.append(_finding(
            "summary_reordered", f"summary names {mentioned}; given order was {given}",
        ))
    return found


def _weighing_findings(lowered: str) -> tuple[list[dict], set[int]]:
    """Findings, and the positions of degree words they account for."""
    found, used = [], set()
    pairs = [(phrase, phrase) for phrase in _WEIGHING]
    for _, _, phrase in narrate._phrase_spans(lowered, pairs):
        found.append(_finding("weighing", f"says {phrase!r}"))
    for match in _EFFECT_DEGREE.finditer(lowered):
        used.add(match.start("degree") if match.group("degree") else match.start("after"))
        found.append(_finding(
            "weighing", f"says {match.group(0)!r}: the strength of a factor is not given",
        ))
    return found, used


def _degree_findings(payload: dict, lowered: str, factors: dict, mentions: list,
                     used: set[int]) -> list[dict]:
    """A degree word beside a factor whose comparison does not say 'much'.

    `used` holds degree words already counted as a claim about a factor's
    strength ("significantly lowers their risk"); those are not counted twice.
    """
    # Masking blanks characters in place, so the mentions' positions still hold.
    text = _mask_band(lowered, payload["risk_level"])
    found, attributed = [], set(used)
    for start, end, field in mentions:
        comparison = factors[field].get("vs_other_customers", "")
        for position, word in _window(text, start, end):
            if word not in _DEGREE_WORDS or position in used:
                continue
            attributed.add(position)
            if "much" not in comparison:
                found.append(_finding(
                    "degree_overstated",
                    f"{word!r} beside {field}, which is "
                    f"{comparison or 'given no comparison'}",
                ))
    # A degree word that sits beside no factor at all ("which is much less
    # than most customers") cannot be pinned to one. It is let through when
    # some factor really is "much" anything, and counted when none is.
    if not any("much" in factor.get("vs_other_customers", "") for factor in factors.values()):
        for match in re.finditer(r"[a-z]+", text):
            if match.group() in _DEGREE_WORDS and match.start() not in attributed:
                found.append(_finding(
                    "degree_overstated",
                    f"{match.group()!r}, and no factor's comparison says 'much'",
                ))
    return found


def _speculation_findings(lowered: str) -> list[dict]:
    pairs = [(phrase, phrase) for phrase in _SPECULATION]
    return [_finding("speculation", f"says {phrase!r}")
            for _, _, phrase in narrate._phrase_spans(lowered, pairs)]


def _sentences(lowered: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence. Splits only where whitespace follows the
    full stop, so '85.5' stays whole."""
    bounds, start = [], 0
    for match in re.finditer(r"[.!?]\s+", lowered):
        bounds.append((start, match.start() + 1))
        start = match.end()
    if start < len(lowered):
        bounds.append((start, len(lowered)))
    return bounds


def direction_phrases(lowered: str) -> list[tuple[int, int, str]]:
    """(start, end, 'raises risk' | 'lowers risk') for each explicit claim."""
    phrases = []
    for match in _DIRECTION.finditer(lowered):
        if _INVERTED.search(lowered[match.end():match.end() + 40].split(".")[0]):
            continue
        direction = "raises risk" if match.group("raise") else "lowers risk"
        phrases.append((match.start(), match.end(), direction))
    return phrases


def _direction_findings(lowered: str, factors: dict, mentions: list) -> list[dict]:
    """'lowers their risk' said of a factor that raises it, or the reverse.

    Deliberately conservative, because attaching a verb to its subject in
    English is not something a regex does reliably. A direction phrase is
    attached to the nearest factor mentioned before it in the same sentence,
    since the previous direction phrase; to all of them when the sentence says
    "both of which" or "all of which". A mention inside an "although ..."
    clause is not attached to a main-clause verb. When nothing is mentioned --
    "the absence of these services lowers their risk" -- nothing is checked.
    It misses some real errors by design; the judge reads those.
    """
    found = []
    phrases = direction_phrases(lowered)
    for sentence_start, sentence_end in _sentences(lowered):
        cursor = sentence_start
        for start, end, direction in phrases:
            if not sentence_start <= start < sentence_end:
                continue
            segment = [m for m in mentions if cursor <= m[0] < start]
            lead = lowered[max(cursor, start - 30):start]
            by_which = "which" in lead
            concession = None if by_which else _CONCESSIVE.search(lowered[cursor:start])
            if concession:
                # Up to the comma that closes the "although ..." clause, or to
                # the verb itself when there is none.
                comma = lowered.find(",", cursor + concession.end(), start)
                boundary = comma if comma != -1 else start
                segment = [m for m in segment if m[0] > boundary]
            if segment and not _PLURAL_REFERENCE.search(lead):
                segment = segment[-1:]
            # dict.fromkeys: one field can be mentioned twice in a segment
            # ("fiber optic internet" is two aliases of one field).
            for field in dict.fromkeys(field for _, _, field in segment):
                given = factors[field]["direction"]
                if given != direction:
                    found.append(_finding(
                        "direction_contradicted",
                        f"says {lowered[start:end]!r} of {field}, which {given}",
                    ))
            cursor = end
    return found


def _value_stated(factor: dict, lowered: str) -> bool:
    value = factor["value"]
    if isinstance(value, bool) or value is None:
        return True
    if isinstance(value, (int, float)):
        # Not "one-year" or "two year": that is a contract term, and counting
        # it would let "a one-year contract" stand in for a tenure of 1.
        stated = narrate.numbers_in(lowered) + [
            float(number) for word, number in _NUMBER_WORDS.items()
            if re.search(rf"\b{word}\b(?![- ]year)", lowered)
        ]
        return narrate._is_allowed(float(value), stated) if stated else False
    text = str(value).lower()
    if text in ("yes", "no"):  # stated as "has" / "does not have", not as the word
        return True
    loose = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"[^a-z0-9]+", " ", text).strip() in loose


def _style_findings(payload: dict, structured: dict, summary: str, lowered: str) -> list[dict]:
    found = []
    if "risk level" in lowered:
        found.append(_finding("says_risk_level", "says 'risk level'"))
    if re.search(r"\bwhich (?:also |further )?" + f"(?:{_RAISE}|{_LOWER})" + r" their risk\b", lowered):
        found.append(_finding("direction_refrain", "'which raises/lowers their risk'"))
    factors = {factor["field"]: factor for factor in payload["factors"]}
    unstated = [
        reason["field"] for reason in structured["reasons"]
        if "value" in factors.get(reason["field"], {})
        and not _value_stated(factors[reason["field"]], lowered)
    ]
    if unstated:
        found.append(_finding("value_unstated", f"no value given for {', '.join(unstated)}"))
    words = len(summary.split())
    if words > WORD_LIMIT:
        found.append(_finding("over_word_limit", f"{words} words, limit {WORD_LIMIT}"))
    return found


def findings(payload: dict, structured: dict) -> list[dict]:
    """Everything the checks see in one accepted answer.

    `structured` is what validate_narrative() returned: risk_level, reasons,
    summary. Each finding is {"type", "detail"}; the type is one of
    GATED_FINDINGS or STYLE_FINDINGS. An answer can have several, and several
    of one type.
    """
    summary = structured["summary"]
    lowered = summary.lower()
    factors = {factor["field"]: factor for factor in payload["factors"]}
    mentions = _mentions(lowered, factors)  # scanned once; three checks use it
    weighing, used = _weighing_findings(lowered)
    return (
        _order_findings(payload, structured, mentions)
        + _degree_findings(payload, lowered, factors, mentions, used)
        + _speculation_findings(lowered)
        + weighing
        + _direction_findings(lowered, factors, mentions)
        + _style_findings(payload, structured, summary, lowered)
    )


def finding_types(payload: dict, structured: dict) -> set[str]:
    return {finding["type"] for finding in findings(payload, structured)}


# --------------------------------------------------------------------------
# The sample
# --------------------------------------------------------------------------

def _plain(customer: dict) -> dict:
    """numpy scalars to Python, NaN to None: one row as api.Customer holds it."""
    plain = {}
    for key, value in customer.items():
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, float) and math.isnan(value):
            value = None
        plain[key] = value
    return plain


def input_key(payload: dict) -> str:
    """Identifies what the language model is sent. Two customers with the same
    key get the same question, so only one of them is worth asking."""
    return narration_cache.cache_key(
        payload, narrate.PROMPT_VERSION, narrate.DEFAULT_MODEL,
        narrate.DEFAULT_TEMPERATURE, narrate.DEFAULT_SEED,
    )


def distinct_inputs(pipeline=None, data: str | None = None) -> list[dict]:
    """One entry per distinct model input in the held-out test set.

    The split is rebuilt by fairness_analysis.build_test_split() and checked
    by its verify_reconstruction(), which refuses to continue unless the
    confusion matrix matches the published one -- so these are provably the
    test rows, not a plausible-looking 1,405 of something else.
    """
    import fairness_analysis  # lazy: pulls in campaign_profit and sklearn's splitter

    pipeline = pipeline if pipeline is not None else explain.load_model()
    threshold = config.load_threshold(str(explain._anchor(config.METADATA_PATH)))
    csv = fairness_analysis.locate_dataset(data)
    _, x_test, _, y_test = fairness_analysis.build_test_split(csv)
    fairness_analysis.verify_reconstruction(
        y_test, pipeline.predict_proba(x_test)[:, 1], threshold,
    )

    raw = x_test[RAW_COLUMNS]
    seen: dict[str, dict] = {}
    for position in range(len(raw)):
        customer = _plain(raw.iloc[position].to_dict())
        explanation = explain.explain_customer(
            customer, model=pipeline, threshold=threshold, top_n=None,
        )
        payload = narrate.narration_payload(explanation)
        key = input_key(payload)
        if key not in seen:
            seen[key] = {
                "key": key, "position": position, "customer": customer,
                "risk_level": payload["risk_level"],
            }
    return list(seen.values())


def choose_sample(inputs: list[dict], n: int, seed: int = SAMPLE_SEED) -> list[dict]:
    """`n` of the distinct inputs: every 'very high', the rest in proportion.

    'very high' is the rarest band and the one a retention call is made on, so
    none of it is left to chance. The remaining places go to the other bands
    in proportion to their size (largest remainder), chosen inside each band
    by a seeded shuffle of a sorted list -- the same sample on every machine.
    """
    if n >= len(inputs):
        return sorted(inputs, key=lambda item: item["position"])
    rng = random.Random(seed)
    by_band: dict[str, list[dict]] = {}
    for item in sorted(inputs, key=lambda item: item["key"]):
        by_band.setdefault(item["risk_level"], []).append(item)

    chosen = list(by_band.pop("very high", []))
    if len(chosen) > n:
        chosen = rng.sample(chosen, n)
    places = n - len(chosen)
    rest = sum(len(items) for items in by_band.values())
    shares = {band: places * len(items) / rest for band, items in by_band.items()}
    quota = {band: int(share) for band, share in shares.items()}
    leftovers = sorted(shares, key=lambda band: (shares[band] - quota[band], band), reverse=True)
    for band in leftovers[:places - sum(quota.values())]:
        quota[band] += 1
    for band in sorted(by_band):
        chosen += rng.sample(by_band[band], quota[band])
    return sorted(chosen, key=lambda item: item["position"])


def write_sample(sample: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([item["customer"] for item in sample], columns=RAW_COLUMNS).to_csv(
        path, index=False,
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Resumable work: one JSON line per finished item
# --------------------------------------------------------------------------

def _read_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append_line(path: Path, record: dict) -> None:
    with open(path, "a") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()


def _partial(out_path: Path) -> Path:
    return out_path.with_name(out_path.name + ".partial.jsonl")


def _refuse_existing(out_path: Path) -> None:
    """A finished file is a paid measurement. Checked before any call is made."""
    if out_path.exists():
        raise FileExistsError(
            f"{out_path} already exists; choose another name. Nothing was sent "
            f"to the API."
        )


# How many calls in a row may fail before the work stops. One failure is a
# blip and is retried on the next start; this many is an outage or a bad key,
# and carrying on would only spend time.
MAX_CONSECUTIVE_FAILURES = 5


def _work(items, out_path: Path, name_of, do, progress, made_with: dict | None = None) -> list[dict]:
    """Do `do(item)` for every item not already in the partial file.

    Each result is appended and flushed as it arrives, so an interrupted run
    resumes from the next item. The finished file is written, and the partial
    one removed, only when every item has a result.

    `made_with` is what every result of this work carries -- the prompt
    version and model, say. A partial file whose results say otherwise was
    started under different settings, and finishing it would produce one file
    measuring two things; that is refused, before any call is made.
    """
    _refuse_existing(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    partial = _partial(out_path)
    done = {record["case"]: record for record in _read_lines(partial)}
    for record in done.values():
        for key, value in (made_with or {}).items():
            if record.get(key) != value:
                raise ValueError(
                    f"{partial} was started with {key}={record.get(key)!r}; this "
                    f"run would use {value!r}. Finish it with the original "
                    f"settings, or delete it to start again. Nothing was sent "
                    f"to the API."
                )
    if done:
        progress(f"Resuming: {len(done)} of {len(items)} already done ({partial.name}).")

    failures, consecutive = [], 0
    for index, item in enumerate(items, start=1):
        name = name_of(item)
        if name in done:
            continue
        try:
            record = do(item)
        except Exception as error:  # noqa: BLE001 -- one failed call must not
            # discard the calls already paid for; they are safely on disk.
            failures.append((name, f"{type(error).__name__}: {error}"))
            consecutive += 1
            if consecutive >= MAX_CONSECUTIVE_FAILURES:
                progress(f"Stopping: {consecutive} calls in a row failed. "
                         f"Last: {failures[-1][1]}")
                break
            continue
        consecutive = 0
        record["case"] = name
        _append_line(partial, record)
        done[name] = record
        if index % 25 == 0:
            progress(f"  {len(done)} of {len(items)} done")

    for name, error in failures:
        progress(f"FAILED {name}: {error}")
    if len(done) < len(items):
        progress(f"{len(done)} of {len(items)} done. Run the same command again "
                 f"to finish; nothing already done will be repeated.")
        return [done[name_of(item)] for item in items if name_of(item) in done]

    results = [done[name_of(item)] for item in items]
    out_path.write_text(json.dumps(results, indent=2))
    partial.unlink(missing_ok=True)
    progress(f"Saved {len(results)} result(s) to {out_path}.")
    return results


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def run(csv_path: Path, out_path: Path, client, pipeline=None,
        limit: int | None = None, progress=print) -> list[dict]:
    """Narrate every row of `csv_path`, with no cache, saving as it goes.

    The output is the list `narrate.py --save` writes, so LLMcalls.ipynb and
    llm_tracing's backfill read it unchanged. No cache on purpose: a cached
    answer was not produced by this run and would not be a measurement of it.
    """
    frame = pd.read_csv(csv_path)
    config.validate_input_frame(frame)
    pipeline = pipeline if pipeline is not None else explain.load_model()
    rows = list(range(len(frame)))[:limit]

    def narrate_row(position: int) -> dict:
        explanation = explain.explain_customer(
            _plain(frame.iloc[position].to_dict()), model=pipeline, top_n=None,
        )
        return narrate.narrate(explanation, client=client, cache=None)

    return _work(
        rows, Path(out_path), lambda position: f"{Path(csv_path).name} row {position}",
        narrate_row, progress,
        made_with={"prompt_version": narrate.PROMPT_VERSION, "model": narrate.DEFAULT_MODEL},
    )


# --------------------------------------------------------------------------
# The judge
# --------------------------------------------------------------------------

# judge_v1 is kept, unused, because outputs/judge/judge_calibration_judge_v1.json
# measures it: it caught 55 of 55 faulty cases and raised 5 false alarms on 48
# clean ones, all five the same -- "does not have an online security add-on"
# for a value of "No internet service", called an added fact. v2 says how a
# yes/no value may be restated, and changes nothing else.
JUDGE_PROMPT_PATH = REPO_ROOT / "prompts" / "judge_v2.txt"
JUDGE_PROMPT_VERSION = JUDGE_PROMPT_PATH.stem

# Chosen by the user on 2026-10-09, in place of gpt-4o-mini: a judge from the
# same model as the writer is more forgiving of text that reads like its own,
# and this one is two generations newer and costs less. The top tier
# (gpt-6.1-sol) would be about $1.30 for the whole harness, over the project's
# cap on live spend. Whatever the model, the calibration is what earns it
# trust: it is scored on known answers before it is used on unknown ones.
JUDGE_MODEL = "gpt-6-luna"

# A reasoning model: it thinks before it answers and bills the thinking as
# output. "low" measured about 240 thinking tokens a verdict on 2026-10-09
# (1,060 in, 330 out, $0.00027). The model's own default is "medium".
JUDGE_REASONING_EFFORT = "low"

# The thinking counts against this cap, so it is far above the ~90 tokens a
# verdict itself takes: a cap near that would cut the reply off mid-JSON.
JUDGE_MAX_TOKENS = 2000

# Closed, like narrate.REJECTION_TYPES, and for the same reason: these are
# counted, and a free-text verdict cannot be.
JUDGE_CHECKS = (
    "adds_fact", "wrong_direction", "overstated_size", "guesses_why",
    "weighs_factors",
)

JUDGE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "faithfulness_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                check: {
                    "type": "object",
                    "properties": {
                        "found": {"type": "boolean"},
                        "quote": {"type": "string"},
                    },
                    "required": ["found", "quote"],
                    "additionalProperties": False,
                }
                for check in JUDGE_CHECKS
            },
            "required": list(JUDGE_CHECKS),
            "additionalProperties": False,
        },
    },
}


class JudgeCompletion(narrate.Completion):
    """A Completion that also says how much of the output was thinking."""

    def __init__(self, *args, reasoning_tokens: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.reasoning_tokens = reasoning_tokens


class JudgeClient(narrate.OpenAIClient):
    """The request shape the judge's model takes.

    Same key handling and the same lazy SDK import as narrate.OpenAIClient,
    and the same `complete()` signature, so judge_one() does not care which it
    is handed and a FakeLLM stands in for either. What differs is what is
    sent: gpt-6-luna refuses any temperature but its default ("Only the
    default (1) value is supported", probed 2026-10-09), so `temperature` is
    accepted here and deliberately not forwarded. The seed is forwarded and
    was accepted. So the judge is steadier than an unseeded call and not
    guaranteed repeatable -- one more reason its verdicts are saved, never
    re-asked.
    """

    def complete(self, messages, *, model, temperature, max_tokens,
                 response_format, seed=None):
        kwargs = {"seed": seed} if seed is not None else {}
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,
            response_format=response_format,
            reasoning_effort=JUDGE_REASONING_EFFORT,
            **kwargs,
        )
        usage = getattr(response, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        choice = response.choices[0]
        return JudgeCompletion(
            text=choice.message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            finish_reason=getattr(choice, "finish_reason", None),
            system_fingerprint=getattr(response, "system_fingerprint", None),
            reasoning_tokens=getattr(details, "reasoning_tokens", None),
        )


def judge_messages(payload: dict, summary: str) -> list[dict]:
    """The judge is shown what the narrating model was shown, and the summary.

    Not the probability, not the decision, not the customer's row: the
    question is whether the summary is supported by its own input, and
    anything more would let the judge mark a summary down for leaving out
    something it was never told.
    """
    return [
        {"role": "system", "content": JUDGE_PROMPT_PATH.read_text()},
        {"role": "user", "content": json.dumps({
            "given": narrate.sent_payload(payload), "summary": summary,
        }, indent=2)},
    ]


def _loose(text: str) -> str:
    """Lower case, punctuation and spacing flattened, for comparing a quote."""
    return re.sub(r"[^a-z0-9$%]+", " ", text.lower()).strip()


def parse_verdict(text: str, summary: str) -> tuple[dict | None, str | None]:
    """(verdict, None), or (None, why the reply cannot be used).

    A "found" with a quote that is not in the summary is the judge describing
    a summary other than the one it was given. That is not a verdict, and it
    is not quietly counted as "faithful" either: the reply is refused, and the
    refusal is counted on its own.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return None, f"not valid JSON ({error.msg})"
    if not isinstance(data, dict) or set(data) != set(JUDGE_CHECKS):
        return None, f"expected exactly the keys {list(JUDGE_CHECKS)}"
    checks = {}
    for check in JUDGE_CHECKS:
        entry = data[check]
        if (not isinstance(entry, dict) or set(entry) != {"found", "quote"}
                or not isinstance(entry["found"], bool)
                or not isinstance(entry["quote"], str)):
            return None, f"{check} must be {{found: bool, quote: str}}"
        quote = entry["quote"].strip()
        if entry["found"]:
            if not _loose(quote):
                return None, f"{check} was found with no quote"
            if _loose(quote) not in _loose(summary):
                return None, f"{check} quotes {quote!r}, which is not in the summary"
        checks[check] = {"found": entry["found"], "quote": quote if entry["found"] else ""}
    return {
        "checks": checks,
        "unfaithful": any(entry["found"] for entry in checks.values()),
    }, None


def judge_one(payload: dict, summary: str, client) -> dict:
    """One verdict. Never raises for a bad reply; a failed call still does."""
    completion = client.complete(
        judge_messages(payload, summary), model=JUDGE_MODEL,
        temperature=narrate.DEFAULT_TEMPERATURE, max_tokens=JUDGE_MAX_TOKENS,
        response_format=JUDGE_RESPONSE_FORMAT, seed=narrate.DEFAULT_SEED,
    )
    verdict, problem = parse_verdict(completion.text or "", summary)
    return {
        "verdict": verdict,
        "error": problem,
        "text": completion.text or "",
        "prompt_tokens": completion.prompt_tokens,
        "completion_tokens": completion.completion_tokens,
        "reasoning_tokens": getattr(completion, "reasoning_tokens", None),
        "finish_reason": getattr(completion, "finish_reason", None),
        "judge_model": JUDGE_MODEL,
        "judge_reasoning_effort": JUDGE_REASONING_EFFORT,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
    }


def _judged_with() -> dict:
    """What every verdict record carries; see _work()'s `made_with`."""
    return {"judge_model": JUDGE_MODEL, "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "judge_reasoning_effort": JUDGE_REASONING_EFFORT}


def judge_run(results: list[dict], out_path: Path, client, progress=print) -> list[dict]:
    """Judge every accepted summary in a saved run."""
    accepted = [result for result in results if result["structured"] is not None]
    return _work(
        accepted, Path(out_path), lambda result: result["case"],
        lambda result: judge_one(result["payload"], result["structured"]["summary"], client),
        progress, made_with=_judged_with(),
    )


# --------------------------------------------------------------------------
# Calibrating the judge
# --------------------------------------------------------------------------

# Which judge check should fire for each code finding. Order has no entry: the
# judge is not asked about it, because code checks it exactly.
_JUDGE_CHECK_FOR = {
    "degree_overstated": "overstated_size",
    "speculation": "guesses_why",
    "weighing": "weighs_factors",
    "direction_contradicted": "wrong_direction",
}

_FLIP = {"raises": "lowers", "lowers": "raises", "increases": "lowers",
         "reduces": "raises", "decreases": "raises"}

_EXTRA_FACTORS = (
    ("techsupport", "They also have no tech support add-on."),
    ("paymentmethod", "They also pay by electronic check."),
    ("paperlessbilling", "They also use paperless billing."),
    ("streamingtv", "They also have streaming TV."),
)


def _plant(kind: str, payload: dict, summary: str) -> str | None:
    """`summary` with one error of `kind` added, or None if it does not apply."""
    factors = {factor["field"]: factor for factor in payload["factors"]}
    if kind == "wrong_direction":
        pattern = re.compile(r"\b(" + "|".join(_FLIP) + r")\b(?= their risk)")
        match = pattern.search(summary)
        if not match:
            return None
        return summary[:match.start()] + _FLIP[match.group(1)] + summary[match.end():]
    if kind == "adds_fact":
        for field, sentence in _EXTRA_FACTORS:
            if field not in factors:
                return f"{summary} {sentence}"
        return None
    if kind == "adds_number":
        if "monthlycharges" not in factors:
            return f"{summary} They pay $97.40 a month."
        if "tenure" not in factors:
            return f"{summary} They have been a customer for 14 months."
        return None
    if kind == "overstated_size":
        lowered = summary.lower()
        for start, end, field in _mentions(lowered, factors):
            comparison = factors[field].get("vs_other_customers", "")
            if not comparison or "much" in comparison or "similar" in comparison:
                continue
            word = comparison.split()[0]  # "lower" or "higher"
            for position, found in _window(lowered, start, end):
                if found == word and "much" not in lowered[max(0, position - 6):position]:
                    return summary[:position] + "much " + summary[position:]
        return None
    if kind == "guesses_why":
        return f"{summary} This may indicate dissatisfaction with the service."
    if kind == "weighs_factors":
        return f"{summary} The contract is the main reason."
    raise ValueError(f"unknown kind {kind!r}")


# What the judge should say about each planted kind.
PLANTED = {
    "wrong_direction": "wrong_direction",
    "adds_fact": "adds_fact",
    "adds_number": "adds_fact",
    "overstated_size": "overstated_size",
    "guesses_why": "guesses_why",
    "weighs_factors": "weighs_factors",
}


def calibration_cases(known_run: list[dict], clean_run: list[dict]) -> list[dict]:
    """Cases whose right answer is known before the judge sees them.

    Three kinds:
      known   -- real answers from `known_run` that the code checks flag, each
                 expecting the matching judge check. On the v3 run these are
                 the problems found by reading it.
      clean   -- real answers from `clean_run` with no gated finding. The
                 judge should say nothing about them.
      planted -- a clean answer with exactly one error written into it. The
                 kinds are taken in turn, but a kind that does not apply to a
                 summary passes its turn to the next, so the counts are not
                 equal: an overstated size needs a comparison that is not
                 already "much", and few clean summaries have one.

    One distinct (input, summary) pair appears once, however many customers
    shared it.
    """
    cases, seen = [], set()

    def add(kind, source, payload, summary, expect):
        identity = (kind, json.dumps(narrate.sent_payload(payload), sort_keys=True), summary)
        if identity in seen:
            return
        seen.add(identity)
        cases.append({
            "case": f"{kind} {len(cases)}: {source}", "kind": kind,
            "payload": payload, "summary": summary, "expect": expect,
        })

    for result in known_run:
        structured = result["structured"]
        if structured is None:
            continue
        expected = sorted({
            _JUDGE_CHECK_FOR[kind]
            for kind in finding_types(result["payload"], structured)
            if kind in _JUDGE_CHECK_FOR
        })
        if expected:
            add("known", result.get("case", "?"), result["payload"],
                structured["summary"], expected)

    clean = []
    for result in clean_run:
        structured = result["structured"]
        if structured is None:
            continue
        if finding_types(result["payload"], structured) & set(GATED_FINDINGS):
            continue
        before = len(cases)
        add("clean", result.get("case", "?"), result["payload"], structured["summary"], [])
        if len(cases) > before:
            clean.append(result)

    kinds = list(PLANTED)
    for index, result in enumerate(clean):
        # Try the kinds in turn from this case's own starting point, so a kind
        # that does not apply to one summary is not simply dropped.
        for offset in range(len(kinds)):
            kind = kinds[(index + offset) % len(kinds)]
            planted = _plant(kind, result["payload"], result["structured"]["summary"])
            if planted:
                add("planted", f"{kind} in {result.get('case', '?')}",
                    result["payload"], planted, [PLANTED[kind]])
                break
    return cases


def calibrate(cases: list[dict], out_path: Path, client, progress=print) -> list[dict]:
    return _work(
        cases, Path(out_path), lambda case: case["case"],
        lambda case: {**judge_one(case["payload"], case["summary"], client),
                      "kind": case["kind"], "expect": case["expect"],
                      "summary": case["summary"]},
        progress, made_with=_judged_with(),
    )


def calibration_summary(records: list[dict]) -> dict:
    """How the judge did on cases with known answers.

    `recall` counts a faulty case as caught when the judge flags it at all;
    `strict_recall` only when it names the expected check. A reply that could
    not be used counts as a miss on a faulty case and is reported on its own
    for a clean one -- it is neither a catch nor a false alarm.
    """
    faulty = [r for r in records if r["expect"]]
    clean = [r for r in records if not r["expect"]]

    def flagged(record):
        return bool(record["verdict"] and record["verdict"]["unfaithful"])

    def named(record):
        return bool(record["verdict"]) and any(
            record["verdict"]["checks"][check]["found"] for check in record["expect"]
        )

    judged_clean = [r for r in clean if r["verdict"]]
    by_kind = {}
    for kind in ("known", "planted"):
        subset = [r for r in faulty if r["kind"] == kind]
        if subset:
            by_kind[kind] = sum(flagged(r) for r in subset) / len(subset)
    by_check = {}
    for check in JUDGE_CHECKS:
        subset = [r for r in faulty if check in r["expect"]]
        if subset:
            by_check[check] = (sum(named(r) for r in subset), len(subset))
    recall = sum(flagged(r) for r in faulty) / len(faulty) if faulty else None
    false_alarm = (
        sum(flagged(r) for r in judged_clean) / len(judged_clean) if judged_clean else None
    )
    return {
        "faulty": len(faulty),
        "clean": len(clean),
        "errors": sum(1 for r in records if r["verdict"] is None),
        "recall": recall,
        "strict_recall": sum(named(r) for r in faulty) / len(faulty) if faulty else None,
        "false_alarm": false_alarm,
        "recall_by_kind": by_kind,
        "caught_by_check": by_check,
        "passes": (
            recall is not None and false_alarm is not None
            and recall >= CALIBRATION_MIN_RECALL
            and false_alarm <= CALIBRATION_MAX_FALSE_ALARM
        ),
    }


# --------------------------------------------------------------------------
# Scoring a run
# --------------------------------------------------------------------------

def upper_bound(successes: int, n: int, z: float = 1.96) -> float | None:
    """Wilson upper limit of a proportion: how high the true rate could
    plausibly be, given `successes` in `n`. 0 in 300 gives about 1.3%."""
    if not n:
        return None
    rate = successes / n
    centre = rate + z * z / (2 * n)
    spread = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n))
    return min(1.0, (centre + spread) / (1 + z * z / n))


def replay(case: dict) -> dict:
    """One saved case, re-checked with today's guards and today's checks.

    Nothing is re-generated: the saved text of each attempt goes back through
    validate_narrative(). So this measures the guards and the checks as they
    are now, against answers a real model really gave.
    """
    payload = case["payload"]
    if not case["attempts"]:
        # Served from the cache: no call was made, so there is no reply to
        # re-check. It was accepted when it was first made; the code checks
        # still read it, and it is not counted as rejected.
        structured = case.get("structured")
        return {
            "first_rejected": None, "final_rejected": None, "structured": structured,
            "findings": findings(payload, structured) if structured is not None else [],
        }
    verdicts = [narrate.validate_narrative(attempt["text"], payload)
                for attempt in case["attempts"]]
    first, last = verdicts[0], verdicts[-1]
    return {
        "first_rejected": first[1],
        "final_rejected": last[1],
        "structured": last[0],
        "findings": findings(payload, last[0]) if last[0] is not None else [],
    }


def summarize(cases: list[dict]) -> dict:
    """Counts and rates over saved cases. A case is {"payload", "attempts",
    optional "judge"} -- a full result from a run works as well as a slim
    baseline record."""
    replays = [replay(case) for case in cases]
    n = len(cases)
    accepted = [r for r in replays if r["structured"] is not None]
    by_type = Counter()
    for item in accepted:
        for kind in {finding["type"] for finding in item["findings"]}:
            by_type[kind] += 1

    judged = [case["judge"] for case in cases if case.get("judge")]
    usable = [j for j in judged if j.get("verdict")]
    by_check = Counter()
    for item in usable:
        for check, entry in item["verdict"]["checks"].items():
            by_check[check] += entry["found"]

    return {
        "n": n,
        "accepted": len(accepted),
        "bands": dict(Counter(case["payload"]["risk_level"] for case in cases)),
        "first_attempt_rejected": sum(1 for r in replays if r["first_rejected"]),
        "first_attempt_by_type": dict(Counter(
            r["first_rejected"] for r in replays if r["first_rejected"])),
        "final_rejected": sum(1 for r in replays if r["final_rejected"]),
        "findings": {kind: by_type.get(kind, 0) for kind in GATED_FINDINGS + STYLE_FINDINGS},
        "judged": len(judged),
        "judge_errors": len(judged) - len(usable),
        "judge_unfaithful": sum(1 for j in usable if j["verdict"]["unfaithful"]),
        "judge_by_check": {check: by_check.get(check, 0) for check in JUDGE_CHECKS},
    }


def flagged_cases(cases: list[dict]) -> list[dict]:
    """Every case a gated check or the judge has something to say about."""
    rows = []
    for case in cases:
        item = replay(case)
        if item["structured"] is None:
            continue
        gated = [f for f in item["findings"] if f["type"] in GATED_FINDINGS]
        verdict = (case.get("judge") or {}).get("verdict")
        judge = [f"{check}: {entry['quote']!r}"
                 for check, entry in (verdict or {}).get("checks", {}).items()
                 if entry["found"]]
        if gated or judge:
            rows.append({
                "case": case.get("case", "?"),
                "summary": item["structured"]["summary"],
                "code": [f"{f['type']}: {f['detail']}" for f in gated],
                "judge": judge,
            })
    return rows


def _pct(count: int, n: int) -> str:
    return "   n/a" if not n else f"{count / n * 100:5.1f}%"


def render_report(cases: list[dict], meta: dict | None = None) -> list[str]:
    """The human-readable result. Returned, not printed, so it is testable."""
    s = summarize(cases)
    n, accepted = s["n"], s["accepted"]
    lines = ["=" * W, "FAITHFULNESS REPORT", "=" * W]
    if meta:
        lines += [
            f"  prompt        : {meta['prompt_version']} ({meta['prompt_sha256'][:12]})",
            f"  model         : {meta['model']}, temperature {meta['temperature']}, "
            f"seed {meta['seed']}",
            f"  measured      : {meta['created']}",
        ]
        judge = meta.get("judge")
        if judge:
            lines.append(
                f"  double check  : {judge['judge_model']} (reasoning "
                f"{judge['judge_reasoning_effort']}), {judge['judge_prompt_version']} "
                f"({judge['judge_prompt_sha256'][:12]})"
            )
    lines += [
        f"  cases         : {n}   "
        + "  ".join(f"{band} {s['bands'].get(band, 0)}" for band in narrate.RISK_LEVELS),
        "",
        "  REJECTED BY THE GUARDS (today's guards, on the saved replies)",
        f"    first attempt   {s['first_attempt_rejected']:4d} of {n}  "
        f"{_pct(s['first_attempt_rejected'], n)}   limit {MAX_FIRST_ATTEMPT_REJECTION:.0%}"
        + (f"   {s['first_attempt_by_type']}" if s["first_attempt_by_type"] else ""),
        f"    after the retry {s['final_rejected']:4d} of {n}  "
        f"{_pct(s['final_rejected'], n)}   limit {MAX_FINAL_REJECTION:.0%}",
        "",
        f"  CODE CHECKS, over the {accepted} accepted summaries"
        f"   (limit {MAX_FINDING_RATE:.0%} each)",
        f"    {'finding':<26}{'count':>6}{'rate':>8}{'could be as high as':>22}",
    ]
    for kind in GATED_FINDINGS:
        count = s["findings"][kind]
        bound = upper_bound(count, accepted)
        lines.append(
            f"    {kind:<26}{count:>6}{_pct(count, accepted):>8}"
            + (f"{bound * 100:>21.1f}%" if bound is not None else f"{'n/a':>22}")
        )
    lines += ["", "  WORDING (reported, never gated)"]
    for kind in STYLE_FINDINGS:
        count = s["findings"][kind]
        lines.append(f"    {kind:<26}{count:>6}{_pct(count, accepted):>8}")

    usable = s["judged"] - s["judge_errors"]
    lines += ["", f"  THE JUDGE'S DOUBLE CHECK, over {s['judged']} summaries"
                  f"   (a second opinion; not gated)"]
    if s["judged"]:
        lines += [
            f"    replies that could not be used {s['judge_errors']:4d}  "
            f"{_pct(s['judge_errors'], s['judged'])}",
            f"    called unfaithful              {s['judge_unfaithful']:4d}  "
            f"{_pct(s['judge_unfaithful'], usable)}",
        ]
        lines += [f"      {check:<24}{s['judge_by_check'][check]:>6}" for check in JUDGE_CHECKS]
    else:
        lines.append("    not judged")

    flagged = flagged_cases(cases)
    lines += ["", f"  FLAGGED CASES ({len(flagged)})"]
    for row in flagged:
        lines += [f"  - {row['case']}"]
        lines += [f"      {text}" for text in narrate._wrap(row["summary"], W - 8)]
        lines += [f"      code : {text}" for text in row["code"]]
        lines += [f"      judge: {text}" for text in row["judge"]]
    lines.append("")
    return lines


# --------------------------------------------------------------------------
# The baseline and the gate
# --------------------------------------------------------------------------

def slim(result: dict, judged: dict | None) -> dict:
    """What CI needs of one result, and nothing else.

    The payload (what the model could be shown) and each attempt's text and
    verdict are enough to re-run every guard and every check. The customer's
    row, the 25 contributions and the latency are left out: a full result is
    about 8 KB and this is under 2.
    """
    record = {
        "case": result["case"],
        "payload": result["payload"],
        "attempts": [
            {key: attempt[key] for key in ("attempt", "accepted", "rejection_type", "text")}
            for attempt in result["attempts"]
        ],
    }
    if judged is not None:
        record["judge"] = {"verdict": judged["verdict"], "error": judged["error"]}
    return record


def current_meta() -> dict:
    """What a baseline has to have been measured with to describe today's code.

    The narrating side only. The judge's settings are not here on purpose: the
    gate does not depend on the judge, so changing or deleting the judge must
    not be able to fail it.
    """
    return {
        "prompt_version": narrate.PROMPT_VERSION,
        "prompt_sha256": file_sha256(narrate.PROMPT_PATH),
        "model": narrate.DEFAULT_MODEL,
        "temperature": narrate.DEFAULT_TEMPERATURE,
        "seed": narrate.DEFAULT_SEED,
    }


def judge_meta() -> dict:
    """Which judge read a run. Recorded in the baseline; never compared."""
    return {
        "judge_model": JUDGE_MODEL,
        "judge_reasoning_effort": JUDGE_REASONING_EFFORT,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "judge_prompt_sha256": file_sha256(JUDGE_PROMPT_PATH),
    }


def build_baseline(results: list[dict], judged: list[dict] | None = None,
                   created: str | None = None, sample_sha256: str | None = None) -> dict:
    """The committed record of one run.

    Refuses a run made under a different prompt or model from the ones in the
    repository now: the meta block is taken from today's code, so writing a
    baseline from an older run would stamp it with a prompt it never saw.

    `judged` is the judge's reading of the run, if there was one. It is stored
    beside the cases as a record and plays no part in the gate.
    """
    judged = judged or []
    for result in results:
        if result.get("cache_hit") or not result["attempts"]:
            raise ValueError(
                f"{result.get('case', '?')} was served from the cache. A baseline "
                f"records what the model answered in one run; a cached answer was "
                f"not produced by it. Use `faithfulness.py run`, which never caches."
            )
        used = (result["prompt_version"], result["model"], result["temperature"], result["seed"])
        now = (narrate.PROMPT_VERSION, narrate.DEFAULT_MODEL,
               narrate.DEFAULT_TEMPERATURE, narrate.DEFAULT_SEED)
        if used != now:
            raise ValueError(
                f"{result.get('case', '?')} was run with {used}, but the code now "
                f"uses {now}. A baseline can only be written from a run of the "
                f"current prompt and model."
            )
    by_case = {record["case"]: record for record in judged}
    return {
        "meta": {**current_meta(), "created": created or date.today().isoformat(),
                 "n": len(results), "sample_sha256": sample_sha256,
                 "judge": judge_meta() if judged else None},
        "cases": [slim(result, by_case.get(result["case"])) for result in results],
    }


def dump_baseline(baseline: dict) -> str:
    """The baseline as text: the meta block spread out, one case per line.

    A case on one line keeps the file a quarter smaller than indenting it
    would, and means a later run changes whole lines -- so a diff shows which
    customers' answers moved rather than a wall of brackets.
    """
    cases = ",\n".join("  " + json.dumps(case) for case in baseline["cases"])
    return ('{\n "meta": ' + json.dumps(baseline["meta"], indent=1).replace("\n", "\n ")
            + ',\n "cases": [\n' + cases + "\n ]\n}\n")


def check_baseline(path: Path = BASELINE_PATH) -> list[str]:
    """Every reason the baseline does not vouch for the code as it is now.

    An empty list is a pass. A missing file is a failure, not a skip: a gate
    that passes when its evidence is deleted is not a gate.
    """
    path = Path(path)
    if not path.exists():
        return [f"{path} does not exist: the current prompt has no measurement."]
    try:
        baseline = json.loads(path.read_text())
        meta, cases = baseline["meta"], baseline["cases"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        return [f"{path} is not a baseline ({type(error).__name__}: {error})."]

    problems = []
    for key, value in current_meta().items():
        if meta.get(key) != value:
            problems.append(
                f"{key}: the baseline measured {meta.get(key)!r}, the code now uses "
                f"{value!r}. Run the harness again for the current one."
            )
    if len(cases) < MIN_CASES:
        problems.append(f"{len(cases)} cases, fewer than the {MIN_CASES} required.")
    if not cases:
        return problems

    s = summarize(cases)
    n, accepted = s["n"], s["accepted"]

    def over(count, total, limit, what):
        if total and count / total > limit:
            problems.append(
                f"{what}: {count} of {total} ({count / total:.1%}), limit {limit:.0%}."
            )

    over(s["first_attempt_rejected"], n, MAX_FIRST_ATTEMPT_REJECTION,
         "rejected on the first attempt by today's guards")
    over(s["final_rejected"], n, MAX_FINAL_REJECTION,
         "no summary after the retry, by today's guards")
    for kind in GATED_FINDINGS:
        over(s["findings"][kind], accepted, MAX_FINDING_RATE, kind)

    # The judge's verdicts are in the baseline and are deliberately not looked
    # at here: it was a one-off second opinion on this run, not a component.
    return problems


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def estimate(calls: int, tokens_in: int, tokens_out: int, model: str) -> str:
    price = PRICE_PER_M.get(model)
    if price is None:
        return f"{calls} calls (no price on record for {model})"
    cost = calls * (tokens_in * price["in"] + tokens_out * price["out"]) / 1_000_000
    return f"about {calls} calls, about ${cost:.3f}"


def _client(judge: bool = False):
    try:
        return JudgeClient() if judge else narrate.OpenAIClient()
    except RuntimeError as error:
        print(f"{error}", file=sys.stderr)
        return None


def _load(path: str) -> list[dict]:
    return json.loads(Path(path).read_text())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure how faithful the explanation layer's summaries are."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sample", help="build the sample of distinct inputs (free)")
    p.add_argument("--n", type=int, default=MIN_CASES)
    p.add_argument("--seed", type=int, default=SAMPLE_SEED)
    p.add_argument("--data", help="path to the raw Telco CSV")
    p.add_argument("--out", default=str(SAMPLE_PATH))

    p = sub.add_parser("score", help="run the code checks over a saved run (free)")
    p.add_argument("run", help="a file written by `run` or by narrate.py --save")
    p.add_argument("--judged", help="the judge's verdicts for that run")

    p = sub.add_parser("calibrate", help="score the judge on known answers (COSTS MONEY)")
    outputs = REPO_ROOT / "outputs"
    p.add_argument("--known", default=str(outputs / "stage2_v3.json"))
    p.add_argument("--clean", default=str(outputs / "stage2_v5.json"))
    p.add_argument("--out", default=str(JUDGE_DIR / f"judge_calibration_{JUDGE_PROMPT_VERSION}.json"))
    p.add_argument("--dry-run", action="store_true", help="build the cases and stop")

    p = sub.add_parser("run", help="narrate the sample, no cache (COSTS MONEY)")
    p.add_argument("--csv", default=str(SAMPLE_PATH))
    p.add_argument("--out", default=RUN_PATH)
    p.add_argument("--limit", type=int, help="only the first N rows")

    p = sub.add_parser("judge", help="judge a saved run (COSTS MONEY)")
    p.add_argument("--run", default=RUN_PATH)
    p.add_argument("--out", default=JUDGED_PATH)

    p = sub.add_parser("baseline", help="write the committed baseline and report (free)")
    p.add_argument("--run", default=RUN_PATH)
    p.add_argument("--judged", default=JUDGED_PATH)
    p.add_argument("--sample", default=str(SAMPLE_PATH))
    p.add_argument("--out", default=str(BASELINE_PATH))
    p.add_argument("--report", default=str(REPORT_PATH))

    p = sub.add_parser("check", help="the gate: does the baseline vouch for today's code?")
    p.add_argument("--baseline", default=str(BASELINE_PATH))

    args = parser.parse_args(argv)

    if args.command == "sample":
        inputs = distinct_inputs(data=args.data)
        sample = choose_sample(inputs, args.n, args.seed)
        write_sample(sample, Path(args.out))
        for label, items in (("distinct inputs", inputs), ("sampled", sample)):
            bands = Counter(item["risk_level"] for item in items)
            print(f"{label:<16}: {len(items):4d}   "
                  + "  ".join(f"{band} {bands.get(band, 0)}" for band in narrate.RISK_LEVELS))
        print(f"Wrote {args.out} (sha256 {file_sha256(Path(args.out))[:12]}).")
        print(f"Narrating it: {estimate(len(sample), 830, 90, narrate.DEFAULT_MODEL)}.")
        return 0

    if args.command == "score":
        cases = _load(args.run)
        if args.judged:
            by_case = {record["case"]: record for record in _load(args.judged)}
            cases = [{**case, "judge": by_case.get(case.get("case"))} for case in cases]
        print("\n".join(render_report(cases)))
        return 0

    if args.command == "calibrate":
        cases = calibration_cases(_load(args.known), _load(args.clean))
        kinds = Counter(case["kind"] for case in cases)
        print(f"{len(cases)} cases: {dict(kinds)}. "
              f"{estimate(len(cases), 1060, 330, JUDGE_MODEL)}.")
        if args.dry_run:
            return 0
        client = _client(judge=True)
        if client is None:
            return 2
        records = calibrate(cases, Path(args.out), client)
        print(json.dumps(calibration_summary(records), indent=2))
        return 0

    if args.command == "run":
        frame = pd.read_csv(args.csv)
        rows = len(frame) if args.limit is None else min(args.limit, len(frame))
        print(f"{rows} customers, no cache: "
              f"{estimate(rows, 830, 90, narrate.DEFAULT_MODEL)}, plus retries.")
        client = _client()
        if client is None:
            return 2
        results = run(Path(args.csv), Path(args.out), client, limit=args.limit)
        if results:
            print("\n".join(narrate.render_rates(narrate.rejection_rates(results))))
        return 0

    if args.command == "judge":
        results = _load(args.run)
        accepted = sum(1 for result in results if result["structured"] is not None)
        print(f"{accepted} accepted summaries: {estimate(accepted, 1060, 330, JUDGE_MODEL)}.")
        client = _client(judge=True)
        if client is None:
            return 2
        judge_run(results, Path(args.out), client)
        return 0

    if args.command == "baseline":
        sample = Path(args.sample)
        baseline = build_baseline(
            _load(args.run),
            _load(args.judged) if Path(args.judged).exists() else None,
            sample_sha256=file_sha256(sample) if sample.exists() else None,
        )
        Path(args.out).write_text(dump_baseline(baseline))
        report = render_report(baseline["cases"], baseline["meta"])
        Path(args.report).write_text("\n".join(report))
        print(f"Wrote {args.out} ({Path(args.out).stat().st_size // 1024} KB) and {args.report}.")
        problems = check_baseline(Path(args.out))
        for problem in problems:
            print(f"GATE: {problem}", file=sys.stderr)
        return 1 if problems else 0

    if args.command == "check":
        problems = check_baseline(Path(args.baseline))
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        if not problems:
            print("OK: the baseline vouches for the current prompt, model, guards and checks.")
        return 1 if problems else 0

    return 2  # pragma: no cover -- argparse refuses an unknown command


if __name__ == "__main__":
    sys.exit(main())
