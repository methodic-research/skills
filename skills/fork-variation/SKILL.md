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

Creates a new variation under the same experiment, branched off an existing
committed variation's git ref. The new branch is `variation/<id>` (NOT
`agent/*`), so the user — or a third-party agent — can push to it freely with
an install token while the variation is open. The original committed variation
stays SHA-pinned and untouched. On commit, Chronicle renames the branch to
`agent/v<id>` and pins its SHA.

## Inputs

- **`experiment_id`** — see prep-variation; same resolution rules.
- **`source_variation`** — the variation index OR plaintext name to fork
  from. Required. If the user says "fork width-doubled," resolve that
  name → index via `chronicle.variations.find_by_name(experiment_id, …)`
  before passing to the SDK calls below.
- **`description`** — a concise one-line summary of what this fork is about,
  shown in the variations list. Provide it (what the fork changes vs the
  source); if omitted, Chronicle auto-generates one at commit (LLM,
  best-effort), but an agent-authored summary is better.
- **`name`** (optional) — plaintext handle for the new fork
  (`baseline-with-larger-batch`). Unique per experiment when set. Prefer
  this over the integer index when referring to the fork in subsequent
  chat. Prompt with a derived suggestion if missing.

## Workflow

```python
from methodic import Chronicle
import subprocess, tempfile, pathlib

chronicle = Chronicle.from_env()

# 1. Resolve the source variation's git_sha (locked at its commit time)
source = chronicle.variations.get(experiment_id, source_variation)
if not source.git_sha:
    raise SystemExit(
        f"source variation has no git_sha — was it created before "
        f"git integration was enabled, or is the experiment repo still pending?"
    )
source_handle = source.name or f"v{source_variation}"

# 2. Create the new variation FIRST (open, no branch yet) so we have its id —
#    the branch is named after the variation, not the user. Create-first +
#    bind (step 4) is exactly the flow the git-ref binding endpoint enables.
var = chronicle.variations.create(
    experiment_id,
    config_yaml=source.config_yaml,
    description=description or f"forked from {source_handle}",
    name=name,  # optional plaintext handle for the fork; pass None to skip
    # What this fork sets out to validate differently from the source, tied
    # to the eval metric — the fork's pre-registration. Prompt the user if
    # they didn't state one; it can be refined later with
    # chronicle.variations.update(...) while the fork is still open. Required
    # to commit without the explicit commit_without_hypothesis override.
    hypothesis=hypothesis,
)
branch = f"variation/{var.variation}"

# 3. Mint a token; clone shallow at the source SHA; cut the branch; push
git_state = chronicle.experiments.git_status(experiment_id)
token = chronicle.experiments.mint_git_token(experiment_id)
clone_dir = pathlib.Path(tempfile.mkdtemp(prefix="chronicle-fork-"))
subprocess.run([
    "git", "clone",
    f"https://x:{token['token']}@{git_state['repo_url'].removeprefix('https://')}",
    str(clone_dir),
], check=True)
subprocess.run(["git", "-C", str(clone_dir), "checkout", "-b", branch, source.git_sha], check=True)
subprocess.run(["git", "-C", str(clone_dir), "push", "origin", branch], check=True)

# 4. Bind the pushed branch to the variation (records the mapping; the SHA is
#    pinned at commit, when Chronicle renames it to agent/v<id>).
chronicle.variations.set_git_ref(experiment_id, var.variation, branch)

fork_handle = name or f"v{var.variation}"
print(f"Forked {source_handle} → {fork_handle} on branch {branch}")
print(f"Local clone: {clone_dir}")
```

## After the skill completes

Tell the user the new variation index, the branch name, and the local clone
path. Remind them: the `variation/...` branch is pushable with an install
token while the variation is open; on commit Chronicle renames it to
`agent/v<id>` (branch-protected, App-only) and pins the SHA.

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
