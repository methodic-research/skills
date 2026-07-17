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

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. Every
step maps to a `chronicle.*` tool: `create_experiment`, `write_report` (kind
`hypothesis_report`), `create_research_prompt`, and the optional
`commit_experiment`. (If the `methodic` SDK happens to be installed and you
prefer it, the SDK equivalents are noted inline.) The bundled launcher
resolves credentials from `~/.methodic` — see the repo README "The MCP tools
(bundled — zero config)".

The experiment's claim comes in three pieces and you produce them:

- a **title** — a short heading (a handful of words; a noun phrase, not a
  sentence), lives in `experiments.title`. This is the experiment's display
  name in listings and the header. Keep it brief — resist packing the claim
  or its caveats into it; that's what the summary and document are for.
- a **short summary** — one or two sentences, lives in
  `experiments.hypothesis_summary`. A normal-length description of the claim,
  used for listing/filtering and shown under the title.
- a **full document** — the detailed hypothesis (background, claim,
  predictions, how it'll be measured), persisted as a `hypothesis_report`
  asset. The experiment **commit gate requires a `hypothesis_report`**, so
  this step is not optional if the user wants to lock the experiment.

## Inputs

- **`title`** — a short heading (aim for a handful of words; a noun phrase,
  not a sentence). Distil it from the hypothesis. This is only the display
  name — move all detail into the summary and the full document, and do not
  restate the whole claim here. If you genuinely can't form a short one, omit
  it (display falls back to the summary). Avoid verbose, sentence-long titles.
- **`hypothesis_summary`** — a one/two-sentence description of the claim
  (normal prose, not a title). If the user gave a long description, the agent
  distills the summary in-context (local agent session — no server LLM
  call). Prompt only if there's genuinely nothing to work from.
- **`hypothesis_document`** — the full hypothesis text (Markdown). The agent
  drafts this from the conversation; show it to the user for confirmation
  before creating the experiment. The Methodic UI renders the body inline
  with MathJax: `$…$` for inline math, `$$…$$` for display math — and when
  a display block spans multiple lines, each `$$` fence must sit **alone on
  its own line** (one equation block per fence pair; a fence opened or
  closed mid-line never terminates and swallows the headings after it).
  Same discipline as `chronicle-write-report`.
- **`config_yaml`** — the experiment's seed config (variation 0's config).
  Resolve in order: explicit from the user → a config the prior
  `chronicle-research-survey` / discussion produced → prompt the user for a
  starting config (or offer a minimal template they can edit later).
- **`research_prompt`** — the high-level research goal this experiment
  anchors to. Default to a one-paragraph framing the agent writes from the
  hypothesis; confirm with the user.
- **`parent_experiment_ids`** (optional) — lineage parents if this
  experiment builds on prior ones (e.g. surfaced by a survey). A parent that
  is still **open** (uncommitted) becomes a **tentative** link, not real
  lineage yet: it's recorded but excluded from lineage reads and **blocks this
  experiment's commit** until resolved (promote once the parent commits, or
  drop). `create_experiment` returns these in `tentative_parents` — see the
  workflow below. A committed/concluded parent links immediately.
- **`commit`** (default `False`) — whether to lock the experiment at the
  end. Only `True` when the user explicitly asks to commit.

## Workflow

1. **Create the experiment.** Call **`chronicle.create_experiment`** with
   `{ "title": <short heading>, "hypothesis_summary": <one/two-sentence
   description>, "config_yaml": <config_yaml>, "rationale": <optional: why
   this is worth testing>, "description": <optional: human-readable card
   text>, "parent_experiment_ids": <parent_experiment_ids or omit> }`. Keep
   `title` short (a noun phrase); the detail lives in `hypothesis_summary`
   and the full `hypothesis_report`. `config_yaml` seeds variation 0. The
   result is JSON in the tool's text content: the new experiment `id` and its
   `state` (`open`). Report "Created experiment `<id>` (open)".

   **If you passed `parent_experiment_ids`, inspect `tentative_parents` in the
   result.** Any entry there is a parent that was still open, so the link is
   tentative (excluded from lineage and a commit blocker until resolved). Tell
   the user which parents are tentative and that they must be resolved before
   commit — promote each once its parent commits
   (`chronicle.promote_lineage`), or drop it at commit (step 4). An empty/absent
   `tentative_parents` means every parent linked as real lineage.

   *(SDK equivalent: `chronicle.experiments.create(hypothesis_summary=…,
   config_yaml=…, rationale=…, description=…,
   parent_experiment_ids=… or None)` → `exp.id`; the open-parent links are
   `exp._create_response.tentative_parents`, also queryable any time via
   `chronicle.experiments.tentative_links(exp.id)`.)*

2. **Attach the FULL hypothesis as a `hypothesis_report`.** Call
   **`chronicle.write_report`** with `{ "experiment_id": "<id>", "kind":
   "hypothesis_report", "summary": <hypothesis_summary>, "body":
   <hypothesis_document> }` — pass the full Markdown doc as `body`, plus any
   structured fields the hypothesis layout accepts (predictions, measurement
   plan, etc.) the agent populated. The result JSON carries the new
   report asset `id`; report "Attached hypothesis_report `<id>`".

   The `hypothesis_report` is the experiment's **pre-registration**: it links
   as an experiment-level **input** and **freezes on commit**. So write it
   **before** committing (it's experiment-level — don't pass a `variation`),
   and do it whether or not we commit now — the commit gate requires this
   asset, and once committed it can no longer be changed.

   *(SDK equivalent: `exp.reports.hypothesis.render(payload={"summary": …,
   "body": …, …})` → `report.id`.)*

3. **Create and link a research prompt as the experiment's anchor.** Call
   **`chronicle.create_research_prompt`** with `{ "experiment_id": "<id>",
   "prompt": <research_prompt_text>, "primary": true }`. research_prompts
   are immutable once created (just `prompt` text — no title) and each
   experiment has exactly one primary. The result JSON carries the prompt
   `id`; report "Linked research prompt `<id>`".

   *(SDK equivalent: `exp.research_prompts.create(research_prompt_text,
   primary=True)` → `rp["id"]`.)*

3b. **Register + attach citations for the papers behind the hypothesis.**
   If literature informed the hypothesis — a survey
   (`chronicle-research-survey`) usually precedes this skill, or the user
   named papers directly — record each as a citation: call
   **`chronicle.register_publication`** with `{ "doi": … }` or
   `{ "arxiv": "<id or URL>" }` (dedup is automatic; a known work returns
   the existing asset), then **`chronicle.link_asset`**
   `{ "experiment_id": "<id>", "asset_id": "<publication id>",
   "link": "input" }`. Prior *experiments* it builds on are lineage
   (`parent_experiment_ids`, step 1) — cite a prior experiment's REPORT
   only when it informs without being an ancestor (pass
   `"propagate_acl": false` for one you don't administer). Citation links
   stay open after commit, so a late cite also works on a committed
   experiment.

   *(SDK equivalent: `chronicle.publications.register(doi=…/arxiv=…)` +
   `chronicle.experiments.add_inputs(...)`.)*

4. **OPTIONALLY commit (lock the specification).** Only when the user
   asked. Call **`chronicle.commit_experiment`** with `{ "experiment_id":
   "<id>" }`. Commit freezes inputs + config; new variations can still be
   added after commit, but the hypothesis/config spec is locked. Report
   "Committed experiment `<id>`".

   **If the experiment has tentative lineage links (step 1), commit refuses
   until you resolve every one** — there is no silent default. Add a
   `tentative_links` map naming each tentative parent: `{ "experiment_id":
   "<id>", "tentative_links": { "<parent_id>": "promote" | "drop" } }`.
   `promote` makes it real lineage but is only valid once that parent has
   itself committed (else commit errors — `drop` it or wait); `drop` discards
   the link. Confirm the disposition with the user rather than guessing.

   *(SDK equivalent: `chronicle.experiments.commit(exp.id,
   tentative_links={"<parent_id>": "drop"})`.)*

## After the skill completes

Tell the user:

1. The new experiment id (and its state — `open` or `committed`).
2. That the full hypothesis is saved as a `hypothesis_report` (id), and the
   title + short summary are on the experiment card.
3. The linked research prompt id.
4. The next steps: add variations with `chronicle-prep-variation`
   (or `chronicle-author-variation` to have the agent write the config
   edit), and — if not already committed — that the experiment must be
   committed before the first variation can be committed/run.

If `parent_experiment_ids` were set, mention the lineage link. Call out any
**tentative** parents (from `tentative_parents`/`tentative_links`) separately:
they aren't real lineage yet and will block commit until promoted (once the
parent commits) or dropped. Also remind the user that retracted parents block
new children unless `allow_retracted_parent: true`.

## Failure modes

- **`create_experiment` returns 403**: the user lacks `Create`
  permission. Surface verbatim.
- **`commit_experiment` rejected — missing `hypothesis_report`**: should
  not happen because step 2 attaches it before step 4, but if the
  `write_report` in step 2 failed and was skipped, commit will refuse.
  Re-run the report write, then re-attempt commit.
- **`write_report` (hypothesis) rejected — experiment is committed**: the
  hypothesis is pre-registration and froze at commit, so it can't be added or
  changed afterward. This only happens if step 2 was skipped/failed and the
  experiment was committed anyway; the hypothesis must be set before commit.
  Surface it — don't retry — and note the experiment would need a fresh
  (uncommitted) one to carry a different hypothesis.
- **`commit_experiment` rejected — unresolved tentative lineage links**: the
  experiment was created off one or more still-open parents and commit needs a
  disposition for each. Re-call `commit_experiment` with a `tentative_links`
  map (step 4): `promote` a parent that has since committed, `drop` the rest.
  The error body lists the unresolved parent ids.
- **`commit_experiment` rejected — retracted parent**: a
  `parent_experiment_id` is retracted and `allow_retracted_parent` wasn't
  set. Tell the user; either drop the parent or re-create with the flag (a
  deliberate choice, not a silent default).
- **`create_research_prompt` returns 403**: the user lacks authority to
  anchor the experiment. Create the experiment + hypothesis_report anyway,
  tell the user the research-prompt link couldn't be made yet, and suggest
  attaching it later.
- **`config_yaml` invalid**: the server validates the seed config on
  create. Surface the validation error and let the user fix the YAML before
  retrying.

## Requires

- Nothing to install — uses the bundled MCP tools
  (`chronicle.create_experiment` / `write_report` / `create_research_prompt`
  / `commit_experiment`).
- Credentials resolved from `~/.methodic` (or `CHRONICLE_API_KEY` exported).
- No `git` — this skill creates an experiment + assets via MCP; the
  experiment's git repo is provisioned server-side and used later by the
  variation skills.
