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
- **`description`** — a concise one-line summary of what this variation is
  about (what's different and why), shown in the variations list so a reader
  gets the gist without opening it. Provide it: prompt the user, or derive a
  short line from their intent. If omitted, Chronicle auto-generates one from
  the hypothesis + config at commit (LLM, best-effort) — but an
  agent-authored summary is better, so set it.
- **`name`** (optional) — a short plaintext handle (`baseline`,
  `width-doubled`) for the new variation. Unique per experiment when set.
  Prefer this over the integer index when later referring to the variation
  in chat. Prompt the user with a suggested name derived from `description`
  if they don't supply one; accept their reply (including a blank/skip).
- **`hypothesis`** — the falsifiable hypothesis this variation validates,
  tied to the eval metric (e.g. "widening attention raises eval/coherence
  vs. v1"). This is the variation's pre-registration. Prompt for it if the
  user didn't state one — a variation with no hypothesis can only be
  committed via the explicit `commit_without_hypothesis` override, so it's
  worth capturing up front. It can also be added/refined later with
  `chronicle.variations.update(experiment_id, variation, hypothesis=...)`
  while the variation is still open.
- **`expected_outcome`** (optional) — the predicted result vs. baseline.

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
    name=name,  # optional plaintext handle; pass None to skip
    # The falsifiable hypothesis this variation validates, tied to the eval
    # metric — the variation's pre-registration. A variation with no
    # hypothesis can only be committed via the explicit
    # commit_without_hypothesis override, so set it here (or later with
    # chronicle.variations.update(...,  hypothesis=...) while still open).
    hypothesis=hypothesis,
    expected_outcome=expected_outcome,  # optional predicted result vs. baseline
)

# Refer to the variation by its name when set — it's how the user
# will think about it. Fall back to the integer when the user
# declined to name it.
handle = var.name or f"v{var.variation}"
print(f"Variation {handle} ready at {clone_dir}")
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

- `pip install methodic-research` (≥ first git-integration release)
- `git` on `$PATH`
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
