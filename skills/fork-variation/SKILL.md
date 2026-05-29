---
name: chronicle-fork-variation
description: |
  Use this skill when the user wants to take an existing (usually committed)
  variation and create a new variation derived from it — phrases like "fork
  variation 2", "branch off this committed variation and let me modify it",
  "I want to tweak v1 but keep it intact". Different from
  `chronicle-prep-variation` (which creates a fresh variation from the
  experiment's seed) and from forking an entire experiment (use the
  Chronicle web UI or a future `chronicle-fork-experiment` skill for that).
---

# Fork variation

Creates a new user-owned variation under the same experiment, branched off
an existing committed variation's git ref. The new branch is `user/<sub>/…`
(NOT `agent/*`), so the user can push to it freely with their install
token. The original committed variation stays SHA-pinned and untouched.

## Inputs

- **`experiment_id`** — see prep-variation; same resolution rules.
- **`source_variation`** — the variation index OR plaintext name to fork
  from. Required. If the user says "fork width-doubled," resolve that
  name → index via `chronicle.variations.find_by_name(experiment_id, …)`
  before passing to the SDK calls below.
- **`description`** (optional) — one-liner for the new variation card.
- **`name`** (optional) — plaintext handle for the new fork
  (`baseline-with-larger-batch`). Unique per experiment when set. Prefer
  this over the integer index when referring to the fork in subsequent
  chat. Prompt with a derived suggestion if missing.

## Workflow

```python
from methodic import Chronicle
import subprocess, tempfile, pathlib, secrets

chronicle = Chronicle.from_env()

# 1. Resolve the source variation's git_sha (locked at its commit time)
source = chronicle.variations.get(experiment_id, source_variation)
if not source.git_sha:
    raise SystemExit(
        f"source variation has no git_sha — was it created before "
        f"git integration was enabled, or is the experiment repo still pending?"
    )

# 2. Mint a token; clone shallow at the source SHA
git_state = chronicle.experiments.git_status(experiment_id)
token = chronicle.experiments.mint_git_token(experiment_id)
clone_dir = pathlib.Path(tempfile.mkdtemp(prefix="chronicle-fork-"))
subprocess.run([
    "git", "clone",
    f"https://x:{token['token']}@{git_state['repo_url'].removeprefix('https://')}",
    str(clone_dir),
], check=True)

# 3. Check out a user branch at the source SHA
user_sub = chronicle.profile().auth0_sub.replace("|", "_")  # safe-ish for branch name
short = secrets.token_hex(4)
branch = f"user/{user_sub}/v{source_variation}-{short}"
subprocess.run(["git", "-C", str(clone_dir), "checkout", "-b", branch, source.git_sha], check=True)
subprocess.run(["git", "-C", str(clone_dir), "push", "origin", branch], check=True)

# 4. Register as a new open variation
source_handle = source.name or f"v{source_variation}"
var = chronicle.variations.create(
    experiment_id,
    config_yaml=source.config_yaml,
    git_ref=branch,
    description=description or f"forked from {source_handle}",
    name=name,  # optional plaintext handle for the fork; pass None to skip
)

fork_handle = var.name or f"v{var.variation}"
print(f"Forked {source_handle} → {fork_handle} on branch {branch}")
print(f"Local clone: {clone_dir}")
```

## After the skill completes

Tell the user the new variation index, the branch name, and the local clone
path. Remind them: pushing to `user/...` branches works freely with an
install token, while pushing to `agent/...` branches is blocked by branch
protection.

## Failure modes

- **`source.git_sha` is null**: variation was created pre-git-integration
  or the experiment repo isn't ready. Surface a clear message; do not try
  to recover automatically.
- **Token mint denied** (403): user lacks `Read` on the source variation.
- **Source SHA unreachable in repo**: rare — implies the source branch was
  rewound and GitHub GC'd the object. Falls back to "the variation row is
  pinned but the underlying code is gone." Surface the issue and suggest
  contacting whoever rewound the branch.

## Requires

Same as `chronicle-prep-variation`.
