---
name: chronicle-delete-asset
description: |
  Use this skill when the user (or a cleanup flow) wants to permanently
  delete Chronicle **assets that are not linked to any experiment** —
  orphaned uploads: phrases like "delete these datasets", "clean up the
  assets I uploaded by mistake", "purge the orphaned uploads", "remove
  that abandoned pending upload". Hard delete is refused (409) while an
  asset is linked as any experiment/variation input or output — linked
  assets are part of an experiment's record and are taken out of use with
  deprecate/invalidate instead (`chronicle.assets.deprecate` /
  `chronicle.assets.invalidate`). For deleting a whole draft experiment
  (which unlinks its assets), use chronicle-delete-experiment.
---

# Delete asset

Hard-delete **orphaned** Chronicle assets — rows no experiment references:
over-uploaded datasets, duplicates, abandoned `pending` uploads. The end
state is: each asset's row, ACLs, and inline content are gone
transactionally, and its storage bytes (`assets/<id>/…` in GCS/S3) and
search document are purged best-effort.

The boundary that defines this skill: **linked means undeletable.** An
asset referenced by any `experiment_input_assets`, `variation_input_assets`,
or `experiment_output_assets` row is part of the research record; the
server refuses the delete with 409 and per-table link counts. Those assets
are governed by the validity flags instead — `deprecate` (soft warning,
still usable) or `invalidate` (hard input-block) — which preserve
provenance. Deleting an open *experiment* (chronicle-delete-experiment)
removes its link rows, which can turn its assets into deletable orphans.

**Delete is irreversible.** Always show the concrete asset list and get an
explicit confirmation first.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. (If the
`methodic` SDK happens to be installed and you prefer it, the SDK equivalents
are noted inline.) The bundled launcher resolves credentials from `~/.methodic`
— see the repo README "The MCP tools (bundled — zero config)".

`chronicle.delete_asset` is **creator-guarded**: via MCP an agent may only
hard-delete assets *it created*, even where `Delete` RBAC would allow more; the
SDK/HTTP path is the escape hatch for the rest. The unlinked-only gate (and the
per-table link counts on a 409) is identical in both paths. The validity
alternatives — `deprecate` (soft warning) / `invalidate` (hard input-block) —
stay **SDK/HTTP-only** (`chronicle.assets.deprecate` / `chronicle.assets.invalidate`,
wrapping `PUT /v1/assets/{id}/deprecate|invalidate`).

## Inputs

- **`asset_ids`** — one or more asset UUIDs. Resolve in order:
  1. Explicit ids from the user.
  2. Ids surfaced by a previous cleanup pass (e.g. assets just unlinked by
     deleting a draft experiment).
  3. Prompt the user — there is no server-side "list my orphans" query;
     candidates come from the user or the surrounding flow.
- **`confirmed`** (default `False`) — explicit go-ahead. Never proceed
  without it.

## Workflow

1. **Preview EXACTLY what will be deleted** — name, type, state, uri. There is
   **no MCP tool to fetch a single asset's metadata**; use the SDK
   `chronicle.assets.get(asset_id)` for the preview if it's available (each
   result carries `id`, `state`, `asset_type`, `name`). If you only have ids
   (no SDK), show the user the concrete ids you're about to delete. Either way,
   present the list, then ask: **"Permanently delete these N assets, their
   storage bytes included? This cannot be undone."** Proceed only on an
   explicit yes.

2. **Delete.** For each asset, call **`chronicle.delete_asset`** with
   `{ "asset_id": "<id>" }`. The server is the source of truth on linkage —
   don't try to pre-compute it; a **409 IS the "still linked" answer** (with
   per-table counts). Sort the outcomes into deleted, linked-skipped (409),
   already-gone (404 — fine in a cleanup loop), and failed (403 etc.).

   *(SDK equivalent: `chronicle.assets.delete(asset_id)`, catching
   `ConflictError` / `NotFoundError`.)*

3. **For anything still linked that the user wants out of use anyway**, the
   validity alternatives are **SDK/HTTP-only** (no MCP tool):
   `chronicle.assets.invalidate(asset_id, reason="wrong data — do not build on")`
   (hard input-block) or `chronicle.assets.deprecate(asset_id, reason=...)`
   (soft warning). Both preserve the row and provenance.

4. **Report** how many were deleted, linked-skipped, already-gone, and failed.

## After the skill completes

Tell the user:

1. Which assets were deleted (ids + names) and the removal summary
   (ACEs, inline content rows) — and that storage bytes + search documents
   were purged best-effort.
2. Which were **skipped because they are linked**, with the server's link
   counts — and that those are governed by deprecate/invalidate, or become
   deletable after the linking experiment is deleted (open drafts only).
3. Any 403s verbatim (the caller lacks `Delete` on the asset).

## Failure modes

- **409 — "asset is linked (…); hard delete is only for unlinked
  assets"**: working as designed. Don't retry; offer invalidate/deprecate,
  or (for a draft) deleting the linking experiment first.
- **403**: the caller lacks the `Delete` action on the asset. Surface
  verbatim.
- **404**: already deleted, or a bad id — treat as already-gone in a
  cleanup loop.
- **Wrong target**: the confirmation preview is the safety net — re-list
  and re-confirm rather than guessing; deletion is unrecoverable.

## Requires

Nothing to install for the delete itself — `chronicle.delete_asset` is a
bundled MCP tool. The optional **preview fetch** and the **deprecate/invalidate
alternatives** have no MCP tool yet and need the `methodic` SDK
(`chronicle.assets.get` / `chronicle.assets.deprecate` / `chronicle.assets.invalidate`).
(API-only; storage purge happens server-side; no `git`.)
