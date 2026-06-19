---
name: chronicle-history-explorer
description: |
  Use this skill when the user wants to explore Chronicle experiment history
  read-only — phrases like "what experiments exist about X", "show me the
  lineage of experiment Y", "explore the history", "what have we tried in
  this area", "where did this experiment come from". The skill combines
  semantic search over past experiments and reports
  (`chronicle.search`), status-filtered browsing
  (`chronicle.list_experiments`), lineage DAG walks
  (`chronicle.get_lineage`), and retraction provenance
  (retracted ancestors in the lineage). Read-only; never
  mutates anything. Do not invoke for surveying external literature (that's
  `chronicle-research-survey`, which also hits the literature MCP) or for a
  fast "is anything on fire" run-status check (that's `chronicle-status`).
---

# History explorer

Read-only exploration of Chronicle's experiment history — the internal
corpus only (past experiments, their variations, and the reports attached
to them). Designed for "what's been done in this area, how does it connect,
and what's been retracted" questions. Never writes.

## Transport — MCP-direct (no SDK needed)

This is a read-only skill, so it uses the **bundled MCP tools** directly — no
`pip install`. (If the `methodic` SDK happens to be installed and you prefer it,
the SDK equivalents are noted inline.) The bundled launcher resolves credentials
from `~/.methodic` — see the repo README "The MCP tools (bundled — zero config)".

Three lenses, used together as the question demands:

- **Semantic** — `chronicle.search` finds past experiments and reports relevant
  to a topic, even without exact keyword matches.
- **Structural** — `chronicle.list_experiments` browses by lifecycle state;
  `chronicle.get_lineage` walks the parent/child DAG.
- **Provenance** — `chronicle.get_lineage` also surfaces retracted ancestors
  (entries with a non-null `retracted_at`) whose retraction undermines a node's
  premises. There is no dedicated upstream-retractions tool — read it off the
  lineage, the way `chronicle-status` does.

## Inputs

- **`query`** (optional) — a topic/keyword for semantic search. If present,
  lead with `chronicle.search`.
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

1. **Semantic search over experiment history + internal reports.** If `query`
   is present, call **`chronicle.search`** with `{ "query": "<query>",
   "asset_types": ["hypothesis_report", "takeaways_report", "research_report"] }`
   (add `created_by` / `created_after` / `created_before` when the user scoped by
   author or time window). The result (JSON in the tool's text content) is a list
   of hits referencing experiments and/or report assets — present each with its
   experiment id, the matched report type, and a snippet.

   *(SDK equivalent: `chronicle.search.history(query, created_by=…,
   created_after=…, created_before=…, asset_types=[…])`.)*

2. **Structural browse by lifecycle state.** If `status` is present, call
   **`chronicle.list_experiments`** with `{ "status": "<status>" }` (optionally
   an `owner`/scope filter). Cap the scan — print the first ~20:
   `id · hypothesis_summary[:60] · [state, retracted?]`. Don't page through
   everything.

   *(SDK equivalent: `chronicle.experiments.iter(status=…)`, breaking early.)*

3. **Lineage DAG for a specific node** — where it came from, what built on it.
   If `experiment_id` is present, call **`chronicle.get_lineage`** with
   `{ "experiment_id": "<id>" }`. The result has `ancestors[]` (parents up) and
   `descendants[]` (children down); show it as a short indented tree, one line
   each: `id · hypothesis_summary[:60]`.

   *(SDK equivalent: `chronicle.experiments.get_lineage(id)` →
   `lineage.ancestors` / `lineage.descendants`.)*

4. **Retraction provenance** — retracted ancestors invalidate premises. From the
   same `chronicle.get_lineage` result, flag any `ancestors[]` entry carrying a
   non-null `retracted_at` (with its `retraction_reason`). If any are present,
   call them out at the top — they change how everything downstream should be
   read. There is no separate upstream-retractions tool; this is read straight
   off the lineage.

   *(SDK equivalent: `chronicle.experiments.get_upstream_retractions(id,
   depth=5)` → `upstream.retractions`.)*

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

- **Search not configured** (`503` from `chronicle.search`): the
  server's search backend (Vertex AI Search) isn't wired in this
  environment. Fall back to the structural lenses — `chronicle.list_experiments`
  and `chronicle.get_lineage` still work without search — and tell the user
  semantic search is unavailable.
- **`experiment_id` not found / 403**: the experiment doesn't exist or the
  user lacks `Read` on it. Surface the message; for a 403, note that
  visibility is ACL-scoped (the user may need a grant).
- **Empty results**: no internal experiments/reports match. Say so plainly
  and suggest broadening the query or running
  `chronicle-research-survey` (which also searches external literature) — do
  not invent results.
- **Large lineage**: a deep DAG can return many nodes. Keep the depth bound
  and summarize counts ("12 descendants; showing the 5 most recent") rather
  than dumping the whole graph.

## Requires

Nothing to install — uses the bundled MCP tools (read-only; no git, no writes).
