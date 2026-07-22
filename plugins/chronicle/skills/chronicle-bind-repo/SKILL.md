---
name: chronicle-bind-repo
description: |
  Use this skill when the user wants their OWN GitHub repository connected to
  a Chronicle experiment as a live two-way sync — phrases like "bind my repo",
  "attach my repo to the experiment", "use my own GitHub repo", "keep my repo
  in sync with Chronicle", "I want the agent's work in my repository". Binding
  means: their repo seeds the experiment, their pushes flow IN continuously,
  and agent work flows BACK as chronicle/* branches they can review/merge
  under their own policies. Bind-at-create only — an existing experiment
  cannot be bound later. Do NOT invoke for a plain one-time copy-in of a local
  checkout (that's `chronicle-import-repo`, the default on-ramp — importing
  never binds), and never bind unless the user explicitly asked for the
  connection.
---

# Bind an external GitHub repo

Create an experiment **bound** to the user's own GitHub repository
(`runes/chronicle/designs/external-repos.md`). The internal managed repo
remains the system of record — pins, locks, and provenance are unchanged —
while the user's repo is a synced view: inbound fast-forward imports of their
branches, outbound `chronicle/<slug>/v<n>` branches carrying agent work.
Sync is never load-bearing: a broken link degrades visibility, never the
experiment.

**This is an explicit verb.** The default create path (and every import flow)
uses the zero-setup managed repo; `chronicle-import-repo` copies content in
without binding. Reach for this skill only on the user's clear ask to stay
connected to their repository.

## Transport

Everything here is bundled MCP: `chronicle.list_github_installations`,
`chronicle.create_experiment` (its `external_repo` parameter is the bind),
`chronicle.get_external_repo`, `chronicle.sync_external_repo`. No SDK leg.

## Prerequisite — a claimed installation

Private repos (and any outbound sync) need the **Methodic Research GitHub
App** installed on the user's account/org and claimed for their Chronicle
scope. That handshake is **browser-only** (Chronicle-initiated; agents cannot
install or claim):

1. `chronicle.list_github_installations` — if an active installation covers
   the repo's owner, use its `installation_id`.
2. If empty (or the wrong account): send the user to **Settings →
   Integrations → GitHub → Connect**, have them install the App on the
   account that owns the repo (selected-repositories is fine — just include
   the target repo), then re-list.

**Public read-only tier:** a public repo can be bound with **no
installation** — omit `installation_id`. Inbound only; nothing is ever
pushed back. Use it when the user just wants their public code streaming in.

## Steps

1. **Confirm the intent** — repo `owner/name`, base branch (default: the
   repo's default branch), monorepo `code_subdir` if the training code isn't
   at the root, and the outbound `sync_mode`:
   - `live` (default) — agent work lands in their repo as it happens
   - `on_commit` — one push per variation commit
   - `manual` — only on sync-now
   - `off` — inbound only
2. **Resolve the installation** (above). Match `account_login` to the repo
   owner.
3. **Create bound** — `chronicle.create_experiment` with the usual fields
   (title / hypothesis_summary / config_yaml / slug — same discipline as
   `chronicle-propose-experiment`) plus:
   ```json
   "external_repo": {
     "installation_id": 12345678,
     "repo": "owner/name",
     "base_ref": "main",
     "code_subdir": "ml/experiments",
     "sync_mode": "live"
   }
   ```
   A rejected spec fails the create cleanly (nothing orphaned). Common
   rejections and their remediations: `installation not connected` → the
   Connect flow above; `private repos require the App installed` → install or
   make it public; a size-cap error → the repo is over the mirror cap.
4. **Wait for the seed** — the internal repo is created as a mirror of
   theirs. Poll `chronicle.get_external_repo(experiment_id)` until
   `link_state` is `active` (public tier: `readonly`); `broken` with a
   `state_reason` means the seed failed — surface the reason.
5. **Hand off** — tell the user:
   - their branches import continuously (fast-forward only; a force-push on
     their side marks the ref *diverged* — Chronicle keeps the last FF point
     and never rewrites);
   - agent work appears as `chronicle/<slug>/v<n>` branches in their repo —
     merging any of it into their mainline is entirely their call and their
     CI's;
   - the link panel lives under the experiment's **Settings → Integrations**
     (state, per-ref ledger, Sync now, sync-mode, unlink);
   - `chronicle.sync_external_repo` triggers an immediate two-way pass any
     time.

## Never

- Bind without the user's explicit ask, or "upgrade" an import to a bind.
- Suggest deleting/renaming anything in their repo except as remediation for
  an outbound collision (a branch of theirs occupying a `chronicle/*` name —
  the link goes `degraded` and names it).
- Promise retro-binding: an existing experiment cannot be bound; the path is
  a new bound experiment (fork/re-create) if the user wants the connection.
