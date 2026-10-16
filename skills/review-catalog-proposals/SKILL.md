---
name: review-catalog-proposals
description: |
  Use this skill when someone wants to work through proposed catalog
  entries — phrases like "review the proposed failure modes", "what's
  waiting for promotion", "should we promote this check". Pulls
  failure-mode and operational-check entries at status `proposed`, checks
  each against the reports behind it and the entries already active, and
  writes a structured RECOMMENDATION (promote / retire / redraft, with
  sharpened wording). It never promotes: only a human moves an entry to
  active. For error reports rather than catalog entries, use
  review-agent-errors.
---

# Review catalog proposals

An `active` catalog entry is read into **every future evaluation on the
platform**. It is the highest-leverage text in the system and the easiest
to poison: a confused report, validated by an agreeable model, becomes a
standing instruction that biases every finding checked thereafter.

So this skill recommends and stops. Promotion is a human act, by design and
by the server's own gate (`the failure-mode catalog is curated by
superadmins`) — an agent finalizing a proposal records its verdict but
leaves `status = proposed` and gets back `applied: false, requires_human:
true`. Do not try to route around that; the rule is the feature.

## What you are judging

A proposal is a *claim that a pattern generalizes*. Three things make it
promotable, and all three have to hold:

1. **It is real.** The reports behind it describe something that happened,
   more than once, to more than one agent where possible.
2. **It is not already in the catalog.** The most common right answer is
   "this is `crash_as_refutation` again, sharpen that entry instead." A
   near-duplicate is worse than no entry: it splits the corpus and makes
   both entries match weakly.
3. **It is actionable as written.** A failure mode has to say what to do
   instead. An operational check has to be *runnable* — "verify X before
   Y", not "be careful about X".

## Trust: whose reports is it built on?

Check the provenance of the reports behind a proposal before recommending
promotion. A proposal resting on reports that only their own reporters
confirmed is **not** supported evidence, however many there are
(autoresearch-assist.md §4.9):

```python
supporting = chronicle.reasoning_errors.list(
    methodic_reviewed=True,        # the only reports that count globally
)
```

Say the count explicitly in your recommendation: "3 supporting reports, 1
Methodic-reviewed" is a different recommendation from "3 supporting
reports, 3 Methodic-reviewed", and a reader cannot tell them apart unless
you write it down.

## Workflow

```python
from methodic import Chronicle
chronicle = Chronicle.from_env()

# What is waiting. Proposals are NOT on `failure_modes.list()` — that serves
# active entries only, which is the whole point of the proposed tier. The
# review queue is the surface for things awaiting a decision.
queue = chronicle.review_queue.list(kind="failure_mode")

# The dedup set: what is already live and would have to be sharpened instead.
active_modes = chronicle.failure_modes.list()
active_checks = chronicle.operational_checks.list()
```

MCP-native: `chronicle.list_review_queue` with `kind: "failure_mode"`,
`chronicle.list_failure_modes`, `chronicle.suggest_operational_checks`.

Proposed entries are not served to agents, so nothing in the queue is doing
harm yet — which is exactly why there is time to be careful with it.

For each proposal:

1. **Dedup against active.** Search by symptom for checks, by description
   for modes. Read the near-misses properly — slug similarity is not the
   test, "would a reader reach for both?" is.
2. **Pull its supporting reports**, and count how many are
   Methodic-reviewed (above).
3. **Read it as an instruction.** Ask what an agent would *do* differently
   after reading it. If the answer is "nothing specific", it needs a
   redraft, not a promotion.
4. **Sharpen the wording** when you recommend promote-with-edits. Give the
   exact replacement text, not a note about what is wrong with it —
   a curator should be able to paste it.

## Recommend

```
failure mode `single_seed_generalization` — RECOMMEND REDRAFT (medium)
  supporting:  4 reports, 1 Methodic-reviewed
  duplicates:  near-miss with `n_of_one` — different enough to keep, but
               `n_of_one` should cross-reference it
  problem:     says "be careful generalizing from one seed", which tells an
               agent nothing it can act on
  proposed title:  State the seed count whenever a comparison rests on one run
  proposed body:   When a claim rests on a single run, say so in the claim
                   itself ("on one seed, …"). A reviewer can then weigh it;
                   silently generalizing is the error, not the single run.
  apply in:    Bridge → Autoresearch → catalog
```

- **RECOMMEND RETIRE** for a proposal that duplicates an active entry or
  that the reports do not support. Retiring a proposal costs nothing —
  it was never served.
- **Confidence is required.** `low` on a promote recommendation means "do
  not promote this on my say-so", and a curator should read it that way.
- **One recommendation per proposal.** If two proposals are the same thing,
  recommend promoting one and retiring the other, naming both ids.

Then summarize and stop. Do not call `finalize_review`.

## Failure modes

- **`403`** — the catalog is superadmin-curated; a plain caller cannot even
  list proposals. Say so plainly rather than falling back to the active
  list and reviewing entries that are already live.
- **A proposal with no supporting reports** — recommend retire. An entry
  nothing generated is an entry nobody needed.
- **Every proposal looks promotable** — treat that as a signal about your
  own bar, not the queue's quality. The base rate of "this is already in
  the catalog" is high, and a reviewer who never says redraft is not
  reviewing.

## Requires

- `pip install methodic-research`, or the bundled MCP tools.
- Superadmin — the proposed tier is not visible otherwise. Like
  `review-agent-errors`, this skill needs read access only.
