# Changelog

Append-only record of file changes made by an assistant in this repo.
Newest entries go at the **bottom**. Past entries are never edited or
deleted — a mistake in an old entry is corrected by a new entry saying so.

Format and rules are defined in `CLAUDE.md` under "CHANGELOG.md —
mandatory, every session".

---

## 2026-08-21 — Create CHANGELOG.md

**Files touched:**
- `CHANGELOG.md` (created)

**What changed:** Created this file. It didn't exist before. It opens with
a header explaining what the file is for, that entries are appended at the
bottom, that nothing already written gets edited or removed, and where the
full rules live (`CLAUDE.md`). Below that header sit the entries themselves,
starting with this one.

**Why:** You asked for a durable, human-readable record of every file an
assistant touches, including changes made on our own initiative rather than
at your request. Git history already records *what bytes changed*, but it
doesn't record *why*, doesn't distinguish work you asked for from work an
assistant decided to do, and doesn't say whether anything was actually run
and verified. That gap is what this file fills.

**Requested or incidental:** Requested. You asked for this file explicitly.

**Verification status:** File created and its existence confirmed with
`ls`. Nothing was executed beyond that — there's no code here to run. Not
committed; the file is currently untracked in git.

---

## 2026-08-21 — Add mandatory CHANGELOG rule to CLAUDE.md

**Files touched:**
- `CLAUDE.md` (appended a new section, "CHANGELOG.md — mandatory, every session")

**What changed:** Added a new section at the end of `CLAUDE.md`, after the
existing "Conventions" section. Nothing already in the file was edited or
removed — this is purely an addition at the bottom, taking the file from
roughly 90 to 116 lines.

The section instructs any future assistant session to maintain
`CHANGELOG.md` without needing to be asked again. It states that an entry
must be appended before ending any turn in which a file was changed, and it
is explicit that this covers changes made on an assistant's own initiative
— an unrequested test, an adjacent fix, a documentation touch-up — not only
changes you directly asked for. It requires that past entries are never
edited or deleted, so corrections happen by adding a new entry rather than
rewriting an old one.

It then lists the six things every entry must contain: the date and a short
title; every file touched named explicitly, with "updated a few files"
called out as unacceptable; a plain-prose description written for someone
who has neither the diff nor the conversation; the reason for the change;
an explicit statement of whether the work was requested or incidental, with
incidental work flagged separately rather than blended into the same
paragraph as requested work; and a verification status covering what was
actually executed versus only reasoned about, whether tests passed, and
whether the change is committed.

It also specifies that a single turn touching several unrelated things
produces several entries rather than one combined entry.

Finally, it states that editing `CLAUDE.md` itself always requires its own
CHANGELOG entry, with no exceptions, and records the reason in the file:
silent edits to `CLAUDE.md` caused confusion previously, which makes it the
single most important file to log.

**Why:** You asked for the rule to live in `CLAUDE.md` specifically so it
survives across sessions. `CLAUDE.md` is loaded into context automatically
at the start of every session, so a rule written there is read by future
sessions without you having to restate it. You also asked specifically for
the self-referential clause about `CLAUDE.md` edits, because silent changes
to that file are what caused the confusion in the first place.

**Requested or incidental:** Requested. Both the rule and the clause about
`CLAUDE.md` edits logging themselves were asked for directly.

**Verification status:** The section was appended and the resulting line
count (116) confirmed with `wc -l`. The text was read back to you in the
same turn for review. No tests were run — this change is documentation only
and touches no code, so the test suite is unaffected by it. Not committed;
`CLAUDE.md` currently shows as modified in `git status`.

---

## 2026-08-21 — Create AUDIT.md (defect audit and roadmap)

**Files touched:**
- `AUDIT.md` (created, ~34 KB)

**What changed:** Created a working document in the repo root recording a
full defect audit of the project plus a prioritised roadmap. It is organised
as a checklist you can tick through rather than an essay.

The findings section states plainly that there are **no critical defects** —
nothing returns a wrong prediction on valid input, loses data, or crashes a
normal request — rather than promoting a lesser finding to fill that slot.
Below that sit ten moderate findings and fourteen cosmetic ones, worst first.
Each moderate finding names the file and line, says whether it was confirmed
by running code or is a suspicion with the reasoning exposed, describes the
actual consequence, gives a runnable command that proves it, and gives the
fix. The single most serious finding is that the batch scoring script accepts
any CSV without validation, so an unseen category value silently changes a
prediction from 0.570 to 0.102 with no error — measured, not hypothesised.

The second half is the roadmap: four items described as blocking
production-grade, four worth doing but not blocking, two direct answers to
questions asked during the session (whether the library-version check is
worth keeping now that scikit-learn emits its own warning, and whether the
threshold-selection methodology is sound), a table of nine commonly
recommended ML additions that would be a *waste* of effort for this project
at its current stage with the reason for each, a twelve-item ordered
worklist, and a verification log separating what was executed from what was
inferred.

The document also opens with two corrections to the briefing given at the
time: CI was described as not yet set up when the workflow file was in fact
already committed, and the shipped model artifact looked stale because its
recorded git commit was three commits behind, when in fact only the
metadata-writing notebook cell had changed since.

**Why:** You asked for a bug hunt and an improvement roadmap, delivered as a
downloadable markdown file you could work through and tick off, with the
teaching voice dropped and findings separated by severity.

**Requested or incidental:** Requested. The file, its structure, and the
severity split were all asked for directly.

**Verification status:** Every confirmed finding was proved by executing
code against the working tree, not by reading alone — roughly twelve
throwaway scripts in total. Among them: the full test suite was run and
passed (48 tests at the time), the README results table was recomputed from
the committed model artifact against a reconstructed train/test split and
every figure matched exactly, the unknown-category prediction swing was
measured, the uncaught `TypeError` in threshold loading was triggered
directly, and the integration-test fixture was shown to depend on a lucky
random seed (21 of the first 40 seeds break its own precondition). Not
committed. **Note for future readers:** `AUDIT.md` was subsequently added to
`.gitignore` by later work, so it is a local-only file and will not appear
in the repository.

---

## 2026-08-21 — Create CLAUDE.md (project orientation)

**Files touched:**
- `CLAUDE.md` (created, ~4 KB / ~80 lines)

**What changed:** Created `CLAUDE.md`, which did not exist before. Its
purpose is to orient any future assistant session cheaply, because
`CLAUDE.md` is loaded automatically at the start of every session in this
directory.

The most important thing in it is a warning not to read the notebook
directly. `telco_customer_churn.ipynb` is around 800 KB on disk because it
stores rendered plot images inline, which is roughly 200,000 tokens — but
its actual code is only about 29 KB, or 7,000 tokens. A session that
sensibly decides to "read the notebook" burns an enormous amount of context
before learning anything. The file therefore leads with a short Python
snippet that extracts just the cell sources.

Beyond that it contains: a table of every file and what it is for, flagging
the ones that are load-bearing in non-obvious ways; a map of the notebook's
41 cells so a session can jump straight to the relevant one; four invariants
that must not be broken; a short list of facts that were expensive to derive
and should not be re-derived (dataset shape, the local Kaggle cache path,
the artifact's reproducing test metrics, the closed-form profit threshold);
and three traps, including that Optuna is declared as a dependency but never
used, so nobody should assume it is the tuner.

**Why:** You asked whether analysis from one chat carries into the next, and
said you did not want to pay to re-scan the project every time. The honest
answer was that it does not — memory held only a couple of reference notes
and nothing about the code. Measuring the re-orientation cost showed roughly
23,000 tokens of re-reading per session, or 200,000 if the notebook were
read the wrong way. `CLAUDE.md` is the mechanism that fixes this, since it
loads automatically, and no such file existed.

**Requested or incidental:** **Incidental.** You asked a question about how
memory works across chats; you did not ask for a file to be created. Writing
`CLAUDE.md` was an assistant decision made to solve the underlying problem
you described. It was reported to you in the same turn, and noted as
untracked so it could be deleted if unwanted.

**Verification status:** The file was written and its size confirmed
(4,000 bytes). The token-cost figures quoted in it and in the accompanying
explanation were measured directly from the files on disk, not estimated
from memory. No tests were run, as this is a documentation file that touches
no code. Not committed at the time of writing. **Note for future readers:**
`CLAUDE.md` has since been edited further by later work — the mandatory
CHANGELOG section was appended, and several facts were corrected as the
project moved on (the test count went from 48 to 52, a `tests/test_artifact.py`
row was added, and `AUDIT.md` was re-described as gitignored). The version
described in this entry is the original, not the current state of the file.

---

## 2026-08-21 — Write persistent memory notes (outside the repository)

**Files touched:**
- `~/.claude/projects/-home-yaponsk-div-academy-aie-tasks-ml-projects-4/memory/churn-doc-artifacts.md` (created)
- `~/.claude/projects/-home-yaponsk-div-academy-aie-tasks-ml-projects-4/memory/churn-doc-verified-claims.md` (created)
- `~/.claude/projects/-home-yaponsk-div-academy-aie-tasks-ml-projects-4/memory/MEMORY.md` (created)

**Note on location:** none of these files are in this repository. They live
in the assistant's per-project memory directory under the user's home
folder. They are logged here anyway because they were created during work on
this project and affect how future sessions behave, so a reader wondering
where certain assumptions come from should know they exist.

**What changed:** Two long-lived notes were written, plus a two-line index
file that points at them.

The first note records that two web documents were published during this
session — a long walkthrough of the project called the Field Manual, and a
rendered version of the defect audit — and gives their URLs together with
the exact procedure for updating them later. That procedure matters because
publishing without supplying the original URL creates a *second* document
rather than updating the existing one, which would quietly leave two
divergent copies.

The second note is a table of every measured number asserted in those
documents alongside the command that re-checks it: the test count, the
pinned prediction for the dummy customer, the recomputed results table, the
model's tuned hyperparameters, the dataset's row and duplicate counts, and
so on. The point is that a future session updating those documents can
re-run the checks and patch the differences, instead of re-deriving
everything from scratch.

**Why:** You asked whether the documents could easily be updated once the
project changed. Testing showed the published copies can be fetched back
byte-for-byte identically, so they are recoverable — but only if a future
session knows the URLs and the update procedure, which nothing recorded.
Separately, the documents are densely tied to things that move: line
numbers, notebook cell numbers, and measured values. Without a list of what
was measured and how, "update the docs" would mean redoing the whole
analysis.

**Requested or incidental:** **Incidental.** You asked a question about
whether future updates would be easy. Creating these notes was an assistant
decision, taken because the honest answer to your question was "not without
recording something first."

**Verification status:** The recovery path was tested rather than assumed —
one published document was fetched back, the hosting wrapper stripped, and
the result compared against the original source, which matched exactly
(72,714 characters versus 72,715, identical after trimming whitespace). The
files were written and their contents read back to confirm the metadata
headers parsed correctly. Not committed, and not committable — they sit
outside the repository by design.

---

## 2026-08-22 — Fix stale README documentation (CI bullet and `tests/` paths)

**Files touched:**
- `README.md`
- `tests/test_config.py`
- `tests/test_telco_model.py`
- `tests/test_integration.py`
- `AUDIT.md`

**What changed:** The README had drifted out of step with the repository in
two places, and both were fixed.

First, its "Known limitations / what I'd add for production" section listed
a bullet saying there was no CI pipeline and that nothing ran the tests
automatically on push. That had stopped being true: `.github/workflows/tests.yml`
is committed and runs the suite on every push and pull request, and the
README's own header carries a CI badge. The document was contradicting
itself roughly three hundred lines apart. The bullet was deleted outright
rather than reworded, because there is no remaining limitation there to
describe.

Second, the "Repo structure" block still showed the layout from before the
test files were moved into a `tests/` directory — it listed all five of them
sitting at the repository root. They were re-indented under a `tests/` line
so the block matches what someone actually sees after cloning, and a line
for `.github/workflows/tests.yml` was added to the same block, since CI was
missing from the structure listing entirely.

The same stale layout appeared inside the test files themselves. Three of
them carried a docstring line telling the reader to run them with, for
example, `pytest test_config.py -v` — a path that no longer exists and would
fail if pasted into a terminal. Those three were corrected to `pytest
tests/test_config.py -v` and equivalents. `tests/test_feature_engineering.py`
and `tests/test_api.py` already had the correct path and were left alone.

In `AUDIT.md`, the two findings covering this (C1 and C2) and the matching
roadmap item were ticked from `[ ]` to `[x]`. Only those three checkbox
characters changed; the finding text was left exactly as written, so it now
reads as a record of what the problem was rather than a live defect.

**Why:** `CLAUDE.md` flagged the stale CI bullet as a known inaccuracy, and
`AUDIT.md` had already filed both problems as C1 and C2 with "delete the
bullet and fix the `tests/` paths" as the number one item on its roadmap.
You then asked for exactly that item by name. The underlying problem is that
a README which contradicts its own badge, and tells you to run commands that
error, undermines trust in the rest of the document.

**Requested or incidental:** Requested. You asked for the CI bullet deleted
and the `tests/` paths fixed. Two smaller pieces within it were taken on
initiative and are called out here rather than folded in silently: adding
the `.github/workflows/tests.yml` line to the structure block was not asked
for, and neither was ticking the `AUDIT.md` checkboxes.

**Verification status:** Executed, not merely reasoned about. After the
edits, `uv run pytest -q` was run and all 48 tests passed in 1.77 s. The
README was re-grepped for "no ci pipeline" and returned zero matches, and
all five test docstrings were re-grepped to confirm every one now names a
`tests/` path. The shipped model's canary prediction for `DUMMY_CUSTOMER`
was recomputed as a sanity check and still read 0.5699995, matching the
documented value. **Committed** as `2b5cf45` on the branch
`docs/readme-ci-and-tests-paths`, along with the changes described in the
next two entries. Not pushed. The `AUDIT.md` checkbox change is not and
cannot be committed — see the following entry.

---

## 2026-08-22 — Keep `AUDIT.md` out of the repository

**Files touched:**
- `.gitignore`

**What changed:** `AUDIT.md` was added to `.gitignore`, under the existing
"Local scratch notes (kept on disk, not part of the repo)" heading at the
bottom of the file. That section previously held a single placeholder entry,
the literal word `nothing`, which matched no actual file; it was replaced
with `AUDIT.md`. The file itself was not moved or deleted — it is still
sitting in the repository root at 34 KB and is still read at the start of a
session. It simply no longer appears in `git status` and will never be
committed or pushed.

**Why:** You asked whether `AUDIT.md` and `CLAUDE.md` should be committed.
The relevant fact is that `origin` points at a public repository,
`github.com/faridqul/telco-churn-retention`. `AUDIT.md` is a 34 KB document
enumerating twenty-four defects in your own portfolio project, written
throughout in the second person — "your uncommitted README change", "your
README spotted this" — so it reads as an external review of your work rather
than as your own engineering notes. Publishing that alongside the project is
a real decision, not a formality. You were offered three options — ignore it,
commit it as-is, or rewrite its voice into neutral first-person notes and
then commit — and you chose to keep it local.

`CLAUDE.md` was treated differently and committed, because it is ordinary
project documentation that helps anyone who clones the repository, and
nothing in it is addressed to you personally.

**Requested or incidental:** Requested. You asked the question and picked
the option directly.

**Verification status:** Confirmed by execution. `git check-ignore -v
AUDIT.md` reported the match against `.gitignore:32`, and `AUDIT.md`
subsequently stopped appearing in `git status`. `ls` confirmed the file is
still present on disk at 34 KB and was not deleted. **Committed** as part of
`2b5cf45` on `docs/readme-ci-and-tests-paths`. Not pushed.

---

## 2026-08-22 — Corrections to CLAUDE.md as the project moved on

**Files touched:**
- `CLAUDE.md`

**What changed:** Five separate facts in `CLAUDE.md` had gone out of date or
became wrong as a result of this session's work, and all five were
corrected. Nothing was deleted from the file beyond the specific sentences
being replaced.

In the Conventions section, a bullet reading "README's 'No CI pipeline'
bullet is stale; CI exists in `.github/workflows/`" was replaced. That bullet
described a defect which this session fixed, so leaving it in place would
have sent the next session hunting for a problem that no longer exists. It
now simply states what CI does: `.github/workflows/tests.yml` runs
`uv run pytest -q` on every push and pull request.

In the file-layout table, the `AUDIT.md` row previously told the reader to
read that file before reporting a bug. That instruction now only makes sense
for someone working on this machine, since `AUDIT.md` was added to
`.gitignore` in the same session and will not exist in a fresh clone. The row
was reworded to say the file is local-only and gitignored, and to make the
instruction conditional — read it *if present*.

The `tests/` row said "48 tests, ~1.7 s" and warned that deleting
`tests/__init__.py` breaks all 5 files at collection. Both numbers moved when
a sixth test file was added, so the row now reads 52 tests, ~2.1 s, and 6
files. A new row was added directly beneath it for `tests/test_artifact.py`,
describing it as the only tests that open the real `.pkl`.

Finally, in "Facts worth not re-deriving", the note about the shipped model
scoring `DUMMY_CUSTOMER` at 0.5699995160102844 previously described that
number as a good canary in the abstract. It now records that the number is
stored in `model_metadata.json` as `dummy_customer_score`, that
`tests/test_artifact.py` asserts against it, and that the notebook's save
cell rewrites the pickle and the number together on a retrain — which is the
non-obvious part, because it explains why the pin cannot go stale.

**Why:** `CLAUDE.md` is loaded automatically at the start of every session in
this directory, which makes a wrong statement in it more expensive than a
wrong statement almost anywhere else — it is read first and trusted by
default. Three of these five facts were made wrong by this session's own
work, so leaving them would have meant knowingly shipping a misleading
briefing to the next session.

**Requested or incidental:** **Incidental.** You did not ask for any of these
edits. Every one was made on initiative, as a consequence of other work:
fixing the README invalidated the CI bullet, gitignoring `AUDIT.md`
invalidated its table row, and adding a test file invalidated the test count
and the canary description. This entry exists in its own right because
`CLAUDE.md` states that any edit to itself must be logged separately, with no
exceptions.

**Verification status:** Every replacement was made by an anchored
string-substitution script that asserts the target text exists before
writing, so a silent no-op was not possible; the resulting lines were read
back and inspected. The test count and timing quoted in the new text were
taken from an actual run of `uv run pytest -q` (52 passed, 1.62 s), not
estimated. **Partly committed:** the CI-bullet and `AUDIT.md`-row edits are
in `2b5cf45`; the test-count, `test_artifact.py` row, and canary-fact edits
were made afterwards and are still uncommitted, showing as modified in
`git status`. Not pushed.

---

## 2026-08-22 — Add tests that load the real model artifact and pin its prediction

**Files touched:**
- `tests/test_artifact.py` (created)
- `telco_customer_churn.ipynb` (cell 38, the save cell)
- `model_metadata.json`
- `README.md`
- `AUDIT.md`

**What changed:** A new test file was added containing four tests, and these
are the first tests in the project that ever open `xgboost_churn_pipeline.pkl`.

The gap they close is worth stating plainly. `test_api.py` and
`test_telco_model.py` replace the model with a mock, which is the right
choice for testing their own wiring but means no real model is involved.
`test_integration.py` fits a genuine pipeline, but a fresh one, on forty rows
of synthetic data. So the actual bytes that `api.py` and `telco_model.py`
load and serve predictions from were never executed by the test suite at all
— in a repository that has a version-drift warning at startup, a
`library_versions` field in its metadata, a long docstring about pickle
fragility, and a hundred-line shell script, all of which exist precisely
because that artifact is fragile.

The four tests are: one that unpickles the artifact and checks it exposes
`predict` and `predict_proba`, which catches a corrupted or unloadable file;
the canary itself, which runs `config.DUMMY_CUSTOMER` through
`engineer_features` and the pipeline and asserts the resulting probability
matches the recorded value to within 1e-6; one that checks the probability
still falls on the same side of the operating threshold, using the same `>=`
comparison both consumers use, so a flipped decision is caught even when the
numeric drift is small; and one confirming the committed pickle and the
committed feature schema agree with each other, rather than trusting the
startup validator's check of `engineer_features` alone.

The expected probability is deliberately **not** hard-coded in the test. It
is read from a new `dummy_customer_score` key in `model_metadata.json`, and
the notebook's save cell (cell 38) was edited to compute and write that key
at the same moment it writes the pickle. The consequence is that retraining
updates the artifact and its canary value together, so these tests cannot
fail merely because you deliberately trained a new model — they only fail
when the pickle and the environment around it disagree. That is the case
worth catching: a library version that unpickles cleanly but predicts
differently, which `verify_version_check.sh` states in its own text that it
cannot detect.

Editing cell 38 required adding `from config import DUMMY_CUSTOMER` to it,
which is a new dependency direction — the notebook did not previously import
`config`. It is import-safe, since `config` executes only constant
definitions at import time, but it is a structural change worth knowing about.

The current value, 0.5699995160102844, was computed from the shipped pickle
and written into `model_metadata.json` by hand rather than by retraining, so
that the key exists without regenerating the artifact. The file's lack of a
trailing newline was preserved, matching what the notebook's `json.dump`
produces, so a future retrain does not produce a spurious one-line diff.

In `README.md`, a line for `test_artifact.py` was added to the repo-structure
block. In `AUDIT.md`, roadmap item 2 was ticked.

**Why:** You asked for a test that loads the real `.pkl` and pins a
prediction. It was item 2 on the `AUDIT.md` roadmap, described there as the
highest value-per-line change available in the repository, on the grounds
that it is what makes the rest of the version-drift machinery meaningful
rather than aspirational.

**Requested or incidental:** Requested. The test itself is what you asked
for. Three things within it went beyond the literal request and are flagged
here rather than folded in: writing `dummy_customer_score` into the notebook
and metadata so the pin maintains itself (the audit recommended this, you did
not ask for it, and it involved editing the notebook); the two extra tests
beyond the pin itself, covering the threshold decision and the schema
agreement; and the `README.md` and `AUDIT.md` touch-ups.

**Verification status:** Executed and adversarially checked. The full suite
was run with `uv run pytest -q` and all 52 tests passed in 1.62 s, up from 48.
The canary was then deliberately made to fail, to prove it can: a tampered
copy of the metadata with the score changed to 0.61 was supplied via the
`METADATA_PATH` environment variable, and the test failed with
`assert 0.5699995160102844 == 0.61 ± 1.0e-06` while the other three still
passed. The tests were also run from a different working directory (`/tmp`)
to confirm they do not depend on where pytest is invoked, and all four
passed. The notebook diff was inspected after the edit to confirm the JSON
round-tripped without reformatting the whole file — 16 insertions and 1
deletion, no image blobs disturbed. The notebook's save cell itself was
**not** executed; retraining was not run, so the claim that a retrain
regenerates the key correctly is reasoned from the code, not observed.
**Not committed.** `tests/test_artifact.py` is untracked, and
`telco_customer_churn.ipynb`, `model_metadata.json` and `README.md` show as
modified.

---

## 2026-08-22 — Harden config.py's failure paths and settle the missing-metadata policy

**Files touched:**
- `config.py`
- `tests/test_config.py`
- `CLAUDE.md`
- `AUDIT.md`

**What changed:** Three related defects in `config.py` were fixed, and the
question underneath all three — what should happen when `model_metadata.json`
is missing or malformed — was answered explicitly instead of being left
implicit and inconsistent.

**The policy that was decided.** A metadata *file* that is missing or
unparseable is now **fatal**, raising a `RuntimeError` whose message names
the file and says to run the notebook's save cell to regenerate it. A
malformed *value* inside a file that reads fine now **degrades** —
`load_threshold` falls back to `DEFAULT_THRESHOLD` with a warning. The
reasoning is that the metadata is what ties the code to the pickle sitting
next to it: it records the operating threshold, the feature schema, and the
library versions the model was built with. Without the file there is no way
to know the artifact is the one the code expects, so serving predictions
anyway would mean guessing, and crashing at startup is the honest outcome.
But if the file is present and just one value in it is wrong, the model
itself is almost certainly fine, and taking the service down over a bad
number is worse than using a sane default.

**What was broken before.** `load_threshold` caught
`FileNotFoundError, KeyError, ValueError` but not `TypeError`, so metadata
containing `{"threshold": null}` or `{"threshold": [0.4]}` crashed the API at
startup rather than degrading. `null` matters more than it sounds: it is what
a hand-edit or any templating step emits for a missing value, so it is a
likelier corruption than the uncastable-string case that was already covered.

Worse, the `FileNotFoundError` branch was dead code in production. Both
`api.py` and `telco_model.py` call `validate_feature_schema()` first, then
`validate_environment_versions()`, and only then `load_threshold()`. The two
validators opened the same file, so on a fresh clone with no metadata you got
a bare `FileNotFoundError` traceback from three lines earlier, never the
graceful fallback the code appeared to offer. A test in `tests/test_config.py`
asserted that this scenario "must not raise" and passed — it was green because
it called `load_threshold` in isolation, testing a property the system as a
whole did not have.

And `validate_environment_versions`, whose docstring states in bold that it
warns and *never raises*, raised `AttributeError` whenever `library_versions`
was a list or a string rather than a dict, because it called `.items()` on it
unconditionally. It also raised `FileNotFoundError` on missing metadata.
`validate_feature_schema` raised a bare `KeyError('feature_columns')` on
metadata lacking that key, inconsistent with the readable `RuntimeError` it
raises for every other schema problem.

**How it was fixed.** A new private helper `_load_metadata()` does the
reading and parsing for all three functions and converts a missing file or
invalid JSON into a readable `RuntimeError`. `load_threshold` now uses it and
catches `KeyError, TypeError, ValueError` around the float conversion only.
`validate_feature_schema` uses it and raises an explicit `RuntimeError` when
`feature_columns` is absent. `validate_environment_versions` wraps the helper
in a `try`/`except` that warns and returns, and gained an `isinstance` check
so a non-dict `library_versions` warns instead of crashing — so its "never
raises" docstring is now enforced rather than merely asserted. That function
is a detection control only, and the fatal case is already covered by
`validate_feature_schema`, which both consumers call first.

In `tests/test_config.py`, the test asserting the wrong property was removed
and replaced by two that assert the decided policy: a missing file and a
truncated file each raise a readable `RuntimeError`. The single
uncastable-string test became a parametrized test covering a string, `null`,
a list and an object. Seven further tests were added covering the validators:
three parametrized cases for a non-dict `library_versions`, one each for a
missing file and corrupt JSON reaching `validate_environment_versions`
without raising, and three confirming `validate_feature_schema` reports a
missing file, corrupt JSON and a missing key as readable `RuntimeError`s.

`CLAUDE.md` gained the policy as a fourth invariant, a note on the
`config.py` row, and an updated test count. `AUDIT.md` had findings M2, M3
and M4 ticked, along with roadmap item 3.

**Why:** You asked for this by naming roadmap item 3 — "`TypeError` in
`load_threshold`; decide the missing-metadata policy" — and said to fix it.
The deeper problem was that `config.py`'s stated purpose is to stop the API
and the batch script drifting apart or failing confusingly, and its own
failure paths did the opposite: one was unreachable, one crashed on a
realistic input, and one contradicted its own docstring.

**Requested or incidental:** Requested. Two things within it are worth
flagging as judgement calls rather than instructions you gave: the *choice*
of policy was mine — `AUDIT.md` recommended making missing metadata fatal and
I followed that, but the split between a fatal missing file and a degrading
bad value is a refinement I decided on and documented rather than something
specified. The `CLAUDE.md` and `AUDIT.md` edits were also taken on
initiative. Per this project's rule, the `CLAUDE.md` edit is logged
separately in the entry that follows this one.

**Verification status:** Executed throughout, both before and after. All
three defects were first reproduced using the exact commands recorded in
`AUDIT.md`, confirming `{"threshold": null}` and `{"threshold": [0.4]}` raised
`TypeError`, that `validate_feature_schema` was the function that actually
raised on a missing file, and that a list-valued `library_versions` raised
`AttributeError` while missing `feature_columns` raised `KeyError`. After the
fix the same commands were re-run: the bad threshold values return 0.4, the
missing file produces the readable `RuntimeError` (its full text was printed
and read), `validate_environment_versions` returns without raising on a list,
a string, a missing file and corrupt JSON, and `validate_feature_schema`
raises `RuntimeError` rather than `KeyError`.

The full suite passes: **64 tests in 3.90 s**, up from 52. One pre-existing
test failed as expected partway through — `test_load_threshold_falls_back_when_file_missing`
— and it was removed deliberately, not repaired, because it asserted the
behaviour the policy decision reverses; the reason is recorded in a comment
block in `tests/test_config.py` so a future reader doesn't restore it.

Both real consumers were then run, not just tested: `telco_model.py` scored
the sample file end to end and flagged 15 of 50 customers, and the API was
started through `TestClient`, reported healthy, and returned
`{"churn_probability": 0.57, "target_for_retention": true, "threshold_used": 0.4}`
for the dummy customer — identical to its behaviour before the change.
Finally the fresh-clone case was simulated by pointing `METADATA_PATH` at a
nonexistent file and running `telco_model.main()`, which now surfaces the
readable `RuntimeError` instead of a bare traceback. **Not committed** —
`config.py` and `tests/test_config.py` show as modified, alongside the
still-uncommitted work from earlier in this session.

---

## 2026-08-22 — Record the missing-metadata policy in CLAUDE.md

**Files touched:**
- `CLAUDE.md`

**What changed:** Three edits, all consequences of the `config.py` work
described in the entry above.

A fourth bullet was added to the "Invariants — don't break these" section
stating the missing-metadata policy in full: a missing or unparseable
metadata file raises `RuntimeError` with a readable message, a malformed
value inside a readable file degrades to `DEFAULT_THRESHOLD`, and
`validate_environment_versions()` never raises at all because it is a
detection control and `validate_feature_schema()` runs first in both
consumers. The `config.py` row in the file-layout table gained a one-line
summary of the same split. The `tests/` row was updated from "52 tests,
~2.1 s" to "64 tests, ~3.9 s".

**Why:** The policy is a decision, not a derivable fact — a future session
reading `config.py` could see *what* it does but not that the asymmetry
between fatal and degrading is deliberate, and might well "fix" the
inconsistency by making both paths behave the same way. Writing it into the
invariants section is what stops that. `CLAUDE.md` is loaded automatically
at the start of every session, so a stale test count there is also actively
misleading rather than merely out of date.

**Requested or incidental:** **Incidental.** You asked for the `config.py`
defects to be fixed. You did not ask for `CLAUDE.md` to be updated; all three
edits were made on initiative because the fix invalidated what the file said
and introduced a decision worth recording. This entry exists separately
because `CLAUDE.md` requires any edit to itself to be logged in its own
entry, without exception.

**Verification status:** Each edit was made by an anchored string
substitution that asserts its target exists before writing, so a silent
no-op was impossible; the resulting lines were read back. The test count and
timing were taken from a real `uv run pytest -q` run (64 passed, 3.90 s), not
estimated. No tests were run *for* this change specifically, as it is
documentation and touches no code. **Not committed** — `CLAUDE.md` shows as
modified.

---

## 2026-08-22 — Input validation on the batch path; reject non-finite numbers in the API

**Files touched:**
- `config.py`
- `telco_model.py`
- `api.py`
- `tests/test_input_validation.py` (created)
- `README.md`
- `AUDIT.md`

**What changed:** You asked whether extreme-value checks were worth adding
to some or all columns. The measurements said no to that specific idea and
yes to two narrower ones, and those two were implemented.

**Why extreme-value range checks were not added.** The model is a tree
ensemble, so out-of-range numbers do not extrapolate — they land in the
terminal leaf and the prediction saturates. Measured against the shipped
pickle: `tenure` of 1,000 and `tenure` of 10^15 both score 0.1201;
`monthlycharges` of 500 and of 10^300 both score 0.6665; `totalcharges` of
10^6 and 10^300 both score 0.5282. An absurd tenure returns the *directionally
correct* answer, that a very long-tenured customer is unlikely to churn. A
range check would therefore reject inputs the model already handles, and
would need an upper bound nobody can justify from the data. This reasoning
is recorded in `CLAUDE.md` and in the new test file's docstring so the
question does not get reopened from scratch.

**What was added instead, first: categorical domain validation on the batch
path.** The pipeline's OneHotEncoder is configured with
`handle_unknown='ignore'`, which means an unrecognised category is encoded
as an all-zeros block — indistinguishable from "no information". No error is
raised. Measured on the shipped model: a customer scoring 0.5700 with
`contract='Month-to-month'` scores 0.1017 with `contract='month-to-month'`,
and the same 0.1017 for `'Two Year'`, `'Monthly'` or an empty string. That is
a flipped retention decision caused by a casing difference, which is exactly
what a CSV exported from a slightly different system looks like. `api.py` was
already immune because its Pydantic `Literal` types reject these with a 422;
`telco_model.py` had no validation whatsoever.

`config.py` gained `CATEGORICAL_DOMAINS` (the allowed values for all fifteen
categorical columns), `NUMERIC_COLUMNS`, `NULLABLE_NUMERIC_COLUMNS`, and
`validate_input_frame()`. The domains live in `config.py` rather than
`api.py` because both consumers need them and that module exists precisely to
stop the two drifting apart. `telco_model.py` now calls the validator
immediately after `pd.read_csv` and before feature engineering, so reported
row numbers still line up with the input file.

The validator checks membership and finiteness, not plausibility. It reports
every problem it finds in a single raised `RuntimeError` rather than the
first one, so a malformed file can be fixed in one pass, and it names
offending rows using 1-based numbers that count the CSV header, so they match
what a text editor shows. It caps the row list at five per problem so a
50,000-row file with a systematically broken column does not print 50,000
line numbers. Blank `totalcharges` is explicitly still allowed, because the
eleven real customers with `tenure==0` have exactly that and the pipeline's
SimpleImputer exists to fill it — rejecting it would reject legitimate data.

**Second: non-finite numbers through the API.** A JSON body containing
`Infinity` passed Pydantic's `ge=0` check, because `inf >= 0` is `True`, and
reached the scaler, which raised `ValueError` mid-request and returned a 500.
`allow_inf_nan=False` was added to the two float fields — but that alone did
not fix it. Pydantic then rejected the value correctly, and FastAPI's default
422 response body echoes the offending input back under `"input"`, so
`json.dumps` refused to serialize `inf` and the client still got a 500. The
underlying quirk is that Python's `json` module accepts `Infinity` and `NaN`
on the way in while refusing to emit them on the way out. A
`RequestValidationError` handler was added that returns the normal 422 body
with non-finite values stringified. The rejection itself is still Pydantic's;
only the reporting changed.

`tests/test_input_validation.py` adds 39 tests. The unknown-category test is
parametrized over `CATEGORICAL_DOMAINS` itself, so a column added to that map
is covered automatically rather than needing a remembered test. One test
asserts that `api.Customer`'s `Literal` types and `config.CATEGORICAL_DOMAINS`
contain the same values, which is what stops the two consumers drifting into
accepting different inputs. Others cover negative and unparseable numerics,
infinities, missing columns, the exact row numbers in the message, all
problems appearing in one pass, blank `totalcharges` still passing, and the
real `simulated_new_customers.csv` still validating.

`README.md` lists the new test file. `AUDIT.md` had M1 ticked.

**Why:** M1 was the highest-ranked moderate finding in the audit — the batch
scorer would accept any CSV and silently produce different answers. Your
question about extreme values was the prompt, and investigating it showed the
real exposure was categorical rather than numeric.

**Requested or incidental:** Requested — you said "yes do it" to the two
changes I recommended. Flagged as beyond that: the `README.md`, `AUDIT.md`
and `CLAUDE.md` updates were taken on initiative, and the
`RequestValidationError` handler was not in the original recommendation
either — it became necessary only when `allow_inf_nan=False` turned out not
to be sufficient on its own. The `CLAUDE.md` edit is logged separately below.

**Verification status:** Measured before, verified after. The saturation
figures and the 0.5700 → 0.1017 swing were obtained by running the shipped
pickle, not estimated. The API's inf behaviour was checked twice: an initial
test appeared to show a failure that was actually the test client refusing to
serialize the request, so it was re-run with a raw JSON body to confirm the
defect was real and server-side before anything was changed.

After the change: `Infinity`, `-Infinity` and `NaN` all return 422 with
"Input should be a finite number", a valid customer still returns 200 with
`churn_probability` 0.57, and `telco_model.py` still scores the real sample
file and flags the same 15 of 50 customers as before. A deliberately
corrupted copy of that file — two bad `contract` values, a `paymentmethod` of
"PayPal", a negative charge, an infinite tenure and an unparseable charge —
was rejected with all five problems listed and correct file line numbers. The
full suite passes: **103 tests in 2.07 s**, up from 64.

One finding was *not* fixed and should not be assumed covered: AUDIT M9, the
unhelpful `AttributeError` from the `.str` accessor in `is_auto_pay` when
`paymentmethod` is an all-empty column, is now caught earlier *in the batch
path* with a readable message — verified — but `engineer_features()` itself
is unchanged, so calling it directly still raises the original unhelpful
error. M9 remains open in `AUDIT.md`. **Not committed at the time of
writing;** committed immediately afterwards as the second of two commits.

---

## 2026-08-22 — Record the input-validation contract in CLAUDE.md

**Files touched:**
- `CLAUDE.md`

**What changed:** Five edits, all consequences of the input-validation work
described above.

A new invariant was added stating that the two consumers must accept the same
inputs, not merely produce the same decision: `config.CATEGORICAL_DOMAINS` is
the batch path's copy of `api.Customer`'s `Literal` types, a test asserts they
agree, and the reason it matters is that `handle_unknown='ignore'` makes an
unvalidated bad category score silently rather than error, with the
0.5700 → 0.1017 swing given as the concrete example.

A new fact was added recording that extreme *numbers* are safe because the
tree ensemble saturates — `tenure=10**15` scores identically to
`tenure=1000` — and that there is deliberately no range check, with unknown
categories named as the real hazard. The `telco_model.py` row, which
previously read "**No input validation** (see AUDIT.md M1)", now says it
validates through `config.validate_input_frame()` and marks M1 fixed. A row
was added for `tests/test_input_validation.py`. The `tests/` row went from
"64 tests, ~3.9 s ... 6 files" to "103 tests, ~2.1 s ... 7 files".

**Why:** The absence of a range check is a decision, not an oversight, and
nothing in the code records a decision not taken — a future session would
reasonably see unbounded numeric inputs as a gap and "fix" it. Writing the
saturation measurement into the file is what prevents that. The
`telco_model.py` row was actively wrong once the validator landed, and
`CLAUDE.md` is loaded automatically at the start of every session, so a wrong
statement there is more costly than almost anywhere else.

**Requested or incidental:** **Incidental.** You asked for the validation to
be implemented; none of these documentation edits were requested. This entry
is separate because `CLAUDE.md` requires any edit to itself to be logged in
its own entry, without exception.

**Verification status:** Each edit was applied by an anchored string
substitution asserting its target exists first, so a silent no-op was
impossible, and the results were read back. The test count and timing come
from a real `uv run pytest -q` run (103 passed, 2.07 s). The saturation
figures quoted in the new fact were measured against the shipped pickle
earlier in the session. No tests were run for this change specifically — it
is documentation and touches no code. Committed together with the code it
describes.

---

## 2026-08-22 — Bring README back in line with the code after an end-to-end audit

**Files touched:**
- `README.md`

**What changed:** You asked whether the README still matched the project. It
was audited claim by claim against the code rather than read for plausibility,
and six things were found stale — five of them caused by this session's own
work — and all six were fixed.

**What was verified as still correct**, so it is not being changed: the entire
Results table was recomputed from the committed pickle against a reconstructed
train/test split, and every figure matched exactly — ROC-AUC 0.8441, precision
0.59, recall 0.69, F1 0.63, accuracy 79%, confusion 256/179/116/854, profit
$6,660 — as did the dataset counts (7,043 raw rows, 1,405 test rows, 22
duplicates). The Approach, model-comparison and threshold-sensitivity sections
are untouched by recent work and remain accurate.

**The six fixes.** The Tests section claimed the suite covers
`load_threshold`'s "fallback behavior (missing file, missing key, bad value)".
Missing-file is no longer a fallback — it was made fatal earlier in this
session — so the README was describing behaviour that had been deliberately
reversed. That sentence now describes behaviour on malformed metadata, and a
new paragraph states the split policy explicitly: a missing or unparseable
file is fatal, a bad value inside a readable file degrades.

The same section claimed the tests "run fast with no trained `.pkl` or
`model_metadata.json` on disk". That stopped being true when
`test_artifact.py` was added — confirmed by deleting both artifacts from a
clone and watching four tests fail and four error. The text now says which
three of the seven files are deliberately unmocked and what each needs. The
neighbouring claim that a fresh clone can run the suite immediately was
checked and *is* still true, since the artifacts are committed, so it was
kept — a clean clone runs 103 tests green.

The Tests section also predated two whole test files, so it gained a
description of artifact pinning (what `dummy_customer_score` is and why a
retrain cannot make the pin stale) and of batch-input validation.

The batch-scoring section described only the feature-schema check. It now also
covers input validation, including the reason it exists — the OneHotEncoder's
`handle_unknown='ignore'` turns an unrecognized category into an all-zeros
block, so a casing slip moves a score from 0.5700 to 0.1017 with no error —
a real sample of the error output, and an explicit note that numeric *ranges*
are deliberately not checked because tree ensembles saturate.

The API section said nothing about rejection. It now states that unknown
categories, negative charges and non-finite numbers return 422, and notes that
the batch path checks against the same domains with a test asserting they
agree.

The repo-structure block described `model_metadata.json` as holding
"threshold + CV scores + feature schema + dataset hash"; it also holds
`library_versions` and `dummy_customer_score`, and now says so.

**One pre-existing gap was also closed**, unrelated to this session's changes:
the README had never explained the version-drift machinery at all, even though
`verify_version_check.sh` appeared in its file listing. A paragraph now covers
what `validate_environment_versions()` does and why it warns rather than
blocking. The `pytest -v` invocation was also changed to `uv run pytest -q`,
matching how the project is actually run — the bare form only works with the
virtualenv already activated.

**Why:** You asked directly whether the README was one-to-one with the project.
A README that describes reversed behaviour is worse than one that is merely
incomplete, because a reader has no way to tell which parts to trust — and the
`load_threshold` sentence contradicted a policy decision made deliberately two
commits earlier.

**Requested or incidental:** Requested — you asked for the audit and then said
to fix what it found. Flagged as beyond that: the version-drift paragraph and
the `pytest -v` correction were not among the six findings; both were taken on
initiative while editing the same section.

**Verification status:** Audited and re-verified by execution, not by reading.
Before the edit, the fresh-clone claim was tested by cloning the repo into a
temporary directory twice — once intact (103 passed) and once with the
artifacts deleted (4 failed, 4 errors) — which is what established that half
the sentence was true and half was false. The Results table was recomputed
from the pickle as described above.

After the edit, every new claim was re-checked against the code: the suite
count and timing (103 passed, ~2 s), that seven test files exist, that
`dummy_customer_score` and `library_versions` are really in the metadata, that
`test_integration.py` genuinely passes with the pickle deleted (5 passed), and
that the sample validation error printed in the README is the real output —
it was regenerated from a deliberately corrupted frame and matches
character-for-character apart from the elisions marked `...`. The six original
findings were re-grepped and confirmed gone. **Not committed at the time of
writing.**

---

## 2026-08-22 — Make the integration fixture's tenure=0 rows deterministic

**Files touched:**
- `tests/test_integration.py`
- `AUDIT.md`

**What changed:** The synthetic fixture in `tests/test_integration.py` drew
each row's tenure with `int(rng.integers(0, 60))`, which gives roughly a
1-in-60 chance per row of producing a zero. A `tenure=0` row is what creates
the missing `totalcharges` value that mirrors the eleven real such rows in the
Kaggle dataset, and `test_pipeline_handles_missing_totalcharges` exists
specifically to prove the real SimpleImputer absorbs them. At n=40, whether
*any* such row appeared was close to a coin flip.

Measured across the first 40 seeds, 21 of them — 52% — produced no missing
`totalcharges` rows at all, and the default `seed=0` produced exactly one. The
entire imputation test rested on that single row appearing by luck.

To be fair to the original code, the test asserted its own precondition, so a
bad seed failed loudly rather than passing silently; this was fragility rather
than a false pass. But "change one integer and half the time the suite goes
red for reasons unrelated to your change" is a genuine maintenance hazard, and
one row is thin coverage for the behaviour under test.

The fixture now forces the first `N_ZERO_TENURE_ROWS` (3) rows to `tenure=0`
and draws the rest from 1..59, so no additional zeros can appear by accident
and the count is exact rather than "at least one". A guard raises if `n` is
small enough to leave no non-zero rows. The precondition assertion in
`test_pipeline_handles_missing_totalcharges` was tightened from
`.isna().any()` to an equality check against `N_ZERO_TENURE_ROWS`, since a
drifting count now means the fixture itself changed, which is worth failing on.

Two parametrized regression tests were added, each run over five seeds. The
first asserts the missing-`totalcharges` count is exact and — more to the
point — that missing values coincide exactly with `tenure == 0` in both
directions, since that pairing is the real-data property being mirrored, not
just the row count. The second asserts the fixture still spans every allowed
categorical value and still contains both churn classes, because forcing the
first rows to a fixed tenure must not cost the categorical coverage that is
the fixture's other job. It checks against `config.CATEGORICAL_DOMAINS`, so it
tracks the same domain map the rest of the project validates against.

**Why:** You asked for roadmap item 4, AUDIT finding M7, by name.

**Requested or incidental:** Requested. Flagged as beyond the literal ask: the
audit's suggested fix was the three forced rows alone; the two regression
tests, the tightened assertion, the `n` guard, and the `AUDIT.md`,
`CLAUDE.md` and `README.md` updates were added on initiative. The `CLAUDE.md`
edit is logged separately below.

**Verification status:** Reproduced first, then verified. The audit's own
verification command was run before the change and returned exactly what it
predicted — `21/40 seeds fail the precondition`, with `seed=0` producing one
missing row. After the change the same command returns `0/40`, and a wider
sweep over seeds 0–199 found the count was exactly 3 in every single case,
with no other value occurring.

Robustness was also checked the way a future maintainer would hit it: the
fixture's default seed was temporarily changed from 0 to 13 — one of the
seeds that previously produced zero missing rows — and the whole file was
re-run, passing 15 of 15. The original file was restored afterwards. The full
suite passes at **113 tests in 1.99 s**, up from 103. **Not committed** at the
time of writing.

---

## 2026-08-22 — Note the integration fixture's determinism in CLAUDE.md

**Files touched:**
- `CLAUDE.md`

**What changed:** Two edits. A convention was added recording that
`tests/test_integration.py`'s fixture forces its first `N_ZERO_TENURE_ROWS`
(3) rows to `tenure=0` so the missing-`totalcharges` rows are exact for every
seed, noting that this used to be left to chance and that 21 of 40 seeds
produced none. The `tests/` row was updated from "103 tests, ~2.1 s" to
"113 tests, ~2.0 s".

**Why:** The forced rows look like an oddity if you don't know why they are
there — a future session tidying the fixture could reasonably restore
`rng.integers(0, 60)` as the more natural-looking code and silently reintroduce
a 52% chance of unrelated failures. The regression tests would catch it, but
the note explains the intent before someone spends time on it. `CLAUDE.md` is
loaded automatically at the start of every session, so a stale test count
there is misleading rather than merely out of date.

**Requested or incidental:** **Incidental.** You asked for the fixture fix;
neither documentation edit was requested. This entry is separate because
`CLAUDE.md` requires any edit to itself to be logged in its own entry, without
exception.

**Verification status:** Both edits were applied by anchored string
substitutions that assert their target exists before writing, and the results
were read back. The test count and timing come from a real `uv run pytest -q`
run (113 passed, 1.99 s). No tests were run for this change specifically — it
is documentation and touches no code. Not committed.

---

## 2026-08-22 — Guard engineer_features()'s .str use against a blank column (M9)

**Files touched:**
- `feature_engineering_telco.py`
- `tests/test_feature_engineering.py`
- `AUDIT.md`

**What changed:** `is_auto_pay` was computed with
`df['paymentmethod'].str.contains('automatic', case=False, na=False)`. A CSV
whose `paymentmethod` column is entirely blank reads back from `read_csv` as
`float64`, and the `.str` accessor on a float column raises
`AttributeError: Can only use .str accessor with string values, not floating`
— an error that names pandas internals rather than the actual problem. The
`na=False` argument already handled *individual* missing values correctly; it
is the whole-column dtype change that broke it.

The column is now converted with `.astype('string')` before `.str` is used, so
a blank column degrades to `is_auto_pay=0` exactly the way individual missing
values already did. Zero is the consistent answer: a payment method that isn't
known isn't an automatic one.

Five tests were added. One covers the blank-column case directly. Three
parametrized cases cover dtypes that must keep behaving identically —
pandas `StringDtype` (what a pyarrow-backed read produces), a categorical
column, and a single missing value among strings — because the risk in adding
an `astype` is that it changes the ordinary cases, not the broken one. The
last covers a zero-row frame, which must still produce all 25 columns rather
than raising.

**Why:** You asked for worklist item 5, "Schema validation on the batch path
(M1, M9)". **M1 was already fixed and ticked earlier in this session** — the
batch scorer has validated its input against the trained categories since the
`0aa8819` commit — so M9 was the remaining half. The audit's own note on M9
says it is "subsumed by M1", because the batch path now rejects a blank column
earlier and with a far better message. That is true and was verified. The
local guard was still worth adding because `engineer_features()` is imported
directly by the notebook and by `api.py`, not only by the batch script, so it
should not depend on its caller having validated first.

**Requested or incidental:** Requested, with the scope correction noted above
— M9 rather than M1+M9, because M1 was already done. Flagged as beyond the
literal ask: the four dtype and empty-frame tests go past what the audit
suggested, and the `AUDIT.md`, `CLAUDE.md` and `README.md` updates were taken
on initiative. The `CLAUDE.md` edit is logged separately below.

**Verification status:** Reproduced with the audit's own command before the
change, producing exactly the documented `AttributeError`. After the change
the same input returns `is_auto_pay=[0, 0]` with all 25 columns intact.

Because this is the project's most load-bearing module, the change was checked
for regressions rather than assumed safe. All four real payment methods still
map correctly — the two "(automatic)" ones to 1, the two manual ones to 0.
`StringDtype`, categorical, mixed-missing and empty-frame inputs were each
exercised and all behave identically to a plain object column. Most
importantly, the committed artifact's pinned prediction is byte-identical:
`DUMMY_CUSTOMER` still scores `0.5699995160102844`, matching
`model_metadata.json["dummy_customer_score"]` exactly, so the change provably
did not alter what the model sees. `telco_model.py` was run end to end and
still flags the same 15 of 50 customers, and the batch path was confirmed to
still reject a blank `paymentmethod` column upfront with the readable message
rather than reaching this code at all. Suite: **118 tests passing**, up from
113. **Not committed.**

---

## 2026-08-22 — Note the .str guard in CLAUDE.md

**Files touched:**
- `CLAUDE.md`

**What changed:** The `feature_engineering_telco.py` row in the file-layout
table now records that the module guards its own `.str` use, with an all-blank
`paymentmethod` degrading to `is_auto_pay=0` rather than raising, and cites
AUDIT M9. The `tests/` row went from "113 tests, ~2.0 s" to "118 tests,
~2.0 s".

**Why:** The `.astype('string')` call looks like redundant noise next to a
`.str` accessor — it is the kind of thing a future session would remove while
tidying, since `na=False` appears to already cover missing values. Recording
what it defends against, in the file that loads automatically at the start of
every session, is what prevents that.

**Requested or incidental:** **Incidental.** You asked for the M9 fix; neither
documentation edit was requested. Logged separately because `CLAUDE.md`
requires any edit to itself to have its own entry, without exception.

**Verification status:** Both edits applied by anchored string substitutions
that assert their target exists first; results read back. The test count comes
from a real `uv run pytest -q` run (118 passed). No tests run for this change
specifically — documentation only. Not committed.

---

## 2026-08-22 — Scope the notebook's warning suppression (M5)

**Files touched:**
- `telco_customer_churn.ipynb` (cell 2)
- `AUDIT.md`

**What changed:** Cell 2 ended with `warnings.filterwarnings('ignore')`, a
bare catch-all that silences every warning for the entire kernel session.
Retraining is the one activity during which you most want to hear about
problems, and that line hid all of them. It was replaced with
`warnings.simplefilter('once')`, which shows each *distinct* warning exactly
once — enough to keep the output readable inside a 200-iteration
cross-validated search, without hiding anything.

A comment block was added listing what the catch-all had been concealing, so
nobody restores it for quietness without knowing the cost.

**What re-running the model-comparison cell actually showed.** The audit
flagged one specific risk as "the real bite": that cell 33's Logistic
Regression number, and the README's conclusion that the dataset has an
information ceiling around ROC-AUC 0.845, might rest on a model that never
converged. That was checked by reconstructing the cell's search — the same
200 iterations over 5 folds, the same `X_tr`/`y_tr` slice — with warnings
captured instead of suppressed.

The result is reassuring on that point: **zero ConvergenceWarnings**, and the
search reproduced ROC-AUC 0.843896 against the README's 0.843897. The
Logistic Regression number is sound, and the information-ceiling conclusion
stands. It was sound by luck rather than by verification, though, since
nothing in the notebook would have revealed the opposite.

The same run surfaced something the audit did not anticipate: **1,457
warnings from that one cell** — 1,001 `FutureWarning` and 456 `UserWarning`.
They say that `LogisticRegression`'s `penalty` argument was deprecated in
scikit-learn 1.8 and **will be removed in 1.10**. Cell 33 searches
`penalty: ['l1', 'l2']`, so that cell stops working on a future scikit-learn
upgrade, and the blanket ignore meant there would have been no advance notice
whatsoever. The accompanying `UserWarning` reads "Inconsistent values:
penalty=l1 with l1_ratio=0.0", which looked as though L1 might be silently
ignored; that was checked directly and it is not — at small `C`, `penalty='l1'`
still drives coefficients to exactly zero (36 of 40 at C=0.01) while `'l2'`
drives none. So the current results are correct and the warning is noise
today, but it announces the same removal.

**This deprecation was NOT fixed**, deliberately. Changing cell 33's search
space to the `l1_ratio` API would alter the Logistic Regression comparison
numbers currently published in the README, which is a decision about what the
project reports rather than a mechanical repair. It is recorded in `CLAUDE.md`
so the next session finds it before a scikit-learn upgrade does.

**Why:** You asked for worklist item 6 / finding M5 by name, and specifically
for cell 33 to be re-run and checked for `ConvergenceWarning`.

**Requested or incidental:** Requested. Flagged as beyond the literal ask: the
investigation of the `penalty` deprecation and the L1-still-works check were
not asked for — they came out of running the cell — and the `AUDIT.md` and
`CLAUDE.md` updates were taken on initiative. The `CLAUDE.md` edit is logged
separately below.

**Verification status:** Executed, at full scale rather than approximated.
The full 200-iteration × 5-fold Logistic Regression search was reconstructed
from the notebook's own cleaning, splitting and preprocessing code and run to
completion (about eight minutes) with `warnings.simplefilter('always')` and
`record=True`, which is what produced the 1,457 count, the zero
ConvergenceWarnings, and the ROC-AUC that matches the README to six decimal
places. The L1-sparsity check was a separate direct experiment on synthetic
data, not an inference from the warning text.

The edited cell 2 was extracted and executed standalone to confirm it still
runs, that the only executable warning-related lines are now `import warnings`
and `warnings.simplefilter('once')`, and that the filter genuinely lets a
warning through — three repeated `FutureWarning`s emit exactly one copy. The
notebook JSON round-tripped without reformatting (34 insertions, 1 deletion,
no image blobs touched). The test suite is unaffected at 118 passing, and the
artifact canary still matches its pin, confirming nothing about the shipped
model changed. **The notebook itself was not re-executed end to end** — no
retraining was performed, so `xgboost_churn_pipeline.pkl` and
`model_metadata.json` are untouched.

---

## 2026-08-22 — Record the warning policy and the sklearn 1.10 deadline in CLAUDE.md

**Files touched:**
- `CLAUDE.md`

**What changed:** A convention was added stating that notebook cell 2 uses
`warnings.simplefilter('once')` rather than a blanket `ignore` and that the
catch-all should not be restored, citing AUDIT M5. It also records the
concrete finding: re-running cell 33 now surfaces roughly 1,457 warnings,
`LogisticRegression`'s `penalty` argument is deprecated in scikit-learn 1.8
and removed in 1.10, so that cell's `penalty: ['l1','l2']` search will break
on upgrade — and that this is deliberately not yet fixed because fixing it
changes the published comparison numbers.

**Why:** A blanket `filterwarnings('ignore')` is the kind of line that gets
reinstated the moment output gets noisy, especially now that the notebook
prints far more than it used to. Recording why it was removed is what makes
that a considered decision rather than an accident. The scikit-learn 1.10
deadline is more important still: it is a dated breakage in a file nobody
runs often, and the only reason it is known at all is that the suppression
was lifted. `CLAUDE.md` loads automatically at the start of every session, so
it is where a future session will actually see it.

**Requested or incidental:** **Incidental.** You asked for the suppression to
be scoped and cell 33 re-run; you did not ask for documentation changes.
Logged separately because `CLAUDE.md` requires any edit to itself to have its
own entry, without exception.

**Verification status:** The edit was applied by an anchored string
substitution asserting its target exists first, and read back. Every figure
quoted in it — the 1,457 warning count, the 1.8/1.10 versions — comes from
the run described in the entry above, not from memory. No tests were run for
this change specifically; it is documentation and touches no code.
