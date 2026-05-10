---
name: chronicle-prep-variation
description: |
  Use this skill when the user wants to start a new variation off an existing
  Chronicle experiment — phrases like "create a new variation", "start a
  fresh variation", "let me try a tweak of variation 1". The skill handles
  the full prep: mints a git token, clones the experiment repo, creates an
  agent-format branch, drops a config scaffold derived from the parent
  variation, and registers the new branch as an open variation in Chronicle.
  Do not invoke for forking an existing committed variation (that's
  `chronicle-fork-variation`) or for the very first variation 0 (which is
  created automatically with the experiment).
---

# Prep variation

Run this skill when the user wants to spin up a new variation under an
existing experiment. The end state is: a new local clone of the experiment
repo, an `agent/<short-id>` branch checked out with a config stub ready to
edit, and a corresponding open variation row in Chronicle.

## Inputs the skill needs

- **`experiment_id`** — the Chronicle experiment UUID. Try in order:
  1. Explicit argument from the user
  2. `methodic` config file (`~/.config/methodic/current_experiment`)
  3. Detect from cwd: if the user is inside a clone of an experiment repo,
     read the Chronicle remote URL and resolve the experiment_id
  4. Prompt the user
- **`from_variation`** (optional) — the parent variation index. Defaults to
  the latest committed variation if omitted.
- **`description`** (optional) — a one-liner the user wants on the variation
  card. Prompt if missing.

## Workflow

```python
from methodic import Chronicle
import subprocess, tempfile, pathlib, secrets

chronicle = Chronicle.from_env()  # picks up CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 1. Confirm experiment exists and the repo is ready
git_state = chronicle.experiments.git_status(experiment_id)
if git_state["state"] != "ready":
    raise SystemExit(f"experiment repo not ready: state={git_state['state']}")

# 2. Mint a 1-hour install token scoped to this repo
token = chronicle.experiments.mint_git_token(experiment_id)

# 3. Clone (shallow) and branch
short = secrets.token_hex(4)
branch = f"agent/{short}-{description_slug}"
clone_dir = pathlib.Path(tempfile.mkdtemp(prefix="chronicle-prep-"))
subprocess.run([
    "git", "clone", "--depth", "1",
    f"https://x:{token['token']}@{git_state['repo_url'].removeprefix('https://')}",
    str(clone_dir),
], check=True)
subprocess.run(["git", "-C", str(clone_dir), "checkout", "-b", branch], check=True)

# 4. Scaffold from parent variation's config (skill-side, no server endpoint)
parent_config = chronicle.variations.get(experiment_id, from_variation).config_yaml
(clone_dir / "config.yaml").write_text(parent_config)
# (later: apply user-hint-driven edits via an LLM call; for now just copy)

subprocess.run(["git", "-C", str(clone_dir), "add", "."], check=True)
subprocess.run(["git", "-C", str(clone_dir), "commit", "-m",
                f"prep: variation off v{from_variation}\n\n{description}"], check=True)
subprocess.run(["git", "-C", str(clone_dir), "push", "origin", branch], check=True)

# 5. Register the branch as an open variation in Chronicle
var = chronicle.variations.create(
    experiment_id,
    config_yaml=parent_config,
    git_ref=branch,
    description=description,
)

print(f"Variation {var.variation} ready at {clone_dir}")
print(f"Branch: {branch}")
print(f"Edit, commit, push, then `chronicle.variations.commit(...)` when ready.")
```

## After the skill completes

Tell the user:
1. The local path of the clone (so they can `cd` in)
2. The branch name (so they know what they're on)
3. The variation index assigned by Chronicle
4. The next steps: edit `config.yaml` (and any other files), `git push`, then
   either run `chronicle.variations.commit(...)` from the SDK or use the
   Chronicle web UI to lock the variation.

## Failure modes

- **Repo not ready** (`state: pending`): tell the user the repo is still
  being created server-side; suggest re-running in ~10 seconds.
- **Token mint denied** (403): the user lacks `Write` on the experiment.
  Surface the message verbatim.
- **Push rejected by branch protection**: should never happen for `agent/*`
  with an install token because the user mints AS the App context — but if
  it does, suggest `chronicle-fork-variation` instead.

## Requires

- `pip install methodic-client` (≥ first git-integration release)
- `git` on `$PATH`
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
