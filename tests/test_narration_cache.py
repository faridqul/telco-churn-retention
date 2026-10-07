"""Tests for narration_cache.py. Real SQLite, in tmp_path. No API key, no cost.

The cache is a cost guard, and the failures that matter are the quiet ones:

  1. SERVING THE WRONG ANSWER. A key that ignores something the answer depends
     on -- the model, the temperature, the seed, a factor's value -- would hand
     one customer another customer's explanation. Every one of those is tested
     as a miss.

  2. CROSSING PROMPT VERSIONS. v3 and v5 answer the same input differently, so
     a v3 row must never be visible to a v5 lookup. Separate tables make that
     structural; the test proves it.

  3. BREAKING A NARRATION. A cache is optional comfort. A corrupt file, a
     directory where the database should be, a read-only disk -- each must
     degrade to a no-op cache with a warning, never an exception.

  4. SERVING AN EXPIRED ANSWER. The TTL is what keeps the cache from deciding
     what a customer is told, so expiry is tested at both ends.

As in tests/test_narrate.py: never phrase an assertion in terms of the constant
it is testing -- the default TTL and the table prefix are compared against
literals.
"""

import json
import sqlite3
import time

import pytest

import narration_cache
import narrate

V5 = "explanation_v5"
V3 = "explanation_v3"


# ==========================================================================
# Fixtures: the smallest payload and result the cache needs
# ==========================================================================

def payload(value="Month-to-month", risk="high"):
    return {
        "risk_level": risk,
        "decision": "target for retention",
        "target_for_retention": True,
        "factors": [
            {"name": "contract type", "field": "contract",
             "direction": "raises risk", "value": value},
        ],
        "protected_drivers_omitted": [],
    }


def result(summary="Their month-to-month contract raises their risk.",
           accepted=True, attempts=1, **overrides):
    base = {
        "narrative": summary if accepted else None,
        "narrative_available": accepted,
        "structured": (
            {"risk_level": "high",
             "reasons": [{"field": "contract", "direction": "raises risk"}],
             "summary": summary}
            if accepted else None
        ),
        "payload": payload(),
        "prompt_version": V5,
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "seed": 42,
        "attempts": [{"attempt": i + 1} for i in range(attempts)],
    }
    return {**base, **overrides}


@pytest.fixture
def cache(tmp_path):
    cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"))
    yield cache
    cache.close()


def key_for(pay=None, version=V5, model="gpt-4o-mini", temperature=0.0, seed=42):
    return narration_cache.cache_key(pay or payload(), version, model, temperature, seed)


# ==========================================================================
# 1. The key
# ==========================================================================

def test_the_same_request_gives_the_same_key():
    assert key_for() == key_for()


@pytest.mark.parametrize("changed", [
    {"pay": payload(value="Two year")},
    {"model": "gpt-4o"},
    {"temperature": 0.7},
    {"seed": 7},
    {"seed": None},
])
def test_anything_that_changes_the_answer_changes_the_key(changed):
    assert key_for(**changed) != key_for()


def test_the_key_is_over_what_was_sent_not_the_whole_payload():
    """The decision and the omitted protected fields are never sent, so they
    cannot change the answer and must not change the key -- otherwise two
    identical requests would miss each other."""
    other = dict(payload(), decision="do not target", target_for_retention=False,
                 protected_drivers_omitted=["gender"])
    assert key_for(pay=other) == key_for()


def test_a_key_is_a_sha256_hex_digest():
    assert len(key_for()) == 64 and set(key_for()) <= set("0123456789abcdef")


# ==========================================================================
# 2. Tables, one per prompt version
# ==========================================================================

def test_a_version_gets_its_own_table():
    assert narration_cache.table_for(V5) == "cache_explanation_v5"


@pytest.mark.parametrize("bad", [
    "explanation v5", "explanation-v5", "Explanation_v5", "v5; DROP TABLE x",
    "", None,
])
def test_a_version_that_is_not_a_plain_name_is_refused(bad):
    """The table name is interpolated into SQL because a name cannot be bound
    as a parameter, so this check is the whole defence."""
    with pytest.raises(ValueError, match="safe table name"):
        narration_cache.table_for(bad)


def test_a_table_is_created_on_demand(cache):
    assert cache.tables() == []
    cache.put(key_for(), V5, result())
    assert cache.tables() == ["cache_explanation_v5"]


def test_one_version_cannot_see_anothers_rows(cache):
    """The same input under two prompts is two different answers."""
    cache.put(key_for(), V5, result(summary="v5 wording"))
    assert cache.get(key_for(), V3) is None
    assert cache.get(key_for(), V5)["narrative"] == "v5 wording"


# ==========================================================================
# 3. Storing and reading back
# ==========================================================================

def test_a_stored_answer_comes_back(cache):
    cache.put(key_for(), V5, result())
    hit = cache.get(key_for(), V5)
    assert hit["narrative"] == "Their month-to-month contract raises their risk."
    assert hit["structured"]["reasons"] == [{"field": "contract", "direction": "raises risk"}]
    assert hit["attempts"] == 1
    assert hit["source"] == "live"


def test_an_unknown_key_is_a_miss(cache):
    assert cache.get(key_for(), V5) is None


def test_a_rejected_narration_is_never_stored(cache):
    """A rejection is evidence about a prompt; the next caller deserves a real
    attempt rather than someone else's failure."""
    cache.put(key_for(), V5, result(accepted=False))
    assert cache.get(key_for(), V5) is None


def test_storing_twice_replaces_rather_than_duplicates(cache):
    cache.put(key_for(), V5, result(summary="first"))
    cache.put(key_for(), V5, result(summary="second"))
    assert cache.get(key_for(), V5)["narrative"] == "second"
    assert cache.stats()["cache_explanation_v5"][0] == 1


def test_the_retry_count_of_the_original_call_is_kept(cache):
    cache.put(key_for(), V5, result(attempts=2))
    assert cache.get(key_for(), V5)["attempts"] == 2


# ==========================================================================
# 4. Expiry
# ==========================================================================

def test_an_expired_row_is_a_miss_and_is_deleted(tmp_path):
    cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"), ttl=0.05)
    cache.put(key_for(), V5, result())
    assert cache.get(key_for(), V5) is not None
    time.sleep(0.06)
    assert cache.get(key_for(), V5) is None
    assert cache.stats()["cache_explanation_v5"][0] == 0, "the row should be gone"
    cache.close()


def test_a_fresh_row_survives(cache):
    cache.put(key_for(), V5, result())
    assert cache.get(key_for(), V5) is not None


def test_prune_clears_expired_rows_everywhere(tmp_path):
    """With a flat TTL, so this is about the sweep rather than the policy."""
    cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"), ttl=0.05)
    cache.put(key_for(), V5, result())
    cache.put(key_for(version=V3), V3, result(prompt_version=V3))
    time.sleep(0.06)
    assert cache.prune() == 2
    assert all(count == 0 for count, _ in cache.stats().values())
    cache.close()


def test_the_ttl_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATION_CACHE_TTL", "123")
    cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"))
    assert cache.ttl == 123
    cache.close()


def test_by_default_there_is_no_flat_ttl(tmp_path, monkeypatch):
    """None means the two-level policy below, not "no expiry"."""
    monkeypatch.delenv("NARRATION_CACHE_TTL", raising=False)
    cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"))
    assert cache.ttl is None
    cache.close()


def test_an_unreadable_ttl_warns_and_keeps_the_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATION_CACHE_TTL", "soon")
    with pytest.warns(RuntimeWarning, match="not a number"):
        cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"))
    assert cache.ttl is None
    cache.close()


# ==========================================================================
# 4b. The expiry policy itself
#
# expires_at() is a pure function of four constants, so the policy can be
# checked here without a database, a clock or a sleep. The numbers are written
# out as literals on purpose: a test that says CURRENT_TTL_SECONDS would pass
# whatever that constant became.
# ==========================================================================

HOUR = 3600
DAY = 24 * HOUR


def test_an_entry_in_use_lives_a_week():
    first_seen = 0
    born = first_seen + 5 * DAY  # well past the settling window
    assert narration_cache.expires_at(born, first_seen, None) == born + 7 * DAY


def test_an_entry_born_in_the_first_day_lives_only_a_day():
    """The first day of a prompt is when it is being judged, so early wording
    must not follow you around for a week."""
    first_seen = 0
    born = first_seen + 3 * HOUR
    assert narration_cache.expires_at(born, first_seen, None) == born + DAY


def test_the_settling_rule_ends_exactly_at_one_day():
    first_seen = 0
    just_inside = narration_cache.expires_at(first_seen + DAY - 1, first_seen, None)
    just_outside = narration_cache.expires_at(first_seen + DAY, first_seen, None)
    assert just_inside - (first_seen + DAY - 1) == DAY
    assert just_outside - (first_seen + DAY) == 7 * DAY


def test_a_retired_pair_gets_a_day_from_the_switch():
    """Not a day from the entry: switching is what starts the clock."""
    first_seen, born, retired = 0, 5 * DAY, 6 * DAY
    assert narration_cache.expires_at(born, first_seen, retired) == retired + DAY


def test_retirement_can_only_shorten_a_life_never_extend_it():
    first_seen, born, retired = 0, 5 * DAY, 5 * DAY + HOUR
    week = born + 7 * DAY
    assert narration_cache.expires_at(born, first_seen, retired) < week


def test_a_flat_ttl_overrides_every_rule():
    """The escape hatch: --ttl, or NARRATION_CACHE_TTL, and the policy is off."""
    first_seen, born, retired = 0, 2 * HOUR, 3 * HOUR
    assert narration_cache.expires_at(born, first_seen, retired, flat_ttl=99) == born + 99


# ==========================================================================
# 4c. The policy, through the database
#
# Timestamps are written straight into SQLite rather than slept through: these
# are a day and a week apart.
# ==========================================================================

def age_row(cache, version, key, seconds_old):
    cache._db.execute(
        f"UPDATE {narration_cache.table_for(version)} SET created_at = ? WHERE key = ?",
        (time.time() - seconds_old, key))
    cache._db.commit()


def age_pair(cache, version, model, first_seen_seconds_ago, retired_seconds_ago=None):
    cache._db.execute(
        "UPDATE meta_pairs SET first_seen = ?, retired_at = ? "
        "WHERE prompt_version = ? AND model = ?",
        (time.time() - first_seen_seconds_ago,
         None if retired_seconds_ago is None else time.time() - retired_seconds_ago,
         version, model))
    cache._db.commit()


def test_a_settled_entry_survives_three_days(cache):
    cache.put(key_for(), V5, result())
    age_pair(cache, V5, "gpt-4o-mini", first_seen_seconds_ago=10 * DAY)
    age_row(cache, V5, key_for(), 3 * DAY)
    assert cache.get(key_for(), V5, "gpt-4o-mini") is not None


def test_a_settling_entry_is_gone_after_two_days(cache):
    cache.put(key_for(), V5, result())
    age_pair(cache, V5, "gpt-4o-mini", first_seen_seconds_ago=2 * DAY)
    age_row(cache, V5, key_for(), 2 * DAY)  # born in the first hours, now old
    assert cache.get(key_for(), V5, "gpt-4o-mini") is None


def test_changing_prompt_retires_the_old_one(cache):
    cache.put(key_for(), V5, result())
    cache.get(key_for(version=V3), V3, "gpt-4o-mini")  # now working on v3
    states = {(v, s) for v, _, s, _ in cache.pairs()}
    assert (V5, "retired") in states
    assert (V3, "settling") in states or (V3, "in use") in states


def test_changing_model_retires_the_old_pair(cache):
    cache.put(key_for(), V5, result())
    cache.get(key_for(model="gpt-4o"), V5, "gpt-4o")
    retired = {(v, m) for v, m, s, _ in cache.pairs() if s == "retired"}
    assert retired == {(V5, "gpt-4o-mini")}


def test_a_retired_entry_dies_a_day_after_the_switch(cache):
    """Even though it is only two days old and would otherwise have a week."""
    cache.put(key_for(), V5, result())
    age_pair(cache, V5, "gpt-4o-mini",
             first_seen_seconds_ago=10 * DAY, retired_seconds_ago=2 * DAY)
    age_row(cache, V5, key_for(), 2 * DAY)
    assert cache.get(key_for(), V5, "gpt-4o-mini") is None


def test_a_rollback_within_the_day_still_finds_the_old_cache_warm(cache):
    """The v4-to-v3 case: go back quickly and nothing was lost."""
    cache.put(key_for(), V5, result())
    age_pair(cache, V5, "gpt-4o-mini",
             first_seen_seconds_ago=10 * DAY, retired_seconds_ago=2 * HOUR)
    age_row(cache, V5, key_for(), 3 * DAY)
    assert cache.get(key_for(), V5, "gpt-4o-mini") is not None


def test_coming_back_to_a_prompt_un_retires_it(cache):
    cache.put(key_for(), V5, result())
    cache.get(key_for(version=V3), V3, "gpt-4o-mini")      # switch away
    cache.get(key_for(), V5, "gpt-4o-mini")                # and back
    retired = {v for v, _, s, _ in cache.pairs() if s == "retired"}
    assert retired == {V3}


def test_importing_a_run_does_not_retire_the_prompt_in_use(cache, tmp_path):
    """Loading an old v2 file must not declare v2 current and retire v5."""
    cache.get(key_for(), V5, "gpt-4o-mini")  # v5 is what we are running
    path = saved_run(tmp_path, version=V3, count=1)
    narration_cache.import_run(str(path), cache)
    assert {v for v, _, s, _ in cache.pairs() if s == "retired"} == set()


def test_a_flat_ttl_ignores_retirement(tmp_path):
    cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"), ttl=10 * DAY)
    cache.put(key_for(), V5, result())
    age_pair(cache, V5, "gpt-4o-mini",
             first_seen_seconds_ago=10 * DAY, retired_seconds_ago=5 * DAY)
    age_row(cache, V5, key_for(), 3 * DAY)
    assert cache.get(key_for(), V5, "gpt-4o-mini") is not None
    cache.close()


# ==========================================================================
# 5. Degrading instead of breaking
# ==========================================================================

def test_a_directory_where_the_file_should_be_degrades(tmp_path):
    (tmp_path / "c.sqlite3").mkdir()
    with pytest.warns(RuntimeWarning, match="narration cache failed"):
        cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"))
    assert cache.enabled is False
    assert "could not open" in cache.reason


def test_a_file_that_is_not_a_database_degrades(tmp_path):
    bad = tmp_path / "c.sqlite3"
    bad.write_text("this is not a database")
    with pytest.warns(RuntimeWarning, match="narration cache failed"):
        cache = narration_cache.from_env(str(bad))
    assert cache.enabled is False


def test_an_unwritable_directory_degrades(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    try:
        with pytest.warns(RuntimeWarning, match="narration cache failed"):
            cache = narration_cache.from_env(str(locked / "c.sqlite3"))
        assert cache.enabled is False
    finally:
        locked.chmod(0o700)


def test_the_noop_cache_answers_everything_quietly():
    cache = narration_cache.NoopCache("because")
    assert cache.get("k", V5) is None
    assert cache.put("k", V5, result()) is None
    assert cache.prune() == 0
    assert cache.stats() == {} and cache.tables() == []
    assert cache.close() is None
    assert cache.reason == "because"


class BrokenConnection:
    """A connection whose every statement fails, the way a locked or
    disappearing database does. sqlite3.Connection.execute cannot be patched
    (it is read-only on the C object), so the connection itself is swapped."""

    def execute(self, *_, **__):
        raise sqlite3.OperationalError("database is locked")

    def commit(self):
        raise sqlite3.OperationalError("database is locked")

    def close(self):
        pass


def test_a_read_that_fails_is_a_miss_not_an_exception(cache):
    """Rule 1: a broken cache must never reach the caller as an error."""
    cache.put(key_for(), V5, result())
    cache._db = BrokenConnection()
    with pytest.warns(RuntimeWarning, match="narration cache failed"):
        assert cache.get(key_for(), V5) is None


def test_a_write_that_fails_is_only_a_warning(cache):
    cache._ensure(V5)  # the table first, so the failure is the INSERT
    cache._db = BrokenConnection()
    with pytest.warns(RuntimeWarning, match="narration cache failed"):
        cache.put(key_for(), V5, result())


def test_a_table_that_cannot_be_created_is_a_miss(tmp_path):
    cache = narration_cache.from_env(str(tmp_path / "c.sqlite3"))
    cache._db = BrokenConnection()
    with pytest.warns(RuntimeWarning, match="narration cache failed"):
        assert cache.get(key_for(), V5) is None


# ==========================================================================
# 6. Importing saved runs
# ==========================================================================

def saved_run(tmp_path, name="stage_test.json", version=V5, count=2, rejected=0):
    results = [
        dict(result(summary=f"answer {i}", prompt_version=version),
             payload=payload(value=f"value {i}"))
        for i in range(count)
    ]
    results += [result(accepted=False, prompt_version=version) for _ in range(rejected)]
    path = tmp_path / name
    path.write_text(json.dumps(results))
    return path


def test_importing_a_run_fills_the_right_table(cache, tmp_path):
    path = saved_run(tmp_path)
    imported, skipped = narration_cache.import_run(str(path), cache)
    assert (imported, skipped) == (2, 0)
    assert cache.stats()["cache_explanation_v5"][0] == 2


def test_an_imported_row_says_where_it_came_from(cache, tmp_path):
    path = saved_run(tmp_path, name="stage2_v5.json", count=1)
    narration_cache.import_run(str(path), cache)
    key = narration_cache.cache_key(
        payload(value="value 0"), V5, "gpt-4o-mini", 0.0, 42)
    assert cache.get(key, V5)["source"] == "stage2_v5.json"


def test_rejected_answers_in_a_saved_run_are_skipped(cache, tmp_path):
    path = saved_run(tmp_path, count=1, rejected=2)
    assert narration_cache.import_run(str(path), cache) == (1, 2)


def test_importing_the_same_file_twice_does_not_duplicate(cache, tmp_path):
    path = saved_run(tmp_path)
    narration_cache.import_run(str(path), cache)
    narration_cache.import_run(str(path), cache)
    assert cache.stats()["cache_explanation_v5"][0] == 2


def test_a_run_lands_in_its_own_versions_table_not_todays(cache, tmp_path):
    """A saved run measures the prompt it ran on. Importing a v3 run must not
    put v3 answers where a v5 request can find them."""
    path = saved_run(tmp_path, version=V3, count=1)
    narration_cache.import_run(str(path), cache)
    assert cache.tables() == ["cache_explanation_v3"]


def test_a_run_from_an_unknown_prompt_version_is_refused(cache, tmp_path):
    path = saved_run(tmp_path, version="explanation_v1", count=1)
    with pytest.raises(ValueError, match="explanation_v1"):
        narration_cache.import_run(str(path), cache)


def test_a_real_saved_run_imports(cache):
    """Against an actual file from outputs/, when one is present -- the shapes
    these tests build by hand are only as good as their resemblance to it."""
    path = narrate.REPO_ROOT / "outputs" / "stage2_v5.json"
    if not path.exists():
        pytest.skip("outputs/stage2_v5.json is a local run, not in the repo")
    imported, _ = narration_cache.import_run(str(path), cache)
    rows = cache.stats()["cache_explanation_v5"][0]
    assert imported > 0
    # Fewer rows than answers, because the key is the input: customers who
    # share three factors and a risk band share one entry. The 50-customer run
    # of 2026-09-28 had 41 distinct inputs, which is the whole argument for
    # caching at all.
    assert 0 < rows <= imported


# ==========================================================================
# 7. The CLI
# ==========================================================================

def test_cli_stats_reports_an_empty_cache(tmp_path, capsys):
    assert narration_cache.main(["--db", str(tmp_path / "c.sqlite3"), "--stats"]) == 0
    assert "empty" in capsys.readouterr().out


def test_cli_imports_and_then_counts(tmp_path, capsys):
    path = saved_run(tmp_path)
    db = str(tmp_path / "c.sqlite3")
    assert narration_cache.main(["--db", db, "--import", str(path)]) == 0
    assert "2 imported" in capsys.readouterr().out
    assert narration_cache.main(["--db", db, "--stats"]) == 0
    out = capsys.readouterr().out
    assert "cache_explanation_v5" in out and "2 rows" in out


def test_cli_prune_reports_what_it_removed(tmp_path, capsys):
    db = str(tmp_path / "c.sqlite3")
    narration_cache.main(["--db", db, "--import", str(saved_run(tmp_path))])
    capsys.readouterr()
    assert narration_cache.main(["--db", db, "--ttl", "0", "--prune"]) == 0
    assert "Removed 2" in capsys.readouterr().out


def test_cli_says_so_when_the_cache_cannot_be_opened(tmp_path, capsys):
    (tmp_path / "c.sqlite3").mkdir()
    with pytest.warns(RuntimeWarning):
        assert narration_cache.main(["--db", str(tmp_path / "c.sqlite3"), "--stats"]) == 2
    assert "Cache unavailable" in capsys.readouterr().err
