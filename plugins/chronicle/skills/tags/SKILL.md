---
name: chronicle-tags
description: |
  Use this skill ONLY when the user explicitly asks to tag something or filter by
  tag — "tag this as turbulence", "tag these experiments turbulence", "what's
  tagged turbulence", "find assets tagged X", "search only things tagged Y". A tag
  is a lightweight, scope-namespaced keyword attached to ANY asset (imported
  PDFs, datasets, reports, arxiv refs) OR experiment; the same tag marks many
  objects, and search can filter by tag. Tagging is USER-REQUEST-DRIVEN — do NOT
  tag things or filter searches by tag on your own initiative; search broadly by
  default. For heavyweight topic groupings you scope/boost searches around use
  chronicle-collections; tags are the lighter keyword layer.
---

# Tags — keyword-label assets + experiments

A **tag** is a lightweight, scope-namespaced keyword (a hashtag) you attach to
any asset or experiment for filtering. The same tag can mark many objects across
asset types and experiments. Tags are **not** access controls — you need
`Write` on the *object* to tag it; the tag itself grants nothing.

**User-request-driven**: only tag or tag-filter when the user asks.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. (If the
`methodic` SDK happens to be installed and you prefer it, the SDK equivalents are
noted inline.) The bundled launcher resolves credentials from `~/.methodic` — see
the repo README "The MCP tools (bundled — zero config)".

## Tag + untag (by name — find-or-create)

1. Call **`chronicle.tag`** with the object and the tag keyword — e.g.
   `{ "asset_id": "<asset_id>", "tag": "turbulence" }` for an asset, or
   `{ "experiment_id": "<exp_id>", "tag": "negative-result" }` for an experiment.
   By name it finds or creates the tag in the object's scope. You need `Write` on
   the object — the tag itself grants nothing. To remove, call the same tool in
   its remove mode (e.g. pass the tag to detach); the result (JSON in the tool's
   text content) confirms the object + tag affected.

   *(SDK equivalent: `chronicle.tags.tag_asset(asset_id, tag="turbulence")` /
   `chronicle.tags.tag_experiment(exp_id, tag="negative-result")` /
   `chronicle.tags.untag_asset(asset_id, tag_id)`. The SDK also exposes
   vocabulary helpers — `list(...)`, `objects(tag_id)`,
   `asset_tags(asset_id)` / `experiment_tags(exp_id)`, `rename`, `delete` — with
   no bundled-MCP equivalent; reach for the SDK or CLI if the user wants to
   browse or manage the tag vocabulary.)*

## Filter a search by tag — only when asked

2. Call **`chronicle.search`** with `{ "query": "boundary layer",
   "filters": { "tags": ["turbulence", "pinn"] } }` — this is tag `ANY(...)`.

   Default behaviour is a **broad search** (no tag filter). Add a `tags` filter
   only on an explicit "search only things tagged …" request.

   *(SDK equivalent: `chronicle.search.query("boundary layer",
   filters={"tags": ["turbulence", "pinn"]})`.)*

## After the skill completes

Tell the user what was tagged/untagged (object + tag), or — for a tag-filtered
search — that results were restricted to those tags.

## Requires

Nothing to install — uses the bundled MCP tools.
