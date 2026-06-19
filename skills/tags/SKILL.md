---
name: chronicle-tags
description: |
  Use this skill ONLY when the user explicitly asks to tag something or filter by
  tag — "tag this as <keyword>", "tag these experiments turbulence", "what's
  tagged <keyword>", "find assets tagged X", "search only things tagged Y". A tag
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

Thin wrapper over the SDK's `chronicle.tags` namespace + `chronicle.search`.
**User-request-driven**: only tag or tag-filter when the user asks.

## Tag + untag (by name — find-or-create)

```python
from methodic import Chronicle
chronicle = Chronicle.from_env()

chronicle.tags.tag_asset(asset_id, tag="turbulence")        # by name → finds or creates the tag in scope
chronicle.tags.tag_experiment(exp_id, tag="negative-result")
chronicle.tags.untag_asset(asset_id, tag_id)
```

`list(...)` autocompletes the scope's vocabulary; `objects(tag_id)` lists what
carries a tag; `asset_tags(asset_id)` / `experiment_tags(exp_id)` list an
object's tags; `rename` / `delete` manage the vocabulary.

## Filter a search by tag — only when asked

```python
hits = chronicle.search.query("boundary layer",
                              filters={"tags": ["turbulence", "pinn"]})   # tag: ANY(...)
```
Default behaviour is a **broad search** (no tag filter). Add a `tags` filter only
on an explicit "search only things tagged …" request.

## MCP-native agents

`chronicle.tag` applies/removes a tag; `chronicle.search` `filters.tags` narrows
by tag. Same user-request-driven rule; you need `Write` on the object.

## After the skill completes

Tell the user what was tagged/untagged (object + tag), or — for a tag-filtered
search — that results were restricted to those tags.

## Requires

- `pip install methodic-research` (the `chronicle.tags` namespace + `search(filters={"tags": …})`)
- `CHRONICLE_API_KEY` + `CHRONICLE_SERVER_URL` exported (or `methodic auth login`)
- CLI equivalent: `chronicle tags …`
