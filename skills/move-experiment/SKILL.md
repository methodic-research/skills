---
name: chronicle-move-experiment
description: |
  Use this skill when the user wants to transfer a Chronicle experiment out
  of their personal space and into an organization — phrases like "move this
  experiment to my org", "transfer this to the <name> organization", "make
  this experiment org-wide", "put this under the team", "consolidate my
  personal experiments into the org". The skill resolves the target
  organization (and optional team), optionally sets the experiment's
  visibility (private / org-wide / public) in the same call, and performs the
  transfer via the SDK. It is **personal → org only** — an experiment that
  already belongs to an org cannot be re-homed (the server refuses with 409).
  Do not invoke this to change who can read an experiment that's already in
  an org (that's an ACL/visibility change), or to delete an experiment
  (that's `chronicle-delete-experiment`).
---

# Move experiment to an organization

Transfer a **personal** experiment into an organization, so it shows up
under the org, the org's admins can administer it, and (optionally) org/team
members can read it. The end state is: the experiment's owner becomes the
target org (and team, if given), the org-admins role gains `Read` +
`Administer`, and the chosen visibility's read grant is applied.

## Transport — MCP-direct (no SDK needed)

This skill uses the **bundled MCP tools** directly — no `pip install`. (If the
`methodic` SDK happens to be installed and you prefer it, the SDK equivalents
are noted inline.) The bundled launcher resolves credentials from `~/.methodic`
— see the repo README "The MCP tools (bundled — zero config)".

The move **adds** org reach — it does not strip the original creator. The
creator keeps full control (their auto-role membership + owner grant), and
`owner_subject` (billing attribution) is unchanged. This is the natural step
after starting work personally and then deciding it belongs to a shared org.

**Personal → org only.** An experiment that already has an organization
can't be moved again (the server returns 409). v1 does not support
org-to-org transfer.

## Inputs

- **`experiment_id`** — the experiment UUID. Resolve in order:
  1. Explicit argument from the user.
  2. Detect from cwd: a clone of an experiment repo whose Chronicle remote
     resolves to an experiment_id.
  3. Prompt the user.
- **`organization_id`** — the target org's principal id. If the user names
  their org (a slug or display name), resolve it against the scopes the
  caller belongs to (see step 1 below) rather than guessing. Required.
- **`team_id`** (optional) — a team within that org to own the experiment.
  When set, the **team** (not the org) becomes the owning scope for an
  org-wide read share, and the caller must be a member of the team.
- **`visibility`** (optional) — who can read the experiment after the move:
  - `"private"` — creator + org admins only.
  - `"organization"` / `"org"` / `"team"` — org/team members get
    read + discuss; **this is the default in an org context**, so omit it
    for the common "share with my org" case.
  - `"public"` — anyone, read-only.
  Omit to take the scope-derived default (org-wide).

## Workflow

1. **Resolve the target organization.** Call **`chronicle.list_scopes`** with
   `{}`. The result (JSON in the tool's text content) is every scope the caller
   can operate as — their personal space plus each team / org they belong to —
   each with `id`, `kind`, `name`, `slug`. Filter to `kind == "organization"`
   and match the org the user named (by slug or name). If exactly one org and
   the user just said "my org", use it; if the user's phrasing is ambiguous
   across several orgs, **ask which one** rather than picking the first. Take
   the matched org's `id` as `organization_id`. Don't guess a UUID.

   *(SDK equivalent: `chronicle.me.scopes()` → typed
   `Scope(id, kind, name, slug)`.)*

2. **Move.** Call **`chronicle.move_experiment`** with
   `{ "experiment_id": "<id>", "organization_id": "<org id>" }`. Add
   `"team_id": "<team id>"` only when a team within that org should own it
   (the caller must be a member of the team). Add `"visibility": "<value>"`
   to override the default; **omit it for the org-wide default** (the common
   "share with my org" case). The result reports the experiment and the org
   it now belongs to.

   *(SDK equivalent: `chronicle.experiments.move(experiment_id,
   organization_id=..., team_id=..., visibility=...)`, or the handle form
   `chronicle.experiments.get(experiment_id).move(...)`.)*

## After the skill completes

Tell the user:

1. That the experiment now belongs to the org (id + the org's name/slug), and
   the team if one was set.
2. The effective visibility — who can now read it (private = creator + org
   admins; org/team = org/team members get read + discuss; public = anyone) —
   and that org admins can administer it.
3. That the original creator keeps their access and that billing attribution
   (`owner_subject`) is unchanged — the move only added org reach.
4. That visibility can be adjusted later through ordinary membership/ACL
   management (it's not frozen by the move).

## Failure modes

- **409 — "already owned by an organization; only personal experiments can be
  moved"**: the experiment is already in an org. Org-to-org transfer isn't
  supported; surface the message. (If they want to share it more widely,
  that's a visibility/ACL change, not a move.)
- **409 — "an experiment with slug '<x>' already exists in the target
  organization …"**: the experiment's slug collides with one the org already
  owns. The user must rename this experiment's slug first
  (`PUT /v1/experiments/{id}`), then re-run the move.
- **403 — "caller is not a member of organization_id/team_id …"**: you can't
  move an experiment into a scope you don't belong to. Re-resolve the target
  against **`chronicle.list_scopes`** (the caller's actual memberships); if the
  user genuinely isn't a member, they need to be added to the org/team first.
- **404**: either the experiment doesn't exist, or the caller lacks
  `Administer` on it (the server hides existence behind 404 on an authz
  miss). Confirm the id; if it's right, the caller needs `Administer` (they
  must be the experiment's owner/admin to give it away).
- **Wrong org picked**: if **`chronicle.list_scopes`** returned several orgs and
  the user's phrasing was ambiguous, ask which one rather than picking the first.

## Requires

Nothing to install — uses the bundled MCP tools. (API-only operation; no `git`.)
