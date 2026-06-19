---
name: chronicle-review-imports
description: |
  Use this skill to review/triage research-report PDFs previously imported
  into a Chronicle org — phrases like "review the imported reports", "check
  the import for problems", "which imported equations/tables were flagged",
  "approve the imported reports". It inspects each import's server-side
  extraction + enrichment state (layout parse, math OCR, table/equation
  annotations), surfaces the objects flagged for human review with their
  unified annotations and model disagreements, and routes actions: accept
  (advisory flags need no action), deprecate/invalidate bad imports,
  approve/reject review-gated imports, or re-enqueue the server jobs.
  For importing new PDFs use chronicle-import-reports.
---

# Review imported reports

Imported research reports (`imported_report` assets) are processed
server-side after upload: a layout parse derives browsable views
(`html/report.html`, `markdown/report.md`, chunk shards), and an
enrichment pass annotates **tables and equations** with two models plus a
`claude-fable-5` reconciliation — recording confidence, explicit model
disagreements, and `requires_human_review` flags. This skill is the human
side of that loop: see what was flagged and decide.

## Transport — MCP-direct (hybrid)

Triage uses the **bundled MCP tool** `chronicle.review_import` directly — no
`pip install` for the inspection pass. It returns the per-import extraction +
enrichment state and the flagged objects (with their unified annotations and
disagreements) so you don't have to presign and fetch
`index/review_items.ndjson` / `annotations/unified/*.json` by hand. (If the
`methodic` SDK is installed, the manual presign+fetch SDK equivalent is noted
inline.)

This skill is **HYBRID**: the *action* half has no MCP tool. Asset
`accept`/`deprecate`/`invalidate`/`approve`/`reject` are **SDK-only** —
keep them on the `methodic` SDK. The server-side re-enqueue is admin-only and
goes through the **REST surface** directly (same posture as the
`*-error-queue` skills). So: MCP for triage/inspection; SDK for the lifecycle
actions; REST for re-enqueue.

Where the state lives (all on the asset; `chronicle.review_import` surfaces
it for you):

- `asset_config.extraction.status` — `layout` (full pipeline) /
  `text_layer` / `ocr` (flat fallbacks) / `failed` (+ `reason`).
- `asset_config.enrichment` — `{status, enriched, failed, review_pending,
  openai_leg}`; `openai_leg: false` means single-model annotation (the org
  has no OpenAI integration configured — expected, recorded, not an error).
- Components: `index/review_items.ndjson` (one line per flagged object),
  `annotations/unified/p####-o####.json` (the reconciled annotation with
  `disagreements`), `tables/*.csv|json`, the derived views.
- Audit: `asset.extraction_review_required` rows in the org's audit view.

## Inputs

- **`asset_ids`** — resolve in order: explicit ids; the ids reported by a
  prior chronicle-import-reports run; or search (`chronicle.search` with
  `{ "query": "...", "filters": { "asset_types": ["imported_report"],
  "organization_id": org } }`) — there is no `assets.list` tool yet, so
  org-wide listing goes through search or the import summary.
- **`organization`** — for context/reporting; resolve as in
  chronicle-import-reports.

## Workflow

1. **Triage each import.** For each `asset_id`, call
   **`chronicle.review_import`** with `{ "asset_id": "<asset_id>" }`. The
   result is JSON in the tool's text content carrying the asset's
   extraction + enrichment state and — when `review_pending` — the flagged
   objects already joined to their unified annotations (so no manual
   presign + NDJSON parse). Bucket the results:
   - `extraction.status == "failed"` → record `(asset_id, reason)` as a
     failed extraction; skip the rest.
   - `enrichment.review_pending` falsy → clean; no action.
   - otherwise → flagged: keep `(asset_id, name, flagged_items[])` where
     each item carries its `unified` annotation (LaTeX / table columns) and
     `disagreements`.

   *(SDK equivalent — the manual fetch path when the tool isn't available:
   `a = chronicle.assets.get(asset_id)` → read `asset_config.extraction` /
   `.enrichment`; then `chronicle.assets.presign(asset_id, operation="read",
   components=["index/review_items.ndjson"])`, GET the url, parse each
   NDJSON line, map `object_id` "...:page:0042:object:0003" → component key
   "p0042-o0003", presign + GET `annotations/unified/<key>.json` for each
   flagged object's reconciled annotation.)*

2. **Present each flagged object to the user**: page, reason, confidence,
   the transcribed LaTeX / table columns, and any model disagreements
   (`unified["disagreements"]` — field, both values, resolution).

3. **Route actions** (SDK-only — no MCP tool for these):
   - **Looks right** → no action needed; flags are advisory.
   - **Import is wrong/garbage** → keep provenance, take it out of use:
     `chronicle.assets.deprecate(asset_id, reason="bad scan — superseded")`,
     or `chronicle.assets.invalidate(asset_id, reason=…)` for a hard
     input-block.
   - **Review-GATED import** (registered with `pending_reasons:
     ["review_required"]`) → lifecycle action: `chronicle.assets.approve(
     asset_id)` clears the gate + finalizes, or
     `chronicle.assets.reject(asset_id, reason=…)` abandons it.

4. **Re-run the server side** (extraction or enrichment) after a fix —
   admin-only, **REST surface** directly (not MCP, not SDK-wrapped): a
   superadmin session POSTs `/v1/admin/jobs` with `{"job_type":
   "pdf_extraction" | "report_enrichment", "config": {"asset_ids": [...]}}`.
   Already-extracted rows are skipped (idempotent); `failed` rows retry.

## After the skill completes

Tell the user, per org:

1. Counts — clean / flagged (with per-object reasons + confidence) /
   failed extractions (with reasons).
2. The disagreements worth eyes: anywhere the two models differed and the
   unifier had to pick (`disagreements[].resolution`), and any equation
   below high confidence (those are review-flagged by policy).
3. Which actions were taken (deprecations, approvals, re-enqueued jobs)
   and that everything is audited (`asset.extraction_review_required`,
   `asset.enrichment_completed`, plus the action's own audit row).

## Failure modes

- **`enrichment` absent**: the asset predates the pipeline, the layout
  parser isn't configured (`pdf_import.docai` dynamic config), or the
  chained job hasn't run yet — check `extraction.status` first.
- **`review_items.ndjson` missing with `review_pending > 0`**: enrichment
  is mid-flight; retry after the job completes.
- **409 — "asset is not awaiting review"**: `approve`/`reject` only apply
  to review-GATED imports (registered with `pending_reasons:
  ["review_required"]`); advisory flags need no lifecycle action.
- **403/404**: org membership/authority as usual — surface verbatim.

## Requires

- The bundled MCP tool `chronicle.review_import` for triage (no install).
- `pip install methodic-research` (≥0.13 — `assets.approve/reject/
  deprecate/invalidate`) for the action half, since those have no MCP tool.
  `requests` only if you fall back to the manual presign+fetch SDK path
  (blob reads, not Chronicle API calls).
- `CHRONICLE_API_KEY` (or credentials in `~/.methodic`); superadmin key
  only for the re-enqueue path.
- No `git`.
