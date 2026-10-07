"""A small SQLite cache for narration, so the same explanation is paid for once.

Run:  uv run python narration_cache.py --import-all
      uv run python narration_cache.py --stats
      uv run python narration_cache.py --prune

WHAT THIS IS, AND WHAT IT IS NOT
A **cost guard, not a store of record.** The JSON files in outputs/ remain the
measurements of a prompt version -- immutable, read by LLMcalls.ipynb, quoted
in CHANGELOG.md. This file can be deleted at any moment and nothing is lost
except money.

That is why it holds accepted answers only. A rejected attempt is evidence
about a prompt and belongs in a saved run, not in a lookup table.

THE KEY IS THE INPUT, NOT THE CUSTOMER
A row is keyed by a sha256 of exactly what the model was sent --
narrate.sent_payload(), the same function that builds the user turn -- plus the
model, the temperature and the seed. Two different customers with the same
three factors and the same risk band therefore share one entry, which is
correct: the explanation is a function of the input. In the 50-customer run of
2026-09-28 only 41 of the 50 inputs were distinct.

ONE TABLE PER PROMPT VERSION
cache_explanation_v5, cache_explanation_v3, ... created on demand. A lookup can
only see its own version's rows, so a v3 answer can never be served to a v5
request even when the inputs match. Retiring a version is one DROP TABLE, and
imported history sits in its own table where no lookup will touch it. The
version is validated before it reaches the SQL, because a table name cannot be
a bound parameter.

ENTRIES EXPIRE, ON A TWO-LEVEL CLOCK
A week while a prompt is the one in use -- long, because a stale entry here
cannot be wrong in the dangerous way: a changed prompt means a different table
and a changed model means a different key.

Two things shorten that:

  SETTLING. An entry born in the first 24 hours of a prompt lives 24 hours.
  That first day is when a prompt is being judged, and hour-one wording should
  not follow you around for a week.

  RETIREMENT. When you move to another prompt or model, the one you left keeps
  its entries for 24 more hours and then loses them. They were already
  unreachable -- a lookup only reads its own version's table -- so this is
  housekeeping plus a rollback window: go back within a day and the old cache
  is still warm, which is exactly how the v4-to-v3 rollback went. Go back later
  and you start cold.

The four numbers live together at the top of this file and feed one pure
function, expires_at(). A flat TTL (--ttl, or NARRATION_CACHE_TTL) switches the
whole policy off and gives every entry the same life -- the escape hatch if any
of this proves to be a bad idea.

Eviction is lazy: an expired row reads as a miss and is deleted on the way
past; --prune sweeps a file.

TWO RULES, BOTH BORROWED FROM llm_tracing.py

  1. A CACHE FAILURE MUST NEVER CHANGE OR BREAK A NARRATION. Every call into
     sqlite3 is wrapped: an unwritable directory, a corrupt file, a locked
     database -- each warns once and degrades, and narration carries on paying
     for calls.

  2. OFF UNLESS ASKED, IN THE LIBRARY. narrate() uses a cache only when handed
     one, so the test suite and any run that measures a prompt cannot be served
     from it by accident. The CLI is the opposite way round: it caches by
     default and takes --no-cache, because that is where a human clicks the
     same customer twice. A measurement run passes --no-cache.

Nothing new is stored: a row holds the same payload the model already received
-- no raw customer row, no protected fields, no probability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Mirrors config.MODEL_PATH: an environment variable with a repo-relative
# default. /data is the only writable path inside the image, which is where
# this would point once an endpoint uses it.
DEFAULT_DB_PATH = os.environ.get("NARRATION_DB", "data/narration.sqlite3")

# --------------------------------------------------------------------------
# HOW LONG AN ENTRY LIVES -- the four numbers, in one place
#
# Change these and nothing else moves: expires_at() below is a pure function of
# them, and every read, prune and report goes through it. To switch the whole
# policy off, give a flat TTL -- `--ttl 3600`, or NARRATION_CACHE_TTL=3600 --
# and every entry simply lives that long, settling and retirement ignored. That
# is the escape hatch if any of this turns out to be a bad idea.
# --------------------------------------------------------------------------

# A week, for the prompt and model in use. Long, because a stale entry here
# cannot be wrong in the dangerous way: a changed prompt means a different
# table, and a changed model means a different key.
CURRENT_TTL_SECONDS = 7 * 24 * 3600

# The first day of a new prompt is when it is being judged: re-run, read,
# re-worded. An entry born in that window lives only a day, so early wording
# cannot follow you around for a week.
SETTLING_WINDOW_SECONDS = 24 * 3600
SETTLING_TTL_SECONDS = 24 * 3600

# How long the previous prompt-and-model's entries stay usable after the switch.
# They are already unreachable from a normal lookup, so this is housekeeping
# plus a rollback window -- go back within a day and the old cache is still
# warm, which is exactly how the v4-to-v3 rollback went.
RETIRED_GRACE_SECONDS = 24 * 3600

# Only used when a flat TTL is asked for explicitly. Kept because the CLI and
# NARRATION_CACHE_TTL both accept one.
DEFAULT_TTL_SECONDS = CURRENT_TTL_SECONDS

# Table names cannot be bound as SQL parameters, so a version that reaches
# CREATE TABLE has to be proved safe rather than escaped.
_SAFE_VERSION = re.compile(r"^[a-z0-9_]+$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
  key         TEXT PRIMARY KEY,
  created_at  REAL NOT NULL,
  model       TEXT NOT NULL,
  temperature REAL NOT NULL,
  seed        INTEGER,
  payload     TEXT NOT NULL,
  structured  TEXT NOT NULL,
  narrative   TEXT NOT NULL,
  attempts    INTEGER NOT NULL,
  source      TEXT NOT NULL
)
"""

# One row per prompt-and-model pair the cache has ever served. Deliberately not
# named cache_*: that prefix marks the per-version answer tables, and this is
# bookkeeping. It must survive a prune, or emptying the cache would restart
# every settling window by accident.
_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta_pairs (
  prompt_version TEXT NOT NULL,
  model          TEXT NOT NULL,
  first_seen     REAL NOT NULL,
  last_seen      REAL NOT NULL,
  retired_at     REAL,
  PRIMARY KEY (prompt_version, model)
)
"""


def expires_at(
    created_at: float,
    first_seen: float,
    retired_at: float | None,
    flat_ttl: float | None = None,
) -> float:
    """When one entry stops being usable. A pure function, so the policy can be
    read, tested and changed without touching any SQL.

      flat_ttl given   -> created_at + flat_ttl, and nothing else applies.
      born settling    -> a day from its own creation.
      otherwise        -> a week from its own creation.
      pair retired     -> whichever comes first, that or a day from the switch.
    """
    if flat_ttl is not None:
        return created_at + flat_ttl
    settling = created_at < first_seen + SETTLING_WINDOW_SECONDS
    expiry = created_at + (SETTLING_TTL_SECONDS if settling else CURRENT_TTL_SECONDS)
    if retired_at is not None:
        expiry = min(expiry, retired_at + RETIRED_GRACE_SECONDS)
    return expiry


def _warn(action: str, error: Exception) -> None:
    warnings.warn(
        f"The narration cache failed while trying to {action} "
        f"({type(error).__name__}: {error}). The narration is unaffected.",
        RuntimeWarning,
        stacklevel=3,
    )


# --------------------------------------------------------------------------
# The key
# --------------------------------------------------------------------------

def cache_key(
    payload: dict,
    prompt_version: str,
    model: str,
    temperature: float,
    seed: int | None,
) -> str:
    """A sha256 over everything that decides what comes back.

    The sent payload, not the whole payload: the decision and the omitted
    protected fields are never sent, so they cannot change the answer.
    `narrate.sent_payload()` is imported inside the function because narrate.py
    imports this module -- at module scope the pair would not import at all.
    """
    import narrate

    material = {
        "sent": narrate.sent_payload(payload, prompt_version),
        "model": model,
        "temperature": temperature,
        "seed": seed,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def table_for(prompt_version: str) -> str:
    """The table a prompt version's rows live in. Refuses anything that is not
    plainly a name, because this string is interpolated into SQL."""
    if not _SAFE_VERSION.match(prompt_version or ""):
        raise ValueError(
            f"prompt version {prompt_version!r} is not a safe table name; "
            f"expected lowercase letters, digits and underscores."
        )
    return f"cache_{prompt_version}"


# --------------------------------------------------------------------------
# The do-nothing cache
# --------------------------------------------------------------------------

class NoopCache:
    """The fallback. `enabled` is False so a caller can say whether it cached.

    Carries `path`, `ttl` and `reason` like the real thing, so a caller can
    print any of them without first asking which kind of cache it holds."""

    enabled = False
    path = None
    ttl = 0.0

    def __init__(self, reason: str = "cache not configured"):
        self.reason = reason

    def get(self, key: str, prompt_version: str, model: str = ""):
        return None

    def put(self, key: str, prompt_version: str, result: dict, source: str = "live",
            touch: bool = True):
        pass

    def touch(self, prompt_version: str, model: str) -> None:
        pass

    def prune(self) -> int:
        return 0

    def tables(self) -> list[str]:
        return []

    def stats(self) -> dict:
        return {}

    def close(self) -> None:
        pass


# --------------------------------------------------------------------------
# The real cache
# --------------------------------------------------------------------------

class Cache:
    """A SQLite file of accepted narrations, one table per prompt version.

    Every method swallows sqlite3 errors and degrades: a read that fails is a
    miss, a write that fails is a write that did not happen. Neither changes
    what the caller tells the user, which is rule 1 at the top of this file.
    """

    enabled = True
    reason = None  # the no-op cache's counterpart; nothing went wrong here

    def __init__(self, connection: sqlite3.Connection, path: str,
                 ttl: float | None = None):
        self._db = connection
        self.path = path
        # None means the two-level policy above. A number means a flat TTL for
        # everything -- the escape hatch.
        self.ttl = ttl
        self._prepared: set[str] = set()

    # -- schema ----------------------------------------------------------

    def _ensure(self, prompt_version: str) -> str | None:
        """Create this version's table once per process. None if that failed."""
        table = table_for(prompt_version)
        if table in self._prepared:
            return table
        try:
            self._db.execute(_SCHEMA.format(table=table))
            self._db.execute(_META_SCHEMA)
            self._db.commit()
        except sqlite3.Error as error:
            _warn(f"create {table}", error)
            return None
        self._prepared.add(table)
        return table

    # -- which prompt and model are current ------------------------------

    def touch(self, prompt_version: str, model: str) -> None:
        """Record that this pair is the one in use, and retire the others.

        Called whenever a request is made for a pair -- a hit or a miss, since
        either way this is the pair being used now. Coming back to an older
        prompt un-retires it and retires whatever replaced it, so a rollback
        behaves like a switch rather than a special case.
        """
        if self._ensure(prompt_version) is None:
            return
        now = time.time()
        try:
            self._db.execute(
                "INSERT INTO meta_pairs (prompt_version, model, first_seen, "
                "last_seen, retired_at) VALUES (?, ?, ?, ?, NULL) "
                "ON CONFLICT(prompt_version, model) DO UPDATE SET "
                "last_seen = excluded.last_seen, retired_at = NULL",
                (prompt_version, model, now, now),
            )
            self._db.execute(
                "UPDATE meta_pairs SET retired_at = ? "
                "WHERE retired_at IS NULL AND NOT (prompt_version = ? AND model = ?)",
                (now, prompt_version, model),
            )
            self._db.commit()
        except sqlite3.Error as error:
            _warn("record the prompt in use", error)

    def _pair(self, prompt_version: str, model: str) -> tuple[float, float | None] | None:
        """(first_seen, retired_at) for a pair, or None if it is unknown."""
        try:
            row = self._db.execute(
                "SELECT first_seen, retired_at FROM meta_pairs "
                "WHERE prompt_version = ? AND model = ?",
                (prompt_version, model),
            ).fetchone()
        except sqlite3.Error as error:
            _warn("read the prompt record", error)
            return None
        return (row[0], row[1]) if row else None

    def _expiry_from(self, created_at: float, pair: tuple | None) -> float:
        """A pair with no record -- rows imported from a saved run, say -- is
        treated as first seen when the row was written, so it gets the settling
        allowance rather than a week. The cautious way round: a day, not seven,
        for an answer whose history is unknown."""
        first_seen, retired_at = pair if pair else (created_at, None)
        return expires_at(created_at, first_seen, retired_at, flat_ttl=self.ttl)

    def expiry_of(self, created_at: float, prompt_version: str, model: str) -> float:
        """When one stored answer runs out, under the current policy."""
        return self._expiry_from(created_at, self._pair(prompt_version, model))

    # -- lookup ----------------------------------------------------------

    def get(self, key: str, prompt_version: str, model: str = "") -> dict | None:
        """The stored answer, or None when it is missing or out of time.

        Asking marks this prompt-and-model pair as the one in use, which is
        what retires the previous one. An expired row is deleted as it is read,
        which is the whole eviction policy: rows nobody asks for cost a few
        kilobytes, and --prune sweeps them when that matters.
        """
        table = self._ensure(prompt_version)
        if table is None:
            return None
        # The pair's state is read BEFORE this request changes it. Asking for a
        # retired prompt is a rollback, and it makes that prompt current again
        # -- but the rows already stored under it must still be judged by the
        # retirement they were under when the request arrived. Otherwise coming
        # back a week later would quietly revive week-old answers.
        pair = self._pair(prompt_version, model)
        if model:
            self.touch(prompt_version, model)
        try:
            row = self._db.execute(
                f"SELECT created_at, structured, narrative, attempts, source "
                f"FROM {table} WHERE key = ?",
                (key,),
            ).fetchone()
        except sqlite3.Error as error:
            _warn("read", error)
            return None
        if row is None:
            return None
        created_at, structured, narrative, attempts, source = row
        if time.time() > self._expiry_from(created_at, pair):
            try:
                self._db.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
                self._db.commit()
            except sqlite3.Error as error:  # pragma: no cover -- the read worked
                _warn("evict", error)
            return None
        return {
            "structured": json.loads(structured),
            "narrative": narrative,
            "attempts": attempts,
            "created_at": created_at,
            "source": source,
        }

    # -- store -----------------------------------------------------------

    def put(
        self,
        key: str,
        prompt_version: str,
        result: dict,
        source: str = "live",
        touch: bool = True,
    ) -> None:
        """Store an accepted narration.

        A rejected one is never cached: it is evidence about a prompt, and the
        next caller deserves a real attempt rather than someone else's failure.

        `touch=False` stores without claiming that this pair is the one in use.
        Importing a saved run needs that: loading an old v2 file must not
        declare v2 current and retire the prompt you are actually running.
        """
        if not result.get("narrative_available"):
            return
        table = self._ensure(prompt_version)
        if table is None:
            return
        if touch:
            self.touch(prompt_version, result.get("model", ""))
        attempts = len(result.get("attempts") or []) or result.get("cached_attempts") or 1
        try:
            self._db.execute(
                f"INSERT OR REPLACE INTO {table} "
                f"(key, created_at, model, temperature, seed, payload, "
                f" structured, narrative, attempts, source) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    time.time(),
                    result.get("model", ""),
                    float(result.get("temperature") or 0.0),
                    result.get("seed"),
                    json.dumps(result["payload"]),
                    json.dumps(result["structured"]),
                    result["narrative"],
                    attempts,
                    source,
                ),
            )
            self._db.commit()
        except (sqlite3.Error, KeyError, TypeError) as error:
            _warn("write", error)

    # -- housekeeping ----------------------------------------------------

    def tables(self) -> list[str]:
        try:
            rows = self._db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name LIKE 'cache_%' ORDER BY name"
            ).fetchall()
        except sqlite3.Error as error:  # pragma: no cover
            _warn("list tables", error)
            return []
        return [name for (name,) in rows]

    def stats(self) -> dict:
        """{table: (rows, age of the newest row in seconds)}, for --stats."""
        out = {}
        now = time.time()
        for table in self.tables():
            try:
                count, newest = self._db.execute(
                    f"SELECT count(*), max(created_at) FROM {table}"
                ).fetchone()
            except sqlite3.Error as error:  # pragma: no cover
                _warn(f"count {table}", error)
                continue
            out[table] = (count, None if newest is None else now - newest)
        return out

    def pairs(self) -> list[tuple]:
        """(prompt_version, model, state, age of the state in seconds) per pair.

        `state` is "in use", "settling" (in use, and inside its first day) or
        "retired HH:MM ago". What --stats prints, and the quickest way to see
        why something expired sooner than expected.
        """
        now = time.time()
        try:
            rows = self._db.execute(
                "SELECT prompt_version, model, first_seen, retired_at "
                "FROM meta_pairs ORDER BY retired_at IS NOT NULL, first_seen"
            ).fetchall()
        except sqlite3.Error:
            return []  # the table only exists once something has been stored
        out = []
        for version, model, first_seen, retired_at in rows:
            if retired_at is not None:
                state, age = "retired", now - retired_at
            elif now < first_seen + SETTLING_WINDOW_SECONDS:
                state, age = "settling", now - first_seen
            else:
                state, age = "in use", now - first_seen
            out.append((version, model, state, age))
        return out

    def prune(self) -> int:
        """Delete every row that has run out of time. Returns how many went.

        Row by row rather than one DELETE per table, because the allowance
        depends on the row's own age, on when its prompt was first seen and on
        whether that prompt has since been retired. At a few hundred rows the
        cost of doing it honestly is nothing.
        """
        now = time.time()
        removed = 0
        for table in self.tables():
            version = table[len("cache_"):]
            try:
                rows = self._db.execute(
                    f"SELECT key, created_at, model FROM {table}"
                ).fetchall()
                doomed = [
                    (key,) for key, created_at, model in rows
                    if now > self.expiry_of(created_at, version, model)
                ]
                if doomed:
                    self._db.executemany(
                        f"DELETE FROM {table} WHERE key = ?", doomed)
                    removed += len(doomed)
            except sqlite3.Error as error:  # pragma: no cover
                _warn(f"prune {table}", error)
        try:
            self._db.commit()
        except sqlite3.Error as error:  # pragma: no cover
            _warn("commit prune", error)
        return removed

    def close(self) -> None:
        try:
            self._db.close()
        except sqlite3.Error as error:  # pragma: no cover
            _warn("close", error)


# --------------------------------------------------------------------------
# Opening one
# --------------------------------------------------------------------------

def from_env(path: str | None = None, ttl: float | None = None):
    """A Cache, or a NoopCache that says why. Never raises.

    Same contract as llm_tracing.from_env(): the caller does not have to care
    whether it worked. A missing parent directory is created; anything else
    that goes wrong -- no permission, a corrupt file, a directory where the
    file should be -- warns once and returns the no-op.
    """
    path = path or DEFAULT_DB_PATH
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = REPO_ROOT / resolved
    if ttl is None:
        # Unset means the two-level policy. A number here or on the command
        # line overrides it with a flat TTL for every row -- the escape hatch.
        raw = os.environ.get("NARRATION_CACHE_TTL")
        if raw:
            try:
                ttl = float(raw)
            except ValueError:
                warnings.warn(
                    f"NARRATION_CACHE_TTL={raw!r} is not a number; using the "
                    f"normal expiry policy instead.",
                    RuntimeWarning,
                    stacklevel=2,
                )
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(resolved))
        # Fails here on a file that is not a database, rather than at the first
        # read halfway through a batch.
        connection.execute("PRAGMA schema_version").fetchone()
    except (sqlite3.Error, OSError) as error:
        _warn(f"open {resolved}", error)
        return NoopCache(f"could not open {resolved}: {error}")
    return Cache(connection, str(resolved), ttl)


# --------------------------------------------------------------------------
# Importing saved runs
# --------------------------------------------------------------------------

def import_run(path: str, cache) -> tuple[int, int]:
    """Load one saved run's accepted answers into its own version's table.

    Returns (imported, skipped). The file's own `prompt_version` picks the
    table, never today's -- the rule llm_tracing.backfill() follows, for the
    same reason: a saved run is a measurement of the prompt it ran on. Rows are
    stamped with the file name, so `source` says where a row came from and
    nothing imported can be mistaken for a live answer.
    """
    results = json.loads(Path(path).read_text())
    name = Path(path).name
    imported = skipped = 0
    for result in results:
        if not result.get("narrative_available"):
            skipped += 1
            continue
        version = result["prompt_version"]
        key = cache_key(
            result["payload"], version, result["model"],
            result.get("temperature", 0.0), result.get("seed"),
        )
        cache.put(key, version, result, source=name, touch=False)
        imported += 1
    return imported, skipped


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect and fill the narration cache. Makes no API calls."
    )
    parser.add_argument("--db", help=f"database file (default {DEFAULT_DB_PATH})")
    parser.add_argument("--ttl", type=float,
                        help="override the expiry policy with a flat TTL, in seconds")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--stats", action="store_true", help="rows per prompt version")
    action.add_argument("--prune", action="store_true", help="delete expired rows")
    action.add_argument("--import", dest="import_paths", nargs="+", metavar="FILE",
                        help="load saved run(s) from outputs/")
    action.add_argument("--import-all", action="store_true",
                        help="load every outputs/*.json")
    args = parser.parse_args(argv)

    cache = from_env(args.db, args.ttl)
    if not cache.enabled:
        print(f"Cache unavailable: {cache.reason}", file=sys.stderr)
        return 2

    if args.stats:
        rows = cache.stats()
        if not rows:
            print(f"{cache.path}: empty.")
        for table, (count, age) in rows.items():
            age_text = "-" if age is None else f"newest {age / 3600:.1f}h old"
            print(f"  {table:<34} {count:>5} rows   {age_text}")
        pairs = cache.pairs()
        if pairs:
            print("\n  prompt and model:")
            for version, model, state, age in pairs:
                print(f"    {version} / {model:<14} {state:<9} {age / 3600:>6.1f}h")
        if cache.ttl is None:
            print(f"\n  expiry: {CURRENT_TTL_SECONDS / 86400:.0f}d in use, "
                  f"{SETTLING_TTL_SECONDS / 3600:.0f}h while settling, "
                  f"{RETIRED_GRACE_SECONDS / 3600:.0f}h after retirement")
        else:
            print(f"\n  expiry: a flat {cache.ttl:.0f}s (policy overridden)")
        print(f"  file {cache.path}")
    elif args.prune:
        print(f"Removed {cache.prune()} expired row(s) from {cache.path}.")
    else:
        paths = args.import_paths
        if args.import_all:
            paths = sorted(str(p) for p in (REPO_ROOT / "outputs").glob("*.json"))
        if not paths:
            print("Nothing to import.", file=sys.stderr)
            return 1
        for path in paths:
            try:
                imported, skipped = import_run(path, cache)
            except (OSError, ValueError, KeyError) as error:
                print(f"FAILED {path}: {type(error).__name__}: {error}", file=sys.stderr)
                continue
            print(f"  {Path(path).name:<24} {imported:>4} imported, {skipped} skipped")
    cache.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
