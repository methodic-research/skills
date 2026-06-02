---
name: chronicle-author-variation
description: |
  Use this skill when the user wants a new variation whose config the AGENT
  writes by applying a requested change — phrases like "make a variation
  that doubles the width", "author a variation with lr 1e-3", "create a
  variation that swaps the dataset to X". This is the LLM-authoring
  counterpart to `chronicle-prep-variation`: same git flow (mint token,
  clone, agent branch), but instead of copying the parent config verbatim,
  the agent reads the parent `config.yaml`, edits it in-context to apply
  the user's change, then commits/pushes/registers it. Use
  `chronicle-prep-variation` when the user just wants a scaffold to edit by
  hand, and `chronicle-fork-variation` when forking a committed variation
  into a user-owned branch.
---

# Author variation

Create a new variation under an existing experiment where the **agent
authors the config edit**. The end state matches `chronicle-prep-variation`
— a clone on an `agent/<short>-<slug>` branch and an open variation row in
Chronicle — except the new `config.yaml` already has the user's requested
change applied (and committed), rather than being a verbatim copy of the
parent.

The defining step is step 4 below: the agent reads the parent config,
applies the change in-context, and writes the result. This is in-context
reasoning by the local Claude session (the default for one-shot edits per
the repo's "Operational LLM calls" note) — **not** a server LLM call and
**never** a direct Anthropic/OpenAI HTTP request.

## Inputs

- **`experiment_id`** — the Chronicle experiment UUID. Resolve in order:
  1. Explicit argument from the user
  2. `methodic` config file (`~/.config/methodic/current_experiment`)
  3. Detect from cwd: if inside a clone of an experiment repo, read the
     Chronicle remote URL and resolve the experiment_id
  4. Prompt the user
- **`from_variation`** (optional) — the parent variation index or plaintext
  name whose config is the starting point. Defaults to the latest committed
  variation. If the user names it ("author off width-doubled"), resolve the
  name → index before the SDK calls.
- **`change_request`** — the edit to apply, in the user's words ("double
  the width", "set lr to 1e-3", "swap dataset to ripple-large"). Required —
  this skill exists to apply it. Prompt if missing.
- **`description`** (optional) — one-liner for the variation card. Default to
  a short rendering of `change_request`; confirm with the user.
- **`name`** (optional) — short plaintext handle (`width-doubled`,
  `lr-1e-3`) for the new variation. Unique per experiment. Prefer this over
  the integer index when later referring to it. Suggest one derived from
  `change_request` and accept the user's reply (including skip).

## Workflow

```python
from methodic import Chronicle
import subprocess, tempfile, pathlib, secrets

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 1. Confirm the experiment repo is ready (same gate as prep-variation).
git_state = chronicle.experiments.git_status(experiment_id)
if git_state["state"] != "ready":
    raise SystemExit(f"experiment repo not ready: state={git_state['state']}")

# 2. Mint a 1-hour install token scoped to this repo.
token = chronicle.experiments.mint_git_token(experiment_id)

# 3. Clone (shallow) and create the agent branch.
short = secrets.token_hex(4)
branch = f"agent/{short}-{description_slug}"
clone_dir = pathlib.Path(tempfile.mkdtemp(prefix="chronicle-author-"))
subprocess.run([
    "git", "clone", "--depth", "1",
    f"https://x:{token['token']}@{git_state['repo_url'].removeprefix('https://')}",
    str(clone_dir),
], check=True)
subprocess.run(["git", "-C", str(clone_dir), "checkout", "-b", branch], check=True)

# 4. *** AGENT AUTHORS THE EDIT *** — the central step of this skill.
#    Read the parent variation's config, apply `change_request` in-context,
#    and write the modified config.yaml. Unlike prep-variation (which copies
#    parent_config verbatim), here the agent mutates it.
parent_config = chronicle.variations.get(experiment_id, from_variation).config_yaml
#
#    The agent (this local Claude session) now edits `parent_config` to apply
#    `change_request`:
#      - parse the YAML structure,
#      - locate the field(s) the change touches (e.g. model.width,
#        trainer.learning_rate, dataset.name),
#      - apply the change ("double the width" → width * 2; "lr 1e-3" →
#        set trainer.learning_rate: 1e-3; "swap dataset" → replace the
#        dataset block),
#      - preserve everything else verbatim (comments, ordering, unrelated
#        keys) as much as the edit allows.
#    Make the change MINIMAL and TARGETED — touch only what `change_request`
#    asks for. If the request is ambiguous (which of two widths? what value
#    exactly?), ask the user before writing rather than guessing.
modified_config = "...the agent writes the edited YAML here, in-context..."
(clone_dir / "config.yaml").write_text(modified_config)

# 5. Commit + push the authored change on the agent branch.
subprocess.run(["git", "-C", str(clone_dir), "add", "."], check=True)
subprocess.run(["git", "-C", str(clone_dir), "commit", "-m",
                f"author: variation off v{from_variation}\n\n{change_request}"], check=True)
subprocess.run(["git", "-C", str(clone_dir), "push", "origin", branch], check=True)

# 6. Register the branch as an open variation in Chronicle — pass the
#    MODIFIED config (not the parent's), so the variation row matches the
#    committed file.
var = chronicle.variations.create(
    experiment_id,
    config_yaml=modified_config,
    git_ref=branch,
    description=description,
    name=name,  # optional plaintext handle; pass None to skip
)

handle = var.name or f"v{var.variation}"
print(f"Authored variation {handle} ({change_request!r}) at {clone_dir}")
print(f"Branch: {branch}")
print(f"Review the diff, then `chronicle.variations.commit(...)` when ready.")
```

## After the skill completes

Tell the user:

1. The local path of the clone (so they can `cd` in and review).
2. The branch name.
3. The variation index/handle assigned by Chronicle.
4. **A short summary of the exact edit the agent made** — which keys
   changed from what to what. The user is approving an agent-authored
   change, so the diff is the important output; show it or describe it
   precisely.
5. The next steps: review the change, `git push` any further hand-edits,
   then `chronicle.variations.commit(...)` (or the web UI) to lock it.

## Failure modes

- **Ambiguous `change_request`**: the agent cannot determine the exact edit
  ("make it bigger" — bigger how? "change the lr" — to what?). Do NOT guess
  and write a config; ask the user to disambiguate, then proceed.
- **Field not found in parent config**: the change references a key that
  isn't in the parent YAML (e.g. asking to change `dropout` when there's no
  dropout key). Surface this — adding a brand-new key may be correct, but
  confirm with the user it's intentional rather than a typo'd field name.
- **Repo not ready** (`state: pending`): the repo is still being created
  server-side; suggest re-running in ~10 seconds.
- **Token mint denied** (403): the user lacks `Write` on the experiment.
  Surface the message verbatim.
- **Push rejected by branch protection**: should never happen for `agent/*`
  with an install token (the user mints AS the App context) — but if it
  does, suggest `chronicle-fork-variation` (user-owned branch) instead.
- **Invalid YAML after the edit**: the agent's edit produced unparseable
  YAML, or `variations.create` rejects the config on validation. Re-read
  the parent, re-apply the change carefully, and re-write before retrying —
  don't push a broken config.

## Requires

Same as `chronicle-prep-variation`:

- `pip install methodic-research` (≥ first git-integration release)
- `git` on `$PATH`
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
