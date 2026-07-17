---
name: chronicle-reproduce-arxiv
description: |
  Use this skill when the user wants to reproduce or build on a published
  arxiv paper in Chronicle — phrases like "reproduce this arxiv paper",
  "reproduce arXiv:2301.12345", "set up an experiment to replicate this
  paper's results", "import this paper and its code", "can we reproduce the
  headline result of <paper>". Registers the paper as an `arxiv` asset,
  locates its public code repository (confirmed with the user), clones it, and
  runs the repository-import core with the paper pre-linked and a
  reproduction-framed research prompt. Takes a `--server-side` flag (or "do
  this on the server / in the background" intent) that hands the clone +
  evaluate + attach work to a tartarus task agent instead of running locally.
  Do not invoke to merely CITE a paper (that's `chronicle-publications`), to
  bulk-import PDF libraries (`chronicle-import-reports`), or for a repo the
  user already has checked out (`chronicle-import-repo`).
---

# Reproduce an arxiv paper

Turn a published arxiv paper into an **open** Chronicle experiment set up to
reproduce it. The end state is: the paper registered as a public `arxiv`
asset and linked as an experiment input, the paper's code repository imported
(managed-repo branch or bundle, via the `chronicle-import-repo` core), a
`hypothesis_report` grounding the reproduction, and a primary research prompt
framed around it — locally by default, or inside a tartarus task agent with
`--server-side`.

## Transport — MCP-direct, plus the import core

Registration and linking are **bundled MCP tools**
(`chronicle.register_publication`, `chronicle.link_asset`,
`chronicle.create_task` for server-side). The clone-and-import half composes
**`chronicle-import-repo`** — read and follow that skill for steps it owns
(evaluate, confirm, create, attach code/docs, report, prompt); this skill
documents only what reproduction adds. Credentials from `~/.methodic` (or
`CHRONICLE_API_KEY`); none → send the user to the web UI to mint an API key.

## Inputs

- **`arxiv`** — an arXiv id or URL, any of: `2301.12345`, `2301.12345v2`,
  `math.GT/0309136`, `https://arxiv.org/abs/…`, `…/pdf/…`. Required.
- **`repo`** (optional) — the code repository URL, if the user already knows
  it. Otherwise located in step 2 and **always confirmed**.
- **`--server-side`** (default off) — run the heavy half (clone, evaluate,
  attach) in a tartarus task agent. Also triggered by intent: "on the
  server", "in the background", or when invoked from a thin client with no
  room to clone.
- **`research_prompt`** (optional) — defaults to reproduction framing:
  *"Reproduce the headline result of <paper title> (arXiv:<id>); identify
  divergences."* Confirm it with the user like any import.

## Workflow

1. **Register the paper.** Call **`chronicle.register_publication`** with
   `{ "arxiv": "<id-or-url>" }`. The resolver normalizes the id, pulls
   metadata from the arXiv Atom API, and dedups on `(arxiv_id, version)` — a
   known paper returns the existing record (`existing: true`), never a
   duplicate. Keep the returned asset id and the title/abstract (they seed
   the evaluation and the prompt).

2. **Locate the code.** This is agent judgment, not an API: look for a repo
   link in the abstract/comments ("Code: https://github.com/…"), in the paper
   body, README badges, the authors' pages — via Paperclip or web search
   where available. **Always confirm the pick with the user** before cloning:
   there are often several candidates (official release vs re-implementation
   vs fork), and "official" matters for a reproduction. Present what you
   found and which one you'd choose, and say why.

   **No discoverable code →** offer the **paper-only import**: create the
   experiment (a minimal placeholder `config_yaml`, flagged as such), link
   the `arxiv` asset (step 3's link call), write the `hypothesis_report` from
   the paper's abstract/claims, and anchor the reproduction prompt — no code
   step. The user can attach code later (`chronicle-bundle-variation`, or
   push + `chronicle-rebind-variation-git`).

3. **Clone and import (local mode — the default).** `git clone` the confirmed
   repo, then run the **`chronicle-import-repo` core** against the clone —
   evaluate, confirm, `create_experiment`, attach code (managed-repo push to
   `import/<slug>` / bundle fallback), attach documents, `write_report`,
   `create_research_prompt` — with two reproduction-specific additions:

   - **Pre-link the paper** as an experiment input right after
     `create_experiment`: **`chronicle.link_asset`** with
     `{ "experiment_id": "<id>", "asset_id": "<arxiv asset id>", "link":
     "input" }`. Arxiv assets are world-readable, so the server skips ACL
     propagation and the link needs only Read. As a citation type the link
     is also exempt from the commit freeze (it stays linkable until the
     experiment concludes) — but link it up front anyway; it anchors the
     whole reproduction.
   - **Frame the research prompt around reproduction** (the default above),
     and ground the `hypothesis_report` in the paper: headline claim, the
     result to reproduce, the metric that decides success, known divergence
     risks (data availability, compute, undocumented hyperparameters).

   The experiment stays **open**; finish exactly as `chronicle-import-repo`
   does — including its step 8: **ask the user for an optional kick-off
   question** ("anything specific you want the agents to work on now beyond
   the reproduction itself?" — e.g. "check whether the result survives on
   dataset Y") and, if given, post it via
   **`chronicle.post_direction_message`** so the steering agent starts on it;
   then hand off (experiment URL + next steps).

4. **`--server-side`: run the import in tartarus.** For long clones/
   evaluations or thin clients, keep only the cheap half local:

   1. Register the paper (step 1) and confirm title/prompt/repo pick with the
      user (steps 2 + the import core's checkpoint) — confirmation cannot be
      delegated to a background agent. Also ask the optional kick-off
      question here (the import core's step 8): in server-side mode it rides
      **inside the task `prompt`** as an explicit "after import, start
      working on: <question>" instruction, not as a direction message — the
      task agent is the one doing the work.
   2. **Create the experiment client-side** (`chronicle.create_experiment`,
      as in the import core) — cheap, and it gives the task an experiment to
      bind to.
   3. **Create the task** — **`chronicle.create_task`** with
      `{ "experiment_id": "<id>", "title": "Import + reproduce arXiv:<id>",
      "prompt": <import instructions>, "input_asset_ids": ["<arxiv asset
      id>"] }`. One call = task create + first message; task creation eagerly
      dispatches the agent engine and the message cold-starts it. The
      `prompt` must tell the in-tartarus agent to follow the
      **`chronicle-task`** contract (`get_task` → work → `link_task_output`
      every produced asset) and then this import core: clone `<repo>` in the
      container, evaluate, push to `import/<slug>` using its task-scoped
      key's git token, attach the paper + docs, `write_report`, anchor the
      confirmed research prompt. Include the confirmed title / summary /
      prompt text verbatim so the agent doesn't re-ask.
   4. **Return immediately**: report the task id and its page
      (`/tasks/<id>` in the web UI) and tell the user to watch the task
      conversation — steering happens there, not here.

   `chronicle.create_task` requires **chronicle-server ≥ 0.179.0**. If it
   isn't in your tools list, the server is older: say exactly that and offer
   local mode. (`chronicle-import-repo` itself has no server-side mode — the
   repository is local by definition.)

## After the skill completes

Tell the user:

1. The paper: title, `arxiv` asset id, and whether it was newly registered or
   already known (`existing: true`).
2. Which repository was imported and why it was chosen (official vs
   re-implementation) — or that this was a paper-only import.
3. Local mode: everything `chronicle-import-repo`'s hand-off covers
   (experiment id/URL, code binding, report + prompt ids, next steps).
4. Server-side mode: the experiment id, the task id + URL, and that the
   import continues in the task conversation — outputs will appear as
   task-linked assets on the experiment.

## Failure modes

- **No credentials** → web UI to mint an API key; agents cannot bootstrap
  credentials.
- **`register_publication` can't resolve the id** — malformed id or arXiv
  API hiccup. Surface the error; re-check the id/URL with the user.
- **No discoverable code** → paper-only import (step 2). Don't fabricate a
  repo pick; if candidates are all unofficial, say so and let the user
  decide.
- **Ambiguous repo candidates** → never guess. Present them and confirm.
- **Clone fails** (private repo, auth wall): the repo isn't publicly
  clonable; ask the user for access or a mirror, or go paper-only.
- **`chronicle.create_task` missing** — server < 0.179.0. Say so; offer
  local mode.
- **`--server-side` without task dispatch available** (local-docker dev
  without the agent engine): task creation succeeds but nothing picks it up,
  or dispatch errors — fall back to local mode **with a warning**.
- **Import-core failures** (managed repo not ready, push rejected, dirty
  clone): handled per `chronicle-import-repo`'s failure modes — bundle
  fallback, etc.

## Requires

- The bundled Chronicle MCP tools (`register_publication`, `link_asset`;
  `create_task` needs chronicle-server ≥ 0.179.0 for server-side mode).
- The **`chronicle-import-repo`** skill (the shared core) and its
  requirements — `methodic-research` SDK + `git` for the local clone/push
  path.
- Credentials in `~/.methodic` (or `CHRONICLE_API_KEY` exported).
- Optional: a literature/web search MCP (e.g. Paperclip) for locating the
  code repo; without it, use the arXiv abstract page and README links.
