---
name: chronicle-history-explorer
description: |
  Use this skill when the user wants to explore Chronicle experiment history
  read-only — phrases like "what experiments exist about X", "show me the
  lineage of experiment Y", "explore the history", "what have we tried in
  this area", "where did this experiment come from". The skill combines
  semantic search over past experiments and reports
  (`chronicle.search.history`), status-filtered browsing
  (`chronicle.experiments.iter`), lineage DAG walks
  (`chronicle.experiments.get_lineage`), and retraction provenance
  (`chronicle.experiments.get_upstream_retractions`). Read-only; never
  mutates anything. Do not invoke for surveying external literature (that's
  `chronicle-research-survey`, which also hits the literature MCP) or for a
  fast "is anything on fire" run-status check (that's `chronicle-status`).
---

# History explorer

Read-only exploration of Chronicle's experiment history — the internal
corpus only (past experiments, their variations, and the reports attached
to them). Designed for "what's been done in this area, how does it connect,
and what's been retracted" questions. Never writes.

Three lenses, used together as the question demands:

- **Semantic** — `chronicle.search.history(...)` finds past experiments and
  reports relevant to a topic, even without exact keyword matches.
- **Structural** — `chronicle.experiments.iter(status=...)` browses by
  lifecycle state; `chronicle.experiments.get_lineage(id)` walks the
  parent/child DAG.
- **Provenance** — `chronicle.experiments.get_upstream_retractions(id)`
  surfaces retracted ancestors whose retraction undermines a node's
  premises.

## Inputs

- **`query`** (optional) — a topic/keyword for semantic search. If present,
  lead with `search.history`.
- **`experiment_id`** (optional) — a specific experiment to anchor on. If
  present, lead with lineage + retraction provenance for that node.
- **`status`** (optional) — filter browsing to `open` / `committed` /
  `concluded`. If the user says "show concluded experiments about X",
  combine with `query`.
- **`created_by`** / **`created_after`** / **`created_before`** (optional) —
  scope the semantic search by author or time window.

At least one of `query` or `experiment_id` should be present; if neither,
fall back to a brief status-grouped listing (like `chronicle-status`'s
no-experiment path) and ask the user to narrow.

## Workflow

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 1. Semantic search over experiment history + internal reports.
if query:
    hits = chronicle.search.history(
        query,
        created_by=created_by,          # optional author filter
        created_after=created_after,    # optional time bounds
        created_before=created_before,
        asset_types=["hypothesis_report", "takeaways_report", "research_report"],
    )
    for h in hits:
        # hits reference experiments and/or report assets — present each
        # with its experiment id, the matched report type, and a snippet.
        print(f"  {h}")

# 2. Structural browse by lifecycle state. Cap the scan — break early.
if status:
    print(f"\n{status} experiments:")
    shown = 0
    for summary in chronicle.experiments.iter(status=status):
        badges = [summary.state]
        if summary.retracted_at:
            badges.append("retracted")
        print(f"  {summary.id}  {summary.hypothesis_summary[:60]}  [{', '.join(badges)}]")
        shown += 1
        if shown >= 20:
            break

# 3. Lineage DAG for a specific node — where it came from, what built on it.
if experiment_id:
    lineage = chronicle.experiments.get_lineage(experiment_id)
    print(f"\nLineage of {experiment_id}:")
    for anc in lineage.ancestors:
        print(f"  ↑ parent  {anc.id}  {anc.hypothesis_summary[:60]}")
    for desc in lineage.descendants:
        print(f"  ↓ child   {desc.id}  {desc.hypothesis_summary[:60]}")

    # 4. Retraction provenance — retracted ancestors invalidate premises.
    upstream = chronicle.experiments.get_upstream_retractions(experiment_id, depth=5)
    if upstream.has_retractions:
        print("\n⚠ Upstream retractions in lineage:")
        for r in upstream.retractions:
            print(f"  exp {r.experiment_id} retracted at {r.retracted_at}: {r.reason}")
```

## After the skill completes

Present results **compactly** — this is exploration, so density beats
verbosity:

- Lead with the most relevant hits (semantic matches or the anchored node),
  one line each: experiment id, plaintext handle/hypothesis, lifecycle
  state, key badges (retracted, concluded).
- For a lineage query, show the DAG as a short indented tree (parents up,
  children down) rather than prose.
- **Surface retractions prominently.** If any ancestor in a node's lineage
  is retracted, call it out at the top — it changes how the user should
  read everything downstream of it.
- Offer the obvious next move: a survey (`chronicle-research-survey`) if the
  user is scoping new work, or a status check (`chronicle-status`) if they
  want run-level detail on one of the surfaced experiments.

## Failure modes

- **Search not configured** (`503` from `chronicle.search.history`): the
  server's search backend (Vertex AI Search) isn't wired in this
  environment. Fall back to the structural lenses — `experiments.iter()`
  and `get_lineage()` still work without search — and tell the user
  semantic search is unavailable.
- **`experiment_id` not found / 403**: the experiment doesn't exist or the
  user lacks `Read` on it. Surface the message; for a 403, note that
  visibility is ACL-scoped (the user may need a grant).
- **Empty results**: no internal experiments/reports match. Say so plainly
  and suggest broadening the query or running
  `chronicle-research-survey` (which also searches external literature) — do
  not invent results.
- **Large lineage**: a deep DAG can return many nodes. Keep the depth bound
  (`depth=5` above) and summarize counts ("12 descendants; showing the 5
  most recent") rather than dumping the whole graph.

## Requires

- `pip install methodic-research` (≥ search-enabled release for the semantic
  lens; the structural + provenance lenses work without it)
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- No `git`, no writes — purely read.
