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

---

## 2026-08-22 — Trim the cell 2 warning comment

**Files touched:**
- `telco_customer_churn.ipynb` (cell 2)

**What changed:** The explanatory comment added to cell 2 in the previous
change was cut from 32 lines to 14. It had listed all five categories of
warning the old blanket `filterwarnings('ignore')` was hiding, each with its
own paragraph, which was more than the point needed.

What remains is the part a reader acts on: that the line used to be a bare
`filterwarnings('ignore')`, that lifting it revealed roughly 1,457 warnings
from the model-comparison cell, that `LogisticRegression`'s `penalty`
argument is removed in scikit-learn 1.10 and will break that cell on upgrade,
that the `ConvergenceWarning` question was checked and came back clean, and
the instruction to suppress a specific category rather than restoring the
catch-all. The `RuntimeWarning`, `InconsistentVersionWarning` and
`UserWarning` details were dropped — they are recorded in `AUDIT.md` M5 and in
the CHANGELOG entry for the original change, so nothing is lost.

**Why:** You asked for it to be trimmed. A comment several times longer than
the code it explains is one a reader skims past, which defeats its purpose —
particularly the sklearn 1.10 deadline, which is the one line that needs to
be noticed.

**Requested or incidental:** Requested. No other change was made — the
executable code is untouched.

**Verification status:** Confirmed the only executable warning-related lines
in the cell are still `import warnings` and `warnings.simplefilter('once')`,
extracted the cell and ran it standalone to confirm it still executes clean,
and checked the notebook JSON round-tripped without disturbing anything else
(11 insertions, 29 deletions, no image blobs touched). Test suite unaffected
at 118 passing. Committed.

---

## 2026-08-22 — Move cell 33's Logistic Regression off the deprecated `penalty` argument

**Files touched:**
- `telco_customer_churn.ipynb` (cell 33)
- `README.md`
- `CLAUDE.md`

**What changed:** The model-comparison cell searched
`'classifier__penalty': ['l1', 'l2']`. scikit-learn deprecated
`LogisticRegression`'s `penalty` argument in 1.8 and removes it in 1.10, so
that cell would have broken on a future upgrade. It now searches
`'classifier__l1_ratio': [1.0, 0.0]` — 1.0 is pure L1, 0.0 is pure L2, the
same two options — with `solver='liblinear'` unchanged. liblinear supports
exactly those two endpoints and rejects anything between them, which is
elasticnet and requires `saga`; that constraint was checked rather than
assumed.

**The search space is provably identical.** `ParameterSampler` sorts its keys,
and `'classifier__l1_ratio'` occupies the same alphabetical position between
`'classifier__C'` and `'classifier__solver'` that `'classifier__penalty'` did.
Both were generated for 200 iterations at `random_state=42` and compared draw
by draw: the `C` values match to within 1e-12 across all 200, and every
`penalty` maps to its `l1_ratio` equivalent in the same position.

**The results still move, in the last decimals.** The two code paths are not
numerically bit-identical — fitting at a fixed `C` through `penalty='l1'` and
through `l1_ratio=1.0` produces different coefficients — so the Logistic
Regression row's ROC-AUC goes 0.843897 → 0.843891, a shift of about 6e-6.
That is four orders of magnitude below this model's own 0.019 fold-to-fold
standard deviation. The comparison table's ordering is unchanged and so is
the README's information-ceiling conclusion.

The full row was recomputed rather than partially estimated: Mean ROC-AUC
0.843891, Std Dev 0.018898, best threshold 0.58 (unchanged), accuracy 0.7758,
profit $26,200. `README.md`'s comparison table and the inline
"0.845812 / 0.843897 / 0.844126" sentence were both updated, and a short note
under the table explains the shift and states that these figures come from a
reconstruction rather than a full notebook re-run. The XGBoost and Random
Forest rows are untouched — the change cannot affect them.

**A correction to a comment written earlier in this same turn.** The first
version of the cell 33 comment asserted that the results were "unchanged.
Verified by re-running the search both ways." That was wrong on the strength
of the evidence available at the time: the identical *parameter draws* had
been verified, and I generalised from that to identical *results* before the
confirming run finished. Two further runs then showed otherwise. The comment
was rewritten twice — once when the outputs first disagreed, and again when a
second run showed that the winning `C` value I had attributed to the API
change (6.3856 → 6.0803) was actually run-to-run instability: with
`n_jobs=-1`, matching the notebook's own configuration, the new API selects
the same `C=6.3856` the old one did. The ROC-AUC difference is systematic; the
`C` difference was not. The committed comment states only what survived
verification.

**Why:** You asked for it, having read the note left in `CLAUDE.md` saying it
was worth doing before the next scikit-learn bump. It also removes all 1,457
deprecation warnings that the previous change exposed — cell 33 now runs
warning-free.

**Requested or incidental:** Requested. Flagged as beyond the literal ask: the
`README.md` table update was a necessary consequence rather than a separate
decision, but it does change published numbers, and the `CLAUDE.md` update was
taken on initiative.

**Verification status:** Executed at full scale, three times, which is what
caught the error described above. The 200-iteration × 5-fold search was run to
completion under the old API (ROC-AUC 0.843896), under the new API single-
threaded (0.843891, C=6.0803), and under the new API with `n_jobs=-1` matching
the notebook (0.843891, C=6.3856, Std 0.018898) — the last of which also
computed the out-of-fold threshold scan that produced the row's threshold,
accuracy and profit figures. The code-path difference was confirmed separately
by fitting at three fixed `C` values through both APIs and comparing
coefficients directly. Solver support for `l1_ratio` was established by trying
liblinear, saga and lbfgs at 0.0, 0.5 and 1.0. The new search emits **zero
warnings**, down from 1,457.

The notebook JSON round-tripped cleanly (22 insertions, 1 deletion, no image
blobs disturbed), no executable `penalty` reference remains anywhere in the
notebook, and the test suite is unaffected at 118 passing. **The notebook was
not re-executed end to end**, so `xgboost_churn_pipeline.pkl` and
`model_metadata.json` are unchanged and the shipped model is untouched — only
the Logistic Regression comparison row, which is not part of the artifact.
Committed.

---

## 2026-08-22 — Add a calibration curve on oof_proba (roadmap item 5)

**Files touched:**
- `telco_customer_churn.ipynb` (two new cells inserted at positions 28 and 29)
- `README.md`
- `CLAUDE.md`
- `AUDIT.md`

**What changed:** A markdown cell and a code cell were inserted after the
sensitivity sweep. The code cell plots a reliability curve of the tuned
XGBoost model's out-of-fold predictions against observed churn, marks both
the operating threshold and the closed-form optimum on it, and prints the
numbers that connect the two.

**The question it answers.** The profit formula has an exact optimum:
targeting pays off when `p * success_rate * clv > cost`, so the break-even
probability is `cost / (success_rate * clv)` — 0.333 at the baseline
constants. The grid chose 0.40. More tellingly, *every* row of the
sensitivity sweep sits above its own closed-form value, mean offset +0.046,
15 of 15 positive. A one-directional gap that consistent is not search noise.

It is calibration. The closed form assumes the model's output *is* a
probability; the grid does not have to. Where the scores run hot, the grid
compensates by demanding a higher one — so the empirical search is earning
its keep rather than being a slower way to compute a formula. That is the
justification for the whole threshold-selection approach, and nothing in the
repo previously stated it.

**A refinement on what the audit predicted.** `AUDIT.md` inferred from the
+0.046 threshold offset that "at any given score, the true churn rate is ~4.6
points below what the model says." Measuring it directly shows the magnitude
is right but the phrase "at any given score" is not: averaged across all bins
the model runs only **+0.022** hot, but in the `[0.30, 0.50)` band where the
decision is actually made it runs **+0.051** hot. The gap is concentrated
where it matters. Those +0.051 and the sweep's +0.046 agree to within 0.004,
which is what ties the two observations together — a single global
"the model is X points optimistic" would have understated the effect exactly
at the boundary. Brier score is 0.1342.

The cell recomputes the sweep offset itself rather than quoting it, using the
same `best_threshold_for` helper the sweep uses, so its central claim is
self-verifying rather than a hardcoded number that can go stale.

`README.md` gained a "Why the searched threshold sits above the closed form"
subsection under the threshold-stability section, with the four measured
figures in a small table and the two practical consequences: a raw score is
not a probability (a customer scored 0.45 churns about 39% of the time), and
calibrating would pull the empirical threshold toward 0.333 while leaving
ROC-AUC unchanged, since it does not alter the ranking.

**Cell numbering shifted.** Inserting two cells moved every index above 27 up
by two. `CLAUDE.md`'s notebook cell map was updated accordingly (test-set
scoring is now 30–33, model comparison 35, SHAP 38–39, save artifact 40–42)
and now carries an explicit warning that `AUDIT.md` predates the shift and
still uses the old numbering, so its "cell 33" is now 35 and its "cell 38" is
now 40. `AUDIT.md`'s own findings were left as written rather than renumbered
— it is a historical document.

**Why:** You asked for roadmap item 5 by name.

**Requested or incidental:** Requested. Flagged as beyond the literal ask: the
audit asked for a calibration curve, and the band-specific measurement, the
self-recomputing sweep offset, and the README subsection go past that. The
`CLAUDE.md` and `AUDIT.md` updates were taken on initiative, and the cell-map
renumbering was forced by the insertion rather than chosen.

**Verification status:** Every number in the new cell and in the README was
measured, not carried over from the audit. `oof_proba` was reconstructed by
running `cross_val_predict` with the committed pickle over a rebuilt
`X_train` — 5,616 rows, mean predicted 0.2866 against an actual churn rate of
0.2644 — and the sweep's mean offset was independently recomputed as +0.0464
across 15 rows, all positive, matching the audit's +0.046.

**The inserted cell was executed**, not merely written: it was extracted from
the notebook and run against the reconstructed state under a headless
matplotlib backend, confirming the plot renders and the printed figures are
the ones quoted here. That run caught a real error in the first draft — the
narrative compared the *baseline* row's offset (+0.067) against the band gap
(+0.051) while claiming they agreed to within 0.005, which they do not. The
cell was rewritten to compare the mean-across-sweep offset (+0.046) instead,
which is the quantity that actually matches, and to say explicitly that a
single row is a coarser read because it is one argmax on a flat curve. The
corrected version was re-executed and its output verified line by line.

The notebook JSON round-trips cleanly, the new code cell carries no baked-in
outputs (`execution_count: None`, empty `outputs`), and the file now holds 43
cells. **The notebook was not re-executed end to end** — no retraining, so
`xgboost_churn_pipeline.pkl` and `model_metadata.json` are untouched. Test
suite unaffected at 118 passing. Committed.

---

## 2026-08-22 — Sync the README's Logistic Regression row to the re-executed notebook

**Files touched:**
- `README.md`
- `CLAUDE.md`

**What changed:** You re-executed the notebook end to end. Its actual outputs
were compared against every figure the README publishes, and one row was
wrong.

**What reproduced exactly**, and therefore needed no change: the whole Results
table — test ROC-AUC 0.8441, precision 0.59, recall 0.69, F1 0.63, accuracy
0.79, confusion matrix 854/179/116/256, campaign profit $6,660, operating
threshold 0.40 — plus the entire calibration section added earlier today
(Brier 0.1342, all-bins gap +0.0222, `[0.30, 0.50)` gap +0.0505, mean sweep
offset +0.0464 over 15/15 positive rows). The calibration figures had been
written from a reconstruction; the real run printed them identically.

More notably, `xgboost_churn_pipeline.pkl`, `simulated_new_customers.csv` and
`dataset_baseline.json` are all **byte-identical** after the retrain, and
`model_metadata.json` changed only in `trained_at` and `git_commit`. The
threshold, CV scores, dataset hash, library versions, feature columns and
pinned `dummy_customer_score` are unchanged. The `random_state=42` seeding
throughout genuinely reproduces the artifact.

**What was wrong.** The Logistic Regression comparison row had been written
from a reconstruction of that cell rather than a real notebook run, and it
was flagged as such in the README at the time. The real run differs:

| Field | README said | Notebook printed |
|---|---|---|
| Mean ROC-AUC | 0.843891 | 0.843892 |
| Std Dev | 0.018898 | 0.018902 |
| Best Threshold | 0.58 | **0.62** |
| Accuracy @ Threshold | 0.7758 | **0.7867** |
| Profit @ Threshold | 26,200 | 26,200 |

The ROC-AUC and Std differences are reconstruction noise in the sixth decimal.
The threshold and accuracy differences are real and larger than expected. The
cause is the same flatness noted when that cell was changed: the winning `C`
is not stable run to run, and the profit-optimal threshold follows it. My own
reconstructions had produced both 0.58 and 0.62 depending on `n_jobs`, which
was the warning sign that the single number should not have been published
from a reconstruction at all.

Three places were corrected: the comparison table row, the inline
"0.845812 / 0.843892 / 0.844126" sentence, and the threshold-split paragraph,
which read "Random Forest's and Logistic Regression's (0.58, for both)" and is
now "Random Forest's (0.58) and Logistic Regression's (0.62)". The note under
the table was rewritten — it no longer says the figures come from a
reconstruction, since they now come from the real run, and it states the
threshold movement plainly along with why it looks larger than it is.

`CLAUDE.md` gained a short procedure for what to re-check after any notebook
re-execution, since this is the second time README figures have drifted from
the notebook and there was nothing written down about it.

**Why:** You re-executed the notebook and asked what needs changing when that
happens. Answering it properly meant checking, not describing.

**Requested or incidental:** Requested in substance — you asked the question,
and the README corrections are the answer applied rather than merely
explained. The `CLAUDE.md` procedure was added on initiative.

**Verification status:** Every published figure was compared against output
text extracted directly from the re-executed notebook's cells, not against
memory or an earlier reconstruction. The byte-identity of the pickle and the
two CSVs was confirmed with `git diff`, and the metadata diff was read in
full. The artifact canary still scores 0.5699995160102844 and still matches
the metadata pin, which is the check that would have caught a genuinely
changed model. Test suite: 118 passing. Committed.

---

## 2026-08-22 — Appendix: show calibrated probabilities without changing the shipped model

**Files touched:**
- `telco_customer_churn.ipynb` (a markdown cell and a code cell appended at the end, indices 43 and 44)
- `README.md`
- `CLAUDE.md`

**What changed:** Two cells were added at the very end of the notebook,
*after* the save cells, that fit a Platt scaler for display and never store
it. They answer "what does a score of 0.45 actually mean?" without touching
anything the project ships.

The code cell plots the reliability curve twice side by side — as shipped,
and after Platt scaling — and prints a translation table converting a raw
score into an actual risk estimate. It then re-runs the profit search on the
calibrated scores to show what calibrating would and would not buy.

The measured answer: the profit-optimal threshold on calibrated scores is
**0.32**, against a closed-form prediction of 0.333. Calibrating moves the
empirical optimum onto the formula, which confirms the earlier diagnosis that
the 0.40-versus-0.333 gap really was miscalibration rather than search noise.
But it changes the targeting decision for only **0.2% of customers** and moves
profit by **$40 on $26,640**. Platt scaling is monotonic, so it cannot reorder
customers and therefore cannot pick a better set to target. It buys a readable
number, not a better campaign.

Methodology, since a calibration curve is easy to draw dishonestly: the Platt
scaler is fitted on out-of-fold predictions, never in-sample, and the "after"
reliability curve is built from a further 5-fold split of those, so the
calibrated line is not self-graded. The translation table uses a scaler fitted
on all the out-of-fold scores, which is appropriate for a display lookup.

The cells were appended at the end rather than inserted, so no existing cell
index moved — the diff is 93 insertions and zero deletions. `CLAUDE.md`'s cell
map records the two new cells and carries an explicit warning that they save
nothing, that their position after the save cells is deliberate, and that
their calibrator should not be wired into the pipeline without reading the
README's note on why the shipped model is uncalibrated.

`README.md`'s calibration section gained a paragraph stating plainly that the
model is *deliberately* left uncalibrated, with the measured justification.
One existing figure was corrected while there: the section said a customer
scored 0.45 "churns about 39% of the time", taken from an empirical bin; the
Platt map in the new appendix prints 0.38 for the same score. Having the
README and the notebook disagree by a point on the same claim was worth
fixing, so the README now says 38% and points at the table.

**Why:** You asked whether real probabilities could be shown without changing
anything — just a plot and a markdown note at the end. That is exactly what
this is, and it is the better trade here: the full calibration option would
have rewritten the artifact, the metadata, the threshold, roughly five
notebook cells, two test files and most of the README's numbers, in exchange
for $40 of profit and a differently-labelled axis.

**Requested or incidental:** Requested — this is the option you described.
Flagged as beyond it: the profit/decision-overlap comparison and the
side-by-side before/after curves go past "an additional plot", and the
`README.md` and `CLAUDE.md` updates were taken on initiative, including the
39% → 38% correction.

**Verification status:** Written, then executed — not assumed. The cell was
run against reconstructed out-of-fold predictions before being inserted, and
then run again by reading its source straight out of the notebook, to confirm
the version actually committed is the version that was tested. Every figure
quoted above and in the README comes from that run. `git status` was checked
immediately after appending to confirm only the notebook changed:
`xgboost_churn_pipeline.pkl`, `model_metadata.json` and
`simulated_new_customers.csv` are untouched, which is the whole premise of
this change. Existing cell indices 26, 29, 35, 40 and 42 were re-checked by
content and are unmoved. The new code cell carries no baked-in outputs
(`execution_count: None`, empty `outputs`), so it will populate on your next
notebook run. Test suite: 118 passing, unaffected — nothing this change
touches is under test. Committed.

---

## 2026-08-22 — Appendix: check whether the three models make the same mistakes

**Files touched:**
- `telco_customer_churn.ipynb` (cell 35 modified; markdown + code cells appended at 45 and 46)
- `README.md`
- `CLAUDE.md`

**What changed:** You raised the point that if the three compared models make
mistakes on different customers, they are catching different signals — and
that this was worth checking. It was, so it is now checked and shown in the
notebook rather than left as a private conclusion.

**The reasoning being tested.** Combining models only pays when they fail on
different rows. Two models at equal accuracy that are wrong about the same
customers are seeing the same thing and there is nothing to pool; two that
are wrong about different customers each hold something the other lacks. The
README's information-ceiling claim rested on three ROC-AUCs landing within
0.002 of each other, which is *circumstantial* — models can reach the same
score while disagreeing completely about who churns.

**The measured answer: they fail on the same people.** Error correlation
`corr(y − p)` between the three models is 0.964 to 0.980. At each model's own
profit-optimal threshold, 65% of all errors are made by all three
simultaneously, with pairwise Jaccard overlap of 0.72 to 0.78. Averaging the
three moves out-of-fold ROC-AUC from 0.8492 to 0.8505 — inside the ~0.019
fold-to-fold standard deviation — and yields $26,780 in profit, which *loses*
to Random Forest alone at $27,000.

So the answer to your question is no, and that is the useful outcome: it turns
the README's information ceiling from an inference into a measurement. Three
structurally different algorithms — boosted trees, bagged trees, a linear
model — failing on the same 65% of customers is what a ceiling looks like when
you measure it. It is also the documented reason there is no stacking here.

A judgement call inside the analysis: each model is judged at its *own*
profit-optimal threshold rather than a shared cutoff. Using one shared
threshold would manufacture disagreement the deployed system would never
see, since each model ships with its own.

**Cell 35 was modified**, which is the only change to an existing cell. It
discarded each tuned estimator after reading its score, so the appendix had
nothing to analyse. It now stores them in a `tuned_estimators` dict. This
changes nothing about the search or the comparison table — it only keeps
objects that were already being built. `CLAUDE.md` records the resulting
dependency: cell 46 needs `tuned_estimators` from cell 35, so running 46 alone
after a kernel restart will not work.

The two new cells were appended at the end, after the save cells, so no
existing index moved and nothing is written to disk.

`README.md`'s model-comparison section gained the error-overlap table and the
explanation, placed directly after the information-ceiling sentence it
supports.

**Why:** You asked whether it was worth checking, and then asked for it to be
visible that the individual mistakes had been investigated — not just the
aggregate scores.

**Requested or incidental:** Requested. Flagged as beyond the literal ask: the
cell-35 modification was necessary to make the analysis possible rather than
separately chosen, and the ensemble/profit comparison, the two-panel figure,
and the `CLAUDE.md` updates were added on initiative.

**Verification status:** Measured, and the cell was executed before being
inserted — which caught a real bug. The first version unpacked
`best_threshold_for`'s return value backwards, printing the threshold in the
profit column ("profit @ 26640.00: $0"). That was fixed and the cell re-run.
After insertion it was executed a second time by reading its source straight
out of the notebook, to confirm the committed version is the tested version.

The Random Forest estimator used is the same one the comparison table reports:
its search was re-run independently and reproduced ROC-AUC 0.8441263938641443
against the table's 0.844126. Figures vary in the last digit between runs
(65.2% vs 65.3% shared errors, 1023 vs 1026 pairwise overlaps) because the
Logistic Regression threshold is itself unstable on a flat curve, as recorded
earlier; the README quotes rounded values that hold across runs.

One number I deliberately did **not** publish: an "oracle" AUC of 0.940 from
letting a referee pick the best model per customer. It uses the labels to
choose, so no realizable combiner can approach it, and quoting it would
overstate what is achievable. It is mentioned here only so nobody recomputes
it and thinks it was missed.

The new code cell carries no baked-in outputs, `xgboost_churn_pipeline.pkl`,
`model_metadata.json` and `simulated_new_customers.csv` are untouched, and the
test suite is unaffected at 118 passing. Committed.

---

## 2026-08-23 — Commit the metadata timestamp from a notebook re-run

**Files touched:**
- `model_metadata.json`

**What changed:** Only `trained_at` and `git_commit`, updated by a notebook
re-execution. `trained_at` moved to 2026-08-23T01:27:47Z and `git_commit` now
records `55aa105`, the commit that was HEAD when the notebook ran.

Nothing else in the file moved: `threshold`, `cv_roc_auc_mean`,
`cv_roc_auc_std`, `hash`, `library_versions`, `feature_columns` and
`dummy_customer_score` are all unchanged, and `xgboost_churn_pipeline.pkl` and
`simulated_new_customers.csv` are byte-identical. By the checklist in
`CLAUDE.md` under "After re-executing the notebook", that is the signal that
the artifact reproduced and nothing downstream needs revisiting.

**Why:** The re-run left the working tree dirty with a pure timestamp change.
Committing it clears that, and — more usefully here — guarantees that every
current version of the notebook and its artifacts is in git, so if the open
editor buffer overwrites the appended appendix cells on save, recovery is a
single `git checkout`.

**Requested or incidental:** Requested — you asked for the outstanding state
to be resolved.

**Verification status:** The full metadata diff was read rather than assumed;
byte-identity of the pickle and sample CSV was confirmed with `git diff`. The
notebook on disk was integrity-checked before committing: valid JSON, 47
cells, no empty cells, both appendix sections present and non-trivial
(cells 43–46 at 943 / 3,535 / 878 / 4,741 characters), and cell 35 still
retains `tuned_estimators`. Test suite: 118 passing, canary matching its pin.

---

## 2026-08-23 — Threshold as a range, and the X_val-only leakage check (item 6, M6)

**Files touched:**
- `telco_customer_churn.ipynb` (markdown + code cells appended at 48 and 49)
- `README.md`
- `CLAUDE.md`
- `AUDIT.md`

**What changed:** An appendix that answers two questions the audit filed
separately but which turn out to be one question.

**Item 6 — how precise is 0.40?** It is the argmax of a profit curve over ~90
candidates, and near an optimum a curve is flat by definition, so an argmax
picks the peak of the noise as much as the peak of the signal. Measured two
independent ways: the per-fold argmax across the same 5 folds is 0.404 ± 0.036
(individual folds 0.40, 0.38, 0.45, 0.43, 0.36), and a 500-resample bootstrap
over customers gives 0.400 ± 0.047 with a 95% interval of [0.29, 0.46]. Every
threshold in **0.35–0.46** is within 1% of peak profit, so the optimum is a
plateau roughly 0.11 wide. Being anywhere in that band costs at most $260 out
of $26,640.

**M6 — is it optimistic from selection leakage?** The threshold comes from
out-of-fold predictions over `X_train`, but the hyperparameters were chosen on
`X_tr`, 80% of those same rows; refitting per fold removes parameter leakage,
not selection leakage. `X_val` is the clean control. Rows the search saw give
0.38 ± 0.051; rows it never saw give 0.43 ± 0.077; the difference is +0.029
with a 95% CI of **[−0.19, +0.18]**, which straddles zero.

**The two are coupled, and that is the real finding.** "Is this threshold
shifted?" cannot be answered before "how much does it wobble on its own." The
audit proposed a ≤0.02 bar for calling M6 negligible, but the estimator's own
resampling spread is ±0.047 — the bar was tighter than the measurement
precision, so no result at that resolution would have meant anything. With the
spread known, the leakage shifts the threshold by about 61% of one standard
deviation, on an interval containing zero: real as a mechanism, unmeasurable
in size at this sample. Nested CV would buy precision the profit curve cannot
use. Documented as checked rather than fixed, which is one of the two options
the audit itself offered.

The `README.md` Results table now reports **0.40 ± 0.05** instead of 0.40, and
a new subsection carries both tables and the reasoning. `CLAUDE.md` records
the plateau and the M6 outcome as facts not to re-derive.

**A note on cell numbering.** Between the last commit and this one you added
your own markdown cell at index 47 ("stacking is basically useless here,
proven by comparing individual results"). It is untouched and is included in
this commit; the new cells landed at 48 and 49 behind it, and the cell map in
`CLAUDE.md` reflects the resulting 50-cell notebook.

**Why:** You asked for worklist item 8 — roadmap item 6 plus finding M6 — by
name.

**Requested or incidental:** Requested. Flagged as beyond the literal ask: the
bootstrap (the audit suggested only per-fold spread), the profit-cost-of-the-
plateau figure, the two-panel figure, and the `README.md`/`CLAUDE.md`/`AUDIT.md`
updates were added on initiative.

**Verification status:** Measured, and the cell was executed before insertion
and again afterwards by reading its source straight out of the notebook, which
is how the index mistake was caught — the first post-insertion run pointed at
cell 48 and hit a syntax error, because your new cell 47 had pushed the code
cell to 49. Re-run correctly at 49.

The profit curve is computed vectorised across all candidate thresholds at
once; the naive loop made the bootstrap take minutes, and the cell now runs in
1.9 s. Every number in the closing narrative is computed rather than
hardcoded — an earlier draft had a hand-written "±0.045" next to a printed
0.047, which is precisely the drift being avoided elsewhere in this project.

`xgboost_churn_pipeline.pkl`, `model_metadata.json` and
`simulated_new_customers.csv` are untouched — nothing here is saved and the
shipped threshold is unchanged at 0.40. Test suite: 118 passing. Committed.

---

## 2026-08-23 — Extract campaign_profit() and unit-test it (C11)

**Files touched:**
- `campaign_profit.py` (created)
- `tests/test_campaign_profit.py` (created)
- `telco_customer_churn.ipynb` (cells 2, 26, 27, 29, 30, 35, 44, 49)
- `README.md`
- `CLAUDE.md`
- `AUDIT.md`

**What changed:** The campaign profit formula —
`TP * success_rate * clv - (TP + FP) * cost` — was written out by hand in
several notebook cells, in three different shapes: a pandas column
assignment, a bare scalar expression, and a loop body. `AUDIT.md` counted
five copies. The real count when I checked was **seven**, because two of the
appendix cells added earlier in this session had each grown their own copy.
That is the defect demonstrating itself: the formula multiplies every time
someone needs it and nobody notices.

It now lives in `campaign_profit.py`, which exposes `campaign_profit()` (the
formula), `break_even_threshold()` (the closed form `cost /
(success_rate * clv)`, which was itself duplicated in four places),
`confusion_at_threshold()`, `profit_curve()` and `best_threshold()`.

Three deliberate design choices. The economics are **keyword-only**:
`campaign_profit(tp, fp, 20, 200, 0.3)` with `clv` and `cost` transposed would
run happily and be wrong by a factor of a hundred, and the whole point of
extracting the formula is to remove that class of error, so positional
passing raises `TypeError`. Nonsense economics are rejected rather than
silently propagated — a negative cost or a `success_rate` of 1.5 raises
`ValueError`. And ties in `best_threshold()` resolve to the **lowest**
threshold: the profit curve is a plateau roughly 0.11 wide, so ties are
common, and first-wins needed to be a documented rule rather than an accident
of `argmax`.

`campaign_profit()` returns a pandas Series when given one, rather than
coercing everything to numpy. Cell 26 assigns the result straight back onto a
DataFrame, and keeping the index means that assignment aligns by label
instead of relying on positional order. Plain lists and tuples *are* coerced,
since they cannot be multiplied by a float.

`tests/test_campaign_profit.py` adds 23 tests: the formula against
hand-computed values, against the README's published $6,660 (so the two
cannot drift apart), the elementwise contract across lists, arrays and
Series, keyword-only enforcement, input validation, the break-even point
proven to be the indifference point, the clv/success_rate product identity
the sensitivity sweep found empirically, `>=` at the boundary, tie-breaking,
and edge cases for a perfect model and an all-negative dataset.

Eight notebook cells now import and call it instead of retyping.

**Why:** You asked for worklist item 9 / finding C11 by name.

**Requested or incidental:** Requested. Flagged as beyond the literal ask: the
audit asked only for `campaign_profit()`, while this also extracts
`break_even_threshold`, `profit_curve`, `best_threshold` and
`confusion_at_threshold` — they were duplicated too, and leaving them would
have half-fixed the problem. Rewiring the notebook was also beyond "extract
and unit-test", but extracting a function nothing calls would not have closed
C11. The `README.md`, `CLAUDE.md` and `AUDIT.md` updates were on initiative.

**Verification status:** Equivalence was proved **before** the notebook was
touched, not after. Each of the existing expressions was run side by side
against the new function on the real out-of-fold predictions: the pandas
Series form, the scalar form that produces the published $6,660, the
`best_threshold_for` loop over the real OOF vector, all fifteen rows of the
sensitivity sweep, the vectorised profit curve, and the closed form. Every
one matched exactly.

After rewiring, the two appendix cells that could be executed standalone were
re-run from the notebook source and produced byte-identical output — cell 49
still reports 0.404 ± 0.036 per-fold and the 0.35–0.46 plateau; cell 46 still
reports 64.5% shared errors and $26,640 / $27,000 / $26,220 / $26,780. Cell 2
was extracted and executed to confirm the new import works.

A test caught a real defect during development: the elementwise test failed
on plain Python lists, because a list cannot be multiplied by a float. The
function was fixed to coerce sequences rather than the test being weakened,
and Series passthrough was then verified explicitly to confirm the fix had
not broken the pandas path.

Suite: **141 passing**, up from 118. `telco_model.py` still scores the sample
file and flags the same 15 of 50. **Cells 26, 30 and 35 were not executed** —
they need a full notebook run — so their correctness rests on the
expression-level equivalence checks above rather than on observed output.
`xgboost_churn_pipeline.pkl` and `model_metadata.json` are untouched.
Committed.

---

## 2026-08-23 — Remove documentation cross-references from code comments

**Files touched:**
- `telco_customer_churn.ipynb` (cells 35, 46, 49)
- `tests/test_integration.py`
- `tests/test_campaign_profit.py`

**What changed:** Comments and docstrings that pointed at other documents —
`AUDIT.md` finding codes like M6 and M7, "roadmap item 6", and references to
the README — were rewritten to explain themselves instead.

Twelve places in total. In the notebook: cell 35 dropped a parenthetical
about the README's Results table; cell 46's opening comment and closing
printout stopped attributing the information-ceiling reading to the README
and simply state it; cell 49 had the heaviest concentration, with six
mentions of "M6" and "roadmap item 6" across its header comment, a section
divider, and two printed lines. Its header was also condensed, and the two
questions it answers are now labelled PRECISION and BIAS rather than by
finding codes. In the tests, `test_integration.py`'s seed-independence
docstring no longer opens with "Locks in the M7 fix", and
`test_campaign_profit.py` no longer describes the $6,660 figure as belonging
to the README.

The substance is unchanged in every case — each comment still explains the
same thing, in some cases more briefly. What is gone is the requirement to go
and read a second file to understand the first.

**Why:** You asked for it. The reasoning holds up: a code comment saying
"see AUDIT.md M6" is useless to anyone without that file, and `AUDIT.md` in
particular is gitignored, so a reader who clones this repository would find
references to a document that does not exist for them. A comment should carry
its own explanation.

**Requested or incidental:** Requested. One thing beyond the literal ask:
cell 49's header comment was shortened while being de-referenced, since it
had grown to nineteen lines.

**Verification status:** After the edits, the notebook and all Python files
were re-scanned for the same patterns (`AUDIT`, `M<digit>`, `C1<digit>`,
`README`, `CHANGELOG`, `CLAUDE.md`, `roadmap`) and come back clean. Cells 46
and 49 were executed from the notebook source and produce unchanged numbers —
cell 49 still reports 0.404 ± 0.036 per-fold, the 0.38/0.43 leakage split and
the [−0.19, +0.18] interval; cell 46 still reports 65.2% shared errors. Test
suite: 141 passing.

A note on scope: `CLAUDE.md` and this file still reference `AUDIT.md` finding
codes. That is deliberate — they are documentation about the project's
history, where a cross-reference is the point, rather than code that has to
stand on its own. Only comments inside code were changed.

---

## 2026-08-23 — Refresh the Logistic Regression row after a full notebook re-execution

**Files touched:** `README.md`

**What changed:** The notebook was re-executed end to end (all 39 code cells,
execution counts 1 through 39 with no gaps, so this was a genuine clean run
from a fresh kernel rather than a few cells re-run in place). That run rewrote
`model_metadata.json` and the stored cell outputs. Comparing the freshly
produced outputs against the figures the README publishes turned up exactly
one disagreement, in the Logistic Regression row of the model-comparison
table. The README carried ROC-AUC 0.843892, std 0.018902, best threshold 0.62
and accuracy 0.7867; the actual run produced 0.843903, 0.018882, 0.58 and
0.7758. Its profit was $26,200 in both, and the ordering of the three models
was unchanged.

Four places were corrected. The comparison table row itself. The sentence
further up that lists all three ROC-AUC figures inline, which quoted the old
0.843892. The paragraph about the threshold split, which asserted that
Logistic Regression's optimum (0.62) sat above Random Forest's (0.58) — in
this run both models land on 0.58, so the sentence now says so instead of
naming two different numbers. And the italic footnote under the table, which
was rewritten more substantially: it used to describe the row as having
*moved* because the search switched from scikit-learn's deprecated `penalty`
argument to `l1_ratio`, presenting 0.58 → 0.62 as a consequence of that
migration. This run lands back on 0.58 with the `l1_ratio` code in place,
which contradicts that framing. The real explanation is the one already
recorded in the project notes: this model's ROC-AUC surface is flat, so the
winning `C` slides between near-tied random draws from run to run and the
threshold follows it. The footnote now says that instead, and gives the
observed ranges (threshold 0.58 or 0.62, accuracy 0.7758 to 0.7867, ROC-AUC
0.843891 to 0.843903) rather than presenting one run's values as a permanent
before-and-after.

**Why:** The project's own post-re-execution checklist calls for comparing the
README against the notebook's real outputs, and singles out both the Logistic
Regression row and the threshold-split prose as the two places that have gone
stale this way before. Both had. Since the next phase of work is
containerisation, the published figures needed to match the artifact the
container will ship.

**Requested or incidental:** Incidental. What was asked for was a verification
that three specific numbers survived the extraction of `campaign_profit()` —
cell 26's threshold and peak profit, cell 30's test-set profit, and cell 35's
three profit figures. All six of those matched exactly. The README correction
is separate work that the comparison surfaced along the way.

**Verification status:** Executed and checked, not merely reasoned about.
`model_metadata.json` moved only in `trained_at` and `git_commit`, which is
the project's own signal that the artifact reproduced and the model did not
change. No notebook cell's *source* changed — only stored outputs — and cells
26 and 30 reproduced byte-identically, which is the strongest available
confirmation that rewiring them onto `campaign_profit()` altered nothing:
threshold 0.40, peak OOF profit $26,640, test-set profit $6,660. Cell 35 gave
26,640 / 27,000 / 26,200 as expected. The two appendix cells whose outputs
also changed were checked against the README and still agree with it — cell 46
on error overlap (correlation 0.964–0.980, 64.6% shared errors, Jaccard
0.72–0.78, averaging at $26,780 versus Random Forest's $27,000) and cell 49 on
threshold precision (0.400 ± 0.047, the 0.35–0.46 plateau, the +0.029 leakage
shift with its interval straddling zero). Test suite: 141 passing in ~2s. Not
committed yet; the re-executed notebook and the rewritten metadata are also
still uncommitted in the working tree.

---

## 2026-08-23 — Correct an order-of-magnitude claim in the Logistic Regression footnote

**Files touched:** `README.md`

**What changed:** Re-checking the previous entry's edit found an arithmetic
error I introduced in it. The original footnote described a single 5e-6 shift
in Logistic Regression's ROC-AUC and called it "four orders of magnitude below
this model's own 0.019 fold-to-fold std" — 0.019 divided by 5e-6 is about
3,800, so "four" was a defensible rounding of 3.6. When I rewrote that
footnote to give a *range* of observed values (0.843891 to 0.843903) instead
of one before-and-after pair, the quantity being compared changed: the span is
now 1.2e-5, and 0.019 divided by that is about 1,583, which is 3.2 orders of
magnitude. I had carried the word "four" across unchanged. It now reads "a
spread three orders of magnitude below its own 0.019 fold-to-fold std."

Two lines were also re-wrapped to the file's ~80-column prose width, in that
same footnote and in the threshold-split paragraph, where the previous edit
had left lines running long.

**Why:** The number was simply wrong after the rewrite, and this document's
whole argument style rests on stated magnitudes being checkable. An
overstatement of the noise floor by a factor of ten is exactly the kind of
claim a reader would be right to test.

**Requested or incidental:** Incidental in origin — nobody asked for this
specific fix — but it came out of an explicitly requested re-check of the
previous turn's work.

**Verification status:** The ratio was recomputed rather than estimated
(0.019 / 1.2e-5 = 1583, log10 = 3.20). The rest of the README was audited
against the notebook's stored outputs in the same pass, and everything else
agrees: the model-comparison row matches cell 35 exactly (0.843903 / 0.018882
/ 0.58 / 0.7758 / 26,200), the sensitivity sweep matches all fifteen rows of
cell 27, the calibration table matches cell 29 (Brier 0.1342, +0.022 all bins,
+0.051 in the decision band, +0.046 mean offset), the precision and leakage
tables match cell 49, and the error-overlap table matches cell 46. One
apparent discrepancy was checked and is not one: the README says a score of
0.45 corresponds to about 38% real risk while cell 29's prose says 39%. The
README is citing cell 44's Platt-calibrated lookup table, which does map 0.45
to 0.38, and the surrounding sentence points the reader at that appendix; 39%
is cell 29's coarser bin-gap estimate. Both are right about their own source.
Also re-confirmed from the notebook rather than from memory: cells 26 and 30
have outputs byte-identical to commit e938061, no cell's source changed, and
`model_metadata.json` differs only in `trained_at` and `git_commit`. Test
suite: 141 passing. Committed.

---

## 2026-08-23 — Split dependencies into runtime / dev / notebook groups

**Files touched:** `pyproject.toml`, `uv.lock`, `README.md`

**What changed:** `pyproject.toml` had a single flat list of fifteen packages
covering everything the project has ever needed. It is now three sets.
`[project.dependencies]` holds only what is required to *serve* a prediction —
fastapi, uvicorn, joblib, numpy, pandas, scikit-learn, xgboost. The `dev`
group keeps pytest and httpx, and is installed by default by `uv sync`, which
is what CI relies on. A new `notebook` group holds jupyter, kagglehub,
matplotlib, seaborn, shap and scipy, and is *not* installed by default;
re-training now needs `uv sync --group notebook`.

Three packages were deleted outright: `optuna`, `lightgbm` and `pyarrow`.
Before removing them I checked they were genuinely unused rather than trusting
the earlier note that said so — no `import` of any of the three exists in any
`.py` file or in any notebook cell. `pyarrow` appears once in the repository,
as a word inside a test docstring describing pyarrow-backed strings; the test
itself uses pandas' own `StringDtype`. I also confirmed pyarrow is not arriving
as a transitive requirement (pandas 3.0.5 requires only numpy and
python-dateutil, and pyarrow's `Required-by` is empty), so removing it removes
it for real.

`scipy` was *added* to the notebook group. It is the opposite defect to the
one this item was about: the notebook does `from scipy.stats import randint,
uniform`, but scipy was never declared anywhere — it happened to be installed
because scikit-learn depends on it. Declaring a direct import is the same
principle as deleting a declaration nothing imports.

`uv.lock` was regenerated, since CI's `uv sync --frozen` fails when the lock
and `pyproject.toml` disagree. Dropping those three packages also removed five
transitive dependencies that came with optuna alone — alembic, colorlog,
greenlet, mako and sqlalchemy, i.e. a database migration stack that was being
installed to run a test suite.

The README gained an "Installing" block at the top of "Running it" explaining
the two commands and why the default set is small, its repo-structure listing
now describes the split, and its test count was corrected.

**Why:** This is preparation for the Dockerfile. An image installs whatever
`[project.dependencies]` lists, so under the old layout a container whose only
job is loading a pickle and answering HTTP would have shipped Jupyter, SHAP
and matplotlib. Doing the split first means the Dockerfile gets written once
against a dependency list that already means something, instead of being
written and then rewritten.

**Requested or incidental:** Requested — this is the first half of worklist
item 11. Adding `scipy` was not asked for and is flagged as incidental; it is
a one-line addition of an already-installed package, made because the audit of
"declared but unused" turned up its mirror image and leaving it seemed worse
than fixing it.

**Verification status:** Measured, not assumed. The effect was checked by
building throwaway virtualenvs via `UV_PROJECT_ENVIRONMENT` rather than by
re-syncing the working environment, so nothing was destroyed to find out. What
CI will now install went from **142 packages to 32**, and from **1.4 GB to
675 MB**. The full suite passes in that minimal environment — 153 tests, all
green, with no notebook package present — which is the real proof that nothing
in the runtime or test path depended on the packages that moved. `uv sync
--frozen --group notebook` was then run in the same throwaway environment and
every notebook import (matplotlib, seaborn, shap, kagglehub, scipy.stats)
resolves, so training still works. `uv export`, which
`verify_version_check.sh` depends on, still succeeds and still contains all
five libraries that script needs. Finally the real development environment was
re-synced with `--group notebook`, which removed exactly the eight dead
packages and nothing else. Committed.

---

## 2026-08-23 — Add the CI version gate the runtime docstring had been promising

**Files touched:** `check_model_environment.py` (new),
`tests/test_check_model_environment.py` (new), `.github/workflows/tests.yml`,
`config.py`, `README.md`

**What changed:** `config.validate_environment_versions()` compares installed
library versions against the ones recorded in `model_metadata.json` and only
*warns*. Its reasoning is sound and unchanged: crashing a live API over a
patch bump trades a risk that the pickle might misbehave for a certainty that
the service is down. But the docstring justified that leniency by saying "A
hard gate belongs in CI, checked against the artifact before it's deployed" —
and no such gate existed. The control was excusing its own weakness by
pointing at something nobody had built. The README repeated the same promise.

`check_model_environment.py` is that gate. It reads `library_versions` from the
artifact metadata, compares against the environment, prints every mismatch,
and exits non-zero. The interesting part is where it deliberately *differs*
from the runtime check: at runtime, unreadable metadata, a missing
`library_versions` block, or a library the code doesn't track are all reasons
to shrug and keep serving. In the gate they are all failures, because CI has
no uptime to protect — only the question of whether this environment matches
the artifact, and "can't tell" is not a yes.

It resolves versions through `config._current_library_versions()`, the same
function the running service uses, rather than keeping its own list. That is
the point rather than an implementation detail: a gate that checks something
different from what production checks can pass while production disagrees.
For libraries that function does not track, it falls back to
`importlib.metadata.version()` so anything recorded in the artifact still gets
verified instead of silently skipped.

A step was added to `tests.yml` that runs it, placed *before* the test suite
on purpose: a version skew would otherwise surface as a confusing pinned-
prediction failure in `test_artifact.py` rather than as the version problem it
actually is. `config.py`'s docstring and the README's "Version drift"
paragraph were both updated to describe the gate that now exists instead of
one that doesn't.

**Why:** Second half of worklist item 11, and a prerequisite for the
Dockerfile. Once an image pins its library set, this check stops being the
primary defence against a version-drifted artifact and becomes a cheap
assertion that the image is what it is believed to be — but that only holds if
the strict check exists somewhere.

**Requested or incidental:** The script and the CI step were requested. The
test file was not, and is flagged as incidental. It was written because a gate
that cannot fail is indistinguishable from no gate, which is precisely the
defect being closed here; shipping an unverified gate would have recreated the
problem in a new place.

**Verification status:** Executed. Every failure path was driven with a
tampered metadata file before the tests were written: a version mismatch, a
library recorded but not installed, a library the runtime doesn't track (which
correctly exercised the importlib fallback and caught a deliberately wrong
fastapi version), a missing `library_versions` block, a `library_versions`
that is a list rather than an object, a corrupt JSON file and an absent file.
All seven produce a non-empty problem list; the real committed metadata
produces an empty one. The 12 new tests cover those paths plus `main()`'s exit
codes and the requirement that all mismatches are reported at once rather than
one per build. Suite is now 153 passing, in both the full development
environment and the minimal environment CI will actually use. The workflow
YAML was parsed to confirm the five steps are in the intended order. What has
*not* been verified is a real GitHub Actions run — that happens on push.
Committed.

---

## 2026-08-23 — Update CLAUDE.md for the dependency split and the new version gate

**Files touched:** `CLAUDE.md`

**What changed:** Three edits. The convention that read "`optuna`,
`lightgbm`, `pyarrow` are declared in `pyproject.toml` and used nowhere" was
false as of this session, so it now records that they were removed while
keeping the part that still matters — that the tuner is `RandomizedSearchCV`
and not Optuna, which is the actual trap that note existed to prevent. A new
convention describes the three-way dependency split and warns against adding
a training-only package to the runtime list. The CI convention now mentions
the gate as well as the test suite, and a new bullet spells out that two
version checks exist with deliberately opposite failure behaviour, and that
both must keep resolving versions through
`config._current_library_versions()`. The layout table gained a row for
`check_model_environment.py`, and its test counts moved from 141 tests across
8 files to 153 across 9.

**Why:** The file is the first thing read in a new session, and a stale
convention there is worse than no convention — the removed-packages note
would have actively misled the next reader into thinking the cleanup hadn't
happened.

**Requested or incidental:** Incidental. Nobody asked for it; it is required
maintenance following the two changes above, and this file's own rule makes an
entry for editing it mandatory.

**Verification status:** Prose only, no executable claims. The counts in it
were taken from an actual test run (153 passing) and an actual directory
listing (9 files in `tests/`), not estimated. Committed.

---

## 2026-08-23 — Report PR-AUC alongside ROC-AUC

**Files touched:** `telco_customer_churn.ipynb` (cells 2, 25, 31, 33, 35, 40,
46), `README.md`, `CLAUDE.md`

**What changed:** ROC-AUC was the only ranking metric the project reported.
With roughly 26% churn that is a soft measure: ROC-AUC gives credit for true
negatives, and since 74% of these customers do not churn it stays comfortable
even when the ranking of actual churners gets worse. PR-AUC (average
precision) ignores true negatives entirely, so it tracks only the class the
retention campaign spends money on. `average_precision_score` is now computed
everywhere `roc_auc_score` already was.

Cell 2 imports the function. Cell 25 adds a 5-fold CV PR-AUC next to the
existing CV ROC-AUC. Cell 31 prints test PR-AUC under test ROC-AUC. Cell 33,
which already drew a precision-recall curve but reported no number, now shows
the average precision in its title and draws the no-skill baseline as a dashed
line. Cell 35 gains a `PR-AUC (OOF)` column in the model-comparison table.
Cell 40 records `cv_pr_auc_mean`, `cv_pr_auc_std` and `churn_rate_train` in
`model_metadata.json`. Cell 46's appendix prints PR-AUC beside OOF AUC for
each model and for their average.

Two things were deliberately *not* done. The searches still use
`scoring='roc_auc'`; PR-AUC is reported, not optimised, because changing the
selection metric would change which model ships, and that is a different
decision from measuring one more thing. And nothing reads the new metadata
keys at runtime — they are provenance for the README, so no validator or
consumer changed.

Everywhere PR-AUC appears it is stated against its baseline. This matters more
than it might look: PR-AUC's floor is the positive rate, not 0.5, so 0.6610
read cold looks mediocre when it is in fact 2.50x a random ranking. The README
now says so in the Results table, and CLAUDE.md records it so it is not
misread later.

**Why:** Requested. It was also already written down as a known limitation in
the README's own list, so that bullet was deleted — the limitation no longer
exists.

**Requested or incidental:** Requested. Removing the now-false limitation
bullet and recording the figures in CLAUDE.md are incidental follow-on edits;
CLAUDE.md's own rule requires this entry to name that edit explicitly.

**Verification status:** The numbers published are measured, but they were
measured by *reconstruction*, not by re-running the notebook — the edited
cells have not been executed, exactly as with the earlier `campaign_profit()`
extraction. A script rebuilt the splits from the cached dataset using the same
seeds, loaded the committed `.pkl`, and recomputed everything. Its fidelity
was established against four numbers the project already publishes, all of
which it reproduced: test ROC-AUC 0.8441, CV ROC-AUC 0.849141 ± 0.017474
(matching `model_metadata.json` to every recorded digit), Random Forest's CV
ROC-AUC 0.844126 (matching cell 35 exactly), and the OOF ROC-AUCs of all three
models (0.8492 / 0.8466 / 0.8472, matching cell 46). Only the Logistic
Regression CV figure differed, 0.843901 against 0.843903, which is that row's
known run-to-run instability.

The measured results: test PR-AUC 0.660997 against a 0.264769 baseline
(2.497x); CV PR-AUC 0.664294 ± 0.037438; OOF PR-AUC 0.660301 for XGBoost,
0.654806 for Logistic Regression, 0.653229 for Random Forest. Worth flagging
one finding rather than burying it: PR-AUC *reverses* Random Forest and
Logistic Regression relative to ROC-AUC. The gap is 0.0016 — a twentieth of
PR-AUC's own fold-to-fold std — so it is noise and changes nothing, and
XGBoost leads on both metrics regardless. But it is a clean illustration of
why the second metric was worth adding, and the README says so.

All seven edited cells were checked to parse (`ast.parse`), the notebook still
has its 50 cells, and the diff touches source only — no stored output was
altered. What has *not* been verified is the cells actually executing: cell 40
now references `cv_pr_auc`, which cell 25 defines, and that link only proves
itself in a real top-to-bottom run. `model_metadata.json` therefore does not
yet contain the new keys. Test suite: 153 passing. Committed.

---

## 2026-08-23 — make_preprocessor() factory, SHAP findings in the README, and the remaining cosmetic defects

**Files touched:** `telco_customer_churn.ipynb` (cells 11, 12, 14, 18, 20, 26,
30, 35, 40), `api.py`, `config.py`, `tests/conftest.py` (new),
`tests/test_api.py`, `tests/test_config.py`, `tests/test_telco_model.py`,
`simulated_new_customers.csv`, `README.md`, `CLAUDE.md`

**What changed:** The last batch of known defects, worked through one at a
time.

*The shared preprocessor.* Cell 12 defined one `ColumnTransformer` and cells
14, 18, 22 and 35 all embedded the same object. `Pipeline.fit()` fits its
steps in place rather than cloning them, so that was one mutable object with
four owners — fitting any pipeline silently re-fits the scaler and encoder the
others hold. It produced no wrong number today, because the search and
cross-validation utilities clone internally and every pipeline is refit before
use. It was live purely as a trap: fit one pipeline on one slice, predict from
another without refitting, and the answer comes from the wrong scaler with no
error. Cell 12 is now a `make_preprocessor()` factory and each pipeline calls
it.

*The API's rounded probability.* `/predict` compared the raw probability
against the threshold but reported it rounded to four places, so a score of
0.39995 produced a response reading `churn_probability: 0.4`,
`threshold_used: 0.4`, `target_for_retention: false` — self-contradictory to
anyone reading it. The obvious repair is to round once and then compare, and
that is what the defect list recommended. **That fix would have been wrong.**
`telco_model.py` compares raw probabilities, so rounding before the comparison
makes the API flag customers the batch script does not — turning a cosmetic
inconsistency into a silent divergence between the two consumers, which is the
one thing this project's invariants forbid. Fixed the other way instead: the
response now reports the unrounded probability, so the number shown is the
number decided on *and* both paths still agree. Five new parametrized tests
pin the boundary.

*The 503 guard* checked `model` but not `threshold`, so a loaded model with an
unset threshold gave `probability >= None`, a TypeError, and a 500 instead of
"not ready yet". It now checks both.

*Test fakes.* `DummyModel` was duplicated verbatim in two test files with a
comment noting the duplication. It now lives in a new `tests/conftest.py`
alongside `_FakeJoblib`. The monkeypatching also changed: the tests patched
`joblib.load` on the shared `joblib` module — `api.joblib is
telco_model.joblib is joblib`, all one object, verified — so the patch reached
every importer in the process. They now replace the module *reference* inside
the one module under test.

*Two numeric-hygiene fixes in the notebook.* The fine threshold grid used
`np.arange(fine_low, fine_high, 0.01)`, which the defect list called half-open.
It is worse than that: it is inconsistent. For the current window (0.35, 0.45)
floating-point error happens to include the endpoint and yield 11 points; for
(0.55, 0.65) it yields 10 and silently drops the top of the intended symmetric
band. The grid is now built inclusively and rounded to 2dp, which gives 11
points for every window and is identical to today's values for the current one.
Separately, cell 30 matched a threshold with float `==`, safe only because both
sides came from the same array; it now uses `np.isclose`, which is what makes
it survive a round-trip through the metadata JSON.

*`feature_schema_version` was written and never read* — an intention, not a
mechanism. `config.SUPPORTED_FEATURE_SCHEMA_VERSION` now declares what the code
implements and `validate_feature_schema()` refuses to start on a mismatch. This
covers the case the column comparison structurally cannot see: same column
names, different meanings, after a corrected formula or a changed unit. An
artifact with no version declared warns and degrades to the column check, so
older artifacts still load.

*`config.py` imported scikit-learn and XGBoost at module level* purely to read
two version strings, costing 559ms and 33ms of a 771ms `import config` paid by
every consumer. It now reads an already-imported module's `__version__` when
there is one and falls back to installed-distribution metadata otherwise. Both
halves matter: the module attribute is the copy that will actually unpickle the
artifact and wins if a shadowed install makes the two disagree, while the
fallback is what removes the import. `import config` dropped to 226ms.

*The sample CSV shipped 25 pre-engineered columns* rather than the 19 raw ones
`telco_model.py`'s contract describes, because cell 11 overwrote `X_test` with
its engineered form before cell 40 sampled it. The notebook now keeps
`X_test_raw`, and the committed CSV was regenerated. It went unnoticed because
`engineer_features()` is idempotent, so the wrong file worked.

*`n_jobs=3` in cell 20* against `-1` everywhere else — a leftover, now `-1`.

*The Interpretability section* was three lines describing the method and
reporting no result, while the notebook produced a full beeswarm. It now
carries the mean |SHAP| table for the top eight features and three findings:
contract type dominates at 0.589, more than twice the next feature; the
engineered `contractvstenure` ranks second overall, above raw `tenure`, which
is the clearest evidence any engineered feature earned its place; and
`onlinesecurity = No` plus `techsupport = No` together outweigh `tenure`,
which matters because unlike contract or tenure those are things the business
can hand someone — a concrete alternative to the flat discount the campaign
currently models. That last point is flagged in the text as a correlational
hypothesis worth an A/B test, not a finding.

**Why:** Requested — the final worklist item before Docker.

**Requested or incidental:** All requested. The new tests (five boundary tests,
a 503 test, three schema-version tests) were not itemised in the request and
are flagged as incidental; each one pins a behaviour changed here that nothing
else asserted.

**Verification status:** Test suite 162 passing, up from 153. The version gate
still passes. Every claim above was measured rather than assumed: the shared
`joblib` identity was confirmed at the interpreter (`api.joblib is
telco_model.joblib is joblib` → True); the `np.arange` inconsistency was
reproduced across five windows before and after the fix; the import cost was
measured with `-X importtime` before and after; the CSV was regenerated and
`telco_model.py` run end to end against it, flagging 15 of 50 customers; the
SHAP figures come from `TreeExplainer` on the committed artifact over the real
test split. The rounding divergence was demonstrated numerically before being
fixed — at p=0.39995 and p=0.39996 the recommended fix disagrees with the batch
path, at p=0.399949 it does not.

Two caveats. The notebook cells changed here have **not** been executed —
`make_preprocessor()`, the grid change, the `np.isclose` change and the
`X_test_raw` change all need a full run to confirm, and the CSV was regenerated
by a separate script that reproduces cell 40's sampling rather than by the
notebook itself. Separately, the notebook *was* re-run by the user partway
through this session, which is what populated `model_metadata.json` with the
PR-AUC keys added earlier today; that run confirmed the previous entry's
reconstruction exactly (`cv_pr_auc_mean` 0.6642944952307156 against a computed
0.664294) and confirmed every PR-AUC figure the README publishes. It also
moved the Logistic Regression row again — ROC-AUC 0.843903 → 0.843899, std
0.018882 → 0.018893, accuracy 0.7758 → 0.7760, profit $26,200 → $26,220 — and
the README was resynced to it, including a sentence that had claimed that row's
profit never moves. Committed.

---

## 2026-08-23 — Corrections found while re-checking the item-12 work

**Files touched:** `README.md`, `telco_customer_churn.ipynb` (cell 30)

**What changed:** A review pass over the previous entry's work turned up four
things, three of them mistakes I had made.

*The README still said 153 tests.* The suite is 162. CLAUDE.md had been
updated and the README had not.

*`tests/conftest.py` was missing from the README's repo-structure listing,*
despite being a new file that entry introduced.

*An overstated claim in cell 30's comment.* I had written that comparing
thresholds with `==` "breaks the moment either value is round-tripped through
JSON". That is not true for the value actually in play: `np.arange(0.35, 0.45,
0.01)` lands on exactly `0.4`, which survives a JSON round-trip unchanged, so
the old `==` was never broken here. The underlying concern is real, but the
accurate version is narrower and more interesting: across the 19 possible fine
windows, 17 contain values that are *not* exactly their two-decimal form —
`0.41` arrives as `0.41000000000000003` — and the current window is one of
them. `0.40` simply happens to be one of the exact values. So the fragility is
real but conditional on which threshold wins, and `.iloc[0]` on an empty match
would raise IndexError rather than return a wrong row. The comment now says
that, and notes that the `np.round()` added to the grid removes the problem at
its source, leaving `np.isclose` as a second line rather than the only one.

*The README's example API response was stale in format.* It showed
`"churn_probability": 0.81` marked "illustrative", which implied a
two-decimal response that the C3 fix no longer produces. It now shows the real
response for the payload in the curl example directly above it
(`0.7443000078201294`), with a sentence explaining why the value is unrounded
— that the decision is evaluated at full precision and the batch script
compares the same way.

**Why:** The previous entry's work was large and much of it was reasoned about
rather than executed. Asked to re-check it, I did, and these are what the check
found.

**Requested or incidental:** The re-check was requested. All four edits are
corrections to my own prior work rather than new scope.

**Verification status:** This pass also executed what the previous entry had
only reasoned about, which is the more important outcome. The real notebook
cell sources for 11, 12, 14, 15, 16, 17, 18 and 20 were compiled and run
against the real dataset, and their numbers match the notebook's stored
outputs exactly: cell 16 ROC-AUC 0.8356, cell 18 ROC-AUC 0.8381, cell 20 mean
ROC-AUC 0.8198 with std 0.0207. That last one is the C14 check — it reproduces
with `n_jobs=-1` where the stored output came from `n_jobs=3`, confirming the
change is numerically neutral. The M8 property was then asserted directly on
the live objects: `model_pipeline` and `model_pipeline_tuned` no longer share a
preprocessor instance. Cell 26's regenerated grid was run against the saved
out-of-fold predictions and produces the identical 11 values, the same 0.40
threshold and the same $26,640 peak; cell 30's `np.isclose` lookup returns the
same row. An AST scan confirms no bare `preprocessor` name is loaded anywhere
in the notebook, which would have been a NameError now that cell 12 defines a
function instead. Every published README figure was re-matched against the
notebook's stored outputs. The batch script runs (15 of 50 flagged), the
version gate passes, and the suite is 162 passing both in the development
environment and in a from-scratch CI-minimal one.

Still unexecuted: cells 22, 26, 30, 35 and 40 in a real top-to-bottom notebook
run. Cells 26 and 30 were verified by executing their logic against saved
predictions rather than in the notebook itself, and the regenerated sample CSV
came from a script reproducing cell 40's sampling rather than from cell 40.
Committed.

---

## 2026-08-23 — Second review pass: a wrong SHAP claim and three imprecise ones

**Files touched:** `README.md`, `config.py`, `CLAUDE.md`

**What changed:** Asked to check the item-12 work again after the first pass
found four problems, I did, and found four more. One is a substantive error.

*The engineered-features claim in the Interpretability section was wrong.* I
had written that `contractvstenure` ranks second and that "the remaining
engineered features (`total_services`, `family_tie`, `charge_change_ratio`)
land far lower". That named three of the five remaining features, omitted
`average_monthly_charges` and `is_auto_pay` entirely, and characterised the
group with a vague phrase I had not actually checked. The real distribution is
far more interesting and is now in the README as a table of all six with their
ranks out of 51: `contractvstenure` 2nd at 0.2821, `average_monthly_charges`
10th at 0.1092 — which is not "far lower" by any reading — `charge_change_ratio`
17th, `total_services` 20th, and then `is_auto_pay` and `family_tie` at ranks
50 and 51 with mean |SHAP| of **exactly zero**. Not rounded to zero: their SHAP
values are 0.0 for all 1,405 test rows, and inspecting the booster confirms it
contains no split on either feature. Two of the six engineered features are
computed on every API request and every batch row and contribute nothing to any
prediction. The section now says so, notes the six together carry 15.5% of
total attribution with almost all of it from one feature, and observes that
`is_auto_pay` is the feature whose `.str` handling `feature_engineering_telco.py`
guards most carefully — that guard protects the column contract, not accuracy.

*The campaign description was over-specific.* I had called the modelled
intervention "a flat $20 discount offer". The notebook deliberately leaves it
open — its own comment says "a discount/incentive, or agent outreach time" —
so the README now quotes that rather than inventing a discount, and the
follow-on sentence no longer contrasts against "a price cut".

*The documented test-suite runtime was false precision.* CLAUDE.md said ~3.8 s
and the README ~4 s. On this machine the suite ran at ~2 s early in the session
and ~8.8 s later, consistently. That was worth checking rather than assuming,
so it was: the pre-item-12 commit was checked out into a separate worktree and
runs at ~8.6 s too, which rules out a regression from this work and points at
machine load. Since no single number is reproducible, both files now say "a few
seconds" and "162 tests" rather than quoting one.

*A misleading figure in a docstring.* `_current_library_versions` said the
scikit-learn and XGBoost imports "cost 559ms and 33ms of a 771ms import
config", which invites the reader to expect a 592ms saving. The measured
end-to-end change is 771ms to 226ms. The docstring now states that outcome
too.

**Why:** The item-12 batch was large and much of it was written faster than it
was checked. Two review passes have now found eight issues between them, which
is the argument for the passes rather than against them.

**Requested or incidental:** The review was requested; all four edits are
corrections to my own prior work.

**Verification status:** Everything asserted above was executed. The SHAP
figures were recomputed from scratch in a second independent run and all eight
published rows reproduce to four decimals; the zeros were then confirmed two
ways, by `max|shap|` over all 1,405 rows and by checking the booster's split
list. The new 503 test was shown to have teeth by reproducing the pre-fix
failure directly (`'>=' not supported between instances of 'float' and
'NoneType'`). `TestClient(app)` without a context manager was confirmed not to
run the lifespan, which is what the same test depends on. An AST scan for
unused imports across all six source modules comes back clean. Every relative
link in the README resolves. The suite is 162 passing, the version gate passes,
the batch script runs (15 of 50 flagged), the notebook still has 50 cells and
parses clean.

The unexecuted set is unchanged from the previous entry: notebook cells 22, 26,
30, 35 and 40 have not been run inside a real top-to-bottom execution, though
26 and 30 were verified by executing their logic against saved out-of-fold
predictions. Committed.

---

## 2026-08-23 — Notebook re-executed: item-12's unexecuted cells confirmed

**Files touched:** `README.md` (plus `model_metadata.json` and
`telco_customer_churn.ipynb`, rewritten by the user's notebook run)

**What changed:** The user re-ran the notebook, which is what the last three
entries had been waiting on. Every cell item 12 changed but could not execute
has now executed, and the results resolve the open question in those entries.

`model_metadata.json` moved only in `trained_at` and `git_commit`. Everything
that would indicate a real change — `threshold`, `cv_roc_auc_*`,
`cv_pr_auc_*`, `dummy_customer_score`, `hash` — is unchanged, and
`xgboost_churn_pipeline.pkl` is byte-identical to the committed one. That is
the confirmation that `make_preprocessor()` did not alter the model: giving
each pipeline its own ColumnTransformer produces exactly the artifact the
shared one did, which is what the reasoning predicted and what could not be
proven without a run.

Three other item-12 changes are now confirmed the same way. Cells 26 and 30
produced byte-identical output, so the rebuilt fine-threshold grid (inclusive
stop, rounded to 2dp) and the `np.isclose` lookup both behave exactly as the
code they replaced — threshold 0.40, peak $26,640, test profit $6,660.
`simulated_new_customers.csv` shows no diff at all, which means cell 40's
`X_test_raw.sample(...)` reproduced the 19-column file byte-for-byte; the
regeneration script used earlier had matched the notebook exactly. Cell 20's
`n_jobs=-1` produced no change either.

The only figure that moved is the Logistic Regression row, for the third run
running. ROC-AUC 0.843899 → 0.843901, std 0.018893 → 0.018884, accuracy
0.7760 → 0.7758, profit $26,220 → $26,200. The README's table row and the
inline three-model ROC-AUC list were updated. Nothing else needed touching,
and that is worth recording: the footnote written two entries ago states this
row's variability as *ranges* rather than as one run's values, and all three
ranges still cover this run (ROC-AUC within 0.843891–0.843903, accuracy within
0.7758–0.7867, profit within $26,200–$26,240). Stating it as a range instead
of a point is why the prose did not go stale this time.

**Why:** Post-execution verification, which this project's own checklist
requires after any notebook re-run.

**Requested or incidental:** The user reported the re-run; the checks and the
README sync follow from it.

**Verification status:** Executed and checked in order. Tests 162 passing, the
version gate passes. The run was contiguous and in order (execution counts 40
through 78, no gaps) but on an existing kernel rather than a fresh one, so it
does not by itself prove a cold-start run — the specific risk that creates, a
stale `preprocessor` variable surviving in the kernel and masking a missed
reference, was already ruled out separately by an AST scan showing no bare
`preprocessor` name is loaded anywhere in the notebook. Every figure the
README publishes was re-matched against this run's stored outputs: the
Results table, the model-comparison table, the sensitivity sweep, the
calibration table, the threshold-precision and leakage tables, and the
error-overlap table (correlations 0.964–0.980, 64.5% shared errors, Jaccard
0.72–0.78, average-of-three profit $26,780) all agree. The SHAP section needs
no recheck this time: the pickle is byte-identical, so the attributions cannot
have moved. Committed.

---

## 2026-08-23 — Cold-kernel re-run: last caveat closed; cell numbering shifted again

**Files touched:** `README.md`, `CLAUDE.md` (plus `model_metadata.json` and
`telco_customer_churn.ipynb`, rewritten by the user's run)

**What changed:** The user did a restart-and-run-all, which closes the one
caveat the previous entry left open. That run's execution counts are 1 through
39 with no gaps, so it is a genuine cold-kernel execution rather than a Run All
over a warm kernel, and `model_metadata.json` again moved only in `trained_at`
and `git_commit` while the pickle stayed byte-identical. Cells 26 and 30
produced byte-identical output for the second run running, this time from a
kernel with no prior state at all. Nothing in the notebook depended on a stale
variable, which was the specific risk a warm-kernel run could not rule out.

Two things needed syncing.

The Logistic Regression row moved again — fourth run, fourth set of digits:
ROC-AUC 0.843901 → 0.843900 and std 0.018884 → 0.018874. Accuracy, threshold,
profit and PR-AUC were all unchanged this time. Table row and inline list
updated.

More importantly, the notebook is now **51 cells, not 50**. The user added a
markdown note at index 37 ("decided, not it doesnt", answering their own
question at cell 36 about whether stacking would help), which shifted every
index above it by one. CLAUDE.md's cell map named the old positions, so it now
pointed at the wrong cells for SHAP, the save block and all four appendices.
The map is corrected — SHAP is 39–40, the save block 41–43, the appendices
44–50 — and the two inline warnings that cited specific indices were updated
with it ("don't move them above cell 43", "cell 47 needs `tuned_estimators`").
The note about historical renumbering now records both shifts rather than one,
so the `AUDIT.md` cross-reference stays usable: its "cell 38" is now 41.

**Why:** Post-execution verification, and the cell map is the single most
load-bearing thing in CLAUDE.md — a wrong index there sends the next session to
the wrong cell.

**Requested or incidental:** The user reported the re-run. The README sync
follows from it; the CLAUDE.md cell-map correction is incidental, caught by
diffing cell sources rather than by being told, and this file's own rule
requires an entry for any CLAUDE.md edit.

**Verification status:** Executed. Execution counts verified as exactly 1..39.
`xgboost_churn_pipeline.pkl` and `simulated_new_customers.csv` both show no
diff. Cells 26 and 30 confirmed byte-identical against the committed version.
The new cell was read directly to confirm it is a markdown note and not code.
The corrected cell map was checked by printing each named index and its first
line. Tests 162 passing, version gate passes.

Worth recording as a pattern: the notebook's cell indices have now moved twice
because of user-added markdown, and both times the documentation drifted
silently. Diffing cell *sources* — not just outputs — after a re-run is what
catches it.

---

## 2026-08-24 — Dockerize the project (AUDIT.md roadmap item 4)

**Files touched:**
- `Dockerfile` (created)
- `.dockerignore` (created)
- `.github/workflows/tests.yml` (added a second job, `docker`; the existing
  `test` job is unchanged)
- `README.md` (added a "Docker" subsection under "Running it"; added a
  paragraph to the version-gate discussion; added `Dockerfile` and
  `.dockerignore` to the repo-structure listing; updated the CI line in that
  listing; removed "Would containerize with Docker" from Known limitations,
  since it is now done; added Docker to the Stack line)

**What changed:** The project now builds a production container image.

*One image, two entrypoints.* `api.py` and `telco_model.py` have an identical
dependency set and share `config.py` and `feature_engineering_telco.py`, so
they ship together. The default `CMD` starts the API under uvicorn; batch
scoring is `docker run -v ./data:/data telco-churn python telco_model.py`.
Building two images was considered and rejected: it would duplicate every
layer for no benefit while manufacturing exactly the API/batch divergence
that the project's central invariant exists to prevent.

*The model is copied in, never trained during the build.* The committed
artifact is byte-reproducible, and training requires the `notebook`
dependency group, which the image does not install.

*Dependencies.* The build runs `uv sync --frozen --no-dev` in a builder stage,
copying only `pyproject.toml` and `uv.lock` first so the expensive dependency
layer is not invalidated by an edit to application code. `--no-dev` was the
open question going in; it is correct. An import audit across every runtime
module — `api.py`, `telco_model.py`, `config.py`,
`feature_engineering_telco.py`, `check_model_environment.py` — found no import
of `pytest` or `httpx`, so the image ships 26 packages instead of 34 and
contains no test runner. `--frozen` makes lockfile drift a build failure,
matching what CI already does.

*The nvidia trim.* The largest single item in the runtime environment turned
out not to be a project dependency at all. `xgboost` hard-depends on
`nvidia-nccl-cu13` on Linux: 288 MB of GPU distributed-training libraries that
a CPU inference container never calls. The builder stage deletes that payload,
taking the image from 858 MB to 570 MB (measured inside both images with `du`,
not from `docker images`, which on this daemon reports inflated figures).
Two alternatives were rejected for concrete reasons, both recorded in comments
in the Dockerfile: switching to the `xgboost-cpu` distribution would break
`check_model_environment.py`, which resolves versions through
`importlib.metadata.version("xgboost")` and would get `PackageNotFoundError`;
and excluding the dependency in `pyproject.toml` would change the project for
every consumer, when this is a property of the image alone. The trim step
*fails the build if it finds nothing to delete*, so if xgboost ever drops the
dependency, someone removes the block deliberately rather than carrying a
silent no-op.

*Two build-time verifications.* `check_model_environment.py` runs as a build
step, which is the point raised in the request: because the image pins its
libraries from `uv.lock`, the gate turns "this image cannot load its own
artifact" into a build failure instead of a runtime surprise. A second inline
check loads the committed `.pkl` and asserts `DUMMY_CUSTOMER` still scores the
`dummy_customer_score` recorded in the metadata — the version gate proves the
versions match, this proves the pickle actually loads and reproduces its
prediction, which version equality alone cannot show. Both run *after*
`USER appuser`, so they also confirm the unprivileged user can read the
artifact.

That last decision immediately paid for itself. The first build failed at the
version gate with `PermissionError: /app/config.py`. Several source files are
mode `0600` in the working tree from a restrictive local umask, and `COPY`
preserves host file modes, so the non-root user could not read its own code.
Fixed with `COPY --chmod=0644`, which makes the image independent of the build
host's umask. Without the build-time check this image would have built clean
and died on its first request.

*Security and filesystem layout.* The container runs as `appuser` (uid 10001),
not root, because `api.py` loads a pickle and `joblib.load` executes arbitrary
code on deserialization. `/app` is read-only to that user. `/data` is created
writable and is where the batch scorer reads and writes; mounting a host
directory there is the whole interface. A `HEALTHCHECK` polls `/health` using
`urllib` from the venv rather than adding curl to the image.

*CI.* A `docker` job was added to the existing workflow, running in parallel
with `test` rather than after it — the two answer different questions and
neither gates the other, so serialising them would only delay the first
failure signal. It builds the image with gha layer caching, waits on the
container's own HEALTHCHECK, then asserts the served `/predict` probability is
exactly `0.7443000078201294` (not merely that a 200 came back), that an
unknown category is rejected with 422, and that the batch scorer writes
through a mounted `/data` as the non-root user. Container logs are dumped on
failure.

**Why:** Requested. Docker was roadmap item 4 in `AUDIT.md` and the last
remaining "what I'd add for production" item in the README that was purely
infrastructural. The audit's argument for ranking it high is specific to this
repo: pinning the runtime library set from `uv.lock` makes it a build artifact
rather than a hope, which demotes `config.validate_environment_versions()`
from primary drift defence to cheap assertion. The README's version-gate
section was extended to say that.

**Requested or incidental:** Requested. The three design decisions inside it
— `--no-dev`, the nvidia trim, and the load-and-score build check — were put
to you as explicit choices before implementation and you selected all three.
The `COPY --chmod=0644` fix was not anticipated; it was forced by a real build
failure and is incidental to the requested work, though not separable from it.

**Verification status:** Verified by execution, extensively.

- Full test suite before starting: `uv run pytest -q` → **162 passed**, tree
  clean.
- Image builds successfully, including a final `--no-cache` cold build from
  scratch after `docker builder prune -af`.
- Both build-time checks print OK on every build:
  `OK: installed library versions match model_metadata.json.` and
  `OK: artifact loads and reproduces dummy_customer_score (0.5699995160102844)`
  — the latter matching the value recorded in `CLAUDE.md` exactly.
- Size measured inside the containers with `du -sx /`: **858 MB untrimmed,
  570 MB trimmed**, a 288 MB delta matching the nvidia directory exactly. An
  untrimmed image was built specifically for this comparison and then deleted.
- `xgboost 3.4.1`, `sklearn 1.9.0`, `numpy 2.5.2`, `pandas 3.0.5` all import
  in the trimmed image, and the build's own `predict_proba` call exercises
  xgboost after the trim.
- Container reaches HEALTHCHECK status `healthy`; `docker exec … id` confirms
  `uid=10001(appuser)`.
- `/predict` on the README's documented payload returns
  `{"churn_probability":0.7443000078201294,"target_for_retention":true,"threshold_used":0.4}`
  — byte-identical to what the README publishes for a host run.
- `contract: "Three year"` (unknown category) is rejected with **422**.
- Batch scorer verified three ways: bare `docker run` with no mount, a mounted
  `/data` with no env vars, and a mounted volume with explicit `INPUT_PATH`
  and `OUTPUT_PATH`. All report `15 of 50 customers flagged`. The container's
  `retention_campaign_targets.csv` is **byte-identical** (`diff`) to the one a
  host run of `uv run python telco_model.py` produces.
- Workflow YAML parses; `yaml.safe_load` reports two jobs, `test` (6 steps)
  and `docker` (8 steps). The `docker` job itself has **not** run on GitHub
  Actions yet — that only happens on push, so it is verified as valid YAML
  and as locally-equivalent commands, not as a green CI run.
- The notebook was not opened, executed, or modified.

Not committed; all changes are in the working tree.

---

## 2026-08-24 — INPUT_PATH / OUTPUT_PATH environment overrides for the batch scorer

**Files touched:**
- `telco_model.py` (added `import os`; `INPUT_PATH` and `OUTPUT_PATH` now read
  from the environment)
- `tests/test_telco_model.py` (added `import importlib` and three new tests
  plus a `restore_telco_model` fixture at the end of the file; the existing
  tests and fixture are unchanged)
- `README.md` (documented the two variables in the "Configuration" subsection;
  updated the test count from 162 to 165)

**What changed:** `telco_model.py`'s two path constants were hardcoded string
literals. They now resolve through `os.environ.get` with those same literals as
defaults, mirroring exactly how `config.py` already handles `MODEL_PATH` and
`METADATA_PATH`:

```python
INPUT_PATH = os.environ.get("INPUT_PATH", "simulated_new_customers.csv")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "retention_campaign_targets.csv")
```

Behaviour with no environment set is unchanged, so a fresh clone runs exactly
as before.

Three tests were added. The existing `isolated_run` fixture monkeypatches the
module attributes, which tests that `main()` *uses* the constants but not that
they *resolve* correctly — so the new tests reload the module with
`importlib.reload` under a modified environment instead. They cover: the
defaults with the variables unset, the values with them set, and an end-to-end
`main()` run that reads and writes through environment-provided paths. A
fixture reloads the module again on teardown so a test that changed the
environment cannot leave the imported module holding overridden paths for
whatever runs next.

**Why:** The container needs to score a CSV that arrives on a mounted volume,
at a path the image cannot know at build time. Without this, the Docker
invocation would have to be
`docker run -v "$PWD:/work" -w /work -e MODEL_PATH=/app/... -e METADATA_PATH=/app/... …`
— long, easy to get wrong, and it drags the model paths into a problem that is
really about the data paths. With it, `-v ./data:/data` is the entire
interface. The image sets both variables to `/data` defaults internally, which
is also what makes the batch path work at all under the non-root user: `/app`
is deliberately read-only, so the module's repo-relative default output path
raises `PermissionError` there. That failure was found by running the
container, not by reasoning about it.

**Requested or incidental:** Requested, as one of three implementation choices
put to you before any code was written; you chose this over leaving
`telco_model.py` untouched. Flagging it explicitly because it is a change to
application source code rather than to container packaging, which is a wider
blast radius than "dockerize the project" implies on its face. The
accompanying tests and the README documentation were not separately requested
and are incidental to it — an untested and undocumented env-var contract
seemed worse than the change itself.

**Verification status:** Verified by execution. `uv run pytest -q` →
**165 passed** (162 before, 3 added), 3.54s, no failures and no new warnings.
The batch scorer was additionally exercised through the container in all three
configurations described in the Docker entry above, and its output confirmed
byte-identical to a host run. Not committed.

---

## 2026-08-24 — Document the Docker design decisions in CLAUDE.md

**Files touched:**
- `CLAUDE.md` (added a new "## Docker" section between "Conventions" and the
  CHANGELOG rules; added `Dockerfile` and `.dockerignore` rows to the Layout
  table; extended the `check_model_environment.py` row to mention it also runs
  as a build step; updated the `tests/` row from 162 to 165 tests)

**What changed:** A new section recording the decisions behind the Dockerfile
that a future session would otherwise have to re-derive from comments, or
worse, silently undo. It covers: why it is one image rather than two; that the
artifact is copied and never trained in the build; why `--no-dev` and
`--frozen`; the nvidia-nccl trim including both rejected alternatives and the
reason the trim step fails loudly when it finds nothing; why `COPY --chmod=0644`
is load-bearing rather than cosmetic; the two build-time verifications and why
they run after `USER appuser`; the `/app` read-only, `/data` writable split and
the fact that the `/data` defaults for `INPUT_PATH` and `OUTPUT_PATH` exist only
inside the image, not in the module; why `campaign_profit.py` is deliberately
absent from the image; and why the CI `docker` job runs parallel to `test`.

Nothing already in the file was reworded or removed. The four edits outside the
new section are additive: two new table rows, one clause appended to an
existing row, and one number corrected.

**Why:** Several of these are decisions that look like mistakes to someone
reading the Dockerfile cold, and would be plausibly "fixed" into breakage.
Deleting `site-packages/nvidia` reads as a hack until you know it is 288 MB of
GPU libraries and that the obvious alternative breaks the version gate.
`COPY --chmod=0644` reads as noise until you know its absence causes a
first-request crash. Omitting `campaign_profit.py` reads as an oversight. This
is the same category of thing the rest of `CLAUDE.md` exists to record.

**Requested or incidental:** Incidental. You did not ask for `CLAUDE.md` to be
updated; the request was to dockerize the project. The file documents the
repo's load-bearing decisions and the Docker work added several, so leaving it
untouched would have made it stale on the same day it was written. Logged as
its own entry because `CLAUDE.md` explicitly requires that.

**Verification status:** Documentation only — no code was changed by this
entry, so there is nothing to execute. Every factual claim in the new section
was taken from a command actually run during this session and reported in the
two entries above: the 858 MB → 570 MB measurement, the 288 MB directory size,
the `PermissionError` that motivated `--chmod`, the pinned
`0.7443000078201294` response, and the 165-test count. The section headings
were confirmed to be in the intended order with `grep -n '^## ' CLAUDE.md`.
Not committed.

---

## 2026-08-24 — Fix a broken CI batch step and the docs command that shared its bug

**Files touched:**
- `.github/workflows/tests.yml` (the `Smoke test the batch scorer` step in the
  `docker` job now copies an input CSV into the mounted directory first)
- `README.md` (rewrote the Docker command block; added a paragraph explaining
  what mounting `/data` does to the shipped sample)
- `Dockerfile` (extended two comments — the usage header and the `/data`
  block — to state the consequence of mounting an empty directory)
- `CLAUDE.md` (added the same caveat to the one-line batch command in the
  Docker section)

**What changed:** The CI job added in the entry above had a genuine bug, found
by running its shell steps verbatim against the built image after a push to
GitHub turned out to be impossible from this environment. The batch step did:

```
mkdir -p out && chmod 777 out
docker run --rm -v "$PWD/out:/data" telco-churn:ci python telco_model.py
```

`out/` is empty. Mounting it at `/data` shadows the sample
`simulated_new_customers.csv` baked into the image, so `INPUT_PATH` pointed at
a file that no longer existed and the step died with `FileNotFoundError:
/data/simulated_new_customers.csv`. It now copies the repo's CSV into `out/`
before running, which also makes the step test the realistic path — a user
mounting a directory containing their own data — rather than relying on a file
the mount hides.

The same trap was in the documentation. The README, the Dockerfile header and
`CLAUDE.md` all showed `docker run -v ./data:/data telco-churn python
telco_model.py` as the batch command with no indication that `./data` must
contain the input. The README block now shows three separate invocations (API;
batch against the shipped sample with no mount; batch against your own CSV with
a mount and `INPUT_PATH`) and spells out that the default input path is
`/data/simulated_new_customers.csv`, so a file at that exact name needs no
`-e` flag. The two code comments gained the corollary sentence.

No behaviour changed in the image itself. The `/data` shadowing is correct and
intended — you bring your own data — and it was already described accurately in
the README's prose. What was wrong was the CI step and the copy-pasteable
commands.

**Why:** The previous entry recorded the `docker` job as "verified as valid
YAML and as locally-equivalent commands, not as a green CI run". Attempting to
push and discovering there are no credentials in this environment turned that
caveat into a reason to close the gap a different way: running each of the
job's four shell steps by hand against the image. The first three passed; the
fourth did not. Had the push succeeded, this would have been a red CI run
instead.

**Requested or incidental:** Incidental, in the sense that you did not ask for
it specifically — but it is a defect in work delivered in this same session, so
it is a correction rather than new scope. It does not amend or contradict the
previous entry; that entry's claim that the step was verified only as
"locally-equivalent commands" was accurate, and this is what happened when they
were actually executed.

**Verification status:** Verified by execution. All four shell steps of the
`docker` job were run verbatim against a freshly rebuilt image:

- `Start the API` — the health-wait loop exits 0; container reports `healthy`.
- `Smoke test /predict` — returns
  `{"churn_probability":0.7443000078201294,"target_for_retention":true,"threshold_used":0.4}`,
  both `grep` assertions pass.
- `Unknown category must be rejected with 422` — returns 422.
- `Smoke test the batch scorer` — now passes: `15 of 50 customers flagged`,
  output written, decision column present.

Additionally confirmed the bare no-mount run still works off the shipped
sample (also `15 of 50`), and that the mounted run's
`retention_campaign_targets.csv` remains byte-identical (`diff`) to a host run.
Image rebuilt and re-measured at 570 MB; both build-time checks still print OK.
`uv run pytest -q` → **165 passed**. Workflow YAML re-parsed: `test` 6 steps,
`docker` 8 steps.

The `docker` job still has **not** run on GitHub Actions. It cannot be pushed
from this environment — there is no `gh` CLI, no git credential helper and no
SSH key, so `git push` fails with `could not read Username for
'https://github.com'`. Both commits from this session are local only.

---

## 2026-08-24 — Self-review of the Docker work: one real test bug and eight inaccuracies

**Files touched:**
- `tests/test_telco_model.py` (rewrote the `restore_telco_model` fixture;
  added `import os`; added a regression guard test at the end of the file)
- `Dockerfile` (corrected three comments; made the usage examples portable)
- `README.md` (fixed a paragraph break, a package count, a stale test-file
  count, the test total, a line wrap, and the mount command)
- `CLAUDE.md` (corrected the package count, the test total, and the mount
  command)
- `.github/workflows/tests.yml` (corrected the Buildx comment; the health-wait
  loop now bails out if the container stops running)

**What changed:** You asked me to check the Docker work for mistakes. I found
one real bug and a set of inaccurate claims. Listing them all, because several
were numbers I had asserted confidently.

*The real bug — a silent test-isolation leak.* The `restore_telco_model`
fixture added earlier today was supposed to reload `telco_model` after a test
had overridden `INPUT_PATH`/`OUTPUT_PATH`, so the module didn't keep the
override. It did the opposite. pytest finalizes fixtures in reverse
instantiation order, so this fixture's teardown ran *before* `monkeypatch`
undid the environment variables — meaning the reload re-read the still-set
overrides and left `telco_model.INPUT_PATH` pointing at a pytest tmp directory
for the remainder of the session. Proved by adding a throwaway probe test
after the suite: `LEAKED: /tmp/pytest-of-yaponsk/.../mounted_input.csv`.

Nothing failed because of it, and that is the uncomfortable part: the fixture
was green only because the three tests using it happen to be the last in the
file, so nothing ran afterwards to observe the corrupted module. That is
precisely the "precondition holds by luck" pattern `AUDIT.md` M7 recorded
elsewhere in this repo, reintroduced by me in the same session.

The fixture now snapshots the two variables itself and restores them before
reloading, which makes it correct regardless of fixture or test ordering. A
permanent regression guard was added as the last test in the file — pytest
runs tests within a module in definition order, so it deterministically
observes what the environment tests left behind. It compares against a fresh
`os.environ.get` resolution rather than hardcoded literals, so it stays valid
if those variables are set in the ambient environment. Verified to actually
catch the bug: reinstating the old teardown makes it fail, restoring the fix
makes it pass.

*Wrong package counts.* I reported the image as shipping "26 packages instead
of 34". Both numbers were wrong. They came from counting lines of
`uv export`, which lists every resolution entry including ones whose
environment markers exclude them on Linux — `colorama` and `tzdata` among
them. Counting installed distributions inside the built image gives **24**,
and evaluating markers for Linux gives **32** for a plain `uv sync`. So the
correct statement is 32 → 24, and the `dev` group adds eight distributions:
pytest, httpx, certifi, httpcore, iniconfig, packaging, pluggy and pygments.
Worth noting the repo's pre-existing README claim of "32 packages" for
`uv sync` was right all along; my 34 contradicted it and I did not notice.

*A stale size estimate in the Dockerfile.* The nvidia-trim comment still said
the trim takes the image "from ~900 MB to ~610 MB" — my estimate from before I
measured anything. Every other file had been updated to the measured
858 MB → 570 MB; this comment had not. Now corrected, and it names the method
(`du -sx /` inside both images).

*A wrong permissions claim.* A Dockerfile comment said "/app is owned by root
at mode 0644". A directory at 0644 would not be traversable and the image
would not work. `ls -la` inside the container shows `/app` is `drwxr-xr-x`
(0755) and the files within it are 0644. Reworded to say that.

*A markdown paragraph break.* The new README Docker section ran the
`OUTPUT_PATH` sentence straight into the following paragraph with no blank
line, so the two would render as one block. Fixed.

*A command I documented but never ran.* All three docs showed
`docker run -v ./data:/data …`. I had only ever tested with an absolute path.
Relative bind-mount sources require Docker 23 or newer, so the documented
command would fail on older daemons with a confusing error. I confirmed
`./data` does work here (Docker 29), then switched all three to
`-v "$PWD/data:/data"`, which works everywhere, and noted why in the README.

*A wrong justification in CI.* The comment on the `Set up Buildx` step said it
was needed "for the cache mount on uv's download cache and for COPY --chmod".
Those work under plain BuildKit. Buildx is required because the default docker
driver cannot export a `type=gha` cache. Comment corrected to say that.

*A slow failure mode in CI.* If the container crashed at startup, the
health-wait loop would spin for the full 90-second timeout before failing,
reporting a timeout rather than a crash. It now checks `.State.Running` each
iteration and exits immediately with the container logs.

*A stale count I did not introduce.* The README said "Three of the seven files
are deliberately not mocked". There are nine `test_*.py` files. This predates
this session's work, but it sits four lines from the test total I had just
updated, so leaving a known-wrong number there would have been worse than
fixing it. Changed to "nine test files".

*Test total.* 165 → 166 with the regression guard, updated in both `README.md`
and `CLAUDE.md`.

**Why:** Requested — you asked me to check the work for mistakes and fix them.

**Requested or incidental:** The review and its fixes are requested. Two items
inside it are incidental and flagged as such above: the README "seven files"
correction, which is pre-existing drift rather than my error, and the CI
`.State.Running` check, which is a robustness improvement rather than a defect
fix.

**Correction to earlier entries:** the entry titled "Dockerize: one
self-verifying image..." states the image "ships 26 packages instead of 34".
That is wrong; the correct figures are 24 installed distributions versus 32.
Per this file's rules the earlier entry is left exactly as written and this
paragraph is the correction. No other factual claim in the two earlier entries
was found to be wrong on re-checking — the 858/570 MB measurements, the
288 MB trim, the pinned `0.7443000078201294` response, the byte-identical
batch output and the `dummy_customer_score` reproduction all re-verified.

**Verification status:** Verified by execution.

- `uv run pytest -q` → **166 passed**.
- The leak was demonstrated with a temporary probe test before the fix
  (1 failed) and confirmed gone after (9 passed in that file).
- The new regression guard was verified to catch the bug it guards against, by
  temporarily reinstating the buggy teardown: guard fails; restore the fix:
  guard passes. The temporary files were removed.
- Package counts measured two ways: `importlib.metadata.distributions()` inside
  the running image (24), and `uv export` with environment markers evaluated
  for Linux (24 runtime-only, 32 with dev).
- Permissions read from `ls -la /app` and `ls -la /data` inside the container.
- `-v ./data:/data` confirmed working on Docker 29 before being replaced with
  the portable form.
- `find … -maxdepth` after other predicates was checked for the GNU warning it
  sometimes emits; it does not warn here, so the trim step was left as is.
- Workflow YAML re-parsed: `test` 6 steps, `docker` 8 steps.
- Image rebuilt, still 570 MB, both build-time checks still print OK; a final
  `--no-cache` build was run to confirm nothing depended on a warm cache.

The `docker` CI job still has not run on GitHub Actions — this environment has
no push credentials. All commits from this session remain local.

---

## 2026-08-24 — Second review pass: healthcheck asserted the wrong thing, CLAUDE.md left in the build context

**Files touched:**
- `Dockerfile` (the `HEALTHCHECK` now checks the `model_loaded` field, not just
  the HTTP status; its comment rewritten to match)
- `.dockerignore` (added `CLAUDE.md`)
- `CLAUDE.md` (added a `HEALTHCHECK` bullet; tightened the `/app` read-only
  claim; fixed two line wraps left ragged by the previous pass's edits)

**What changed:** A second review pass over the Docker work, after the first
one. Two substantive findings and some tidying.

*The healthcheck did not check what its comment claimed.* The comment said
`/health` "reports model_loaded, which is only True once the lifespan handler
has finished loading the pickle — so this distinguishes 'process is up' from
'ready to answer'". The probe itself only asserted
`urlopen(...).status == 200`. Reading `api.py:114`, `/health` returns HTTP 200
unconditionally — `model_loaded` is a value in the response *body*, never in
the status — so the probe would have reported a model-less process as healthy.
That is exactly the state `/predict` answers with a 503, i.e. the one state a
healthcheck most needs to catch.

In practice the window is very narrow: uvicorn does not accept connections
until the lifespan handler finishes, so "up but no model" shows as connection
refused rather than a 200, and a lifespan exception kills the container
outright. So this was a wrong justification more than an outage waiting to
happen. Fixed by making the probe true to its comment rather than by softening
the comment: it now parses the JSON and requires `model_loaded is True`.
Verified the container still reaches `healthy` (probe exit code 0).

*`CLAUDE.md` was being sent to the Docker daemon on every build.* The
`.dockerignore` excludes `README.md`, `CHANGELOG.md`, `AUDIT.md` and `LICENSE`
but I missed `CLAUDE.md`, which is assistant guidance for working on this repo
and has no business in a build context. Found by building a throwaway busybox
stage that does `COPY . /ctx` and listing the result — which is also how the
rest of `.dockerignore` got confirmed working: the context is **648 KB**, with
`.venv`, `.git`, `tests/` and the notebook all correctly excluded.

*Precision fixes in `CLAUDE.md`.* The bullet said "`/app` is read-only". `/app`
is not a read-only mount — it is root-owned with a 0755 directory and 0644
files, and the container runs as `appuser`, so it is read-only *to that user*.
Reworded, since this is the same class of imprecision the previous pass
corrected in the Dockerfile. A new bullet records the healthcheck decision so
nobody simplifies it back to a status check. Two line wraps left ragged by the
previous pass's string edits were rejoined.

**Why:** Requested — you asked me to check the work again.

**Requested or incidental:** Requested. Nothing here expands scope beyond
reviewing and correcting this session's Docker work.

**Verification status:** Verified by execution, on a fresh `--no-cache` build:

- Build passes both build-time checks:
  `OK: installed library versions match model_metadata.json.` and
  `OK: artifact loads and reproduces dummy_customer_score (0.5699995160102844)`.
- Container reaches `healthy` under the stricter probe; inspected
  `.State.Health.Log` shows `exit=0`.
- Image 570 MB; **24** installed distributions counted inside the running
  image; running user `appuser`.
- `/predict` returns `0.7443000078201294`; unknown category → 422.
- Batch scorer: bare run `15 of 50`; mounted run byte-identical (`diff`) to a
  host run.
- `docker stop` completes in ~650 ms, so uvicorn handles SIGTERM as PID 1 and
  no init/tini wrapper is needed — checked because a process that ignores
  SIGTERM would silently cost 10 s on every deploy.
- Build context inspected directly: 648 KB, `CLAUDE.md` now absent.
- The pre-existing `test` job in `.github/workflows/tests.yml` diffed against
  its state at commit `0d21750` and confirmed **byte-identical** — this
  session's workflow change is purely additive.
- Host file modes checked with `stat`: exactly three copied sources
  (`api.py`, `telco_model.py`, `config.py`) are 0600, so the "several" in the
  `--chmod` rationale is accurate.
- `uv run pytest -q` → **166 passed**.

No correction to any earlier entry is needed from this pass. The `docker` CI
job still has not run on GitHub Actions; this environment has no push
credentials and all commits remain local.

---

## 2026-08-24 — The docker CI job has now actually run on GitHub Actions, and passed

**Files touched:**
- `CLAUDE.md` (the CI bullet in the Docker section now records the confirmed
  run; a new bullet documents the cache-export cost)
- `CHANGELOG.md` (this entry)

**What changed:** The branch was pushed and both CI jobs were watched through
to completion on real GitHub Actions infrastructure. Both passed.

Run [32672676187](https://github.com/faridqul/telco-churn-retention/actions/runs/32672676187),
triggered by the push of `c378ddf` to `docs/readme-ci-and-tests-paths`:

- **`test`** — success in 16s. Version gate then 166 tests.
- **`docker`** — success in 2m5s. Every step green: checkout, Set up Buildx,
  Build the image, Start the API, Smoke test /predict, Unknown category must
  be rejected with 422, Smoke test the batch scorer, Container logs.

This is the first time the `docker` job has executed on GitHub. It was written
in an environment with no push credentials, so up to now it had only been
verified by running its shell steps by hand against a local build. The parts
that could not be checked that way — `docker/build-push-action@v6` with
`load: true`, and `type=gha` cache import/export — are exactly the parts that
are now confirmed.

Pulled from the runner's own log rather than inferred:

- `#12 importing cache manifest from gha:11944333437161345256` — cache-from
  wired up correctly.
- `#30 exporting to GitHub Actions Cache` → `preparing build cache for export
  20.7s done` → `sending cache export 41.0s done` — cache-to genuinely
  exported rather than silently no-opping, which is the failure mode that
  would have left every future run paying full build cost.
- `trimming /app/.venv/lib/python3.12/site-packages/nvidia (288M)` — the
  nvidia trim reproduces on a clean runner, so the 288 MB figure is not an
  artifact of this machine.
- `OK: installed library versions match model_metadata.json.`
- `OK: artifact loads and reproduces dummy_customer_score (0.5699995160102844).`
- `{"churn_probability":0.7443000078201294,"target_for_retention":true,"threshold_used":0.4}`
  — the actual served response, printed by the step, matching the pin.
- `Success! 15 of 50 customers flagged for retention.` — the batch scorer
  through a mounted `/data` as the non-root user.

Also confirmed the `.State.Running` guard added in the previous pass is present
in the pushed workflow (line 95); it did not appear in the first log grep
because that grep filtered on "healthy".

`CLAUDE.md` gained a note that the ~60s cache export is deliberate and should
not be "optimised" to `mode=min` — `mode=min` would cache only the final image
and skip the expensive `uv sync` builder layer, which is the one worth reusing.

**Why:** Requested. Every entry since the Dockerfile landed carried the caveat
that the `docker` job had never run on GitHub Actions, and closing that was the
point of this turn.

**Requested or incidental:** Requested.

**Note on the caveat in earlier entries:** you asked for the "has not run on
GitHub Actions" caveat to be removed from the CHANGELOG. It appears in two
earlier entries (the self-review entry and the second-review entry) and I have
**not** edited either, because this file's own rule is that entries are never
edited or deleted and a stale claim is corrected by a new entry. This entry is
that correction: both of those caveats are now superseded and no longer true.
`CLAUDE.md`, which is not append-only, was edited directly.

**Verification status:** Verified on GitHub, not locally. `gh run watch
32672676187 --exit-status` exited 0; `gh run view` reports conclusion
`success` for the run and for both jobs individually. Individual step results
and the log excerpts above were read back with
`gh run view --job 97275782262 --log`.

One non-blocking observation, not acted on: GitHub annotated both jobs with
"Node.js 20 is deprecated" for `actions/checkout@v4`, `astral-sh/setup-uv@v5`,
`docker/setup-buildx-action@v3` and `docker/build-push-action@v6` — they are
being force-run on Node 24. It affects the pre-existing `test` job as much as
the new `docker` job, it is a warning rather than a failure, and bumping action
majors is a separate change from this session's work, so it was left alone.

---

## 2026-08-24 — Correct the docker job's runtime: ~2m is the cold-cache figure, not the steady state

**Files touched:**
- `CLAUDE.md` (the cache bullet added in the previous entry now gives both the
  cold and warm timings)

**What changed:** The previous entry's `CLAUDE.md` bullet said to "expect ~2
minutes for the `docker` job". That was measured on the very first run, when
the gha cache was empty, and it is not the steady state.

Pushing the doc-update commit triggered a second run, which is the natural
warm-cache measurement: **50s**, against 2m5s cold — a 2.5x speedup, with the
builder layers reported as `CACHED` and `importing cache manifest from
gha:8709624423317703715` in the log. So the bullet now gives both numbers and
names the two runs they came from, rather than presenting a cold-start figure
as typical.

The point of the bullet is unchanged and now better supported: the ~60s
`mode=max` export on a cold run is what buys the warm-run speedup, so it
should not be "optimised" down to `mode=min`.

**Why:** Accuracy. A number I had just written was measured under conditions I
did not state, and someone reading it would budget CI time wrongly or conclude
the cache was not working.

**Requested or incidental:** Incidental. The second run happened as a side
effect of pushing the previous commit; I watched it rather than ignoring it,
which is what surfaced the discrepancy.

**Verification status:** Verified on GitHub. Run
[32672906226](https://github.com/faridqul/telco-churn-retention/actions/runs/32672906226)
reports `docker` 50s and `test` 19s, both success; `gh run watch --exit-status`
exited 0. Cache reuse read from the job log (`CACHED` on the builder layers).
Documentation only — no code changed, so there is nothing else to run.

---

## 2026-08-24 — Record why a PR-event CI run is slower than a push run

**Files touched:**
- `CLAUDE.md` (one bullet added to the Docker section's CI notes)

**What changed:** Opening PR #1 triggered a fourth CI run, this one on the
`pull_request` event rather than `push`. Its `docker` job took **2m38s** — well
above the 50s and 42s the two previous push runs took, and above even the 2m5s
first cold run.

That looks like a regression and is not one. GitHub scopes Actions caches by
ref: a `pull_request` run can restore caches created on its *base* branch and
the default branch, but not ones created on the head branch. So the PR run
could not see the cache the branch's own push runs had written, and rebuilt
from cold. Once this branch merges, `main` will carry the cache and later PRs
will restore from it.

Recorded because the previous two entries document "~50s warm", and the first
thing anyone will actually look at is the check timing on a PR — where they
would see 2m38s and reasonably conclude the caching had broken.

**Why:** A number I documented would have been contradicted by the first place
a reader encounters it.

**Requested or incidental:** Incidental. It surfaced from watching the PR's own
checks rather than assuming they would match the push runs.

**Verification status:** Verified on GitHub. Run
[32673084519](https://github.com/faridqul/telco-churn-retention/actions/runs/32673084519)
(`pull_request` event, PR #1): `test` 19s, `docker` 2m38s, both success —
compared against run
[32673006178](https://github.com/faridqul/telco-churn-retention/actions/runs/32673006178)
(`push`, same commit `1a36c6b`): `test` 22s, `docker` 42s. PR reports
`MERGEABLE (CLEAN)`. Documentation only; no code changed.

---

## 2026-08-24 — Correction: PR cache scoping, and the previous entry's claim was wrong

**Files touched:**
- `CLAUDE.md` (rewrote the bullet added in the previous entry; it now carries a
  measured table instead of an inferred explanation)

**What changed:** The previous entry explained a slow PR-event CI run by saying
a `pull_request` run "can restore caches from its *base* and the default
branch, not from the head branch", and concluded: "Expect cold-cache timings on
PR checks until the branch merges and `main` starts carrying the cache."

The second half of that is **wrong**, and the next PR run disproved it within
minutes. Pushing the commit that contained the claim triggered a second
`pull_request` run, which completed its `docker` job in **43s** — warm, with no
merge having happened.

What is actually going on, counted from `CACHED` layers in the build logs
rather than inferred:

| event | run | CACHED layers | docker job |
|---|---|---|---|
| push | 32672676187 | 0 | 2m5s |
| push | 32672906226 | 15 | 50s |
| pull_request | 32673084519 | **0** | **2m38s** |
| pull_request | 32673261952 | 15 | 43s |

`push` and `pull_request` maintain **separate** cache scopes. The first run in
each scope is cold; every run after that in the same scope is warm. The first
PR run genuinely could not read what the push runs had written — that part of
the previous entry held — but it wrote its own cache, which the second PR run
restored. Merging has nothing to do with it.

**Why:** I explained a one-off observation with a mechanism I had not measured,
and stated a forward-looking prediction ("until the branch merges") that the
very next run falsified. The corrected bullet reports counts from the logs and
makes no prediction beyond what was observed.

**Requested or incidental:** Incidental — a correction to my own previous
entry, caught by checking the follow-up run instead of assuming it would match.

**Correction to an earlier entry:** the entry titled "Record why a PR-event CI
run is slower than a push run" contains the wrong claim quoted above. Per this
file's append-only rule that entry is left exactly as written; this paragraph
supersedes it. Its factual observations (2m38s on the PR event vs 42s on the
push at `1a36c6b`) were correct — only the causal explanation and the
prediction were not.

**Verification status:** Verified on GitHub. `CACHED` layer counts obtained
with `gh run view <run> --job <job> --log` and counted per run; the two
`pull_request` runs import different cache manifests
(`gha:6178796840260627049` and `gha:1873493280279772642`), confirming the
second read a scope the first had populated. All four runs concluded
`success`. Documentation only; no code changed.

---

## 2026-08-24 — Bump the four GitHub Actions off the deprecated Node.js 20 runtime

**Files touched:**
- `.github/workflows/tests.yml` (four `uses:` pins raised to their current
  major versions; `actions/checkout` appears twice, once per job)

**What changed:** Every run of this workflow was carrying a GitHub annotation:
"Node.js 20 is deprecated. The following actions target Node.js 20 but are
being forced to run on Node.js 24." All four pinned actions were affected —
two of them (`checkout`, `setup-uv`) in the pre-existing `test` job, two
(`setup-buildx-action`, `build-push-action`) in the `docker` job added earlier
today.

| action | was | now |
|---|---|---|
| `actions/checkout` | v4 | **v7** |
| `astral-sh/setup-uv` | v5 | **v10** |
| `docker/setup-buildx-action` | v3 | **v4** |
| `docker/build-push-action` | v6 | **v7** |

Two of these are large jumps, so rather than bumping blind I read each action's
current `action.yml` and confirmed every input this workflow passes still
exists: `enable-cache` and `cache-dependency-glob` for `setup-uv`, and
`context`, `load`, `tags`, `cache-from`, `cache-to` for `build-push-action`.
`checkout` and `setup-buildx-action` are used with no inputs at all here, so
there was nothing to break.

Nothing about the workflow's behaviour changed — same jobs, same steps, same
assertions. This is purely getting off a runtime GitHub has already begun
force-migrating.

**Why:** Requested. The annotation was flagged as non-blocking when the
`docker` job first ran green, and you asked for it to be cleared. Worth doing
promptly rather than waiting: GitHub is currently force-running these on Node
24 anyway, so the pinned versions were already not running on the runtime they
were built against.

**Requested or incidental:** Requested.

**Verification status:** Verified on GitHub — the only place these can be
verified, since the versions are resolved by the Actions runner and nothing
about them is exercisable locally. Done on a branch rather than pushed
straight to `main`, so an incompatibility would not have turned `main` red.
Local pre-checks first: YAML re-parsed (`test` 6 steps, `docker` 8 steps) and
each action's inputs cross-checked against its current `action.yml`. CI result
recorded in the entry that follows this one.

---

## 2026-08-24 — Correction: `setup-uv@v10` does not resolve; the right pin is v7

**Files touched:**
- `.github/workflows/tests.yml` (`astral-sh/setup-uv` corrected from `@v10` to
  `@v7`, with a comment explaining why it is not the newest release)

**What changed:** The bump in the previous entry set `astral-sh/setup-uv@v10`,
taken from `gh api repos/astral-sh/setup-uv/releases/latest`, which reports
`v10.0.1`. CI rejected it outright:

```
Unable to resolve action `astral-sh/setup-uv@v10`, unable to find version `v10`
```

The mistake was assuming a repository's newest *release* implies a matching
floating *major tag*. It does not, and this repository is a case where they
diverge: `astral-sh/setup-uv` publishes bare major tags only up to `v7`
(`v1`…`v7`) while its releases run to `v10.0.1`. So `@v10` names a tag that has
never existed.

Corrected to `@v7`, which is the right answer for a reason beyond mere
resolvability — the entire purpose of the bump was escaping the deprecated Node
20 runtime, and `runs.using` per version is:

| version | runtime |
|---|---|
| v5 (before) | `node20` |
| **v7 (now)** | **`node24`** |
| v10.0.1 | `node24` |

v7 already clears the deprecation, keeps the floating-major convention the
other three pins use, and continues to receive patch updates within v7 — where
pinning `v10.0.1` would have frozen an exact version. Both inputs this workflow
passes, `enable-cache` and `cache-dependency-glob`, were confirmed present in
v7's `action.yml`.

Worth recording that the failure was cheap because the bump went to a branch
rather than to `main`: the red run was on `ci/bump-action-versions`, and `main`
stayed green throughout.

**Why:** A wrong pin that broke CI. Also worth writing down as a general trap —
`releases/latest` is not a safe source for an action pin; the tag has to be
confirmed to exist.

**Requested or incidental:** Incidental — a correction to my own error in the
previous entry.

**Correction to an earlier entry:** the entry titled "Bump the four GitHub
Actions off the deprecated Node.js 20 runtime" lists `astral-sh/setup-uv` going
to **v10**. That pin does not resolve and never ran. The correct value is
**v7**; the other three rows in that entry's table (`checkout@v7`,
`setup-buildx-action@v4`, `build-push-action@v7`) are right and were confirmed
green. Per the append-only rule that entry stands as written and this
supersedes it.

**Verification status:** The failing run is
[32766852431](https://github.com/faridqul/telco-churn-retention/actions/runs/32766852431)
— `test` failed at "Set up job" in 3s with the unresolved-action error, while
`docker` **passed in 35s**, which is what isolated the fault to `setup-uv`
alone and confirmed the other three bumps were fine. All four tags were then
verified to exist via `gh api .../git/ref/tags/<tag>`, and each action's
`runs.using` was read to confirm node24. Post-fix CI result recorded in the
entry that follows.

---

## 2026-08-24 — Formal significance test for the model comparison

**Files touched:** `telco_customer_churn.ipynb` (cell 35 modified; cells 51–52
appended), `README.md`, `CLAUDE.md`

**What changed:** The README's Known-limitations list said the ROC-AUC and
profit gaps between the three models had been judged "probably noise" by eye
and never tested. They are tested now, and the result does not fully support
what the eye said.

Before writing anything I checked whether a paired test was even legitimate.
It is: XGBoost's search (cell 22) and the Logistic Regression and Random
Forest searches (cell 35) all pass the same `cv_strategy` object and both fit
on `X_tr`/`y_tr`, and `StratifiedKFold(shuffle=True, random_state=42)` returns
identical fold indices on repeated calls — verified by generating the splits
twice and comparing, not assumed. Fold *k* is therefore the same split for
every model. The new cell asserts this at runtime rather than relying on the
reader to trust it.

Cell 35 previously kept only `best_estimator_` for each model, so
`cv_results_` died with the search object and the per-fold scores were
unreachable downstream. It now also stores `cv_fold_scores`.

The appendix was **appended** as cells 51–52 rather than inserted next to the
comparison table. Inserting would have shifted every index above it, and that
has already silently broken CLAUDE.md's cell map twice in this project's
history. Narrative adjacency was not worth a third occurrence.

**The finding.** The requested test — Wilcoxon on the 5 `cv_results_` folds —
returns p = 0.6250, 0.4375 and 1.0000 for the three pairs. Those numbers are
uninformative, and the cell says so explicitly: with 5 pairs there are 2⁵ = 32
equally likely sign patterns under the null, so the smallest two-sided p the
test can return is 2/32 = 0.0625. **No 5-fold result can ever reach p < 0.05.**
Reporting "not significant" from it would have been a fact about the sample
size presented as a fact about the models. That is a limitation of the test as
specified, not of the data, so the cell adds a companion with actual power:
5×5 repeated stratified CV over the same tuned estimators, 25 paired folds.

There, **XGBoost beats Random Forest at p = 0.0003** — past the Bonferroni
threshold of 0.0167 for three comparisons, and reproduced at 0.0003 in two
independent runs. The other two pairs do not separate (0.1073 and 0.6528).

So the blanket "information ceiling / it's all noise" reading is wrong as
stated. The models are distinguishable. What survives is the *practical*
conclusion, for a better reason than before: the effect is +0.0023 ROC-AUC,
about a sixth of one fold's own standard deviation, and it points the wrong
way for the metric that pays — Random Forest earns $27,000 of campaign profit
against XGBoost's $26,640 while losing on ROC-AUC. Detectable and material are
different things, and the original note conflated them in both directions.

**Why:** Requested — closing the "no formal significance test" item.

**Requested or incidental:** The test, the README update and the CHANGELOG
entry were requested. Storing `cv_fold_scores` in cell 35 is incidental but
unavoidable — the test cannot reach the data otherwise. The repeated-CV
companion was not requested; it is flagged as incidental and was added because
delivering only a test that cannot reject would have answered the question
with a number that means nothing.

The limitations item was **not** deleted. The instruction allowed removing it
if the test supported the existing conclusion; it partly did not, so the item
is rewritten to record that one pair is genuinely significant. Quietly deleting
it would have buried the one result that contradicted the prior claim.

**Verification status:** Executed, twice. The pairing check was run directly.
The p-values come from real searches reproducing the notebook's own
configuration — XGBoost's mean CV ROC-AUC came back 0.845812, matching the
published figure exactly, and Random Forest's 0.844126, likewise. Cell 52 was
then executed **verbatim from the notebook source** against reconstructed
objects and completed without error, producing the same conclusions. The one
number that moved between runs is the XGBoost-vs-Logistic-Regression p (0.1135
then 0.1073), which is that row's documented instability; the README quotes the
cell's own value and flags the range. Tests: 166 passing.

Not yet done: the notebook has not been re-run end to end, so cells 51–52 carry
no stored output and `cv_fold_scores` is not yet populated in a saved run. The
cell was proven to execute, but its output in the committed notebook will be
empty until the next full run.

---

## 2026-08-25 — Notebook re-run: significance appendix confirmed, LR row flipped to 0.62

**Files touched:** `README.md` (plus `model_metadata.json` and
`telco_customer_churn.ipynb`, rewritten by the user's run)

**What changed:** The user re-ran the notebook cold — execution counts 1 through
40, no gaps — which populates the significance appendix added yesterday and
closes the "no stored output" caveat on it.

The appendix reproduces exactly what the standalone harness produced: the
5-fold test returns 0.6250 / 0.4375 / 1.0000 with the 0.0625 floor printed
beside them, and the 25-fold companion returns **p = 0.0003 for XGBoost vs
Random Forest**, 0.1135 for XGBoost vs Logistic Regression and 0.6528 for
Random Forest vs Logistic Regression. The headline result therefore reproduces
at 0.0003 across three independent runs now. The mean differences match to six
decimals. Nothing in the README's significance section needed changing except
one p-value.

That one is the XGBoost-vs-Logistic-Regression figure. The README carried
0.1073, taken from the standalone execution; the notebook's own run gives
0.1135. Both were already flagged as the same row's known wobble, and the note
now lists all three observed values (0.1135, 0.1073, 0.1135) rather than two.

The Logistic Regression row itself moved more than usual this time: its best
threshold **flipped from 0.58 to 0.62**, taking accuracy to 0.7869 and profit
to $26,240, with PR-AUC 0.6548 → 0.6551. This is the documented alternation,
not a new phenomenon, but it falsified two pieces of prose that had been
written when both non-XGBoost models happened to land on 0.58. The
threshold-split paragraph said "both 0.58 in this run"; it now gives the two
values separately and points at the instability note. The instability note's
own accuracy range was 0.7758–0.7867, and 0.7869 sits just outside it, so the
range was widened. Its ROC-AUC range (0.843891–0.843903) and profit range
($26,200–$26,240) both still hold unchanged.

One figure in the error-overlap table also drifted: pairwise Jaccard is now
0.73–0.78 where it was 0.72–0.78. The shared-error percentage (65.3%, reported
as 65%), the correlations (0.964–0.980) and both profit figures are unchanged.

**Why:** Post-execution verification, per this project's checklist.

**Requested or incidental:** The user reported the re-run; the README sync
follows from it.

**Verification status:** Executed and checked in order. `model_metadata.json`
moved only in `trained_at` and `git_commit`; `xgboost_churn_pipeline.pkl` and
`simulated_new_customers.csv` are byte-identical, so the artifact reproduced
and the significance work touched nothing that ships. Cells 26 and 30 produced
byte-identical output again, so the threshold (0.40), peak OOF profit
($26,640) and test profit ($6,660) are unmoved. No cell source changed. A
fourteen-point automated cross-check of README figures against this run's
stored outputs — Results table, model comparison, significance table, error
overlap — comes back with zero failures. Tests 166 passing; version gate
passes.

Worth noting for future runs: the significance conclusion is the stable part
here, and the Logistic Regression row is the unstable part. Anything written
about that row should be phrased as a range or explicitly dated to a run, which
is what has now had to be corrected three separate times.

---

## 2026-08-25 — Root-caused the Logistic Regression drift: a missing random_state

**Files touched:** `telco_customer_churn.ipynb` (cell 35), `README.md`,
`CLAUDE.md`

**What changed:** The user asked why the Logistic Regression row changes every
run when the other two do not. The answer turned out to be a real defect, and
the explanation this project had been repeating for weeks was wrong.

The README said the row was inherently unstable: a flat ROC-AUC surface, so the
winning `C` slides between near-tied draws. That describes the amplifier, not
the cause, and it never explained the actual puzzle — everything in the search
is seeded, so nothing should have moved at all.

`LogisticRegression` was the only one of the three estimators constructed
without a `random_state`. `XGBClassifier(random_state=42)` and
`RandomForestClassifier(..., random_state=42)` both had one from the start.
Nothing about logistic regression looks stochastic, which is exactly why it
went unnoticed — but with `solver='liblinear'`, scikit-learn uses
`random_state` to shuffle the data, so an unseeded estimator scores the *same*
candidate differently on every fit. Seeding `RandomizedSearchCV` does not help:
that only fixes which 200 candidates get sampled, not how each one is fit.

Both halves of the mechanism were measured. Fitting one fixed `C` five times
unseeded gives five different CV scores with a spread of 2.3e-05; seeded, it
gives the identical value five times out of five. Meanwhile the top five
candidates in the real search sit within 1.0e-05 of each other — half the
noise. So the argmax was selecting noise: a different `C` won each run, its
probabilities were calibrated slightly differently, and the profit-optimal
threshold followed between 0.58 and 0.62, dragging accuracy and profit with it.

Cell 35 now passes `random_state=42`, with a comment explaining why an
apparently deterministic estimator needs one. The README's instability
footnote was rewritten: it now states the old diagnosis was wrong, gives the
measured numbers, and notes the flat surface was the amplifier rather than the
cause. CLAUDE.md's post-re-run checklist item 4 changes from "watch this row,
it drifts" to "it is fixed — if it moves again, something else is unseeded,
don't write it off as a flat surface a second time", and a new convention
records that every estimator in a search needs its own seed.

**Why:** Asked directly. It also ends a recurring maintenance cost — this row
forced README corrections after three separate notebook runs.

**Requested or incidental:** The question was asked; the fix was not explicitly
requested and is flagged as incidental. It was applied rather than only
reported because the row's numbers change on every run regardless, so seeding
does not destabilise anything that was stable — it stabilises something that
never was.

**Verification status:** Executed. The unseeded-vs-seeded comparison was run
directly (five repetitions each). The seeded search was then run in full to
obtain the row rather than predicting it: ROC-AUC 0.843894, std 0.018894,
PR-AUC 0.654827, best threshold 0.62, accuracy 0.7867, profit $26,200 — and
the winning `C` is 6.1265. The significance appendix was re-run seeded: XGBoost
vs Random Forest holds at p = 0.0003 (fourth independent reproduction) and
XGBoost vs Logistic Regression settles at 0.1073, which should now be stable
rather than alternating with 0.1135. XGBoost's and Random Forest's rows
reproduced unchanged, confirming the seed reaches only the intended estimator.
Tests 166 passing.

**Important caveat:** the README now carries seeded figures while the
notebook's stored outputs are still from the last unseeded run, so the two
disagree until the notebook is re-run. This is deliberate — the seeded values
are measured, not predicted, using the notebook's exact configuration — but if
a re-run does *not* reproduce ROC-AUC 0.843894 and threshold 0.62 exactly, that
is a real signal and should be investigated rather than papered over.
## 2026-08-26 — Browser frontend for the /predict endpoint

**Files touched:** `frontend/index.html` (new file, new directory)

**What changed:** Added a single-page browser frontend for the prediction
service. It is one self-contained HTML file — markup, CSS and JavaScript in
the same document, no framework, no build step, no npm. Opening the file in a
browser is the entire install procedure.

The page renders a form covering all 19 fields `api.Customer` requires: 15
dropdowns whose options are transcribed from `config.CATEGORICAL_DOMAINS`, a
`seniorcitizen` dropdown offering only 0 and 1 (it lives in `NUMERIC_COLUMNS`
but `api.Customer` constrains it with `Field(ge=0, le=1)`, so a dropdown is the
only widget that cannot produce an out-of-range value), and number inputs for
`tenure`, `monthlycharges` and `totalcharges`. `totalcharges` is the only
optional field, matching its `float | None` type; blank submits as JSON `null`.

Every field is pre-filled with `config.DUMMY_CUSTOMER`'s values, so submitting
the untouched form asks for the one prediction this repo already has a pinned
answer for — `dummy_customer_score`, 0.5699995160102844. That makes the default
state of the page a working end-to-end check rather than an arbitrary example.

The API base URL is an editable field at the top of the page rather than a
constant in the JavaScript, so the same file can be pointed at a local uvicorn
or a deployed instance without an edit. It defaults to `http://localhost:8000`.

On success the page shows the probability as a percentage, the exact unrounded
float underneath it, a target/do-not-target badge, and a bar with the score
drawn as a fill and the threshold drawn as a separate marker. The two are drawn
as distinct things deliberately: the model produces a ranking and the threshold
is an independently-chosen business decision, which is the distinction this
project is built around, and a single number would hide it.

Three failure paths are handled and visibly distinguished: 422 (renders each
Pydantic error as `field — message`, parsed from the `detail` array), 503 (the
model-not-loaded case `api.py` returns before the globals are set), and a
thrown `fetch` (no HTTP reply at all — wrong URL, API down, or CORS refusal),
whose message names all three causes since the browser will not tell the page
which one it was.

Two small decisions worth recording. The numeric inputs deliberately carry no
`min="0"` attribute, so a negative number reaches the API and is rejected there
rather than being blocked by the browser — the server stays the authority on
validation, and the 422 path is reachable from the UI instead of being dead
code. And a blank *required* numeric is submitted as the empty string rather
than being coerced to 0, so the API reports a missing value instead of scoring
a zero the user never typed.

**Why:** Requested. The user asked for a simple frontend matching the /predict
contract, reading dropdown values from `config.py` rather than inventing them,
with the 422 case handled explicitly. They identified themselves as a beginner
at frontend/API work and asked for readable code over clever code, which is why
this is one commented file rather than a component tree.

**Requested or incidental:** Requested in full. The tech-stack choice (vanilla
JS over React/Streamlit) and the serving approach were put to the user before
any code was written; they chose vanilla JS and an editable URL field, and
delegated the CORS decision — see the following entry.

**Verification status:** Executed, against the real API. `uv run uvicorn
api:app --port 8000` was started with the committed artifact and exercised with
curl: the form's default payload returns 0.5699995160102844, matching
`model_metadata.json["dummy_customer_score"]` exactly; `monthlycharges: -5`
returns 422 with the `detail` array shape the error handler parses. The
JavaScript was extracted and passed `node --check`. Every `name=` attribute in
the form was diffed against `tuple(CATEGORICAL_DOMAINS) + NUMERIC_COLUMNS` (19
present, none missing, none extra) and every `<select>`'s option set was diffed
against its `CATEGORICAL_DOMAINS` entry (all 15 match exactly). `uv run pytest
-q` — 166 passed, unchanged. Committed to branch `feat/frontend-demo`, not yet merged. The page has not been
opened in an actual browser by the assistant; the HTTP behaviour it depends on
was verified directly, but its visual rendering has not been.

## 2026-08-26 — CORS enabled on api.py so a browser page can call it

**Files touched:** `api.py`

**What changed:** Added `CORSMiddleware` to the FastAPI app — an import line
and a six-line `app.add_middleware(...)` call directly after the `app =
FastAPI(...)` construction, with a comment explaining what it is for. Configured
with `allow_origins=["*"]`, `allow_methods=["GET", "POST"]` and
`allow_headers=["Content-Type"]`, which is the minimum the frontend needs. No
existing line was modified or removed; the change is purely additive.

**Why:** Browsers refuse to let a page call an API on a different origin unless
the API's response says it is permitted. `frontend/index.html` is loaded from a
file or a local static server, so it is always a different origin from the
service, and its POST carries `Content-Type: application/json`, which makes it
a non-simple request that triggers a preflight `OPTIONS`. Without this
middleware the preflight is unanswered, the POST is never sent, and the page
sees a bare network error. This affects browsers only — `curl`,
`telco_model.py`, the Docker smoke test and the test suite were all already
working and are unaffected either way.

`allow_origins=["*"]` is a deliberate choice for this service rather than an
unconsidered default: there is no authentication, no cookie and no credential
for another site to ride on, and `/predict` only scores a customer the caller
supplied themselves, so there is nothing a permissive origin policy exposes.
The comment in the file says so, and says to narrow it if the service ever
gains auth.

**Requested or incidental:** Incidental, and flagged as such. The user asked
for a frontend, not a backend change, and described the API as already built,
tested and deployed. They were shown the CORS problem and the three ways out
(same-origin StaticFiles mount, this, or a separate proxy process) before any
code was written, and asked for whichever was best for learning and as a
portfolio piece. This one was chosen because their other answer — an editable
API URL field — requires cross-origin calls by definition, which rules out the
same-origin mount, and because a standalone frontend is the more useful
portfolio artifact. **A reader who wants the backend untouched should revert
this entry's change and replace the frontend's URL field with a same-origin
path.**

**Note on dependencies:** none added. `CORSMiddleware` re-exports Starlette's,
which FastAPI already depends on, so `pyproject.toml`, `uv.lock`, the
`Dockerfile` and CI are untouched.

**Verification status:** Executed. Confirmed importable in the project venv
before the edit. After the edit, against a live `uvicorn api:app`: a preflight
`OPTIONS /predict` carrying `Origin: null` (what a `file://` page sends) returns
200 with `access-control-allow-origin: *`; a `POST` carrying `Origin:
http://localhost:5500` returns the prediction with the same header present.
`uv run pytest -q` — 166 passed, unchanged, including `tests/test_api.py`'s
startup and boundary tests. Committed to branch `feat/frontend-demo`, not yet merged.


## 2026-08-27 — DATA_DICTIONARY.txt: a per-feature reference for the dataset

**Files touched:** `DATA_DICTIONARY.txt` (new file)

**What changed:** Added a plain-text data dictionary documenting every column
the dataset carries — the dropped identifier, the target, the 19 raw features
the API accepts, and the 6 engineered features — in seven sections.

Each raw feature entry gives its allowed values, its share of the dataset, its
churn rate per level, and any validation rule attached to it. Each engineered
feature gives the exact formula as implemented in
`feature_engineering_telco.py`, its observed range, and the rationale for its
existence. A fifth section collects the structural traps, a sixth lists the 25
model columns in metadata order alongside the preprocessing each branch
receives, and a seventh names every file where these definitions are enforced.

Every percentage in the file was computed from the cached Kaggle dataset
during this session rather than copied from the README, on the 7,021-row
deduplicated frame. The file states that scope explicitly at the top so the
figures are not mistaken for test-set model metrics.

Four things the document records that were not previously written down
anywhere in the repo:

- **`total_services` is not monotonic in churn.** Churn rises from 21.1% at 0
  services to 45.8% at 1 service, then falls steadily to 5.3% at 6. The 0
  bucket is contaminated: 1,512 of its 2,197 rows are customers with no
  internet at all, who churn at 7.2%. Read naively this feature looks
  backwards, and the file says so.
- **The four protective add-ons and the two streaming add-ons behave
  differently.** Security, backup, device protection and tech support each
  roughly halve churn; streaming TV and movies barely move it. The six are
  otherwise identically shaped, so this distinction is easy to miss.
- **`charge_change_ratio` is weaker than its name suggests** — range 0.636 to
  1.451, median exactly 1.000, with 603 rows sitting at exactly 1.0. For most
  customers `totalcharges / tenure` is close to `monthlycharges` by
  construction.
- **"Electronic check" is a manual payment method**, and the single
  highest-churn category in the data at 45.1%. It reads as automatic and is
  not, which is precisely what `is_auto_pay` disambiguates.

**Why:** Requested — the user asked for a text file explaining every feature
the dataset carries. Written as `.txt` because that is what was asked for; it
converts to Markdown without restructuring if that is ever preferred.

**Requested or incidental:** Requested. No code, test, notebook or
configuration file was modified — this is a documentation addition only, and
nothing about the model, the artifact or the API changed.

**Verification status:** Executed. Every distribution and churn rate was
computed from
`~/.cache/kagglehub/datasets/blastchar/telco-customer-churn/versions/1/`
during this session. The engineered-feature statistics were produced by
importing the real `engineer_features()` rather than reimplementing its
formulas. Two claims were checked separately after drafting: the churn split
is 1,857 / 5,164 of 7,021, and the 25-column list in section 6 is identical in
both content and order to `model_metadata.json["feature_columns"]`. The
formulas quoted in section 4 were transcribed from
`feature_engineering_telco.py` as it currently stands. **Not yet committed.**

## 2026-08-27 — DATA_DICTIONARY.txt: cheat sheet added, cut 30%, one number fixed

**Files touched:** `DATA_DICTIONARY.txt`

**What changed:** Three things, in one revision of the file added earlier today.

**A cheat sheet, as section 0.** A single table listing all 25 features sorted
by "spread" — the churn rate of the column's worst level divided by its best.
That ranking puts `contract` (15.2x) at the top and `gender` (1.03x) at the
bottom, and lets a reader see the whole dataset's signal structure without
reading any prose. Engineered columns are marked `(E)`, and four footnotes
carry the caveats that would otherwise mislead. Under the table sits a
five-item "read first" list of the things most often got wrong. The section
numbering shifted by one: the old section 0 (dataset facts) is now section 1,
and everything below moved down accordingly.

**Cut from 439 to 306 lines, exactly 30%,** as asked. The saving came from
four places, none of which dropped a fact: the six add-on columns became one
table instead of six near-identical blocks; sections 6 and 7 merged; the
three-line `===` banners around each section heading became one self-titling
rule; and several notes were tightened. Two trap entries the new cheat sheet
already states in full were compressed to a single cross-referencing line.

**One number was wrong and is now right.** In the add-on comparison table the
`streamingtv` row carried 39.9% in the "churn when No" column. 39.9% is that
level's *share of rows*, not its churn rate — the correct figure is 33.3%.
The error was introduced when the six per-column blocks were collapsed into a
table, and was caught by re-reading the table against the computed statistics
rather than by any test. The adjacent spread figure (1.11x) was always correct,
having been computed separately, which is what made the inconsistency visible.

The add-on table also now reports Yes-vs-No spreads rather than spreads across
all three levels. Including "No internet service" inflates every add-on to
roughly 5x, but that level is just `internetservice == "No"` restated, so the
inflated figure describes internet service rather than the add-on. On the
honest basis the four protective add-ons range 1.73x to 2.85x while the two
streaming ones sit at 1.11x and 1.12x — close to no signal at all, which is a
sharper statement of the protective-versus-streaming split than the first
draft made.

**Why:** Requested — the user asked for the file to be about 30% shorter with
a cheat sheet at the start.

**Requested or incidental:** The shortening and the cheat sheet were
requested. The `streamingtv` correction and the switch to Yes-vs-No spreads
were not asked for; both are flagged as incidental. The correction was applied
rather than merely reported because leaving a known-wrong number in a
reference document would be worse than the edit.

**Verification status:** Executed. All figures were re-derived from the cached
Kaggle dataset in this session; the Yes-vs-No add-on spreads were computed
directly rather than inferred from the three-level numbers. The file is 306
lines with no line exceeding 80 characters, and all seven section headings
resolve. No code, test or configuration file was touched. **Not yet
committed**, and still sitting on the `feat/frontend-demo` branch alongside
unrelated frontend work — see the open question raised with the user.

## 2026-08-27 — Standalone fairness analysis (fairness_analysis.py)

**Files touched:** `fairness_analysis.py` (new file), `fairness_report.txt`
(new file, generated output)

**What changed:** Added a standalone fairness analysis that loads the
committed pipeline and scores it. **It trains nothing.** It reads
`MODEL_PATH` and the threshold through `config`, and reuses
`campaign_profit.profit_curve()` / `best_threshold()` rather than restating
the profit formula. No new dependency: everything it imports is already in the
runtime set, and it locates the dataset by globbing the kagglehub cache so it
does not pull in the notebook group.

Seven sections, matching the requested structure: a reliability gate, Tier 1
protected attributes, a Tier 2 socioeconomic proxy, an intersectional
diagnostic, a per-group threshold cost, the impossibility constraint, and a
plain-language summary.

**Two design decisions that were not in the request and are worth recording.**

First, **the notebook caches no predictions**, only the pipeline and a 50-row
sample CSV. The test split is therefore reconstructed by replaying cells 3-11
and the seeded `train_test_split`. Reconstruction is a silent-failure risk —
wrong rows would still produce a plausible report — so `verify_reconstruction()`
scores the artifact and raises SystemExit unless the confusion matrix equals
the published 256/179/116/854. It passes.

Second, **out-of-fold predictions cannot be obtained without refitting**, which
the request explicitly ruled out. The reliability gate nevertheless requires an
OOF companion for groups in the marginal band. The conflict is resolved by
making OOF opt-in behind `--with-oof`, which warns before refitting; without it,
marginal groups are reported with a bootstrap interval and an explicit note that
the companion was not computed. Point estimates are never shown bare.

**Findings.** Every flagged gap runs in the same direction, and it is the
opposite of the naive expectation: recall is *higher* for the group that churns
more. Seniors 86.5% vs non-seniors 63.3% (+23.3pp, CI [+14.1, +31.6]);
manual-pay 76.8% vs auto-pay 47.0% (+29.8pp); no-partner 75.3% vs has-partner
56.6%; no-dependents 72.6% vs has-dependents 53.4%. Precision gaps are all
small and every precision CI crosses zero. The people being under-served are
the low-base-rate groups — a churning customer with a partner or dependents is
markedly less likely to be contacted. The report states this direction
explicitly, because "a 23-point gap" otherwise reads as harm to seniors.

The seniorcitizen x gender intersection shows no interaction: all four cells
land within 2.0pp of the additive main-effects prediction.

Recall parity between seniors and non-seniors costs **$220 of $6,680** (3.3%)
on the test set. The report also records *how* parity is reached — by raising
the senior cutoff from 0.40 to 0.56, so fewer at-risk seniors are contacted.
Equal recall here is levelling down, which is an argument against enforcing it,
and is visible only because the per-group thresholds are printed rather than
summarised.

**Requested or incidental:** The analysis was requested in the structure
delivered. The reconstruction gate, the opt-in OOF flag and the direction
paragraph were not requested; all three are flagged as incidental and were
added because without them the report would have been quietly misleading.

**Verification status:** Executed. The reconstruction gate passes. The OOF path
was run and confirms both marginal findings at roughly four times the sample:
senior recall 86.5% on 89 churners becomes 82.6% on 386; has-dependents 53.4%
on 73 becomes 51.4% on 253. The section 7 summary is byte-identical with and
without `--with-oof`, confirming OOF is additive rather than verdict-changing.
The reliability bands were checked at every boundary (29/30, 49/50, 99/100,
149/150) and the INSUFFICIENT branch was exercised with a synthetic 40-row
group: no rate is printed, no comparison is made, no finding is recorded.
`fairness_report.txt` is the committed output of the default no-retrain run;
the `--with-oof` report was deliberately not kept, since reproducing it
requires a refit. **No test file was added for this module** — the branches
above were checked by hand, not pinned. **Not yet committed.**

## 2026-08-27 — Tests for fairness_analysis.py, verified by mutation testing

**Files touched:** `tests/test_fairness_analysis.py` (new file)

**What changed:** 46 tests for the fairness module added in the previous
entry, which shipped with its branches checked by hand rather than pinned.
Suite total goes 166 -> 212, runtime 4.3s -> 7.2s.

Coverage is weighted toward the two failure modes that would do real damage,
rather than spread evenly:

- **The reliability gate**, tested at both sides of all four boundaries
  (29/30, 49/50, 99/100, 149/150), plus a monotonicity check that would catch
  bands written out of order, plus the INSUFFICIENT branch end-to-end: a group
  under 30 churners must yield no rate, no comparison and no finding.
- **The reconstruction gate**, in both directions. One customer moved across
  the threshold must abort, and the message must name expected and actual —
  it fires long after whoever changed the cleaning has stopped looking.
- **None versus zero.** A subgroup with no churners has an undefined recall,
  not a recall of 0.0. Returning 0.0 would read as "the model catches nobody
  in this group", which is the most damaging possible misreport, so it gets
  its own tests.
- The `>=` comparison, matching the repo-wide invariant that the API and the
  batch scorer round nothing and compare identically.
- That `section_threshold_cost` uses the shared `campaign_profit()` rather
  than growing a private copy of the formula.
- That parity never earns more than the unconstrained optimum, which would
  make the cost-of-fairness figure negative and meaningless.

**Mutation testing.** The suite was not trusted for passing. Ten deliberate
defects were introduced one at a time and the suite re-run against each. The
first pass caught 5 of 7 and **two survived**, both from the same mistake:
`test_a_large_and_certain_gap_is_flagged_as_real` asserted
`abs(gap) > fa.GAP_FLAG_PP`, and the parity test asserted against
`fa.RECALL_PARITY_TOLERANCE`. Both assertions were phrased in terms of the
constant they were testing, so they moved when it moved and caught nothing.
Both now compare against documented literals, with the constants pinned
separately, and a comment in the file explains the trap. A further test was
added asserting the parity row actually narrows the recall gap relative to
the unconstrained row — guarding the opposite failure, where the constraint
never binds and the reported cost is a meaningless zero.

Second pass: 9 of 10 caught. The survivor is `BOOTSTRAP_SEED = 42 -> 1`, and
it is deliberately left uncaught. It is an equivalent mutant, not a defect:
what matters is that the seed is fixed, which `test_bootstrap_is_reproducible`
already verifies, and the specific value is an implementation detail rather
than a contract the way the 10pp rule and the 30-churner floor are.

**Requested or incidental:** Requested — the previous entry recorded the
missing tests as a known gap and the user asked for them. The mutation-testing
pass and the two assertion fixes it exposed were not requested and are flagged
as incidental; they were done because a test suite that has not been shown to
fail is not evidence of anything.

**Verification status:** Executed. 46 tests pass in 4.9s standalone; the full
suite is 212 passing in 7.2s. Mutation results are recorded above, and
`fairness_analysis.py` was diffed against its pre-mutation backup afterwards
to confirm no mutation was left behind. Tests needing the raw CSV or the
committed pickle skip cleanly when absent, so a fresh checkout still runs.
**Not yet committed.**
