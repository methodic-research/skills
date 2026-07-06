---
name: chronicle-checkpoint-resume
description: |
  Use this skill when an agent/runner with its OWN training code needs to make a
  Chronicle run durable and reproducible — phrases like "snapshot the
  environment", "upload checkpoints as it trains", "resume training from the last
  checkpoint", "continue the crashed run". It owns three things: capturing an
  environment snapshot at run start (library/hardware versions + your custom
  config state), uploading resumable checkpoints during training, and
  discovering + downloading the latest checkpoint to resume from. It is
  training-AGNOSTIC — the training loop is the caller's; this skill never writes
  it. It is the durable-state companion to chronicle-run-variation (which owns
  the run lifecycle + W&B linking): run-variation marks the run, this skill makes
  it survive a crash and continue. Distill afterward with chronicle-write-report.
---

# Checkpoint & resume

Make a Chronicle run **reproducible** (snapshot what ran) and **resumable**
(upload checkpoints, then resume from the latest one). This is the durable-state
companion to `chronicle-run-variation`: that skill starts/marks the run and links
W&B; this one snapshots the environment, streams checkpoints to Chronicle as
training produces them, and — on a fresh or restarted run — finds the latest
checkpoint and downloads it so training continues instead of restarting.

**Training is the caller's.** Whatever your loop does, the only framework-specific
lines are *write a checkpoint dir* and *load a checkpoint dir*; everything else is
the same `methodic` SDK calls below.

## Inputs

- **`experiment_id`** / **`variation`** / **`run`** — the run triple (same
  resolution as `chronicle-run-variation`; a just-committed variation has a
  pending run 0).
- **`checkpoint_dir`** — where your trainer writes checkpoints locally (default
  `./out`). Each checkpoint is a *directory* of files.
- **`asset_type`** — `"checkpoint"` for resumable mid-training state,
  `"snapshot"` for the final saved model. Same convention as the managed
  Menlo Park runner.

## Workflow

```python
from pathlib import Path
from methodic import Chronicle, UploadTracker

chronicle = Chronicle.from_env()
run = chronicle.run(experiment_id, variation, run_number)
run.start()                       # (or use chronicle-run-variation to start + link W&B)

# 1. SNAPSHOT THE ENVIRONMENT — anything JSON-serializable, namespaced. Capture
#    what makes the run reproducible plus your own config / run-specific state.
import platform, subprocess
env = {
    "python": platform.python_version(),
    "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
    "packages": subprocess.check_output(["pip", "freeze"]).decode().splitlines(),
    # custom configuration state + run-specific info:
    "trainer": {"framework": "my-trainer", "seed": 1234, "mixed_precision": "bf16"},
    "hyperparameters": resolved_config,
}
try:
    import torch
    env["torch"] = torch.__version__
    env["cuda"] = torch.version.cuda
    env["gpus"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
except Exception:
    pass
run.upload_environment(env)

# 2. RESUME DISCOVERY — find the latest ready checkpoint produced by an EARLIER
#    run of this variation, and download it. latest_output defaults to variation
#    scope (across runs), which is what you want: the checkpoint is from a prior
#    run. Returns None on a first run → train from scratch.
resume_dir = Path("./resume")
ckpt = run.latest_output("checkpoint")
if ckpt:
    run.download_asset(ckpt["id"], resume_dir)
    load_state(resume_dir)        # ← your framework loads the dir (mirror of save_state)
    print(f"Resumed from checkpoint {ckpt['id']} (created {ckpt['created_at']})")
else:
    print("No prior checkpoint — training from scratch")

# 3. CHECKPOINT DURING TRAINING — write a dir, hand it to the SDK. It presigns,
#    uploads each file straight to cloud storage, and finalizes on a background
#    thread, tracking upload state in local SQLite for crash recovery.
tracker = UploadTracker(db_path=Path("./uploads.sqlite"))

def checkpoint(step: int) -> None:
    out = Path(checkpoint_dir) / f"checkpoint-{step}"
    out.mkdir(parents=True, exist_ok=True)
    save_state(out)               # ← your framework writes the dir
    run.upload_directory_async(out, asset_type="checkpoint", upload_tracker=tracker)

# 4. *** THE CALLER'S OWN TRAINING RUNS HERE *** — call checkpoint(step)
#    periodically; for long runs call run.heartbeat() too.

run.succeed()                     # blocks until pending uploads finish
```

`save_state` / `load_state` are the only framework-specific lines:

- **Framework-agnostic** — write/read whatever your loop needs (weights,
  optimizer, scheduler, RNG, step) as files under the dir.
- **HuggingFace Accelerate** — `accelerator.save_state(str(dir))` /
  `accelerator.load_state(str(dir))` (or `trainer.train(resume_from_checkpoint=str(dir))`).
- **Raw PyTorch** — `torch.save({...}, dir / "state.pt")` /
  `torch.load(dir / "state.pt")`.

See the methodic SDK guide **Integrations for third-party trainers** for the full
multi-framework examples.

## Resume scope: variation, not run

A continuation run (run *N+1*) resumes from a checkpoint produced by run *N*, so
**look across all runs of the variation** — `run.latest_output("checkpoint")`
does this by default (`across_runs=True`). Scoping to the current run would find
nothing on a fresh run. Two equivalent ways to discover, depending on whether the
SDK is installed:

- **SDK**: `run.latest_output("checkpoint")`, or `run.list_outputs(across_runs=True)`
  to inspect/choose yourself.
- **MCP (no SDK install)**: `chronicle.list_outputs(experiment_id, variation=…)`
  — returns outputs newest-first; take the first whose `asset_type` is
  `"checkpoint"` and `state` is `"ready"`.

### Resuming from an input-linked checkpoint

If a researcher explicitly linked a checkpoint as a **variation input** (e.g. to
branch training from another variation), read it from the inputs instead:
`chronicle.variation(experiment_id, variation).list_inputs()` → the
`asset_type == "checkpoint"` entry → `run.download_asset(id, resume_dir)`.

## After the skill completes

Tell the user:
1. Whether the run **resumed** (from which checkpoint id + timestamp) or started fresh.
2. How many checkpoints were uploaded, and the final `snapshot` asset id if one was saved.
3. The next step: `chronicle-write-report` to distill the run.

## Failure modes

- **`latest_output` returns None when you expected a checkpoint** — you likely
  scoped to the run instead of the variation, or the prior checkpoint never
  reached `ready` (upload not finalized). List with `across_runs=True` and check
  `state`.
- **Upload still in flight at exit** — `run.succeed()` blocks on pending uploads;
  call it (don't `sys.exit` first). On crash, a restarted process resumes
  incomplete uploads from the `UploadTracker` db (re-PUT + finalize are
  idempotent).
- **Resume dir partially downloaded** — `download_asset` streams every component;
  re-run it (idempotent) if interrupted.
- **`checkpoint` vs `snapshot`** — resume reads `checkpoint`; don't mark the final
  model `checkpoint` or a resume will load a non-resumable snapshot.

## Requires

- `pip install methodic-research` (≥ the `runs.latest_output` release) — or the
  bundled MCP server for `chronicle.list_outputs` discovery without the SDK.
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done).
- The training, the `save_state`/`load_state` functions, and the compute are
  yours — this skill records durable state via the API; it never trains.
