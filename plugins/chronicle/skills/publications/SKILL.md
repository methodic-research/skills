---
name: chronicle-publications
description: |
  Use this skill when the user wants to register or cite a published work by its
  DOI, BibTeX, or arXiv id — "cite this paper", "add this DOI as a citation",
  "register this BibTeX", "reference arXiv:… in this experiment", "cite the
  paper this builds on", "cite this search result". A publication is a public,
  shared, immutable reference record (a cited work) keyed by DOI (arXiv papers
  by id+version); registering one is idempotent (a known work returns the
  existing record). To cite work that ISN'T published yet, register a draft you
  own and finalize it later. Citing = linking the publication to an experiment
  as an input; citation links stay open after commit (they lock at
  conclusion). Use chronicle-tags for keyword labels and chronicle-collections
  for topic groupings; this skill is specifically for cited works.
---

# Publications — cite works by DOI, BibTeX, or arXiv id

A **publication** is a public, **system-owned, immutable** reference record for a
cited work — registered from a **DOI**, a **BibTeX** entry, or an **arXiv
id/URL**, deduped by DOI (arXiv by id+version), and linkable to an experiment as
a citation. Anyone can register one; the result belongs to the system and is
world-readable, so publications carry **no user tags** and can't be edited after
registration. Because the record is world-readable, citing it needs only Read —
the server skips ACL propagation on such links.

For work that isn't published yet, register a **draft** (private + mutable, owned
by you), cite it now, and **finalize** it with the real DOI/BibTeX once it's
accepted — citation links stay intact.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. (SDK
equivalents under `chronicle.publications` are noted inline.) The bundled
launcher resolves credentials from `~/.methodic` — see the repo README "The MCP
tools (bundled — zero config)".

## Register a publication (by DOI, BibTeX, or arXiv)

1. Call **`chronicle.register_publication`** with **exactly one** of a DOI, a
   BibTeX entry, or an arXiv id/URL:
   - `{ "doi": "10.1145/3292500.3330701" }` — resolved (Crossref → doi.org) and
     deduped. A known DOI returns the existing record (`existing: true`); no
     duplicates.
   - `{ "bibtex": "@article{smith2024, …}" }` — parsed directly. If the entry has
     a DOI it dedups like the DOI path.
   - `{ "arxiv": "2301.12345" }` (also `2301.12345v2`, `math.GT/0309136`, or an
     `arxiv.org/abs|pdf/…` URL) — resolved via the arXiv API into a public
     `arxiv` asset, deduped by `(arxiv_id, version)`. This is the identifier
     literature-MCP (e.g. Paperclip) results usually carry.

   The result's `publication.id` is what you cite. *(SDK:
   `chronicle.publications.register(doi=…)` / `register(bibtex=…)` /
   `register(arxiv=…)`.)*

2. **No-DOI BibTeX → resolution.** If a BibTeX entry has no DOI and similar
   records already exist, the result is
   `{ "status": "needs_resolution", "candidates": [...] }`. Prefer **citing an
   existing candidate** (use its `id`); only if none match, re-call with
   `{ "bibtex": "…", "confirm_create": true }` to mint a new record.

## Cite it (link to an experiment)

3. Link the publication to the experiment as an input — that **is** the citation:
   **`chronicle.link_asset`** with
   `{ "experiment_id": "<exp_id>", "asset_id": "<publication_id>", "link": "input" }`.
   - **Timing:** citation types (publications, arxiv papers, reports) are
     exempt from the input commit freeze — they stay linkable (and
     unlinkable) after commit, locking only when the experiment
     **concludes**. So citing at takeaways/distillation time works.
   - **ACLs:** registered publications and arxiv assets are system-owned and
     world-readable — the server skips ACL propagation for them, so the
     default call above needs only Read and just works. Citing a
     **non-public** asset (someone's internal report or a draft you don't
     own) with the propagating default requires **Administer** on it; for a
     plain reference pass `propagate_acl: false` (Read suffices — a
     citation references, it doesn't need to share).

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
