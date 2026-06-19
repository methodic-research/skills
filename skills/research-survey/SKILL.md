---
name: chronicle-research-survey
description: |
  Use this skill when the user wants to survey prior art before starting
  work — phrases like "survey the literature on X", "what's been tried for
  Y", "research <topic> before I design an experiment", "is there prior art
  on this". The skill does a two-source survey: (a) Chronicle's INTERNAL
  corpus — past experiments, their lineage, and internal research docs —
  via `chronicle.search.history(...)`, and (b) external arxiv/papers via the
  configured literature MCP. It then synthesizes a prior-art + gaps summary
  for the user and OPTIONALLY persists it as a `research_report` asset. Do
  not invoke this for turning a hypothesis into an experiment (that's
  `chronicle-propose-experiment`) or for read-only browsing of experiment
  history alone (that's `chronicle-history-explorer`).
---

# Research survey

Survey what's already known about a research question before committing
effort to it. The end state is a synthesized prior-art summary that
separates *what's been tried* (internal experiment history + internal
research docs) from *what the field has published* (external literature),
and names the gaps that motivate a new experiment. Optionally saved back
to Chronicle as a `research_report`.

## Transport — MCP-direct (hybrid)

The Chronicle-internal half uses the **bundled MCP tools** directly — no
`pip install`: `chronicle.search` (history), `chronicle.get_lineage`,
`chronicle.list_experiments`, and the optional save via `chronicle.write_report`
(kind `research_report`). The bundled launcher resolves credentials from
`~/.methodic` — see the repo README "The MCP tools (bundled — zero config)".
(If the `methodic` SDK happens to be installed and you prefer it, the SDK
equivalents are noted inline.)

This skill is **hybrid by design** for a different reason than missing tools:
the EXTERNAL literature half goes through a *separate* literature MCP server
(e.g. Paperclip), not Chronicle — leave it exactly as it is. And the
synthesis step is **agent-native** (a local Claude session, no tool at all,
no server LLM call). So: MCP-direct for the Chronicle corpus, the external
literature MCP untouched, and the synthesis done in-context.

This skill reads two corpora that do NOT overlap:

- **Chronicle internal** — your org's own experiment history and internal
  research documents (`hypothesis_report`, `takeaways_report`,
  `research_report`). Reached via `chronicle.search` + `chronicle.list_experiments`.
  Arxiv/published papers are **not** in here.
- **External literature** — arxiv and the published record, reached via
  the configured literature MCP (e.g. Paperclip). If no literature MCP is
  configured, say so and proceed with Chronicle-internal results only.

## Inputs

- **`topic`** — the research question or subject to survey. Required.
  Prompt if the user was vague ("research diffusion models" → ask which
  aspect).
- **`experiment_context`** (optional) — one or more experiment UUIDs to
  bias the internal search toward a subgraph of related work. If the user
  is already working inside an experiment, default to that experiment's id
  plus its lineage (see resolution below).
- **`created_after`** / **`created_before`** (optional) — bound the
  internal-history search by time when the user wants "recent" prior art.
- **`save_as_report`** (default `False`) — whether to persist the synthesis
  as a `research_report`. Only flip to `True` when the user explicitly
  asks to save it, and only when there's an experiment to attach it to.

## Workflow

1. **Resolve internal search context.** If the user is inside an experiment
   (`anchor_experiment_id`) and no explicit `experiment_context` was given,
   call **`chronicle.get_lineage`** with `{ "experiment_id":
   "<anchor_experiment_id>" }` and widen the context to the whole research
   subgraph: `[anchor_experiment_id] + ancestors[].id + descendants[].id`
   from the result JSON. Otherwise use the explicit ids (or none).

   *(SDK equivalent: `chronicle.experiments.get_lineage(anchor_experiment_id)`
   → `lineage.ancestors` / `lineage.descendants`.)*

2. **Search Chronicle's internal corpus** — past experiments + research
   docs. Call **`chronicle.search`** with `{ "query": <topic>,
   "experiment_context": <context or omit>, "created_after":
   <created_after>, "created_before": <created_before>, "filters":
   { "asset_types": ["hypothesis_report", "takeaways_report",
   "research_report"] } }`. This is semantic search scoped to experiment
   history and the internal research documents — NOT arxiv. The result JSON
   is the internal hits.

   *(SDK equivalent: `chronicle.search.history(topic,
   experiment_context=…, created_after=…, created_before=…,
   asset_types=[…])`.)*

3. **Pull the related experiments themselves** for the "what's been tried"
   column — committed/concluded ones are the strongest prior art. Call
   **`chronicle.list_experiments`** (e.g. filtered to `concluded` then
   `committed` status). The agent decides in-context whether each entry's
   `hypothesis_summary` is on-topic; cap the scan (~40) and stop early —
   don't page through everything.

   *(SDK equivalent: `chronicle.experiments.iter(status="concluded")` /
   `status="committed"`, breaking early.)*

4. **External literature via the configured literature MCP** — UNCHANGED.
   There is NO Chronicle tool for arxiv — use the *separate* literature
   MCP's paper-search tools (e.g. Paperclip). The agent issues those tool
   calls directly, here, with `topic` (and any refinements) as the query.
   If no literature MCP is configured in this session, skip this step and
   note the gap in the synthesis ("external literature not surveyed — no
   literature MCP configured").

5. **Synthesize** — agent-native, no tool. THE AGENT does this in-context
   (local Claude session) — no server LLM call, no direct Anthropic/OpenAI
   HTTP. Produce a structured prior-art + gaps writeup:
   - What's been tried internally (cite experiment ids + report titles)
   - What the literature says (cite papers from the MCP results)
   - The gap: what neither has resolved, i.e. what a new experiment would
     actually add.

6. **OPTIONALLY persist the synthesis as a `research_report`.** Only when
   `save_as_report` is set and there's an `anchor_experiment_id`. Call
   **`chronicle.write_report`** with `{ "experiment_id":
   "<anchor_experiment_id>", "kind": "research_report", "title":
   "Prior-art survey: <topic>", "body": <synthesis_markdown> }`. The result
   JSON carries the new asset `id`; report "Saved survey as research_report
   asset `<id>`".

   *(SDK equivalent: `exp.reports.research.render(payload={"title": …,
   "body": …})`, or the lower-level `chronicle.assets.create_inline(
   asset_type="research_report", content=…, output_of={"experiment_id":
   …})`.)*

## After the skill completes

Present the synthesis to the user in three compact sections:

1. **Tried internally** — bulleted, each line citing an experiment id (and
   its plaintext handle/hypothesis) plus the relevant report. Note
   conclusions and any retractions.
2. **Published literature** — bulleted, each line citing a paper from the
   literature MCP (title + identifier). If the MCP wasn't available, say so
   explicitly rather than silently omitting the section.
3. **Gap** — one short paragraph: what a new experiment would add that
   neither corpus already covers. This is the hand-off to
   `chronicle-propose-experiment`.

If `save_as_report` was set, tell the user the `research_report` asset id
and which experiment it's linked to.

## Failure modes

- **Search not configured** (`503` from `chronicle.search`): the server's
  search backend (Vertex AI Search) isn't wired in this environment. Tell
  the user internal search is unavailable, fall back to
  `chronicle.list_experiments` + `chronicle.get_lineage` for a best-effort
  "what's been tried" pass, and still run the external literature MCP if
  present.
- **No literature MCP configured**: there's no arxiv/paper search tool in
  this session. Don't fabricate citations. State plainly that external
  literature wasn't surveyed and proceed with Chronicle-internal results
  only.
- **`save_as_report` requested but no experiment to attach to**: a
  `research_report` must hang off an experiment via `output_of`. Tell the
  user to either name an experiment or create one first
  (`chronicle-propose-experiment`), and present the synthesis inline
  without saving.
- **`write_report` returns 403**: the user lacks `Write` on the target
  experiment. Surface the message verbatim and present the synthesis inline
  instead of persisting it.

## Requires

- Nothing to install for the Chronicle half — uses the bundled MCP tools
  (`chronicle.search` / `get_lineage` / `list_experiments` / `write_report`).
- Credentials resolved from `~/.methodic` (or `CHRONICLE_API_KEY` exported).
- A configured literature MCP (e.g. Paperclip) for the external half —
  optional; the skill degrades gracefully to Chronicle-internal-only.
- No `git`, no repo clone — this skill reads and (optionally) writes one
  asset.
