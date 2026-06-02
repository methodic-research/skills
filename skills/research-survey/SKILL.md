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

This skill reads two corpora that do NOT overlap:

- **Chronicle internal** — your org's own experiment history and internal
  research documents (`hypothesis_report`, `takeaways_report`,
  `research_report`). Reached via `chronicle.search.*`. Arxiv/published
  papers are **not** in here.
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

```python
from methodic import Chronicle
from methodic.search import SearchFilters

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 1. Resolve internal search context. If the user is inside an experiment,
#    widen to its lineage so we survey the whole research subgraph, not
#    just the one node.
experiment_context = explicit_experiment_ids or []
if anchor_experiment_id and not experiment_context:
    lineage = chronicle.experiments.get_lineage(anchor_experiment_id)
    experiment_context = [anchor_experiment_id] + [
        e.id for e in lineage.ancestors + lineage.descendants
    ]

# 2. Search Chronicle's internal corpus: past experiments + research docs.
#    `history` is semantic search scoped to experiment history and the
#    internal research documents — NOT arxiv.
internal_hits = chronicle.search.history(
    topic,
    experiment_context=experiment_context or None,
    created_after=created_after,    # optional bounds
    created_before=created_before,
    asset_types=["hypothesis_report", "takeaways_report", "research_report"],
)

# 3. Pull the related experiments themselves for the "what's been tried"
#    column — committed/concluded ones are the strongest prior art.
related_experiments = []
for status in ("concluded", "committed"):
    for summary in chronicle.experiments.iter(status=status):
        # cheap relevance gate: the agent decides in-context whether the
        # hypothesis_summary is on-topic. Cap the scan — break early.
        related_experiments.append(summary)
        if len(related_experiments) >= 40:
            break

# 4. External literature via the configured literature MCP.
#    There is NO Chronicle SDK call for arxiv — use the MCP's paper-search
#    tools (e.g. Paperclip). The agent issues those tool calls directly,
#    here, with `topic` (and any refinements) as the query. If no literature
#    MCP is configured in this session, skip this step and note the gap in
#    the synthesis ("external literature not surveyed — no literature MCP
#    configured").

# 5. Synthesize. THE AGENT does this in-context (local Claude session) —
#    no server LLM call, no direct Anthropic/OpenAI HTTP. Produce a
#    structured prior-art + gaps writeup:
#      - What's been tried internally (cite experiment ids + report titles)
#      - What the literature says (cite papers from the MCP results)
#      - The gap: what neither has resolved, i.e. what a new experiment
#        would actually add.
synthesis_markdown = "...the agent writes this from the two corpora above..."

# 6. OPTIONALLY persist the synthesis as a research_report.
if save_as_report and anchor_experiment_id:
    report = chronicle.experiments.get(anchor_experiment_id)  # handle
    asset = chronicle.assets.create_inline(
        asset_type="research_report",
        content=synthesis_markdown,
        output_of={"experiment_id": anchor_experiment_id},
    )
    print(f"Saved survey as research_report asset {asset.id}")
```

When an experiment handle is available, the report can also be rendered
through the typed path instead of `create_inline`:

```python
exp = chronicle.experiments.get(anchor_experiment_id)
report = exp.reports.research.render(payload={
    "title": f"Prior-art survey: {topic}",
    "body": synthesis_markdown,
})
```

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

- **Search not configured** (`503` from `chronicle.search.*`): the server's
  search backend (Vertex AI Search) isn't wired in this environment. Tell
  the user internal search is unavailable, fall back to
  `experiments.iter()` + `get_lineage()` for a best-effort "what's been
  tried" pass, and still run the external literature MCP if present.
- **No literature MCP configured**: there's no arxiv/paper search tool in
  this session. Don't fabricate citations. State plainly that external
  literature wasn't surveyed and proceed with Chronicle-internal results
  only.
- **`save_as_report` requested but no experiment to attach to**: a
  `research_report` must hang off an experiment via `output_of`. Tell the
  user to either name an experiment or create one first
  (`chronicle-propose-experiment`), and present the synthesis inline
  without saving.
- **`create_inline` / report render returns 403**: the user lacks `Write`
  on the target experiment. Surface the message verbatim and present the
  synthesis inline instead of persisting it.

## Requires

- `pip install methodic-research` (≥ search-enabled release)
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- A configured literature MCP (e.g. Paperclip) for the external half —
  optional; the skill degrades gracefully to Chronicle-internal-only.
- No `git`, no repo clone — this skill reads and (optionally) writes one
  asset.
