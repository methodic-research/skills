---
name: chronicle-collections
description: |
  Use this skill ONLY when the user explicitly asks to organize research into a
  collection — "make a collection for <topic>", "add these papers to the
  structural-loads collection", "group these experiments under hydrodynamics",
  "associate this experiment with the <topic> collection", "search only within
  the <topic> collection". A collection is a named, ACL'd topic grouping that
  holds ANY assets (imported PDFs, datasets, reports, arxiv refs) AND experiments
  — overlapping is fine. Two uses: (a) ASSOCIATE a collection with an experiment
  so searches run in that experiment's context surface its members (a boost), and
  (b) SCOPE a search to a collection as a hard filter. Do NOT scope searches to a
  collection on your own initiative — search broadly by default; only narrow when
  the user asks. For keyword-labelling individual assets/experiments use
  chronicle-tags; for plain prior-art search use chronicle-research-survey.
---

# Collections — curate a topic grouping of assets + experiments

A **collection** is a heavyweight, named grouping centred on a topic (e.g. a
"structural loads" or "magento hydrodynamics" collection of papers + relevant
experiments). It is **curatorial** — membership organizes and surfaces things;
it never grants access. Collections **overlap** (an object can be in many), span
any asset type AND experiments, and are scope-owned (personal / team / org).

**User-request-driven**: only curate or scope when the user asks for it.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. (If the
`methodic` SDK happens to be installed and you prefer it, the SDK equivalents are
noted inline.) The bundled launcher resolves credentials from `~/.methodic` — see
the repo README "The MCP tools (bundled — zero config)".

## Create + add members

1. Call **`chronicle.collection_add`** with `{ "name": "Magento hydrodynamics",
   "description": "papers + experiments on …", "asset_ids": [paper1, paper2],
   "experiment_ids": [exp_a] }`. This creates the collection if it doesn't exist
   and adds the members in one call. Members are ANY assets and/or experiments —
   imported PDFs, datasets, reports, arxiv refs, experiments — and overlap across
   collections is fine. The result (JSON in the tool's text content) carries the
   collection `id`.

   Pass `reindex_mode` when relevant: `"lazy"` (default — search reflects the
   change on the normal reindex cadence) or `"eager"` (restamp promptly when the
   user wants to search the collection right away). The Postgres membership write
   is immediate regardless of mode.

   *(SDK equivalent: `chronicle.collections.create(name, description=…)` then
   `chronicle.collections.add(col["id"], asset_ids=[…], experiment_ids=[…],
   reindex_mode=…)`.)*

## Two ways a collection affects search

**Associate with an experiment (boost).** Members float up when searching in that
experiment's context:

2. Call **`chronicle.collection_associate`** with `{ "experiment_id": "<id>",
   "collection_ids": ["<col_id>"] }`.

   *(SDK equivalent: `chronicle.collections.associate(experiment_id,
   [col["id"]])`.)*

**Scope a search (hard filter) — only when the user asks.** Restrict results to a
collection's members (and/or experiments):

3. Call **`chronicle.search`** with `{ "query": "turbulence onset",
   "scope": { "collections": ["<col_id>"] } }`.

   Default behaviour is to **search broadly** (no `scope`). Add a scope only on
   an explicit "search within …" request.

   *(SDK equivalent: `chronicle.search.query("turbulence onset",
   scope={"collections": [col["id"]]})`.)*

## Existence-only access (important)

A collection's ACL is **existence-only** — it gates knowing the collection
exists, never reading its members. Listing members returns only the members the
caller can already read; counts don't leak hidden ones. Adding a member needs
`Write` on the collection **and** `Read` on the member, and changes no
permissions anywhere — so scoping/boosting can never reveal something the user
couldn't already see.

## After the skill completes

Tell the user the collection id + what was added/associated; for a scoped
search, say results were narrowed to the collection (and what a broad search
would add).

## Requires

Nothing to install — uses the bundled MCP tools.
