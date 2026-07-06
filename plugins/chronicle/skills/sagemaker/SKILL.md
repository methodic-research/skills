---
name: sagemaker
description: |
  Use this skill when you need to make a training project run correctly as a
  Chronicle-launched Amazon SageMaker training job — phrases like "prepare this
  variation for SageMaker", "run this on SageMaker", "train on spot", "make it
  resumable on SageMaker". It owns three SageMaker-specific things: declaring
  Python deps in requirements.txt so SageMaker installs them, pointing checkpoints
  at /opt/ml/checkpoints so SageMaker's continuous S3 sync gives you free
  same-cloud + spot-interruption resume (Layer 1) while still pushing the
  canonical checkpoint to GCS for cross-cloud resume (Layer 2), and reading the
  CHRONICLE_* env the launcher injects so the run reports lifecycle + streams
  metrics. It is the SageMaker packaging companion to chronicle-checkpoint-resume
  (the framework-agnostic durable-state skill) and chronicle-run-variation (which
  owns the run lifecycle + launch). For humans and internal variation agents.
---

# Prepare a SageMaker training job

Make a Chronicle variation's training code **SageMaker-ready** and launch it as a
managed SageMaker training job. SageMaker runs your source tree natively
(installs `requirements.txt`, runs your entrypoint) and continuously syncs a
local checkpoint directory to S3 — so the work here is mostly *conforming to two
SageMaker conventions* (`requirements.txt` + `/opt/ml/checkpoints`) and *reading
the `CHRONICLE_*` env* the platform injects. The container, the worker key, and
the S3 wiring are the launcher's job (Chronicle's `managed_sagemaker` runner);
this skill makes your project run correctly inside it.

**Training is yours.** The only SageMaker-specific lines are *write checkpoints
under `/opt/ml/checkpoints`* and *resume from it on restart*; everything else is
the same `CheckpointManager` / `methodic` SDK calls as the local path.

## Inputs

- **`project_dir`** — the variation's training project root (default the current
  repo). Must be `pip`-installable: a `pyproject.toml` or `setup.py` at the root.
- **`entrypoint`** — the training script SageMaker runs (e.g. `train.py`).
- **`instance_type`** — a SageMaker catalog instance, e.g. `ml.g5.12xlarge`,
  `ml.p4d.24xlarge` (must be in Chronicle's SageMaker instance catalog).
- **`use_spot`** — request managed-spot capacity (cheaper, interruptible; resumed
  automatically from the S3-synced `/opt/ml/checkpoints`). Default `false`.
- **`region`** — training region; falls back to the platform's configured default.
- **`integration_id`** *(optional)* — a registered customer cloud integration to
  launch into your own AWS account instead of the methodic account.

## Workflow

### 1. Declare dependencies — `requirements.txt`

SageMaker installs `requirements.txt` from your source root before running the
entrypoint. Pin what the training needs (the worker contract pulls in `methodic`
+ `menlo_park`):

```text
# requirements.txt
methodic-research
torch
accelerate
transformers
```

### 2. Checkpoint to `/opt/ml/checkpoints` — both layers, one call

`CheckpointManager` with `local_checkpoint_dir="/opt/ml/checkpoints"` gives you
**both** durability layers from a single call: the directory is what SageMaker
continuously syncs to S3 (**Layer 1** — same-cloud, free, restored automatically
on a spot interruption), and the manager *also* uploads the checkpoint to GCS via
presigned URLs (**Layer 2** — canonical, lets the run resume on a different cloud
or account). No new library code — `CheckpointManager` already does both.

```python
# train.py — entrypoint SageMaker runs
import os
from pathlib import Path
from menlo_park.checkpoint import CheckpointManager

# The launcher (Chronicle managed_sagemaker runner) injects all CHRONICLE_*.
ckpt = CheckpointManager(
    experiment_id=os.environ["CHRONICLE_EXPERIMENT_ID"],
    variation=int(os.environ["CHRONICLE_VARIATION"]),
    run=int(os.environ["CHRONICLE_RUN"]),
    local_checkpoint_dir="/opt/ml/checkpoints",   # ← the SageMaker-synced dir
)

# RESUME — on a spot restart SageMaker has already re-downloaded
# /opt/ml/checkpoints, so the latest checkpoint is on local disk; load it and
# continue. (Cross-cloud resume comes via CHRONICLE_RESUME_ASSET_ID / Layer 2.)
latest = max(Path("/opt/ml/checkpoints").glob("checkpoint-*"), default=None,
             key=lambda p: int(p.name.split("-")[-1]))
if latest:
    accelerator.load_state(str(latest))
    print(f"Resumed from {latest}")
else:
    print("No checkpoint present — training from scratch")

# *** THE CALLER'S OWN TRAINING LOOP RUNS HERE *** — periodically:
ckpt.save_checkpoint(accelerator, step=step)   # writes the dir + uploads (both layers)

# at the end of a successful run:
ckpt.save_snapshot(model, tokenizer, step=step)
ckpt.close()                                   # blocks until pending uploads finish
```

### 3. Lifecycle + metrics come from `CHRONICLE_*`

The launcher injects the worker contract; your code reads it (directly, or via
`CheckpointManager` / `methodic`). You do not set these — only read them:

| Env var | Purpose |
|---|---|
| `CHRONICLE_API_KEY` | Bearer token for Chronicle/Scribe (short-lived; refreshed by the worker) |
| `CHRONICLE_SERVER_URL` | Chronicle REST endpoint (start / heartbeat / succeed / fail) |
| `CHRONICLE_SCRIBE_URL` | Scribe endpoint for metric + log streaming (absent → no-metrics) |
| `CHRONICLE_EXPERIMENT_ID` / `CHRONICLE_VARIATION` / `CHRONICLE_RUN` | which run this is |
| `CHRONICLE_RESUME_ASSET_ID` | (optional) prior checkpoint asset to resume from (Layer 2) |

For long runs, call `run.heartbeat()` (or let `menlo_park.train` drive it) so the
run isn't marked lost; stream metrics with the Scribe client. See
`chronicle-checkpoint-resume` for the framework-specific `save_state`/`load_state`
details and `chronicle-run-variation` for run start/link.

### 4. Bundle + launch as a `managed_sagemaker` run

Bundle the project as a `code_artifact` (see `chronicle-bundle-variation`) linked
as the variation input, then set the variation's `launch_config` and provision —
exactly the `chronicle-run-variation` flow, with the SageMaker runner:

```yaml
# variation launch_config
runner_type: managed_sagemaker
instance_type: ml.g5.12xlarge
use_spot: true
max_wait_seconds: 86400        # spot wait + runtime bound (required with spot)
# region: us-west-2            # optional; defaults to the platform's region
# integration_id: <id>         # optional; your own AWS account instead of methodic
```

Then `POST /v1/experiments/{id}/variations/{v}/provision` (bearer auth) submits
the SageMaker job; the run reports back over `CHRONICLE_*` and the managed
reconciler backstops terminal state if the container dies before self-reporting.

## After the skill completes

Tell the user:
1. That the project is SageMaker-ready: `requirements.txt` present, checkpoints
   pointed at `/opt/ml/checkpoints` (both layers), `CHRONICLE_*` read not set.
2. The `launch_config` written to the variation (runner, instance, spot).
3. The next step: provision the run, then `chronicle-write-report` to distill it.

## Failure modes

- **Checkpoints not resuming after a spot interruption** — they must be written
  *under* `/opt/ml/checkpoints` (the path SageMaker syncs). A different local dir
  is not synced and is lost on interruption. Confirm `local_checkpoint_dir`.
- **`ModuleNotFoundError` at job start** — a dep is missing from `requirements.txt`
  (SageMaker only installs what's declared), or the project isn't installable
  (no `pyproject.toml`/`setup.py` at the bundle root — see
  `chronicle-bundle-variation`).
- **Spot job rejected for missing max-wait** — SageMaker requires a wait bound
  with managed spot; set `max_wait_seconds` (≥ runtime) in the launch_config, or
  the launcher's default is used.
- **Run never reports / marked lost** — the entrypoint didn't read `CHRONICLE_*`
  or never heartbeats. The managed reconciler will still reconcile the terminal
  state from SageMaker, but in-run metrics/logs require the contract.
- **Customer-integration launch returns 501** — the own-AWS path isn't enabled
  yet; omit `integration_id` to use the methodic-account path.

## Requires

- `requirements.txt` listing `methodic-research` + your training deps; an
  installable project (`pyproject.toml`/`setup.py` at the root).
- Chronicle's SageMaker runner enabled for the methodic account (feature flag) or
  a registered cloud integration; the chosen `instance_type` in the catalog.
- The training, the entrypoint, and the checkpoint `save`/`load` are yours — this
  skill makes the project conform to SageMaker; it never trains.
