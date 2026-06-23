---
name: chronicle-task
description: |
  Use this skill when you are an agent **executing a Chronicle task** — a
  discrete, steered unit of work launched from the Tasks surface
  (designs/tasks.md), with its context (an experiment, dataset, or asset)
  **auto-injected**. Your launch env carries the task id (`AGENT_TASK_ID` / the
  session-asset id); the *what* comes from your steer. Triggers: "work on this
  task", "do the task", "generate a dataset for this experiment and register
  it", "gather and summarize this experiment's results", or any time you're
  driving a task session and need to (1) discover your injected context, (2) do
  the work with the existing Chronicle skills, and (3) record what you produced
  back to the task. This skill is **generic** — it owns the task *mechanics*
  (read context · do steered work · document outputs), never domain behavior.
  For the byte/registration mechanics of a specific output, defer to the
  purpose-built skills (chronicle-register-dataset, chronicle-write-report,
  chronicle-dataset). NOT for creating/launching a task (that's the SPA /
  `POST /v1/tasks`) — this is for an agent *inside* one.
---

# Execute a task

Drive one Chronicle **task** to its result. A task is a generic, steerable
`agent_session` (`session_mode = task`) for a unit of work that isn't an
experiment's main research loop — prepping a dataset, summarizing an
experiment's results, a one-off analysis. The end state is: the steered work
done, and every asset you produced **linked back to the task** (its provenance)
and wired to its experiment where the steer implies it.

**This skill owns three mechanics only — the *what* is your steer:**

1. **Read your injected context.** Don't ask the user what experiment/dataset
   you're working with — it was auto-injected when the task launched. Resolve it:

   ```
   chronicle.get_task(task_id)        # task_id from your launch env (AGENT_TASK_ID)
   → { title, inputs: [{target_type: "experiment"|"asset", target_id}], outputs: [...] }
   ```

   Then ground on each input — `chronicle.get_experiment` / `chronicle.search`
   (scoped to the experiment) for an `experiment` ref; the asset read / `load`
   tools for an `asset` (a dataset, a report) ref. Your scoped key can read
   exactly this context and no more — that *is* the boundary.

2. **Do the steered work**, composing the purpose-built skills rather than
   reimplementing them:
   - generate / register a dataset → **chronicle-register-dataset** (by-reference
     + metadata) or **chronicle-dataset** (byte upload);
   - write a summary / takeaways → **chronicle-write-report**;
   - anything else the steer asks — you have the full methodic skill set.

3. **Document your outputs** (the one thing that must not be implicit). After
   creating an asset:

   ```
   chronicle.link_task_output(task_id, asset_id)     # provenance: this task made it
   ```

   and, when the steer ties it to an experiment, **also** wire it there — the two
   links are independent:

   ```
   chronicle.link_asset(experiment_id, asset_id, link="input"|"output")
   ```

## The two canonical shapes

**"Generate a dataset for experiment X."** `get_task` → an `experiment` input
(X). Build/locate the dataset bytes; register it (chronicle-register-dataset);
`link_task_output(task, dataset)`; then `link_asset(X, dataset, "input")` — the
dataset X *consumes* (task output → experiment input, the design's "bridge").

**"Summarize experiment X's results."** `get_task` → an `experiment` input (X).
Read X's runs/reports/outputs (`chronicle.search` + `chronicle.get_experiment` +
`chronicle.list_outputs`); write the summary (chronicle-write-report);
`link_task_output(task, report)`. The summary is the task's output, surfaced on
X via the task↔experiment association.

## After the task

Tell the user:
1. The task title + the assets produced (with their ids).
2. For each, where it's linked — to the task (always) and to an experiment
   (when applicable), so the provenance is legible.
3. Anything the steer asked for that you could **not** do within your injected
   read-scope (you can't reach experiments/assets outside your `task_inputs`).

## Failure modes

- **No task id in env** — you're not in a task session, or the launcher didn't
  set `AGENT_TASK_ID`. Ask the caller for the task id rather than guessing; don't
  fabricate one.
- **Context ref unreadable** — your scoped key only reaches your `task_inputs`.
  A 403/empty on something outside them is expected; surface it, don't try to
  widen scope.
- **`link_task_output` refused (not Administer)** — your task key lacks
  `Administer` on the task; surface the error (don't silently skip recording the
  output — the provenance matters).
- **Asset created but un-linked** — never leave a produced asset only in your
  conversation: a task's outputs must be `link_task_output`'d so they show on the
  task and on the asset's "produced by task" line.

## Requires

- `chronicle.get_task` + `chronicle.link_task_output` (the task MCP surface).
- The sibling skills it composes: `chronicle-register-dataset`,
  `chronicle-dataset`, `chronicle-write-report`, and `chronicle.link_asset` /
  `chronicle.get_experiment` / `chronicle.search` / `chronicle.list_outputs`.
