---
name: chronicle-distill
description: |
  Use this skill when the user wants to synthesize an experiment's findings
  ACROSS ALL its variations into a single review-gated report — phrases like
  "distill the experiment", "synthesize the findings", "write the takeaways
  across all variations", "summarize what every variation showed", "give me the
  final report for this experiment". This is the agent-side equivalent of the
  platform's managed distillation: it pulls every variation (or one variation,
  or a filtered corpus), reads each one's outputs + W&B metrics, and writes a
  takeaways_report (experiment scope), variation_report (one variation), or
  research_report (corpus). The report is registered REVIEW-GATED (not
  finalized) — it sits pending until the experiment owner approves it, which is
  also what unblocks conclude. For a single-scope write-up that finalizes
  immediately use chronicle-write-report instead; for prior-art synthesis use
  chronicle-research-survey.
---

# Distill experiment

Synthesize an experiment's findings **across all of its variations** into one
report — the agent-side counterpart to the platform's managed distillation. You
do the work yourself: pull every variation, read its outputs and real W&B
metrics, reason across them, and register the synthesis as a report.

Two disciplines define this skill, both inherited from the managed distillation
flow:

1. **Review-gated, not finalized.** The report is registered `pending` with
   `review_required` — it is **not** auto-finalized. It stays pending until the
   experiment owner approves it (`PUT /v1/assets/{id}/approve`) or rejects it
   (`.../reject`). For an experiment-scope `takeaways_report`, that owner
   approval is *also* what unblocks `experiment.conclude`. This is deliberate:
   an agent-written cross-variation synthesis is a draft for a human to ratify,
   not a fait accompli.
2. **Honest about what didn't work.** Every report carries an explicit
   `## What didn't work` section — the ablations that hurt, the variations that
   underperformed, the dead ends — present even when the headline is a success.
   If there genuinely are none, say so; don't drop the section.

## Scope

| `scope` | Pulls | Writes | Linked as |
|---|---|---|---|
| `experiment` (default) | every non-retracted variation + its outputs | `takeaways_report` | experiment output |
| `variation` | one variation (by index or name) + its outputs | `variation_report` (with `outcome`) | variation-scoped output |
| `corpus` | a filtered set of variations (by index list or outcome) | `research_report` | experiment output |

The experiment-scope `takeaways_report` is the one that gates conclude. The
others are informational (they nag for review in the UI but block nothing).

## What the report must contain

The agent drafts the body (Markdown + `$…$` LaTeX math) with these sections:

1. **Summary** — the headline finding across the experiment, 1–3 sentences.
2. **Per-variation findings** — one short block per variation: what it tried, the
   real metrics it produced, success vs failure. Use a table for the metric grid.
3. **What worked** — the positive cross-variation result, with the numbers.
4. **What didn't work** — **required.** Negative results across variations.
5. **Open questions** — load-bearing unresolved questions for the owner (≤5; each
   with one line on why it matters). Optional but encouraged.

## Pulling the real numbers — before you draft

Synthesize from the metrics the runs actually produced, not invented ones. For
each variation, resolve its `wandb_run` pointer from the experiment outputs and
fetch W&B directly with your own `WANDB_API_KEY` (the same pattern as
chronicle-write-report's "Pulling the run's metrics"):

```python
import wandb  # WANDB_API_KEY in env

def variation_metrics(chronicle, experiment_id):
    """Map variation index -> final W&B summary, for every linked run."""
    outputs = chronicle._transport.get(f"/experiments/{experiment_id}/outputs")
    out = {}
    for a in outputs:
        if a.get("asset_type") != "wandb_run":
            continue
        cfg = a.get("asset_config") or {}
        try:
            run = wandb.Api().run(f"{cfg['entity']}/{cfg['project']}/{cfg['run_id']}")
            out[a.get("variation")] = {"summary": dict(run.summary), "url": run.url}
        except Exception as e:
            out[a.get("variation")] = {"error": str(e)}  # record, don't crash
    return out
```

No `wandb_run` pointer for a variation → note "no linked W&B run" for it rather
than omitting it; a variation with no metrics is still a finding.

## Inputs

- **`experiment_id`** — the Chronicle experiment UUID. Resolve in order:
  explicit arg → `methodic` config → cwd detection → prompt the user (same as
  chronicle-write-report).
- **`scope`** (default `experiment`) — `experiment` | `variation` | `corpus`.
- **`variation`** (required for `scope=variation`) — index or name; resolve a
  name → index before the SDK calls.
- **`corpus_filter`** (for `scope=corpus`) — `{ variation_ids: [...] }` or
  `{ outcomes: ["succeeded", ...] }`.
- **`title`** — short human title for the report.
- **`write_research_report`** (experiment scope, default `False`) — also emit a
  longer-form `research_report` alongside the `takeaways_report`.

## Workflow

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 1. Enumerate the variations in scope and pull each one's context.
exp = chronicle._transport.get(f"/experiments/{experiment_id}")
variations = [v for v in exp.get("variations", []) if not v.get("retracted_at")]
if scope == "variation":
    variations = [v for v in variations if v["index"] == variation]
elif scope == "corpus" and corpus_filter:
    # apply variation_ids / outcomes filter
    ...

metrics = variation_metrics(chronicle, experiment_id)   # real W&B numbers
# Also read any per-variation variation_report / takeaways already attached, and
# session context if you need detail (chronicle.search.history / outputs).

# 2. *** AGENT SYNTHESIZES ACROSS VARIATIONS *** — the central step.
#    Markdown + $…$ math, with the required sections (Summary, Per-variation
#    findings, What worked, What didn't work, Open questions). Cite the REAL
#    metrics from `metrics`. Write the negative-results section in good faith.
markdown_summary = "...the agent writes the cross-variation synthesis here..."

# 3. Register the report REVIEW-GATED (pending + review_required) — NOT finalized.
asset_type = {"experiment": "takeaways_report",
              "variation":  "variation_report",
              "corpus":     "research_report"}[scope]

output_of = {"experiment_id": experiment_id}
content = {"title": title, "markdown_summary": markdown_summary}
if scope == "variation":
    output_of["variation"] = variation
    content["variation_id"] = variation
    content["outcome"] = outcome  # "success" | "failure_rca"

result = chronicle.assets.create_inline(
    asset_type=asset_type,
    name=title,
    content=content,
    content_type="application/json",
    output_of=output_of,
    pending_reasons=["review_required"],   # <-- review-gated; do NOT auto-finalize
)
asset_id = result["asset"]["id"]
print(f"Registered {asset_type} {asset_id} (pending review) on experiment {experiment_id}")
```

If `write_research_report` is set (experiment scope), repeat step 3 with
`asset_type="research_report"` and a longer-form body.

## Record the findings

The report body is the detailed record; a **finding** is the one-line
"what's working / what's not" signal per variation that lands on the
experiment's running-summary header and the activity feed (a `finding.recorded`
event) — so the state of the research reads at a glance without opening the
report. After registering the report, record one finding **per variation you
analysed**, drawn from the "Per-variation findings" section you just wrote:

```python
# For scope="experiment"/"corpus": loop the variations you covered.
# For scope="variation": a single finding for `variation`.
# The server keys on `evidence_variation` — recording again for the same
# variation REPLACES its finding (one finding per variation, not a stack).
for v_index, judged in per_variation_findings.items():
    chronicle.experiments.record_finding(
        experiment_id,
        # Judge from the METRICS, not the run's succeed/fail outcome:
        #   "working"     — improved on baseline / confirmed the hypothesis
        #   "partial"     — mixed or conditional result
        #   "not_working" — regressed, or cleanly ruled the approach out
        status=judged["status"],
        summary=judged["one_liner"],   # the signal in a sentence
        evidence_variation=v_index,
        source_asset_id=asset_id,      # the report this distilled
    )
```

(MCP-native agents: the `chronicle.record_finding` tool, same fields. On
methodic-research < 0.38 fall back to
`chronicle._transport.post(f"/experiments/{id}/findings", json={...})`.)

This keeps the running summary honest about the ablations that failed, not just
the headline — the same discipline as the required "What didn't work" section.
Recording a finding needs `Write` (the authority the report write already used);
a finding write failing is non-fatal (the report still landed) — surface it and
continue.

## After the skill completes

Tell the user:

1. The report asset id, type, and that it is **pending owner review** (not
   finalized) — it won't satisfy the conclude gate until approved.
2. How to ratify it: approve in the UI, or `PUT /v1/assets/{id}/approve`
   (reject with `.../reject`).
3. For an experiment-scope `takeaways_report`: that approving it is what unblocks
   `experiment.conclude`. If a takeaways report **already** existed, note that
   concluding will require choosing `on_exist_action: keep | regenerate` (the
   UI prompts; the API 409s without it).
4. Explicitly flag whether `## What didn't work` is substantive — if the agent
   left it thin, say so.

## Failure modes

- **`create_inline` 403** — the caller lacks `Write` on the experiment. Surface
  the message verbatim.
- **`pending_reasons` not accepted** — the report would auto-finalize. Do **not**
  fall back to a finalized write for a cross-variation distillation; the
  review-gate is the point. Surface that the SDK/server needs the review-gated
  create path (the managed distillation flow uses it via `POST /v1/assets` with
  `pending_reasons`).
- **No variations in scope** — an experiment with zero non-retracted variations
  has nothing to distill; tell the user rather than writing an empty report.
- **W&B unavailable for a variation** — record "no metrics" for that variation
  and continue; never invent numbers to fill the table.
- **Empty `## What didn't work`** — state there were no negative results so the
  absence is a recorded choice, not a gap.

## Distinction from related skills + the managed flow

- **chronicle-write-report** — single experiment/variation, **finalizes
  immediately**. Use it for a one-off write-up; use **this** skill to synthesize
  across all variations into a review-gated report.
- **chronicle-research-survey** — prior-art synthesis (pre-experiment literature
  review), not results.
- **Managed distillation** (`POST /v1/experiments/{id}/distill` /
  `chronicle.distill`) — spawns the platform's own distillation agent to do this
  work server-side, on its own compute. This skill is the **agent-side** path:
  the calling agent does the synthesis itself. Same report types, same
  review-gate, attribution by the calling key.

## Requires

- `pip install methodic-research`
- `pip install wandb` + `WANDB_API_KEY` exported (to pull real metrics)
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- No `git` — this skill writes assets via the API; no repo checkout needed.
