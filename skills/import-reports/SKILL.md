---
name: chronicle-import-reports
description: |
  Use this skill when the user wants to import one or more research-report
  PDFs into a Chronicle organization's library — phrases like "import these
  papers", "add this folder of PDFs to the org", "register these research
  reports for the team", "bulk import the reading list". Each PDF becomes an
  org-scoped `imported_report` asset (sha256-deduped within the org) that the
  server extracts (math-capable OCR for image-only scans) and indexes into
  role-filtered search. Organization scope is REQUIRED — these are org-library
  documents, never personal uploads. For write-ups the agent authors use
  chronicle-write-report; for training data use chronicle-dataset; arxiv
  papers arrive via the server-side corpus pipeline, not this skill.
---

# Import research reports

Get finished, third-party research-report PDFs into an organization's
Chronicle library. The end state per PDF: one `imported_report` asset owned
by the org (components: `report.pdf` now; `extracted.md` appears when the
server-side extraction job finishes), provenance (`sha256`, size, source
filename, who/when/batch) recorded in `asset_config`, and a search document
whose `allowed_readers` is the org — so org members find it in role-filtered
search and nobody else does. Server contract:
`runes/chronicle/designs/bulk-pdf-import.md`.

The boundary that defines this skill: **imports are org-scoped.** An
`imported_report` always names an organization (optionally a team); the
server refuses personal-scope rows for this type (400). Within one org, the
same bytes import once — dedup is on `(organization_id, sha256)` and a
re-run reports "already imported" rather than duplicating. (Until the
per-org dedup index ships server-side, a re-run can create a duplicate row —
list the org's `imported_report` assets and compare `sha256` before
re-importing a batch.)

## Inputs

- **`paths`** — PDF files and/or directories (directories are scanned for
  `*.pdf`, non-recursive unless the user says otherwise). Refuse non-PDF
  files rather than silently skipping; name them.
- **`organization`** — REQUIRED. Resolve in order:
  1. Explicitly named org (name/slug/id) — match against the caller's
     scopes; if ambiguous, ask.
  2. The recorded default (`~/.methodic/config.yaml` `organization_id`, or
     `$CHRONICLE_ORGANIZATION_ID`).
  3. Otherwise ask — never guess, and never fall back to personal scope.
  *Always tell the user which org was used.*
- **`team_id`** (optional) — narrows ownership to a team within the org.
- **`visibility`** (default `scope_default` = org-wide read) — `private`
  keeps it to the importer + org admins. `public` is refused server-side for
  imported third-party documents.
- **`import_source`** (optional) — a batch label for the audit trail, e.g.
  `acme_reading_list_2026_06`. Default: `import_<org-slug>_<date>`.

## Workflow

```python
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from methodic import Chronicle
from methodic.errors import ConflictError

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 1. Resolve the org from the caller's scopes (explicit name beats default).
orgs = [s for s in chronicle.me.scopes() if s.kind == "organization"]
organization_id = ...  # match the user's org, or the recorded default

# 2. Import each PDF: register (presigned), PUT, finalize.
imported, duplicates, failed = [], [], []
for path in sorted(pdf_paths):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        info = chronicle.assets.create_with_presigned(
            asset_type="imported_report",
            components=["report.pdf"],
            name=path.stem,
            content_type="application/pdf",
            asset_config={
                "sha256": digest,
                "size_bytes": path.stat().st_size,
                "source_filename": path.name,
                "import": {
                    "import_source": import_source,
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                },
            },
            organization_id=organization_id,
            team_id=team_id,            # optional
            visibility=visibility,      # omit for scope_default (org-wide)
        )
        chronicle.assets.upload_component(
            info.upload_urls["report.pdf"], path, "application/pdf"
        )
        chronicle.assets.finalize(info.asset_id)
        imported.append((path.name, info.asset_id))
    except ConflictError:               # 409 — same sha256 already in this org
        duplicates.append(path.name)
    except Exception as err:            # 403/404/size cap — keep going, report at end
        failed.append((path.name, str(err)))

print(f"imported {len(imported)}, already-present {len(duplicates)}, "
      f"failed {len(failed)} into org {organization_id}")
```

For batches beyond a few hundred files, the streaming bulk path (Scribe
`assets:bulk-presign` + Chronicle `assets:bulk-import`, per the design doc)
replaces this loop once it ships; the per-file loop above is correct at any
size, just chattier.

## After the skill completes

Tell the user:

1. Counts and ids — imported / already-present (dedup) / failed — and **which
   organization** (and team) now owns them.
2. What happens next, server-side and async: an extraction job produces
   `extracted.md` for each PDF — born-digital PDFs from their text layer,
   image-only scans via math-capable OCR (equations preserved as LaTeX) —
   and search indexing follows (lazy cadence: searchable within ~a day;
   scanned PDFs are only weakly searchable until their extraction lands).
3. How to verify listing/search scoping:
   - org member: `chronicle.assets.list` scoped to the org
     (`GET /v1/assets?owner=<org-id>`) shows the new assets;
     `chronicle.search.query("<phrase>")` finds them once indexed.
   - **superadmin** (testing an org they're not a member of): the same
     `owner=<org-id>` listing works, and `chronicle.search.query(...,
     as_scope=<org-id>)` returns exactly what a plain org member would see.
     Both write an `admin.act_as_scope` audit row visible in the org's
     audit view — cross-org context switches are always audited.

## Failure modes

- **404 — "scope not found"**: the caller isn't a member of that org (or the
  id is wrong). Existence isn't leaked; re-check the org with the user.
- **403**: the caller lacks create authority in the org (or, on the bulk
  path, the `bulk_importer`/`administer` grant). Surface verbatim.
- **409 — duplicate**: same `sha256` already imported into this org. Not an
  error — report it as already-present with the existing asset if returned.
- **413 / size cap**: PDFs over the server cap (`pdf_import.max_pdf_mb`,
  default 50 MB) are refused at registration. Check sizes locally first and
  list offenders rather than uploading doomed bytes.
- **Stuck `pending`**: a PUT that died leaves the asset
  `pending/["upload_in_progress"]` — re-PUT the component and call
  `finalize` again; abandoned rows are reaped server-side after the TTL.
- **`public` visibility**: refused for `imported_report` (copyright
  posture). Use `scope_default` or `private`.

## MCP-native agents

An MCP-driven agent can upload a *single* PDF with
`chronicle.upload_asset(filename=..., asset_type="imported_report",
content_type="application/pdf", link="none", scope="organization",
organization_id=...)`. Multi-file batches, sha256 provenance, dedup
reporting, and the verification pass are this skill's job — prefer it
whenever more than one file is involved.

## Requires

- `pip install methodic-research` (≥0.13 — `assets.create_with_presigned` /
  `upload_component` / `finalize`)
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- Organization context: a default from `~/.methodic/config.yaml` /
  `$CHRONICLE_ORGANIZATION_ID`, or the user names the org explicitly
- No `git` — API-only; extraction, OCR, and indexing run server-side.
