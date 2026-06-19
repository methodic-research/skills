---
name: chronicle-rebind-variation-git
description: |
  Use this skill to switch an existing **open** variation from a bundled
  `code_artifact` to **git-managed** code: the user has pushed a branch/ref to
  the experiment's repo and wants to bind it to a variation that was created
  with a bundle (`chronicle-bundle-variation`), dropping the now-stale bundle.
  Phrases like "switch this variation to git", "bind my pushed branch to
  variation 3", "use the git branch instead of the bundle for this variation",
  "rebind this variation to a git ref and drop the bundle". It binds the ref via
  `chronicle.set_variation_git_ref`, then cleans up the variation's
  `code_artifact` bundle (`chronicle.unlink_variation_input` +
  `chronicle.delete_asset`). Works only while the variation is **OPEN** —
  git-ref binding and input cleanup both freeze at commit. Distinct from
  `chronicle-bundle-variation` (creates a bundle variation),
  `chronicle-prep-variation` / `chronicle-author-variation` (create a *fresh*
  git variation), and `chronicle-fork-variation` (forks a *committed* variation).
---

# Rebind variation to git

Bind a git ref to an existing **open** variation and remove the bundle it was
created with. Use it after `chronicle-bundle-variation` when you decide the
variation's code should live on a branch in the experiment repo instead of a
one-off tarball.

Why this is safe: on commit the server packs the bound git ref into a fresh
`code_artifact` (stamped later than the bundle), and the worker selects the
**latest** `code_artifact` — so the git code wins the run even before cleanup.
Cleanup just removes the dead bundle so the variation carries exactly one code
source. Both steps require the variation to be **open**: binding and input
cleanup are refused once it is committed (inputs freeze at commit).

## Transport — MCP-direct (no SDK needed)

This is a CRUD skill, so it uses the **bundled MCP tools** directly — no
`pip install`. The bundled launcher resolves credentials from `~/.methodic`
(see the repo README "The MCP tools"). Needs a Chronicle server exposing the
variation↔git tools (chronicle-server ≥ 0.69.0). The SDK equivalents
(`chronicle.variations.*`, methodic-research ≥ 0.28) are noted inline if you
prefer the SDK.

## Prerequisite — the branch must already be pushed

This skill **binds** an existing ref; it does not push code. Get your code onto
a branch in the **experiment's** repo first (the managed repo
`chronicle-prep-variation` / `chronicle-fork-variation` use): mint an install
token, clone the experiment's `repo_url`, commit your code on a `variation/<id>`
branch (the repo root must be `pip install -e .`-able with the config's
`packages:`, same contract as the bundle), and push. Then run this skill with
that branch as `git_ref`. The protected `agent/*` namespace is rejected.

## Inputs

- **`experiment_id`** — the Chronicle experiment UUID. Resolve in order:
  explicit arg → `methodic` config (`~/.config/methodic/current_experiment`)
  → detect from cwd → prompt.
- **`variation`** — the **open** variation to rebind, by **integer index**
  (Chronicle addresses variations by int id). If the user gives a plaintext
  name, resolve it to the index in step 1.
- **`git_ref`** — a branch/tag/SHA already pushed to the experiment repo.
  Required. Not `agent/*`.

## Workflow

1. **Resolve + state-check.** Call **`chronicle.get_experiment`** with
   `{ "experiment_id": "<id>" }`. In the returned `variations[]`, find the
   target — match the integer `variation`, or a plaintext `name` and take its
   integer `variation`. Confirm it is **open** (`state` is `"open"` /
   `committed_at` is null); if it is committed, **stop** — binding and cleanup
   freeze at commit (to change code after commit, use `chronicle-fork-variation`).
   Keep the `name` for display.
   *(SDK: `chronicle.variations.get(experiment_id, variation)` → `.state`.)*

2. **Bind the git ref.** Call **`chronicle.set_variation_git_ref`** with
   `{ "experiment_id": "<id>", "variation": <int>, "git_ref": "<branch>" }`.
   Records the mapping; the SHA pins at commit (when the branch is renamed to
   `agent/v<variation>` and the repo is packed into a `code_artifact`). Errors
   if the ref is `agent/*` or the variation is committed.
   *(SDK: `chronicle.variations.set_git_ref(...)`.)*

3. **Find the stale bundle.** Call **`chronicle.list_variation_inputs`** with
   `{ "experiment_id": "<id>", "variation": <int> }`. From the returned
   `inputs[]`, select every asset whose `asset_type` is `"code_artifact"` — the
   bundle. (The git `code_artifact` does not exist yet; it's packed at commit.)
   *(SDK: `chronicle.variations.list_inputs(...)`.)*

4. **Clean up each bundle.** For each selected `code_artifact` `id`:
   1. **`chronicle.unlink_variation_input`** with
      `{ "experiment_id": "<id>", "variation": <int>, "asset_id": "<id>" }`
      (refused once committed).
   2. **`chronicle.delete_asset`** with `{ "asset_id": "<id>" }` — hard-deletes
      the now-unlinked asset (creator-guarded). If it is refused (you didn't
      create it, or it is still linked elsewhere), leave it: it is orphaned —
      note it and point the user at `chronicle-delete-asset`.
   *(SDK: `chronicle.variations.unlink_input(...)` then `chronicle.assets.delete(...)`.)*

5. **Report.** Tell the user the variation now points at `git_ref`, which bundle
   asset(s) were removed (or left orphaned), and the next step:
   **`chronicle.commit_variation`** (SDK: `chronicle.variations.commit(...)`)
   pins the SHA, packs the repo into a `code_artifact`, and creates run 0
   against the git code.

## Failure modes

- **Variation committed** (error on `set_variation_git_ref` /
  `unlink_variation_input`): the git ref and inputs freeze at commit. To change
  code after commit, create a new variation with `chronicle-fork-variation`. The
  step-1 state check catches this before any mutation.
- **`agent/*` git_ref**: the protected namespace is App-only; push to a
  `variation/<id>` branch (or another plain branch) and bind that.
- **`git_ref` not pushed**: binding records the mapping, but commit fails to
  pack a missing ref. Push the branch first (see prerequisite).
- **`delete_asset` refused** (creator guard / still linked): the unlink
  succeeded but the asset can't be hard-deleted by you — it is orphaned; surface
  the message and suggest `chronicle-delete-asset`.
- **Write denied**: the caller lacks `Write` on the experiment.

## Requires

- The bundled Chronicle MCP tools (zero install) **or** `methodic-research`
  ≥ 0.28 for the SDK path.
- A Chronicle server exposing the variation↔git tools (chronicle-server
  ≥ 0.69.0): `set_variation_git_ref`, `list_variation_inputs`,
  `unlink_variation_input`.
- Credentials in `~/.methodic` (or `CHRONICLE_API_KEY` exported).
- The target branch already pushed to the experiment repo (see prerequisite).
