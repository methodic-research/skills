---
name: chronicle-publications
description: |
  Use this skill when the user wants to register or cite a published work by its
  DOI or BibTeX — "cite this paper", "add this DOI as a citation", "register this
  BibTeX", "reference arXiv:… in this experiment", "cite the paper this builds
  on". A publication is a public, shared, immutable reference record (a cited
  work) keyed by DOI; registering one is idempotent (a known DOI returns the
  existing record). To cite work that ISN'T published yet, register a draft you
  own and finalize it later. Citing = linking the publication to an experiment
  as an input. Use chronicle-tags for keyword labels and chronicle-collections
  for topic groupings; this skill is specifically for cited works.
---

# Publications — cite works by DOI or BibTeX

A **publication** is a public, **system-owned, immutable** reference record for a
cited work — registered from a **DOI** or a **BibTeX** entry, deduped by DOI, and
linkable to an experiment as a citation. Anyone can register one; the result
belongs to the system and is world-readable, so publications carry **no user
tags** and can't be edited after registration.

For work that isn't published yet, register a **draft** (private + mutable, owned
by you), cite it now, and **finalize** it with the real DOI/BibTeX once it's
accepted — citation links stay intact.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. (SDK
equivalents under `chronicle.publications` are noted inline.) The bundled
launcher resolves credentials from `~/.methodic` — see the repo README "The MCP
tools (bundled — zero config)".

## Register a publication (by DOI or BibTeX)

1. Call **`chronicle.register_publication`** with **either** a DOI or a BibTeX
   entry:
   - `{ "doi": "10.1145/3292500.3330701" }` — resolved (Crossref → doi.org) and
     deduped. A known DOI returns the existing record (`existing: true`); no
     duplicates.
   - `{ "bibtex": "@article{smith2024, …}" }` — parsed directly. If the entry has
     a DOI it dedups like the DOI path.

   The result's `publication.id` is what you cite. *(SDK:
   `chronicle.publications.register(doi=…)` / `register(bibtex=…)`.)*

2. **No-DOI BibTeX → resolution.** If a BibTeX entry has no DOI and similar
   records already exist, the result is
   `{ "status": "needs_resolution", "candidates": [...] }`. Prefer **citing an
   existing candidate** (use its `id`); only if none match, re-call with
   `{ "bibtex": "…", "confirm_create": true }` to mint a new record.

## Cite it (link to an experiment)

3. Link the publication to the experiment as an input — that **is** the citation:
   **`chronicle.link_asset`** with
   `{ "experiment_id": "<exp_id>", "asset_id": "<publication_id>", "link": "input" }`.
   Inputs freeze on commit, so cite before committing (or while still open).

## Unpublished work — drafts + finalize

4. To reference work that isn't out yet, register with `{ "bibtex": "…",
   "draft": true }` (or `{ "doi": …, "draft": true }`). You get a **private,
   mutable** draft you own; cite it now (step 3). You can publish the experiment
   with a draft citation attached — there's no gate.

5. When the work is accepted, **finalize** the draft via the SDK/REST
   (`chronicle.publications.finalize(id, doi=…/bibtex=…)` →
   `POST /v1/publications/{id}/finalize`): it's promoted in place to a public,
   registered record, and your existing citation link stays intact. Finalizing is
   the only edit a publication ever takes.

## Find an existing publication first

Before registering by BibTeX, you can check for an existing record with
**`chronicle.search_publications`** `{ "q": "<title words>" }` (or
`chronicle.search` with `filters.asset_types=["publication"]`) and cite a match
instead. *(SDK: `chronicle.publications.search("<title>")`.)*

## After the skill completes

Tell the user what was registered or reused (title + whether it was an existing
record or newly created), and which experiment it was cited on. For a draft, note
that it's a private placeholder to finalize once published.

## Requires

Nothing to install — uses the bundled MCP tools.
