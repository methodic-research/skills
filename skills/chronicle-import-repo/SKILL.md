---
name: chronicle-import-repo
description: |
  Use this skill when the user has an EXISTING body of work — a local research
  repository, a paper-in-progress with code, a directory of experiments — and
  wants it turned into a Chronicle experiment. Phrases like "import this repo
  into Chronicle", "set up an experiment from this repo", "turn this project
  into a Chronicle experiment", "how do I upload my files / connect my local
  directory", "onboard this codebase". Run it inside the checkout: it evaluates
  the repo (README, paper sources, scripts, deps), confirms a title /
  hypothesis / research prompt with the user, creates the experiment, pushes
  the code to the managed repo (or bundles it), attaches paper sources and
  reports, and anchors a research prompt. The experiment is left OPEN — import
  never commits. Do not invoke for a from-scratch hypothesis (that's
  `chronicle-propose-experiment`), for adding code to an experiment that
  already exists (`chronicle-bundle-variation` / `chronicle-prep-variation`),
  or for an arxiv paper you don't have locally (`chronicle-reproduce-arxiv`).
---

# Import a repository

Turn the repository you are sitting in into a first-class Chronicle
experiment. The end state is: a new **open** experiment whose variation 0 runs
the imported code (managed-repo branch bound, or a `code_artifact` bundle
linked), the paper sources and documents attached as assets, a full
`hypothesis_report` capturing the repo evaluation, and a primary
`research_prompt` anchoring the goal. Import is the on-ramp from *existing
work* — the user should never be left staring at a blank experiment page.

Import **never commits**. Commitment locks the spec and is a researcher
decision; the hand-off (last step) tells the user how.

## Transport — MCP-first, SDK for the git leg

Creates, reports, prompts, and links use the **bundled MCP tools**
(`chronicle.create_experiment`, `set_variation_git_ref`, `upload_asset`,
`link_asset`, `write_report`, `create_research_prompt`) — no install. The
managed-repo push needs `git_status` + `mint_git_token`, which are SDK-only
(`from methodic import Chronicle; Chronicle.from_env()`), plus `git` itself —
same split as `chronicle-prep-variation`. Credentials resolve from
`~/.methodic` (or `CHRONICLE_API_KEY`); if none exist, send the user to the
web UI to mint an API key — agents cannot bootstrap credentials.

## Inputs

- **`repo_root`** — the checkout to import. Defaults to cwd. Everything else
  is *derived* from it in step 1 and *confirmed* in step 2:
- **`title`** — short noun-phrase heading (same discipline as
  `chronicle-propose-experiment`: detail goes in the summary/report, not here).
- **`hypothesis_summary`** — one/two sentences: what question this work
  answers and what remains open.
- **`research_prompt`** — the anchoring goal. For the canonical case ("we
  have a method and a paper draft") this is the open question, e.g. "find an
  example where method X actually beats method Y".
- **`config_yaml`** — variation 0's config (required by `create_experiment`).
  Prefer a real experiment/training YAML found in the repo; otherwise draft a
  minimal one and flag it as a placeholder in step 2.
- **code attach mode** — managed-repo **push** (default) or **bundle**
  (frozen zip). See step 4 for when to fall back.

## Workflow

1. **Evaluate the repository.** Read the `README`, any paper source (`*.tex`,
   `paper/`, `docs/`), experiment/training scripts and entry points,
   dependency manifests (`pyproject.toml`, `requirements.txt`), and existing
   configs. Produce: the title, hypothesis summary, research prompt, a
   candidate `config_yaml`, and an **inventory of importable artifacts** —
   paper sources, prose docs/PDFs, datasets (local files or `gs://`/`s3://`
   URIs referenced in configs), notable configs.

2. **Confirm with the user** (interactive checkpoint — do not skip). Show:
   title, hypothesis summary, research prompt, the artifact inventory with
   what will be attached where, the attach mode for the code, and — when no
   runnable training entry point is evident — what variation 0 should do (a
   placeholder config is fine; say so). Never silently commit; the experiment
   is left **open**.

3. **Create the experiment.** Call **`chronicle.create_experiment`** with
   `{ "title": <title>, "hypothesis_summary": <summary>, "config_yaml":
   <config_yaml> }`. This provisions the managed GitHub repo via the creator
   pipeline and eagerly spawns the steering agent, exactly like a from-scratch
   create. The result carries `experiment_id`, `variation` (0), and the
   resolved `slug` — keep all three.

4. **Attach the code — default: managed-repo push.** The original repo is
   *copied in*; Chronicle cannot adopt an external repo as the experiment's
   canonical repo (no such primitive — the creator pipeline always mints a
   fresh managed repo). Provenance rides in the pushed history.

   ```python
   from methodic import Chronicle
   chronicle = Chronicle.from_env()

   git_state = chronicle.experiments.git_status(experiment_id)
   assert git_state["state"] == "ready"   # pending → retry in ~10s; degraded → bundle path
   token = chronicle.experiments.mint_git_token(experiment_id)  # 1-hour install token
   ```

   ```bash
   # From inside repo_root. One-shot URL push — no remote is stored, so the
   # token never lands in .git/config. NEVER push to agent/* (protected,
   # App-only); import/<slug> is the convention.
   git push "https://x:${TOKEN}@${REPO_URL#https://}" HEAD:import/<slug>
   ```

   Then bind it to variation 0: **`chronicle.set_variation_git_ref`** with
   `{ "experiment_id": "<id>", "variation": 0, "git_ref": "import/<slug>" }`.
   At variation commit the server pins the SHA, renames the branch to
   `agent/v0`, and packs the repo into a `code_artifact` — so the imported
   code is what run 0 executes.

   `git push HEAD:...` pushes the last **commit** — uncommitted changes don't
   ride. If the tree is dirty, ask: commit first (a plain `git add -A && git
   commit` in their repo, with their OK), or take the bundle path (the zip
   captures the working tree byte-for-byte).

   **Fall back to the bundle path when:** the checkout isn't a git repo; the
   tree is dirty and the user won't commit (or explicitly wants a frozen
   snapshot); the managed repo isn't `ready` (creator pipeline degraded /
   GitHub App unconfigured — say so, per the failure-modes list); or the push
   is rejected. Bundle per the `chronicle-bundle-variation` archive contract —
   zip **from the project root** (contents at archive root, no wrapper dir),
   `.git` kept as provenance, cruft excluded:

   ```bash
   (cd repo_root && zip -qr /tmp/code.zip . -x "*.pyc" "*__pycache__*" "*.egg-info/*" "*venv/*")
   ```

   Upload + link in one MCP call: **`chronicle.upload_asset`** with
   `{ "experiment_id": "<id>", "filename": "code.zip", "asset_type":
   "code_artifact", "content_type": "application/zip", "variation": 0,
   "link": "input" }` — omit `base64_content` to get a presigned PUT
   `upload_url` for the bytes, then finalize as the tool result instructs.
   Note the worker contract: run 0 `pip install -e code/`s the extracted
   root, so a repo without a `pyproject.toml`/`setup.py` won't run as-is —
   fine for an open import, but tell the user.

5. **Attach the documents.**
   - **LaTeX paper sources** — zip the `.tex` project (single file: as-is)
     and attach it through the server's LaTeX-attach pipeline
     (`POST /v1/experiments/{id}/papers` — landing concurrently in
     chronicle-server): if a `chronicle.*` paper-attach tool is present in
     your tools list, use it. Otherwise upload the zip via
     `chronicle.upload_asset` as `asset_type: "latex_source"`,
     `link: "input"` (experiment-level — no `variation`), and tell the user
     the experiment page's paper drop zone also takes the same zip — either
     way the server compiles it (chronicle-tex/Tectonic), extracts the PDF,
     and indexes it.
   - **Prose docs / third-party PDFs** without LaTeX go in as
     `imported_report` via the **chronicle-import-reports** flow — note it is
     org-scoped (requires an organization; never personal).
   - **Datasets** found in the inventory: offer
     **chronicle-register-dataset** (data already at a `gs://`/`s3://` URI —
     metadata-only registration) or **chronicle-dataset** (local bytes).

6. **Write the hypothesis report.** Call **`chronicle.write_report`** with
   `{ "experiment_id": "<id>", "kind": "hypothesis_report", "summary":
   <hypothesis_summary>, "body": <full evaluation> }` — the body is the step-1
   evaluation in full: repo inventory, method summary, what the existing
   results show, open questions. This is the experiment's pre-registration and
   the commit gate requires it; write it now even though import doesn't
   commit. (Math renders via MathJax — `$…$` / `$$…$$`, display fences alone
   on their own lines, same discipline as `chronicle-write-report`.)

7. **Anchor the research prompt.** Call **`chronicle.create_research_prompt`**
   with `{ "experiment_id": "<id>", "prompt": <research_prompt>, "primary":
   true }`. Prompts are immutable once created — use the step-2 confirmed text.

8. **Ask for a kick-off question.** Ask the user: *"Is there a specific
   question or idea you want the Methodic agents to start working on now?"*
   (e.g. "find an example where our method beats method X"). This is optional
   — accept "not yet" and move on. If they give one, post it as the
   experiment's first direction message with
   **`chronicle.post_direction_message`** `{ "experiment_id": "<id>",
   "text": <the question> }` — this wakes (or cold-starts) the experiment's
   steering agent, which begins working immediately; the conversation
   continues in the Direction tab on the experiment page. Do **not** merge
   the question into the research prompt retroactively — the prompt is
   immutable and was confirmed in step 2; the direction message is the live
   work order. If the tool is absent (server < 0.181.0), tell the user to
   paste the question into the Direction tab — same effect.

9. **Hand off.** Print the experiment page (`/experiments/<id>` in the
   Chronicle web UI) and the "what to do next" summary below.

## After the skill completes

Tell the user:

1. The experiment id + slug (state: **open** — import never commits) and its
   page in the web UI.
2. How the code went in: the `import/<slug>` branch bound to variation 0 (and
   that commit will pin the SHA and pack it for the worker), or the
   `code_artifact` bundle id linked as a variation-0 input.
3. What documents/datasets were attached (ids), and what was *offered* but
   deferred (e.g. datasets awaiting `chronicle-register-dataset`).
4. The `hypothesis_report` and research-prompt ids.
5. If a kick-off question was posted (step 8): say so, and point at the
   Direction tab to watch the agent's response.
6. Next steps: steer the experiment agent from the Direction chat on the
   experiment page, refine the config, then **commit when the spec is
   settled** (`chronicle.commit_experiment`, then
   `chronicle.commit_variation` to dispatch run 0); add variations with
   `chronicle-prep-variation` / `chronicle-author-variation`.

## Failure modes

- **No credentials** — `~/.methodic` empty and no `CHRONICLE_API_KEY`: send
  the user to the web UI to mint an API key. Standard skill rule; do not try
  to bootstrap credentials.
- **Managed repo not ready** (`git_status` stuck `pending`, or the creator
  pipeline is degraded / GitHub App unconfigured): retry once after ~10s, then
  take the bundle path **and say so** — the user can rebind to git later with
  `chronicle-rebind-variation-git`.
- **Push rejected** — `agent/*` is protected (use `import/<slug>`); a token
  older than 1 hour has expired (re-mint); anything else, fall back to the
  bundle and surface the git error.
- **`create_experiment` 403** — the user lacks `Create`. Surface verbatim.
- **`config_yaml` invalid** — the server validates the seed config; surface
  the validation error, fix with the user, retry.
- **`write_report` / `create_research_prompt` fails after create** — the
  experiment exists; don't orphan it. Report what succeeded, retry the failed
  call, and if it keeps failing tell the user exactly which step to re-run.
- **Dirty working tree on the push path** — see step 4: commit with the
  user's OK or switch to the bundle.

## Requires

- The bundled Chronicle MCP tools (zero install) for creates/links/reports.
- `pip install methodic-research` + `git` on `$PATH` for the managed-repo
  push (SDK `git_status` / `mint_git_token`); `zip` for the bundle fallback.
- Credentials in `~/.methodic` (or `CHRONICLE_API_KEY` exported).
- The sibling skills it composes for documents/datasets:
  `chronicle-import-reports`, `chronicle-register-dataset`,
  `chronicle-dataset`.
