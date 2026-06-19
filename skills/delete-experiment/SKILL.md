---
name: chronicle-delete-experiment
description: |
  Use this skill when the user wants to permanently delete one or more
  **open (uncommitted)** Chronicle experiments — phrases like "delete this
  experiment", "remove that draft", "I/the agent created too many
  experiments, clean them up", "consolidate these experiments", "throw away
  the experiments I'm not using". The skill resolves the target
  experiment(s), shows the user exactly what will be removed, requires an
  explicit confirmation (delete is irreversible), then hard-deletes each
  open one via the SDK. Committed or concluded experiments are NOT deleted —
  the skill reports them and points the user at retraction
  (`chronicle-retract-experiment` / `chronicle.experiments.retract`)
  instead. Do not invoke this to undo results on a committed experiment
  (that's retraction) or to remove a single variation (that's a variation
  operation).
---

# Delete experiment

Hard-delete **open** Chronicle experiments — the right tool for cleaning up
drafts that were started and abandoned (e.g. an agent that spun up more
experiments than intended). The end state is: each targeted open experiment
and everything it owns (variations, runs, asset/research-prompt **links**,
ACLs, auto-roles, and best-effort its GitHub repo + search document) is gone.

This is distinct from **retraction**. Retraction is a soft flag that
preserves the row, lineage, and audit trail — the right tool for
committed/concluded work that is part of the historical record. Hard delete
physically removes a draft that was never committed, and the server **only
allows it while the experiment is open**. The skill never deletes committed
or concluded experiments; it reports them so the user can retract instead.

**Delete is irreversible.** Always confirm with the user before deleting,
and show them the concrete list first.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. (If the
`methodic` SDK happens to be installed and you prefer it, the SDK equivalents
are noted inline.) The bundled launcher resolves credentials from `~/.methodic`
— see the repo README "The MCP tools (bundled — zero config)".

`chronicle.delete_experiment` is **creator-guarded**: via MCP an agent may only
hard-delete experiments *it created*, even where `Delete` RBAC would allow more.
Deleting another principal's draft you hold `Delete` on goes through the SDK/HTTP
path. The open-only rule, the committed/concluded refusal, and the descendants
refusal are identical in both paths.

## Inputs

- **`experiment_ids`** — one or more experiment UUIDs (or short
  slugs/names the user used). Resolve in order:
  1. Explicit ids/slugs from the user.
  2. "The ones I just created" / "my unused drafts" → list the user's
     **open** experiments and propose the set (confirm before deleting).
  3. Detect a single experiment from cwd (a clone of an experiment repo) if
     the user means "this one".
  4. Prompt the user.
- **`confirmed`** (default `False`) — explicit go-ahead. Delete is
  irreversible, so **never** proceed without it. Showing the list and
  getting a "yes" is mandatory, even for a single experiment.

## Workflow

1. **Resolve the candidate set.** For "clean up the drafts I'm not using",
   call **`chronicle.list_experiments`** filtered to **open** experiments
   (e.g. `{ "status": "open" }`) and let the user pick / confirm. Pass
   `"owner": "_all"` to span every scope the caller can see; omit for just
   their personal scope. The result (JSON in the tool's text content) is a
   list of experiment summaries.

   *(SDK equivalent: `chronicle.experiments.iter(status="open")`.)*

2. **Show the user EXACTLY what will be deleted** — id, slug/name, hypothesis,
   state — and get an explicit confirmation. **Do NOT skip this.** For each
   target, call **`chronicle.get_experiment`** with
   `{ "experiment_id": "<id>" }` to make the preview concrete; the result is an
   `ExperimentDetail` whose `experiment` carries `id`, `state`, `slug`,
   `hypothesis_summary`. Present the list, then ask: **"Delete these N
   experiments? This is permanent and cannot be undone."** Proceed only on an
   explicit yes — getting a "yes" is mandatory, even for a single experiment.

   *(SDK equivalent: `chronicle.experiments.get(exp_id)` → `detail.experiment`.)*

3. **Delete each OPEN experiment.** For each confirmed target, first check its
   state via `chronicle.get_experiment` and **skip (and collect) anything not
   open** — the server would 409 it anyway, but checking first gives a cleaner
   report. For the open ones, call **`chronicle.delete_experiment`** with
   `{ "experiment_id": "<id>" }`. Collect what was deleted, what was skipped
   (not open), and any that failed (409 / 404 / 403).

   *(SDK equivalent: `chronicle.experiments.delete(exp_id)`.)*

4. **Report** how many were deleted, how many skipped (not open), and how many
   failed.

## After the skill completes

Tell the user:

1. Which experiments were deleted (ids + slugs) and, briefly, the removal
   summary the server returned (variations/runs/links/auto-roles removed).
2. Which were **skipped because they were committed or concluded**, and that
   those can't be hard-deleted — to take one out of use, **retract** it
   (`chronicle.retract_experiment` — see chronicle-retract-experiment), which
   flags it and auto-invalidates its output assets while preserving the record.
3. Any that **failed** and why (verbatim server message).
4. That the underlying **asset rows/bytes** were intentionally left intact
   (they may be shared across experiments); only the deleted experiments'
   link rows were removed. Assets that are now **unlinked everywhere**
   (orphans) can be purged with chronicle-delete-asset
   (`chronicle.delete_asset`) if the user wants them gone too.

## Failure modes

- **409 — "committed or concluded; hard delete is only allowed while open.
  Retract it instead."**: the experiment was committed/concluded between the
  preview and the delete (or the user pointed at one directly). Don't retry
  the delete — offer retraction instead.
- **409 — "experiment has descendants …"**: another experiment recorded this
  one as **explicit** lineage (only possible once it had committed). Deleting
  would orphan formed lineage. Surface the message; the user must remove the
  dependent experiment(s) first, or retract instead. (Tentative fork edges
  off an open draft do **not** block deletion — they're dropped in the
  cascade.)
- **403**: the caller lacks the `Delete` action on the experiment. Surface
  verbatim.
- **404**: no such experiment (already deleted, or a bad id). Treat as
  already-gone in a cleanup loop; don't error the whole run.
- **Resolved the wrong set**: if you derived candidates from a list/heuristic
  rather than explicit ids, the confirmation step is the safety net —
  re-list and re-confirm rather than guessing.

For retraction the MCP tool is `chronicle.retract_experiment` — see
chronicle-retract-experiment; unlike delete it has no creator guard (retraction
preserves the record, so any holder of `Delete` may flag it).

## Requires

Nothing to install — uses the bundled MCP tools. (API-only operation; the
experiment's repo is torn down server-side as part of the delete; no `git`.)
