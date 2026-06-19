---
name: chronicle-bundle-variation
description: |
  Use this skill when an agent has **external** training code — from a
  3rd-party git repo, or loose packaged code that isn't in Chronicle's
  managed experiment repo — and wants a **managed Menlo Park worker** to
  install and run it. Phrases like "bundle my code and run it on a worker",
  "package this external repo or scripts as the variation's code", "ship my
  training to a managed Chronicle worker". It snapshots the local project into
  a zip — an external git checkout (with `.git`, so the commit history rides
  along as durable provenance) or packaged code not under git at all —
  registers the zip as the variation's `code_artifact` input, and creates the
  variation, so the worker pulls the bundle, `pip install`s it, and trains.
  Prefer this over pointing Chronicle at an external git repo + ref: a
  3rd-party ref isn't durable (it can be deleted or force-pushed) and may need
  credentials Chronicle doesn't have, so the agent — which already has the
  code checked out — captures the bytes into the variation itself. This is the
  BUNDLE counterpart to the **internal**-repo skills
  (`chronicle-prep-variation` / `chronicle-author-variation`, which put code in
  the experiment's managed repo) and to `chronicle-run-variation` (BYO: the
  agent runs the training itself, no worker). Use this when a managed worker
  should run external code you don't want to (or can't) put in the managed
  repo.
---

# Bundle variation

Create a variation whose training code is a **bundled archive** that the
managed Menlo Park worker installs and runs — instead of code in the
experiment's managed git repo. The agent zips its local project, registers the
zip as the variation's `code_artifact` input, and creates the variation. On
commit, run 0 is dispatched to a worker that downloads the bundle, extracts it,
`pip install`s it, auto-scans the `packages:` from the config, and trains.

Use this for **external** code — a 3rd-party git checkout, or packaged code
that isn't under git at all. Prefer it over pointing Chronicle at an external
git repo + ref: a 3rd-party ref isn't durable (it can be deleted or
force-pushed) and may need credentials Chronicle doesn't have, so the agent —
which already has the code checked out — captures the bytes into the variation
itself. When the project is a git checkout, `.git` rides along in the zip and
the commit history is durable provenance; when it isn't under git, the bundle
is just the packaged code.

## Archive layout — must match the worker's extractor

The worker (`menlo-park-d`, `code.rs`) extracts a `code_artifact` zip with
**`unzip -d code/` and NO path stripping**, then runs `pip install -e code/`.
So the bundle must satisfy:

- **Contents at the archive root** — `code/pyproject.toml`, `code/<pkg>/…`.
  Build the zip **from the project root**; do NOT wrap it in a parent
  directory (a wrapper dir lands the code one level too deep and breaks
  `pip install -e code/`).
- **`code/` is an installable package** — a `pyproject.toml` or `setup.py` at
  the root, and every name in the config's `packages:` list must import after
  installing it.

Use **zip**, not `.tar.gz`: the worker's gzip path strips one leading
directory (to handle GitHub's `owner-repo-sha/` tarball nesting), so a
hand-rolled tarball would have to replicate that wrapper exactly. Zip
side-steps it. (This skill is authored to match the worker on purpose — the
worker contract is fixed; the skill conforms to it.)

## Inputs

- **`experiment_id`** — the Chronicle experiment UUID. Resolve in order:
  explicit arg → `methodic` config (`~/.config/methodic/current_experiment`)
  → detect from cwd → prompt.
- **`code_dir`** — local path to the project root to bundle (the directory
  with `pyproject.toml`/`setup.py`). Defaults to cwd.
- **`config_yaml`** — the full experiment YAML (`packages`, `model`,
  `dataset`, `objective`, `trainer`). A path to a local file (e.g.
  `configs/experiment.yaml`) or inline text. Required. Its `packages:` must
  be importable after `pip install`-ing `code_dir`.
- **`description`** / **`name`** (optional) — variation card one-liner and a
  short plaintext handle (unique per experiment).

## Workflow

```python
from methodic import Chronicle
from pathlib import Path
import subprocess, tempfile

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

code_dir = Path(code_dir or ".").resolve()
assert (code_dir / "pyproject.toml").exists() or (code_dir / "setup.py").exists(), (
    f"{code_dir} has no pyproject.toml/setup.py — the worker's `pip install -e code/` needs one"
)

cfg = config_yaml
if "\n" not in cfg and Path(cfg).exists():
    cfg = Path(cfg).read_text()

# 1. Bundle the project ROOT into a zip: contents at top level, `.git` kept,
#    build/venv cruft dropped. Matches the worker's `unzip -d code/` (no strip)
#    so files land at code/pyproject.toml, code/<pkg>/…  Run from code_dir so
#    archive paths are root-relative.
zip_path = Path(tempfile.mkdtemp(prefix="chronicle-bundle-")) / "code.zip"
subprocess.run(
    ["zip", "-qr", str(zip_path), ".",
     "-x", "*.pyc", "*__pycache__*", "*.egg-info/*", "*venv/*"],
    cwd=str(code_dir), check=True,
)  # .git is intentionally NOT excluded → commit history rides along as provenance

# 2. Register the code_artifact and upload the zip (presigned PUT → finalize).
#    No output_of — this is a variation INPUT (linked in step 3), not an output.
info = chronicle.assets.create_with_presigned(
    asset_type="code_artifact",
    name="code.zip",
    components=["code.zip"],
    content_type="application/zip",
)
chronicle.assets.upload_component(
    info.upload_urls.get("code.zip") or info.upload_urls["default"],
    zip_path, "application/zip",
)
chronicle.assets.finalize(info.asset_id)

# 3. Create the variation with the bundle linked as an input. No git_ref —
#    the code rides in the artifact, not the experiment repo.
var = chronicle.variations.create(
    experiment_id,
    config_yaml=cfg,
    description=description,   # optional
    name=name,                # optional plaintext handle; pass None to skip
    input_asset_ids=[info.asset_id],
)

handle = name or f"v{var.variation}"
print(f"Bundled {code_dir} → code_artifact {info.asset_id}")
print(f"Variation {handle} created with the bundle linked as a code_artifact input.")
print("Review, then `chronicle.variations.commit(...)` to dispatch run 0 to a worker.")
```

## After the skill completes

Tell the user:

1. The `code_artifact` asset id and the variation index/handle it's linked to.
2. That the code rides in the bundle (no git push); `.git` is included for
   provenance.
3. The next step: `chronicle.variations.commit(experiment_id, variation)` —
   commit creates the pending **run 0**, which a managed Menlo Park worker
   executes (a persistent worker polling for work, or an on-demand provisioned
   instance). It downloads the bundle, `unzip`s it, `pip install -e code/`s it,
   and trains.
4. If a `packages:` entry won't import after installing `code_dir`, the run
   fails fast with that `ModuleNotFoundError` — fix the package name or the
   project layout before committing.

## Failure modes

- **`code_dir` has no `pyproject.toml`/`setup.py`** — the worker's
  `pip install -e code/` needs an installable package; a bare
  `requirements.txt` + scripts won't install today. Make the project a
  package first (the assert above catches this before any upload).
- **Wrong zip layout** — if the zip wraps everything in a top folder, the
  worker's no-strip `unzip` lands code at `code/<folder>/…` and
  `pip install -e code/` fails. Always zip **from** the project root
  (`cwd=code_dir`, archive paths starting at `.`).
- **`packages:` name mismatch** — the config lists a package the installed
  project doesn't expose → `ModuleNotFoundError` at auto-scan. The `packages:`
  names must match the importable top-level packages.
- **`create_with_presigned` / `variations.create` 403** — the caller lacks
  `Write` on the experiment. Surface the message verbatim.
- **Heavy `.git`** — a large repo history bloats the bundle (every worker
  downloads it). If size is a problem, slim the history first (a fresh shallow
  clone, or `git gc`) — or drop `.git`, accepting that provenance is then the
  config only, not the commit.

## Requires

- `pip install methodic-research`
- `zip` on `$PATH`
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- A managed Menlo Park runner to execute the committed run — this skill
  delivers the code + variation; it does not provision the worker. (To run the
  training yourself instead, use `chronicle-run-variation`.)
