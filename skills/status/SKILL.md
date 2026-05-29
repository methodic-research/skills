---
name: chronicle-status
description: |
  Use this skill when the user wants a quick read on what's happening with
  a Chronicle experiment — phrases like "what's running on experiment X",
  "any failures recently", "show me the status of my experiments", "what's
  going on with v2's run". Returns a structured snapshot: lifecycle state,
  recent runs and their statuses, any retracted ancestors that affect
  lineage validity. Read-only; never mutates anything.
---

# Status

Fast, read-only summary of one experiment (or the user's active experiments
if none specified). Designed to answer the "is anything on fire" question
without diving into the web UI.

## Inputs

- **`experiment_id`** (optional) — single experiment to inspect. If omitted,
  the skill lists all experiments owned by the caller and reports each in
  brief.
- **`include_retracted_ancestors`** (default `True`) — also walk the lineage
  upstream and surface any retracted parents/grandparents.

## Workflow (single experiment)

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()

detail = chronicle.experiments.get(experiment_id)
exp = detail.experiment
print(f"Experiment {exp.id}")
print(f"  Hypothesis: {exp.hypothesis_summary}")
print(f"  State: {exp.state}", end="")
if exp.retracted_at:
    print(f"  (RETRACTED at {exp.retracted_at}: {exp.retraction_reason})", end="")
print()
print(f"  Created: {exp.created_at} by {exp.created_by}")
print(f"  Variations: {len(detail.variations)}")
for v in detail.variations:
    badges = []
    if v.committed_at: badges.append("committed")
    if v.retracted_at: badges.append("retracted")
    if v.latest_status: badges.append(f"last run: {v.latest_status}")
    # Prefer the plaintext name; fall back to the integer index when
    # the user hasn't named the variation. See `Variation naming` in
    # the repo README for the convention.
    handle = v.name or f"v{v.variation}"
    print(f"    {handle} — {v.run_count} runs — {', '.join(badges) or 'open'}")

# Surface upstream retractions — these invalidate this experiment's premises
if include_retracted_ancestors:
    upstream = chronicle.experiments.get_upstream_retractions(experiment_id, depth=5)
    if upstream.has_retractions:
        print()
        print("⚠ Upstream retractions in lineage:")
        for r in upstream.retractions:
            print(f"  exp {r.experiment_id} retracted at {r.retracted_at}: {r.reason}")
```

## Workflow (no specific experiment)

```python
print("Recent experiments:")
for summary in chronicle.experiments.iter():
    badges = [summary.state]
    if summary.retracted_at: badges.append("retracted")
    print(f"  {summary.id}  {summary.hypothesis_summary[:60]}  [{', '.join(badges)}]")
```

(For multi-experiment listing, cap at the first ~20 results — use the
SDK's `experiments.iter()` and break early to avoid scanning everything.)

## After the skill completes

If anything looks off (recent failures, retracted ancestors, repo in
`failed` state), surface it prominently. Don't bury it under the normal
status output.

## Requires

Same as `chronicle-mint-git-token`. No git, no writes — purely read.
