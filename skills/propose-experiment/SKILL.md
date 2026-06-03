---
name: chronicle-propose-experiment
description: |
  Use this skill when the user wants to turn a hypothesis into a new
  Chronicle experiment — phrases like "propose an experiment", "create an
  experiment for this hypothesis", "let's set up an experiment to test X",
  "spin up an experiment from what we just discussed". The skill drafts the
  hypothesis (short summary + full document), creates the experiment,
  attaches the full hypothesis as a `hypothesis_report`, creates and links
  a research prompt, and optionally commits (locks) the experiment. Do not
  invoke this for surveying prior art first (that's
  `chronicle-research-survey`) or for adding a variation to an experiment
  that already exists (that's `chronicle-prep-variation`).
---

# Propose experiment

Turn a hypothesis the user and the agent developed together into a
first-class Chronicle experiment. The end state is: a new experiment in
`open` (or `committed`, if the user asked to lock it) state, with a full
`hypothesis_report` attached and a `research_prompt` linked as its primary
anchor.

The hypothesis comes in two forms and you produce both:

- a **short summary** — one or two sentences, lives in
  `experiments.hypothesis_summary`, used for listing/filtering.
- a **full document** — the detailed hypothesis (background, claim,
  predictions, how it'll be measured), persisted as a `hypothesis_report`
  asset. The experiment **commit gate requires a `hypothesis_report`**, so
  this step is not optional if the user wants to lock the experiment.

## Inputs

- **`hypothesis_summary`** — short one/two-sentence claim. If the user gave
  a long description, the agent distills the summary in-context (local
  Claude session — no server LLM call). Prompt only if there's genuinely
  nothing to work from.
- **`hypothesis_document`** — the full hypothesis text (Markdown). The agent
  drafts this from the conversation; show it to the user for confirmation
  before creating the experiment.
- **`config_yaml`** — the experiment's seed config (variation 0's config).
  Resolve in order: explicit from the user → a config the prior
  `chronicle-research-survey` / discussion produced → prompt the user for a
  starting config (or offer a minimal template they can edit later).
- **`research_prompt`** — the high-level research goal this experiment
  anchors to. Default to a one-paragraph framing the agent writes from the
  hypothesis; confirm with the user.
- **`parent_experiment_ids`** (optional) — lineage parents if this
  experiment builds on prior ones (e.g. surfaced by a survey).
- **`commit`** (default `False`) — whether to lock the experiment at the
  end. Only `True` when the user explicitly asks to commit.

## Workflow

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# The experiment is created under the key's default org. If the user asked
# to create it in a different org they belong to, set the active scope first:
#   chronicle.active_org = "<org-principal-id>"
# (See the README "Active scope (org override)" convention.)

# 1. Create the experiment. hypothesis_summary is the short field;
#    config_yaml seeds variation 0.
exp = chronicle.experiments.create(
    hypothesis_summary=hypothesis_summary,
    config_yaml=config_yaml,
    rationale=rationale,                       # optional: why this is worth testing
    description=description,                    # optional: human-readable card text
    parent_experiment_ids=parent_experiment_ids or None,
)
print(f"Created experiment {exp.id} (open)")

# 2. Attach the FULL hypothesis as a hypothesis_report. The commit gate
#    requires this asset, so do it whether or not we commit now. `render`
#    in template mode fills the canonical hypothesis layout from a payload.
report = exp.reports.hypothesis.render(payload={
    "summary": hypothesis_summary,
    "body": hypothesis_document,               # the full Markdown doc
    # plus any structured fields the hypothesis template accepts
    # (predictions, measurement plan, etc.) the agent populated.
})
print(f"Attached hypothesis_report {report.id}")

# 3. Create and link a research prompt as the experiment's anchor.
#    research_prompts are immutable once created (just `prompt` text — no
#    title) and each experiment has exactly one primary. The experiment-
#    bound create() makes the prompt and links it as primary in one call.
rp = exp.research_prompts.create(research_prompt_text, primary=True)
print(f"Linked research prompt {rp['id']}")

# 4. OPTIONALLY commit (lock the specification). Only when the user asked.
#    Commit freezes inputs + config; new variations can still be added
#    after commit, but the hypothesis/config spec is locked.
if commit:
    chronicle.experiments.commit(exp.id)
    print(f"Committed experiment {exp.id}")
```

## After the skill completes

Tell the user:

1. The new experiment id (and its state — `open` or `committed`).
2. That the full hypothesis is saved as a `hypothesis_report` (id), and the
   short summary is on the experiment card.
3. The linked research prompt id.
4. The next steps: add variations with `chronicle-prep-variation`
   (or `chronicle-author-variation` to have the agent write the config
   edit), and — if not already committed — that the experiment must be
   committed before the first variation can be committed/run.

If `parent_experiment_ids` were set, mention the lineage link and remind
the user that retracted parents block new children unless
`allow_retracted_parent: true`.

## Failure modes

- **`experiments.create` returns 403**: the user lacks `Create`
  permission. Surface verbatim.
- **`commit` rejected — missing `hypothesis_report`**: should not happen
  because step 2 attaches it before step 4, but if the render in step 2
  failed and was skipped, commit will refuse. Re-run the report render,
  then re-attempt commit.
- **`commit` rejected — retracted parent**: a `parent_experiment_id` is
  retracted and `allow_retracted_parent` wasn't set. Tell the user; either
  drop the parent or re-create with the flag (a deliberate choice, not a
  silent default).
- **`research_prompts.create` returns 403 or a not-yet-available method**:
  the research-prompts namespace is being built concurrently. If the method
  is missing in the installed SDK, create the experiment + hypothesis_report
  anyway, tell the user the research-prompt link couldn't be made yet, and
  suggest attaching it later via
  `chronicle.research_prompts.attach(exp.id, rp_id, primary=True)`.
- **`config_yaml` invalid**: the server validates the seed config on
  create. Surface the validation error and let the user fix the YAML before
  retrying.

## Requires

- `pip install methodic-research` (≥ experiments + research-prompts release)
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- No `git` — this skill creates an experiment + assets via the API; the
  experiment's git repo is provisioned server-side and used later by the
  variation skills.
