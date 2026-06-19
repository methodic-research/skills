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
  `set_git_ref`, then cleans up the variation's `code_artifact` bundle (unlink +
  delete). Works only while the variation is **OPEN** — git-ref binding and
  input cleanup both freeze at commit. Distinct from `chronicle-bundle-variation`
  (creates a bundle variation), `chronicle-prep-variation` /
  `chronicle-author-variation` (create a *fresh* git variation), and
  `chronicle-fork-variation` (forks a *committed* variation into a new one).
---

# Rebind variation to git

Bind a git ref to an existing **open** variation and remove the bundle it was
created with. Use it after `chronicle-bundle-variation` when you decide the
variation's code should live on a branch in the experiment repo instead of in a
one-off tarball.

Why this is safe: on commit the server packs the bound git ref into a fresh
`code_artifact` (stamped later than the bundle), and the worker selects the
**latest** `code_artifact` — so the git code wins the run even before cleanup.
Cleanup just removes the now-dead bundle so the variation carries exactly one
code source. Both steps require the variation to be **open**: `set_git_ref` and
input-unlink are refused (409) once it is committed (inputs freeze at commit).

## Prerequisite — the branch must already be pushed

This skill **binds** an existing ref; it does not push code. Get your code onto
a branch in the **experiment's** repo first (the same managed repo
`chronicle-prep-variation` / `chronicle-fork-variation` use): mint an install
token (`chronicle.experiments.mint_git_token`), clone
`chronicle.experiments.git_status(...)["repo_url"]`, commit your code on a
`variation/<id>` branch (the repo root must be `pip install -e .`-able with the
config's `packages:`, same contract as the bundle), and push. Then run this
skill with that branch as `git_ref`. The protected `agent/*` namespace is
App-only and rejected by the server.

## Inputs

- **`experiment_id`** — the Chronicle experiment UUID. Resolve in order:
  explicit arg → `methodic` config (`~/.config/methodic/current_experiment`)
  → detect from cwd → prompt.
- **`variation`** — the **open** variation to rebind, by index. If the user
  gives a plaintext name, resolve it to the index first from
  `chronicle.experiments.get(experiment_id).variations` (match on `name`).
- **`git_ref`** — a branch/tag/SHA already pushed to the experiment repo to
  bind. Required. Not `agent/*`.

## Workflow

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 0. The variation must be OPEN: set_git_ref + unlink_input both 409 on a
#    committed variation. Bail early with a clear message.
v = chronicle.variations.get(experiment_id, variation)
if v.state != "open":
    raise SystemExit(
        f"variation {variation} is '{v.state}'; rebinding to git (and bundle "
        f"cleanup) only works while it is open — inputs freeze at commit. "
        f"To change code after commit, create a new variation (fork-variation)."
    )

# 1. Bind the pushed ref to the open variation. Records the variation→ref
#    mapping; the SHA pins at commit, when Chronicle packs the repo into a
#    code_artifact. Rejects the protected agent/* namespace (409).
chronicle.variations.set_git_ref(experiment_id, variation, git_ref)

# 2. Clean up the stale bundle: find linked code_artifact input(s) and remove
#    each — unlink the link, then hard-delete the now-orphaned asset. Pre-commit
#    only (unlink is refused once committed). There is normally exactly one (the
#    bundle); the git code_artifact does not exist yet (it's packed at commit).
removed, orphaned = [], []
for asset in chronicle.variations.list_inputs(experiment_id, variation):
    if asset.get("asset_type") != "code_artifact":
        continue
    chronicle.variations.unlink_input(experiment_id, variation, asset["id"])
    try:
        chronicle.assets.delete(asset["id"])  # now unlinked; needs Delete / creator
        removed.append(asset["id"])
    except Exception as e:
        orphaned.append(asset["id"])
        print(f"unlinked {asset['id']} but could not hard-delete it ({e}); "
              f"it is now an orphan — purge later with chronicle-delete-asset")

handle = v.name or f"v{variation}"
print(f"Rebound {handle} to git ref '{git_ref}'.")
print(f"Removed bundle code_artifact(s): {removed or 'none found'}"
      + (f"; left orphaned: {orphaned}" if orphaned else ""))
print("On commit, Chronicle packs the git ref into a code_artifact and the run uses it.")
```

## After the skill completes

Tell the user:

1. The variation now points at `git_ref`; the bundle `code_artifact`(s) were
   unlinked and deleted (or left orphaned if delete was refused — say which).
2. Next: `chronicle.variations.commit(experiment_id, variation)` pins the SHA,
   packs the repo into a `code_artifact`, and creates run 0 against the git code.
3. If any bundle asset was only unlinked (not deleted) — e.g. the caller wasn't
   its creator or lacks `Delete` — point them at `chronicle-delete-asset`.

## Failure modes

- **Variation already committed** (409 on `set_git_ref` / `unlink_input`): the
  git ref and inputs freeze at commit. To change code after commit, create a new
  variation with `chronicle-fork-variation` instead. The skill checks `state`
  up front and bails before touching anything.
- **`agent/*` git_ref** (409): the protected namespace is App-only. Push to a
  `variation/<id>` branch (or another plain branch) and bind that.
- **`git_ref` not pushed / unknown to the repo**: binding records the mapping,
  but commit will fail to pack a missing ref. Push the branch first (see
  prerequisite).
- **delete refused** (409 linked / creator guard): the unlink succeeded but the
  asset is still referenced elsewhere, or the caller didn't create it. It's left
  orphaned — surface the message and suggest `chronicle-delete-asset`.
- **Token / write denied** (403): the caller lacks `Write` on the experiment.

## Requires

- `pip install methodic-research` (≥0.28 — `variations.list_inputs` +
  `variations.unlink_input`)
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- The target branch already pushed to the experiment repo (see prerequisite)
