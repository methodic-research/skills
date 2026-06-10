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

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 1. Resolve the target organization. `chronicle.me.scopes()` returns every
#    scope the caller can operate as — their personal space plus each team /
#    org they belong to — as a typed `Scope(id, kind, name, slug)`. Match the
#    user's named org; don't guess a UUID.
orgs = [s for s in chronicle.me.scopes() if s.kind == "organization"]
#    Pick the one the user named (by slug or name); if exactly one org and the
#    user just said "my org", use it; if ambiguous, ask which one.
organization_id = ...  # the matched org's id (e.g. orgs[0].id)

# 2. Move. Omit `visibility` for the org-wide default; pass it to override.
result = chronicle.experiments.move(
    experiment_id,
    organization_id=organization_id,
    team_id=team_id,            # optional; None for org-direct
    visibility=visibility,      # optional; None = scope-derived (org-wide)
)
print(f"Moved {result['experiment_id']} to org {result['organization_id']}")
```

The handle form is equivalent and chains:

```python
exp = chronicle.experiments.get(experiment_id)  # or any Experiment handle
exp.move(organization_id=organization_id, visibility="organization")
```

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
  (`PUT /experiments/{id}`), then re-run the move.
- **403 — "caller is not a member of organization_id/team_id …"**: you can't
  move an experiment into a scope you don't belong to. Re-resolve the target
  against `chronicle.me.scopes()` (the caller's actual memberships); if the
  user genuinely isn't a member, they need to be added to the org/team first.
- **404**: either the experiment doesn't exist, or the caller lacks
  `Administer` on it (the server hides existence behind 404 on an authz
  miss). Confirm the id; if it's right, the caller needs `Administer` (they
  must be the experiment's owner/admin to give it away).
- **Wrong org picked**: if `chronicle.me.scopes()` returned several orgs and
  the user's phrasing was ambiguous, ask which one rather than picking the first.

## Requires

- `pip install methodic-research` (≥ 0.10.0 — `experiments.move` + `me.scopes`)
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- No `git` — this is an API-only operation.
