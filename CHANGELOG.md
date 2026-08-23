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
