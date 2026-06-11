---
name: chronicle-retract-experiment
description: |
  Use this skill when the user (or an agent flow) wants to take a
  **committed or concluded** Chronicle experiment — or a single variation —
  out of use while preserving the record: phrases like "retract this
  experiment", "this result turned out to be wrong", "flag this as
  invalid", "mark these findings as withdrawn", "the bug invalidated those
  runs". Retraction is a soft flag with a required reason: the row,
  lineage, and audit trail survive; the experiment's output assets are
  invalidated; live agent deployments are torn down; the GitHub repo is
  archived read-only. For deleting an **open (uncommitted) draft** use
  chronicle-delete-experiment instead — hard delete is refused once the
  experiment is committed.
---

# Retract experiment

Soft-retract a Chronicle experiment (or one variation) that is part of the
historical record but should no longer be built on — wrong results, an
invalidating bug, superseded findings. The end state is: the experiment is
flagged `retracted` with your reason, every output asset it produced is
**invalidated** (hard-blocked as an input to new work unless
`allow_invalid_assets` is set), still-live agent deployments are torn
down, and the GitHub repo is archived (read-only, fully cloneable).

This is the counterpart to **hard delete**. Delete physically removes an
*open draft* that was never committed; retraction preserves committed/
concluded work while taking it out of use. Retraction is orthogonal to
lifecycle — a retracted experiment can still be committed or concluded,
and runs are not force-terminated. It is **idempotent**: retracting again
just updates the reason.

Downstream effects worth telling the user about:

- New experiments cannot list a retracted experiment as a parent unless
  they pass `allow_retracted_parent: true`.
- Descendant experiments can check exposure via
  `GET /experiments/{id}/upstream-retractions`
  (`chronicle.experiments.get_upstream_retractions(id)` in the SDK).
- The retraction reason is indexed — searches surface it.

## Inputs

- **`experiment_id`** — the target experiment UUID (or the slug/name the
  user used; resolve via list/search or cwd detection, as in
  chronicle-delete-experiment).
- **`reason`** — required, non-empty. Written for the *next* researcher:
  say what is wrong and what invalidated it ("normalization bug in the
  dataset loader skewed every eval metric"), not just "bad".
- **`variation`** — optional variation index, when only one variation's
  results are wrong. Retracting the experiment covers all its variations;
  retracting a variation is independent and narrower.
- **`document_asset_id`** — optional `retraction_report` asset id, when a
  fuller writeup of the retraction exists (upload via
  chronicle-write-report first).
- **`confirmed`** — retraction is not destructive, but it invalidates
  outputs and archives the repo, so show the experiment (id, state,
  hypothesis) and the reason, and get an explicit go-ahead before flagging.

## Workflow

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 1. Show the user what they're about to retract.
detail = chronicle.experiments.get(experiment_id)
e = detail.experiment
print(f"{e.id}  [{e.state}]  {e.hypothesis_summary!r}")
if e.retracted_at:
    print(f"already retracted: {e.retraction_reason!r} — proceeding updates the reason")

# 2. On explicit confirmation: retract the experiment...
result = chronicle.experiments.retract(
    experiment_id,
    reason=reason,                        # required, non-empty
    document_asset_id=document_asset_id,  # optional retraction_report
)
print(f"retracted; outputs invalidated: {result['outputs_invalidated']}")

# ...or just one variation:
# chronicle.variations.retract(experiment_id, variation, reason=reason)
# (also available pre-bound: exp.variations.retract(variation, reason=...))

# 3. Optionally show what downstream work is now exposed:
exposed = chronicle.experiments.get_upstream_retractions(experiment_id)
```

## After the skill completes

Tell the user:

1. The experiment (or variation) retracted, with the recorded reason and
   the count of output assets invalidated.
2. That the record is preserved — lineage, audit trail, and the (now
   archived, read-only) GitHub repo — and the retraction is searchable.
3. That new experiments must pass `allow_retracted_parent: true` to build
   on it, and invalidated outputs need `allow_invalid_assets: true` to be
   linked as inputs.
4. If the user actually wanted a never-committed draft *gone*, point at
   chronicle-delete-experiment.

## Failure modes

- **403** — the caller lacks the `Delete` action on the experiment (the
  same action gates delete and retract). Surface verbatim.
- **404** — no such experiment (bad id, or it was hard-deleted as an open
  draft).
- **Retracted the wrong scope** — experiment-level retraction covers every
  variation; if only one variation was wrong, that's
  `chronicle.variations.retract(...)`. There is no un-retract endpoint, so
  confirm scope before flagging (re-retracting can update the reason, but
  the flag itself stays).

## MCP-native agents

An agent driving Chronicle through the MCP server (not the Python SDK) has
`chronicle.retract_experiment(experiment_id, reason, document_asset_id?)` —
the same `Delete`-gated soft flag, output invalidation, teardown, and repo
archival as the SDK/HTTP path, and the same idempotent reason update. Note
the split on the autonomous path: `chronicle.delete_experiment` carries a
creator guard (an agent may only hard-delete drafts it created), while
`chronicle.retract_experiment` is plain RBAC — retraction preserves the
record, so any holder of `Delete` may flag it. Variation-level retraction
has no MCP tool yet; use the SDK for that.

## Requires

- `pip install methodic-research`
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- No `git` — API-only; the repo archival happens server-side.
