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

Thin wrapper over the SDK's `chronicle.collections` namespace + `chronicle.search`.
**User-request-driven**: only curate or scope when the user asks for it.

## Create + add members

```python
from methodic import Chronicle
chronicle = Chronicle.from_env()

col = chronicle.collections.create("Magento hydrodynamics",
                                   description="papers + experiments on …")
# Members are ANY assets and/or experiments — overlap across collections is fine.
chronicle.collections.add(col["id"],
                          asset_ids=[paper1, paper2],   # imported PDFs, datasets, reports, arxiv …
                          experiment_ids=[exp_a])
```

`add`/`remove` take `reindex_mode` (`"lazy"` default — search reflects the change
on the normal reindex cadence; `"eager"` — restamp promptly when the user wants
to search the collection right away). The Postgres membership write is immediate
regardless of mode.

## Two ways a collection affects search

**Associate with an experiment (boost).** Members float up when searching in
that experiment's context:
```python
chronicle.collections.associate(experiment_id, [col["id"]])
```

**Scope a search (hard filter) — only when the user asks.** Restrict results to
a collection's members (and/or experiments):
```python
hits = chronicle.search.query("turbulence onset",
                              scope={"collections": [col["id"]]})
```
Default behaviour is to **search broadly** (no `scope`). Add a scope only on an
explicit "search within …" request.

## Existence-only access (important)

A collection's ACL is **existence-only** — it gates knowing the collection
exists, never reading its members. `members(id)` returns only the members the
caller can already read; counts don't leak hidden ones. Adding a member needs
`Write` on the collection **and** `Read` on the member, and changes no
permissions anywhere — so scoping/boosting can never reveal something the user
couldn't already see.

## MCP-native agents

`chronicle.collection_add` (with `reindex_mode`) and
`chronicle.collection_associate`; `chronicle.search` accepts `scope`. Same
existence-only + user-request-driven rules.

## After the skill completes

Tell the user the collection id + what was added/associated; for a scoped
search, say results were narrowed to the collection (and what a broad search
would add).

## Requires

- `pip install methodic-research` (the `chronicle.collections` namespace + `search(scope=…)`)
- `CHRONICLE_API_KEY` + `CHRONICLE_SERVER_URL` exported (or `methodic auth login`)
- CLI equivalent: `chronicle collections {create,list,show,add,remove,associate}`
