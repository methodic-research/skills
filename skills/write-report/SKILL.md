---
name: chronicle-write-report
description: |
  Use this skill when the user (or an agent flow) wants to attach a written
  research document to a Chronicle experiment or variation — a post-
  experiment takeaways/findings write-up, a general research note, or any
  document where the math and figures matter. Phrases like "write up the
  findings", "document what we learned", "summarize this variation's
  results", "attach a takeaways report". The document is Markdown + LaTeX
  math ($…$) that the Methodic UI renders inline with MathJax, plus figures
  uploaded as image assets and embedded by reference. It always includes an
  explicit "What didn't work" section — negative results are part of the
  record. This is the shared write-up path for both the synthesis flow and
  the variation flow. For creating the experiment + its hypothesis use
  chronicle-propose-experiment; for authoring a variation's config use
  chronicle-author-variation.
---

# Write report

Attach a research write-up — Markdown + LaTeX math, with embedded figures —
to an experiment, or to one of its variations. The body renders inline in
the Methodic UI with MathJax (no PDF needed for the in-app read) and is
searchable. The discipline that defines this skill: the write-up is honest
about **what didn't work**, not just what did.

The math is rendered by MathJax from `$…$` (inline) and `$$…$$` (display)
delimiters in the Markdown — keep it to math *expressions*. This is a
Markdown document, not a full LaTeX paper; the compiled-PDF path
(`exp.reports.<kind>.render`, template or freeform) is for that, and stays
the canonical full artifact when one exists.

## What the write-up must contain

The agent drafts the body with these sections (Markdown headings):

1. **Summary** — one to three sentences; the headline finding.
2. **What worked** — the positive result, with the numbers that matter and
   the math that explains them (inline `$…$`, displayed `$$…$$` for
   derivations).
3. **What didn't work** — **required, and not an afterthought.** The
   approaches that failed or underperformed, the ablations that hurt, the
   configurations ruled out, the dead ends. A *successful* run still has
   negative results worth recording — they stop the next experiment from
   re-running them. If there genuinely are none, say so explicitly ("no
   negative results — every variation improved on baseline") rather than
   dropping the section. This is the part reviewers and the next agent read
   first.
4. **Open questions** — what's still unresolved and load-bearing (≤3; each
   with one line on why it matters). Optional.
5. **Figures** — loss curves, comparisons, ablation plots, embedded as
   `![alt](asset:<id>)` (step 1 of the workflow uploads them and returns the
   ids).

## Inputs

- **`experiment_id`** — the Chronicle experiment UUID. Resolve in order:
  1. Explicit argument from the user
  2. `methodic` config (`~/.config/methodic/current_experiment`)
  3. Detect from cwd if inside a clone of the experiment repo
  4. Prompt the user
- **`variation`** (optional) — variation index or plaintext name to scope
  the write-up to a specific variation's results. Omit for an
  experiment-level document. Resolve a name → index before the SDK calls.
- **`kind`** (default `research_report`) — `research_report` for a general
  note / findings doc, or `takeaways_report` for a formal post-experiment
  summary. Both render the same way; `takeaways_report` is the type the
  conclude gate recognizes.
- **`title`** — short human title for the document.
- **`figures`** (optional) — local image file paths to upload and embed
  (`.png`, `.jpg`/`.jpeg`, `.svg`, `.webp` only).
- **`outcome`** (variation-scoped only) — `success` or `failure_rca`,
  recorded on the asset so failure write-ups are findable as such.

## Workflow

```python
from methodic import Chronicle
from pathlib import Path

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

output_of = {"experiment_id": experiment_id}
if variation is not None:
    output_of["variation"] = variation

# 1. Upload figures as `image` assets and collect their ids for embedding.
#    Binaries go through the presigned-upload path: register → PUT → finalize.
#    A single file still goes in `components=[name]` — that's the SDK shape;
#    Chronicle resolves a lone component to one image when it's embedded.
def _image_content_type(p: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }[p.suffix.lower()]  # KeyError → unsupported type; only static images embed

figure_ids = {}  # local filename -> asset_id
for fig in (figures or []):
    p = Path(fig)
    ctype = _image_content_type(p)
    info = chronicle.assets.create_with_presigned(
        asset_type="image",
        name=p.name,
        components=[p.name],
        content_type=ctype,
        output_of=output_of,
    )
    chronicle.assets.upload_component(
        info.upload_urls.get(p.name) or info.upload_urls["default"], p, ctype
    )
    chronicle.assets.finalize(info.asset_id)
    figure_ids[p.name] = info.asset_id

# 2. *** AGENT DRAFTS THE WRITE-UP *** — the central step.
#    Markdown + $…$ math, with the required sections (Summary, What worked,
#    What didn't work, Open questions, Figures). Embed figures by id, e.g.:
#       ![loss curve](asset:{figure_ids["loss_curve.png"]})
#    Write the negative-results section in good faith — it is the point.
markdown_summary = "...the agent writes the Markdown + math document here..."

# 3. Persist as an inline report asset — auto-finalized, no compile step.
#    The UI renders the body from the `markdown_summary` field with MathJax.
result = chronicle.assets.create_inline(
    asset_type=kind,                      # "research_report" | "takeaways_report"
    name=title,
    content={
        "title": title,
        "markdown_summary": markdown_summary,
        **({"outcome": outcome} if (variation is not None and outcome) else {}),
    },
    content_type="application/json",
    output_of=output_of,
)
asset_id = result["asset"]["id"]
print(
    f"Attached {kind} {asset_id} to experiment {experiment_id}"
    + (f" (variation {variation})" if variation is not None else "")
)
for name, fid in figure_ids.items():
    print(f"  figure {name} → {fid}")
```

## After the skill completes

Tell the user:

1. The report asset id and kind, and the experiment (and variation) it's
   linked to.
2. The figure asset ids embedded, if any.
3. That it renders in the Methodic UI on the asset page (the **Document**
   section), math and figures inline.
4. Explicitly note that the **What didn't work** section is part of the
   record — if the agent left it near-empty, say so, so the user can fill
   it in rather than discovering the omission later.

## Failure modes

- **`create_with_presigned` / `create_inline` 403** — the caller lacks
  `Write` on the experiment. Surface the message verbatim.
- **Unsupported image type** (`_image_content_type` KeyError) — only
  png/jpeg/svg/webp embed. Convert the figure or drop it; don't upload an
  arbitrary binary as an `image`.
- **Empty "What didn't work"** — do not silently omit the section. State
  there were no negative results, so the absence is a recorded choice, not a
  gap.
- **`create_inline` rejects the content** — `markdown_summary` must be a
  JSON string; check the content shape. The asset is a single inline JSON
  document, no components.
- **Figure uploaded but not embedded** — the asset exists but nothing
  references it. Either embed `![](asset:<id>)` in the body or skip the
  upload; a dangling image asset just clutters the experiment outputs.
- **Need a compiled PDF too?** This skill writes the lightweight inline
  body the UI renders. For the formal compiled report (the PDF artifact),
  use `exp.reports.<kind>.render(...)` (template or freeform) — they
  coexist: the PDF is the full artifact, this is the in-app read.

## Requires

- `pip install methodic-research`
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- No `git` — this skill writes assets via the API; no repo checkout needed.
