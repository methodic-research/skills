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

Fast, read-only summary of one experiment (or the user's active experiments if
none specified). Answers "is anything on fire" without opening the web UI.

## Transport — MCP-direct (no SDK needed)

This is a read-only skill, so it uses the **bundled MCP tools** directly — no
`pip install`. (If the `methodic` SDK happens to be installed and you prefer it,
the SDK equivalents are noted inline.) The bundled launcher resolves credentials
from `~/.methodic` — see the repo README "The MCP tools (bundled — zero config)".

## Inputs

- **`experiment_id`** (optional) — single experiment to inspect. If omitted,
  list the caller's experiments and report each in brief.
- **`include_retracted_ancestors`** (default `True`) — also surface retracted
  parents/grandparents that affect this experiment's lineage validity.

## Workflow (single experiment)

1. Call **`chronicle.get_experiment`** with `{ "experiment_id": "<id>" }`. The
   result (JSON in the tool's text content) is an `ExperimentDetail`:
   `experiment` (id, `hypothesis_summary`, `state`, `created_at`/`created_by`,
   `retracted_at` + `retraction_reason`, `git_repo_state`) and `variations[]`
   (variation index, `name`, `committed_at`, `retracted_at`, `run_count`,
   `latest_status`).
2. If `include_retracted_ancestors`, call **`chronicle.get_lineage`** with
   `{ "experiment_id": "<id>" }` and flag any `ancestors[]` entry carrying a
   non-null `retracted_at` — those invalidate this experiment's premises.

Present a compact snapshot:
- Experiment line: id · `state` (+ `RETRACTED … reason` when set) · created by ·
  `git_repo_state` when it isn't `ready`.
- One line per variation: `name or v<index>` — `run_count` runs —
  `committed` / `retracted` / `last run: <status>` / `open`.
- A prominent `⚠ Upstream retractions` block if any ancestor is retracted.

*(SDK equivalent, if you prefer it: `chronicle.experiments.get(id)` →
`detail.experiment` / `detail.variations`, and
`experiments.get_upstream_retractions(id, depth=5)`.)*

## Workflow (no specific experiment)

Call **`chronicle.list_experiments`** (optionally with an `owner`/scope filter)
and print the first ~20: `id · hypothesis_summary[:60] · [state, retracted?]`.
Don't page through everything.

*(SDK equivalent: `chronicle.experiments.iter()`, breaking early.)*

## After the skill completes

If anything looks off (recent failures, retracted ancestors, repo in `failed`
state), surface it prominently — don't bury it under the normal output.

## Requires

Nothing to install — uses the bundled MCP tools (read-only; no git, no writes).
