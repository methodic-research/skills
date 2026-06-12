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

Where the state lives (all on the asset):

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
  prior chronicle-import-reports run; or search
  (`chronicle.search.query("...", filters={"asset_types":
  ["imported_report"], "organization_id": org})`) — there is no SDK
  `assets.list` yet, so org-wide listing goes through search or the
  import summary.
- **`organization`** — for context/reporting; resolve as in
  chronicle-import-reports.

## Workflow

```python
import json
import requests
from methodic import Chronicle

chronicle = Chronicle.from_env()

flagged, clean, failed_extractions = [], [], []
for asset_id in asset_ids:
    a = chronicle.assets.get(asset_id)
    cfg = a.get("asset_config") or {}
    extraction = cfg.get("extraction") or {}
    enrichment = cfg.get("enrichment") or {}

    if extraction.get("status") == "failed":
        failed_extractions.append((asset_id, extraction.get("reason", "?")))
        continue
    if not enrichment.get("review_pending"):
        clean.append(asset_id)
        continue

    # Pull the review items + each flagged object's unified annotation.
    urls = chronicle.assets.presign(
        asset_id, operation="read", components=["index/review_items.ndjson"]
    )
    items_url = urls["index/review_items.ndjson"]["url"]
    items = [json.loads(l) for l in requests.get(items_url, timeout=30).text.splitlines() if l]
    for item in items:
        # object_id "...:page:0042:object:0003" → component key "p0042-o0003"
        parts = item["object_id"].split(":")
        key = f"p{parts[-3]}-o{parts[-1]}"
        ann_component = f"annotations/unified/{key}.json"
        ann_url = chronicle.assets.presign(
            asset_id, operation="read", components=[ann_component]
        )[ann_component]["url"]
        item["unified"] = requests.get(ann_url, timeout=30).json()
    flagged.append((asset_id, a.get("name"), items))

# Present each flagged object to the user: page, reason, confidence, the
# transcribed LaTeX / table columns, and any model disagreements
# (unified["disagreements"] — field, both values, resolution). Then act:
#
# 1. Looks right → no action needed; flags are advisory.
# 2. Import is wrong/garbage → keep provenance, take it out of use:
#    chronicle.assets.deprecate(asset_id, reason="bad scan — superseded")
#    # or .invalidate(...) for a hard input-block.
# 3. Review-GATED import (registered with pending_reasons
#    ["review_required"]) → lifecycle action:
#    chronicle.assets.approve(asset_id)            # clears gate, finalizes
#    chronicle.assets.reject(asset_id, reason=...) # abandons it
```

Re-running the server side (extraction or enrichment) after a fix is an
**admin jobs** call — not yet SDK-wrapped (same posture as the
`*-error-queue` skills), so a superadmin session uses the REST surface
directly: `POST /v1/admin/jobs` with
`{"job_type": "pdf_extraction" | "report_enrichment", "config":
{"asset_ids": [...]}}`. Already-extracted rows are skipped (idempotent);
`failed` rows retry.

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

- `pip install methodic-research` (≥0.13 — `assets.get/presign/approve/
  reject/deprecate/invalidate`) and `requests` for presigned-URL fetches
  (blob reads, not Chronicle API calls).
- `CHRONICLE_API_KEY`; superadmin key only for the re-enqueue path.
- No `git`.
