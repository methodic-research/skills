---
name: chronicle-share
description: |
  Use this skill when the user wants to share a single Chronicle **asset** — a
  report, dataset, figure, or any uploaded file — independent of the experiment
  it belongs to. Phrases like "share this report with @alice", "give the ml-team
  read access to this dataset", "make this report public", "make just this one
  report visible to my org", "make this asset private again", "who can see this
  asset", "stop sharing this with bob". It grants/revokes per-person or per-team
  read access and sets an asset's visibility (private / organization / public)
  via the bundled MCP tools. This shares ONE asset without exposing its whole
  experiment — to change who can read an entire **experiment**, that's a
  different concern (manage the experiment's roles); to *move* an asset into an
  org so it bills there, use `chronicle-move-experiment`'s asset analog
  (`chronicle.move_asset`); to upload a dataset use `chronicle-dataset` and to
  write a report use `chronicle-write-report`.
---

# Share an individual asset

Share a single asset — most often a **report** you just wrote, or a dataset —
with a specific person, a team/org, or the public, **without** making the whole
experiment readable. Asset sharing is **additive** over what the asset already
inherits from its experiment: granting read here never removes the experiment's
own access, and "private" only removes the broadcast grant (per-person shares
stay). The headline case: a private experiment whose one takeaways report you
want to hand to a collaborator or make public.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. The
bundled launcher resolves credentials from `~/.methodic` (see the repo README
"The MCP tools (bundled — zero config)"). SDK equivalents on
`chronicle.assets` are noted inline if you prefer the SDK.

All of these require **`Administer`** on the asset. You have it if you created
the asset, or if you administer the experiment it's an output of (an
experiment's admins administer its reports). A caller without it gets a 404
(the server hides asset existence from non-administrators).

## Inputs

- **`asset_id`** — the asset's UUID. Resolve in order:
  1. Explicit argument from the user.
  2. The `asset_id` a prior skill in this session just returned —
     `chronicle-write-report` (the report), `chronicle-dataset` (the dataset),
     or a distillation takeaways report.
  3. If the user names an experiment and a kind ("the takeaways report on
     experiment X"), list that experiment's outputs (`chronicle.get_experiment`
     / its assets) and match by `asset_type` + name; if several match, **ask
     which one**.
  4. Prompt the user.
- **The intent + target**, one of:
  - a **person** — a user handle (`@alice`) or principal id;
  - a **team or org** — named by the user, resolved to a `scope_id` via
    `chronicle.list_scopes`;
  - a **visibility** — `private` / `organization` (a.k.a. `org` / `team`) /
    `public`.

## Workflow

Pick the branch that matches what the user asked. You do **not** need
`list_scopes` for a person or a visibility change — only to resolve a named
team/org to its id.

1. **Share with a specific person.** Call **`chronicle.grant_asset_access`**
   with `{asset_id, principal_id: "@alice", action: "read"}`. `principal_id`
   accepts a handle (`@alice`, `o/acme`, `t/ml-team`) or a raw id — the server
   resolves it. Idempotent.
   *(SDK: `chronicle.assets.grant_access(asset_id, "@alice")`.)*

2. **Share with a whole team or organization.** First resolve the scope: call
   **`chronicle.list_scopes`** with `{}`, filter to the team/org the user named
   (match `slug`/`name`; if ambiguous across several, **ask which one** — don't
   guess a UUID), and take its `id`. Then call
   **`chronicle.share_asset_with_scope`** with `{asset_id, scope_id, action:
   "read"}`. Every member of that scope can then read the asset.
   *(SDK: `chronicle.assets.share_with_scope(asset_id, scope_id)`.)*

3. **Set visibility (the broadcast grant).** Call
   **`chronicle.set_asset_visibility`** with `{asset_id, visibility}`:
   - `"public"` — anyone can read this asset.
   - `"org_public"` (a.k.a. `"organization"` / `"org"` / `"team"`) — the asset's
     owning org/team can read it.
   - `"private"` — remove the broadcast grant. Per-person shares from step 1/2
     and the experiment's inherited access are left intact.
   This swaps the broadcast grant atomically (so `public → private` actually
   demotes) and re-indexes, so a shared report becomes searchable to the new
   readers. *(SDK: `chronicle.assets.set_visibility(asset_id, "public")`.)*

4. **See who can read it.** Call **`chronicle.list_asset_access`** with
   `{asset_id}` → the list of `(principal, action)` grants. Use this to answer
   "who can see this" before/after a change. *(SDK:
   `chronicle.assets.list_access(asset_id)`.)*

5. **Stop sharing with someone.** Call **`chronicle.revoke_asset_access`** with
   `{asset_id, principal_id, action: "read"}`. Idempotent — `removed: false` if
   the grant wasn't there. *(SDK: `chronicle.assets.revoke_access(asset_id,
   principal_id, "read")`.)*

## After the skill completes

Tell the user the concrete end state: who/what now has read access (or no longer
does), and — for a visibility change — that a public/org grant also makes the
asset **searchable** to those readers. If they shared a report, remind them the
experiment itself stays as private as it was; only this asset moved.

## Failure modes (surface verbatim)

- **403 / 404 on a mutation** — you lack `Administer` on the asset. The asset's
  creator has it, as do the admins of the experiment it's an output of. If the
  user expects access they don't have, they need an experiment admin to grant
  it (or to be added to the experiment's `:admins`).
- **"caller is not a member of <scope>"** (on `share_asset_with_scope`) — you
  can only share into a team/org you belong to. Re-resolve the scope via
  `chronicle.list_scopes` and confirm you're a member.
- **Unknown visibility value** — `set_asset_visibility` accepts only
  `private` / `org_public` (or `organization` / `org` / `team`) / `public`.
- **`set_asset_visibility` not found** — the tool ships in chronicle-server
  ≥ 0.73.0. If the deployed server predates it, fall back to
  `grant_asset_access`/`revoke_asset_access` with `principal_id: "everyone"`
  for public/private, and `share_asset_with_scope` for org-wide.

## Requires

- Nothing to install — the MCP tools are bundled. Credentials in `~/.methodic`.
- `Administer` on the asset (its creator / the owning experiment's admins).
