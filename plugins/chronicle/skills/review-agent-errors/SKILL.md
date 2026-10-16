---
name: review-agent-errors
description: |
  Use this skill when someone wants to work through the agent-error review
  queue — phrases like "pull the review queue", "review the reported
  errors", "what's waiting for review", "give me a recommendation on these
  reports". Pulls reasoning and operational error reports awaiting review,
  gathers the evidence behind each one, and writes a structured
  RECOMMENDATION (confirm / reject, with the catalog entry it matches).
  It never finalizes: a human applies the recommendations in Bridge. Use
  report-agent-error to FILE a report; this skill judges ones already
  filed. For proposed catalog entries rather than reports, use
  review-catalog-proposals.
---

# Review agent errors

Read the queue, judge what is in it, and hand back recommendations a person
can apply. One pull, one pass, one list of recommendations.

## This skill does not decide

**It writes no decision to Chronicle.** Not "unless you are a superadmin",
not "unless the user says go" — never. It reads, reasons, and recommends;
a human applies the result in Bridge or with `chronicle.finalize_review`.

That ceiling is the point rather than an oversight. The API *does* let a
local agent finalize (`review_method: "local_agent"`), which means the
shortest path from "an agent noticed something" to "the platform believes
it" can run entirely through agents — the same agent filing the report and
clearing it. A recommend-only skill puts a person on that path while still
doing the expensive parts: the reading, the evidence-gathering, the
drafting.

If the user asks you to apply a recommendation, point them at the id and
the surface. Do not call `finalize_review` yourself, and say plainly that
this skill does not.

## Two tiers, and why your recommendation matters

A report reviewed by its experiment's **owner** is confirmed *for that
experiment*. It does not count as validated evidence anywhere else. Only a
**Methodic** review (superadmin) admits a report to the corpus the global
failure-mode and operational-check catalogs are built from
(autoresearch-assist.md §4.9).

So there are two different jobs here, and you should know which one you are
doing:

| Pull | Job |
|---|---|
| `methodic_reviewed: false` on the global queue | Recommending what Methodic should admit to the global catalog corpus. High bar. |
| an experiment's own queue | Recommending what its owner should confirm locally. Lower bar — it only has to be true *here*. |

Never describe an owner-tier confirm as "validated". It is not, and the
distinction is the entire reason the two flags exist.

## Workflow

### 1. Pull

```python
from methodic import Chronicle
chronicle = Chronicle.from_env()

# Everything a Methodic reviewer has not yet cleared. Drop `methodic_reviewed`
# for the whole queue, or pass experiment_id for one experiment's.
reports = chronicle.reasoning_errors.list(
    state="ai_validated",          # or omit for everything pending
    methodic_reviewed=False,
)
```

MCP-native: `chronicle.list_agent_errors` with the same filters.

Take them oldest-first unless the user asks otherwise — a queue reviewed
newest-first starves its tail.

### 2. Gather the evidence, per report

A recommendation that cannot name its evidence is a guess. For each report:

- **The catalog it would join.** `chronicle.failure_modes.list()` for
  reasoning, `chronicle.operational_checks.list(q=<symptom>)` for
  operational — search checks by the *symptom* the report describes, never
  by a slug you would have to already know. Does this report already have a
  home? A confirm that maps onto an existing entry is worth far more than one
  that proposes a new one.
- **The report's own pointers.** `evidence` carries run / shard / report
  ids — resolve the ones that matter. Never quote session content; the
  pointers are what you were given.
- **Its experiment**, when it has one: the finding or claim check it came
  out of (`claim_check_id`), and the lesson recorded alongside it
  (`lesson_id`).
- **Whether it is the same thing as another report in this pull.** Two
  reports of one mistake should get one recommendation and a note that they
  duplicate.

### 3. Judge

Three questions, in order:

1. **Did it happen?** A report describing a run that succeeded, or a claim
   the record contradicts, is rejected regardless of how plausible it reads.
2. **Is it the *kind* of thing it says it is?** Reasoning errors get filed
   as operational and vice versa constantly. If the kind is wrong, say so —
   `reclassify` keeps the report id, so this is cheap to correct and the
   correction rate is itself a signal about the skill instructions.
3. **Would it recur elsewhere?** A mistake specific to one dataset is a
   *research lesson*, not a catalog entry. Recommend confirming it locally
   and say it should not go global.

`user_confirmed: true` means the **researcher** identified the mistake — a
human already validated the instance, in context. Do not recommend
rejecting one on your own reading of the text; if you think it is wrong,
say what evidence would settle it and recommend it stay in the queue.

### 4. Recommend

Print one block per report. Enough for a human to act without re-reading
the source:

```
report 0f3c… — RECOMMEND CONFIRM (high)
  kind:      reasoning (filed correctly)
  maps to:   crash_as_refutation
  because:   run 3 exited 137 at step 200; the finding cites its eval loss
             as evidence against the hypothesis. Textbook case of the
             existing mode — no new entry needed.
  evidence:  run 3 status, finding f-12, claim check cc-88
  apply in:  Bridge → Autoresearch → review queue
```

Rules for the block:

- **Confidence is required and means something.** `low` means "someone
  should look at this properly" — do not use it to hedge a recommendation
  you actually believe.
- **`RECOMMEND HOLD`** is a real answer for a report whose evidence you
  could not resolve. Say what is missing. Recommending a confirm you cannot
  support is worse than returning nothing.
- **Name the catalog entry or say there is none.** "Propose a new mode" is
  a recommendation with a cost — a new entry is read into every future
  evaluation — so it needs the argument for why nothing existing fits.

### 5. Stop

Summarize: how many reviewed, how many each way, and which need a human's
judgment rather than a rubber stamp. Then stop. Do not apply anything.

## Failure modes

- **Empty queue** — a real answer. Say so; do not widen the filter to find
  something to do.
- **`403` on a report** — it is scoped to an experiment you lack `Owner`
  on, or it is a global report and you are not a superadmin. Skip it and
  say which; do not retry with a different account.
- **The queue is mostly one reporter's** — worth saying out loud. A single
  agent flooding the queue is a signal about that agent's instructions, not
  a set of findings to grind through.
- **A report you cannot evaluate without session content** — recommend
  HOLD. Evidence is pointers by design; if the pointers do not settle it,
  a human with the session should decide.

## Requires

- `pip install methodic-research`, or the bundled MCP tools
  (`chronicle.list_agent_errors`, `chronicle.list_failure_modes`,
  `chronicle.suggest_operational_checks`).
- `Owner` on an experiment to see its reports; superadmin for the global
  queue. Reviewing is a **read** here — this skill needs no write access at
  all, which is the clearest statement of what it does.
