---
name: chronicle-mint-git-token
description: |
  Use this skill when the user wants raw push/pull access to a Chronicle
  experiment's git repo for a manual workflow — phrases like "give me a
  git token", "I want to push to the experiment repo from my IDE", "what's
  the clone URL for experiment X". Returns a 1-hour install token + the
  HTTPS clone URL. Do not use this for the prep-variation or
  fork-variation flows — those skills mint their own tokens transparently.
---

# Mint git token

One-shot mint for users who want to drive git themselves (e.g., an IDE
that wants its own credential, a script, or a manual `git clone` followed
by hand-edits). Skills that wrap multi-step workflows (prep, fork) handle
their own minting; this skill is for the explicit "I want a credential
in my hand" case.

## Inputs

- **`experiment_id`** — see prep-variation.

## Workflow

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()
token = chronicle.experiments.mint_git_token(experiment_id)
git_state = chronicle.experiments.git_status(experiment_id)

print(f"Clone URL: {git_state['repo_url']}")
print(f"Token (use as Bearer in HTTPS auth): {token['token']}")
print(f"Expires at: {token['expires_at']}  (1 hour from mint)")
print()
print("Quick clone:")
print(f"  git clone https://x:{token['token']}@{git_state['repo_url'].removeprefix('https://')}")
```

## After the skill completes

- Remind the user **the token expires in 1 hour**.
- Remind the user **`agent/*` branches are read-only with this token** —
  branch protection blocks pushes; they need to create their own branch.
- Suggest `git config credential.helper cache --timeout 3600` if they want
  git to remember the credential for the duration.

## Security notes

- The token is logged server-side in the Chronicle audit log
  (`action: git.token.mint`). Token use itself happens at GitHub and isn't
  visible to Chronicle.
- High-risk pushes (per the surveillance pipeline) trigger automatic
  revocation of all of this user's outstanding tokens. The user will see
  `403` on their next push and need to re-mint.

## Requires

Same as `chronicle-prep-variation`, minus `git` (this skill prints, doesn't run git).
