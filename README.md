# skills

[![skills-e2e](https://github.com/methodic-research/skills/actions/workflows/skills-e2e.yml/badge.svg?branch=main)](https://github.com/methodic-research/skills/actions/workflows/skills-e2e.yml)

Agent plugins and skills for working with the [Chronicle](https://docs.methodiclabs.ai) experiment platform.

These skills help your agent track research hypotheses and experimental
results, and provide role-filtered search over past experimental results and
uploaded research documents. Hypotheses become first-class experiments;
variations and runs record what was tried and what it produced — metrics,
datasets, figures, write-ups, always including what *didn't* work. Search
respects your role's access: you find everything you're allowed to see and
nothing you aren't. And lineage travels with the record — parents,
retractions, invalidated outputs — so new work builds on results whose
provenance and current standing are explicit.

This repo is a marketplace for Claude Code and Codex (`methodic`) containing two plugins: **`chronicle`** — the mechanics layer, one skill per platform verb (upload a dataset, write a report, cite a DOI, run a variation) plus the bundled MCP server — and **`research`** — the workflow layer, multi-step research practices (synthesis, results evaluation, literature review, paper authoring) that compose those mechanics, with you as the approval gate. Install both; the research skills invoke the chronicle ones by name.

## Getting started

> **Quick start (TL;DR).** The default path is UI first, then the plugin:
> create an account + API key in the Methodic UI, paste its one-line setup
> command (plus one `pip install`) in your terminal, install the plugin from
> the marketplace — and you're working.
>
> ```bash
> # 1. UI: sign up at https://methodiclabs.ai/chronicle/signup, open
> #    "API keys" in the sidebar, create a key, and paste the one-line
> #    setup command the UI shows. It looks like:
> mkdir -p ~/.methodic && echo 'api_key: sk_user_...' > ~/.methodic/credentials.yaml && chmod 600 ~/.methodic/credentials.yaml
> # …optional: install the SDK (only for large/multi-file uploads + W&B):
> pip install methodic-research
> ```
> ```text
> # 2. Claude Code: install the plugins from the marketplace.
> /plugin marketplace add methodic-research/skills
> /plugin install chronicle
> /plugin install research
> ```
> ```bash
> # Codex equivalent:
> codex plugin marketplace add methodic-research/skills
> codex plugin add chronicle@methodic
> codex plugin add research@methodic
> ```
>
> That's the whole default path — once the plugin is installed you can start
> immediately ("survey the literature on …", "propose an experiment for …").
> The `pip install` is now **optional**: the plugin bundles an MCP server
> (step 3) that talks to Chronicle directly, so most skills work with no
> Python. Install `methodic-research` only for the SDK-only paths
> (large/multi-file dataset uploads, agent-side W&B). Details below.

> **Heads-up for agents (initial bootstrap).** Creating the account and API
> key happens in the Methodic UI, logged in as the user — there is no API an
> agent can call to bootstrap credentials it doesn't yet have (no key, no JWT
> → no access). If `~/.methodic/credentials.yaml` is missing, ask the user to
> do step 1 below — create a key in the UI and run the one-line setup command
> it shows in **their** terminal — then retry. Don't ask for the raw key in
> chat. The files that command writes are the same credentials everything
> here reads: the skills/SDK, the MCP `Authorization` header, and direct REST
> calls.

### 1. Create an account and API key (the Methodic UI)

Everything starts in the Methodic UI — the one step only you can do (initial
bootstrap — an agent can't do it for you; see the note above):

1. **Create an account** at
   [methodiclabs.ai/chronicle/signup](https://methodiclabs.ai/chronicle/signup)
   (or sign in if you already have one).
2. **Create an API key**: open **API keys** in the sidebar and create one.
   If you work in an organization, create the key in that organization's
   context — the setup command then records the org as your default; create
   it in your personal context otherwise.
3. **Paste the one-line setup command** the UI shows into your terminal —
   one paste, no environment variables. It writes the standard `~/.methodic`
   client config that `Chronicle.from_env()` reads, and everything here uses
   the same files: skills/SDK, the MCP `Authorization` header, and direct
   REST calls. It looks like:

   ```bash
   # Key created in your personal context:
   mkdir -p ~/.methodic && echo 'api_key: sk_user_...' > ~/.methodic/credentials.yaml && chmod 600 ~/.methodic/credentials.yaml

   # Key created in an organization context — additionally records that org:
   mkdir -p ~/.methodic && echo 'organization_id: <org-principal-id>' > ~/.methodic/config.yaml && echo 'api_key: sk_user_...' > ~/.methodic/credentials.yaml && chmod 600 ~/.methodic/credentials.yaml
   ```

4. **(Optional) Install the SDK** — the bundled MCP server (step 3) handles
   most skills with no Python at all. Install `methodic-research` only for the
   SDK-only paths: **large / multi-file directory dataset uploads**
   (`chronicle.datasets.upload` shards a directory; the MCP `upload_asset` is
   single-blob) and **agent-side W&B fetch**. Skills prefer the SDK when it's
   importable, and fall back to the MCP tools otherwise:

   ```bash
   pip install methodic-research   # optional — see above
   ```

What the setup command wrote:

- `~/.methodic/credentials.yaml` holds the secret on its own (`chmod 600`)
  so it can be permissioned and rotated separately. Pasting a new key's
  setup command overwrites it — rotation is the same one paste.
- `~/.methodic/config.yaml` stays absent for personal keys: the defaults
  are already right (`server_url` falls back to the hosted API, so the
  setup command never sets it). A key created in an organization context
  records `organization_id:` here — the default organization skills name
  on org-scoped operations (experiment/dataset creates) when you don't
  name one explicitly.
- Environment variables still win over the files when you need them (CI,
  ephemeral shells, self-hosted servers): `CHRONICLE_API_KEY`,
  `CHRONICLE_SERVER_URL`. Full resolution order in the
  [auth guide](https://docs.methodiclabs.ai/guide/auth/).

### 2. Install the plugins (the skills)

Inside Claude Code:

```text
/plugin marketplace add methodic-research/skills
/plugin install chronicle
/plugin install research
```

`chronicle` is the mechanics layer (platform verbs + the bundled MCP server); `research` is the workflow layer that composes it — installing `research` without `chronicle` gets you skills that immediately tell you to install both.

That's it — with step 1 done, you can start immediately: the skills auto-trigger by intent ("survey the literature on …", "propose an experiment for …", "make a variation that …").

**Updating.** Refreshing the marketplace alone does *not* move your installed version — do **both** steps, then restart Claude Code:

```text
/plugin marketplace update methodic
/plugin update chronicle@methodic
/plugin update research@methodic
```

(From a shell, use the qualified `chronicle@methodic` name; the `/plugin` menu inside Claude Code runs the same two steps interactively.) An install that's been sitting on an old version is the usual reason new skills or the bundled MCP server appear "missing".

<!-- MIGRATION NOTICE — added 2026-07-05 for the methodic@methodic → chronicle@methodic rename.
     Delete this whole blockquote once the rename has propagated: target ~2026-08-05 (1mo),
     no later than ~2026-09-05 (2mo). Tracking: methodic-research/skills#48 -->
> **Migrating from `methodic@methodic`?** The plugin was renamed `methodic` → `chronicle`. If you installed it before the rename, switch once — then restart Claude Code:
>
> ```text
> /plugin marketplace update methodic
> /plugin uninstall methodic@methodic
> /plugin install chronicle@methodic
> ```
>
> The marketplace name (`methodic`) and your `~/.methodic` credentials are unchanged.

Inside Codex:

```bash
codex plugin marketplace add methodic-research/skills
codex plugin add chronicle@methodic
codex plugin add research@methodic
```

For local development from a checkout, add the checkout path as the marketplace
source instead:

```bash
codex plugin marketplace add .
codex plugin add chronicle@methodic
codex plugin add research@methodic
```

The Codex plugin manifests are `plugins/chronicle/.codex-plugin/plugin.json` and
`plugins/research/.codex-plugin/plugin.json`; the Codex packages mirror the same
skills directories (`skills/` and `research-plugin/skills/`), and the chronicle
package starts the same local stdio MCP launcher via `sh ./mcp/launch.sh` (the
research plugin ships no MCP server of its own — it uses the chronicle one).

Inside [Hermes Agent](https://github.com/NousResearch/hermes-agent), install
straight from `methodiclabs.ai` — no clone, no marketplace:

```bash
hermes skills install https://methodiclabs.ai/.well-known/skills/chronicle-status
```

Hermes reads the same `SKILL.md` format this repo already writes, so nothing is
forked for it. See [Hermes Agent](#hermes-agent) below for both install routes
and which to pick.

### 3. The MCP tools (bundled — zero config)

Chronicle hosts an **MCP server** (`/v1/mcp/messages`, served by `chronicle-server`) exposing native `chronicle.*` tools — internal search, experiment create/read/commit, move/delete/retract lifecycle, report-write, image + generic asset (dataset) upload + ACL management + orphan hard-delete, research prompts, session search. **The plugin bundles a launcher that wires these up for you** (`.mcp.json` → `mcp/launch.sh`): on install it registers a local stdio MCP server that reads the **same `~/.methodic/credentials.yaml`** and proxies to your Chronicle server — no manual config, no key pasted into a file. It also intercepts `upload_asset`/`upload_image` calls that pass a local `path`, doing presign → PUT → finalize over HTTP so the bytes never pass through the model. (Runtime: the launcher probes for `node` ≥18, then `bun`, then `python3` ≥3.8, and runs a dependency-free stdlib implementation under whichever it finds. Claude Code does **not** bundle Node — only Claude Desktop does — so the Python fallback means a Python-only ML workstation works with nothing extra installed; on Windows without a POSIX `sh`, use the Desktop bundle or the remote HTTP config below. First tool use prompts for approval.) Calling these tools directly is leaner on tokens than the SDK — a structured tool call vs. reading + regenerating SDK code — so MCP-direct is the default for read/CRUD skills.

**Without the plugin** (direct-API users), point Claude Code at the remote server yourself with a project-scoped `.mcp.json` at your repo root:

```json
{
  "mcpServers": {
    "chronicle": {
      "type": "http",
      "url": "https://api.methodiclabs.ai/v1/mcp/messages",
      "headers": { "Authorization": "Bearer sk_user_..." }
    }
  }
}
```

(or `claude mcp add`). Use the same API key the setup command wrote to `~/.methodic/credentials.yaml`. The tools must be deployed on your Chronicle server — they ship with `chronicle-server`.

### 4. Literature search (external MCP)

Literature/arxiv search is **not** in Chronicle — Chronicle search is internal-only (experiment history + research docs). The `chronicle-research-survey` skill pulls papers from a separate **external literature MCP** (e.g. Paperclip); add that server the same way (`.mcp.json` / `claude mcp add`) to enable the literature leg. Without it, the survey runs Chronicle-internal only.

### Team / repo pre-config

To give a whole team a one-trust setup, commit a `.claude/settings.json` to the project — teammates are prompted to add the marketplace and enable the plugin when they trust the folder:

```json
{
  "extraKnownMarketplaces": {
    "methodic": { "source": { "source": "github", "repo": "methodic-research/skills" } }
  },
  "enabledPlugins": { "chronicle@methodic": true, "research@methodic": true }
}
```

### Claude Desktop (one-click)

Claude Desktop can't run Claude Code skills, but it *can* run the same MCP server — so you get the `chronicle.*` tools (internal search, experiment create/read/commit, lifecycle, report-write, dataset + image upload, ACL management, run-log search) directly in Desktop.

1. Download `chronicle-<version>.mcpb` from the [latest release](https://github.com/methodic-research/skills/releases/latest).
2. Open it in Claude Desktop (double-click, or **Settings → Extensions → Install from file**).
3. When prompted, paste your `sk_...` API key — or leave it blank to reuse `~/.methodic/credentials.yaml` if you already ran the CLI setup. The server URL defaults to `https://api.methodiclabs.ai`.

The bundle is the same zero-dependency `mcp/server.js` the Claude Code plugin runs, so uploads and credential resolution behave identically. Build it yourself with `bash desktop/build.sh` (writes `desktop/dist/chronicle-<version>.mcpb`).

### Hermes Agent

[Hermes Agent](https://github.com/NousResearch/hermes-agent) reads the same
`SKILL.md` format this repo already writes — `name` + `description` frontmatter,
everything else optional — so **no skill is forked for it**. Every skill here
works in Hermes unmodified, by either route below.

#### Install from methodiclabs.ai

The zero-setup route. `methodiclabs.ai` publishes a
[well-known skills index](https://methodiclabs.ai/.well-known/skills/index.json),
so Hermes can install any skill by name:

```bash
hermes skills search https://methodiclabs.ai
hermes skills install https://methodiclabs.ai/.well-known/skills/chronicle-status
hermes skills install https://methodiclabs.ai/.well-known/skills/synthesis
```

`install` takes one skill at a time — there's no `--all` — so to take the whole
set, loop over the names in the index:

```bash
curl -s https://methodiclabs.ai/.well-known/skills/index.json \
  | jq -r '.skills[].name' \
  | xargs -n1 -I{} hermes skills install \
      https://methodiclabs.ai/.well-known/skills/{} --yes
```

`--yes` skips the per-skill confirmation so the loop runs unattended; it does
**not** weaken the security scan each install runs (that's `--force`, which
installs despite a *blocked* verdict — don't use it here). No `jq`? Swap in
`python3 -c "import json,sys; [print(s['name']) for s in json.load(sys.stdin)['skills']]"`.

The site holds no skill content — it redirects to this repo's raw files, so what
you install is what's on `main`. Details and the republish flow:
[`.well-known/README.md`](.well-known/README.md).

> Prefer this over `hermes skills tap`. A tap is one repo plus one base path and
> `tap add` refuses a second entry per repo, so it reaches the skills under
> `skills/` and can never reach the four under `research-plugin/skills/`.

#### Point Hermes at a checkout

Best when you're editing skills or want to track `main` without reinstalling.
Registers the checkout instead of copying anything into `~/.hermes/skills/`:

```bash
git clone https://github.com/methodic-research/skills.git
python3 skills/hermes/install.py     # --print to see the YAML without writing
```

That appends both skill directories to `skills.external_dirs` and the Chronicle
MCP launcher to `mcp_servers` in `$HERMES_HOME/config.yaml` (default
`~/.hermes`). Every skill loads from the checkout, and `git pull` is the update
path. It's idempotent, backs the config up before writing, and preserves your
comments when `ruamel.yaml` is importable. Hand-written config, flags, and
caveats: [`hermes/README.md`](hermes/README.md).

#### Which route

| | Install from the site | Point at a checkout |
|---|---|---|
| Setup | One command per skill | Clone + one command, once |
| Updates | `hermes skills update` | `git pull` |
| Editing skills locally | No — installs a copy | Yes — edits are live |
| Needs a checkout | No | Yes |

Both give you the same skills. Either way, run the API-key setup from
[step 1](#1-create-an-account-and-api-key-the-methodic-ui) first — the skills
call Chronicle through the same `~/.methodic/credentials.yaml` as everything else.

#### Caveats

- Hermes truncates a skill `description` at 1024 characters (it doesn't reject
  it). A few skills here exceed that, so the tail of their trigger text is
  clipped in Hermes' index. They load and work normally.
- The MCP launcher needs a POSIX `sh`. On bare Windows, use WSL or point Hermes
  at the remote HTTP MCP server instead.

## What's inside

### The `research` plugin (workflow layer)

Multi-step research practices that compose the chronicle skills below — your
own agent does the work, you are the approval gate, and every milestone lands
on the experiment feed via `chronicle.report_activity`. These replace the
managed autoresearch agent fleet removed by
[methodic-research/methodic#642](https://github.com/methodic-research/methodic/issues/642):
the `chronicle-task` and `synthesis-event-handler` skills (the removed task
agents' and in-container synthesis agent's contracts) are gone with it, and
these user-side workflows are the replacement.

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `synthesis` | "what should we try next", "run a synthesis pass", "propose and queue the next variations" | The aggregate ideation workflow: grounds in the experiment record (lineage, runs, lessons), invokes `evaluate-results` + `literature-review` for the evidence base, drafts pre-registered proposals (hypothesis + expected outcome **required**), and — only for the ones you accept — queues execution: `chronicle.propose_variation` (create + commit + run → the worker job queue) for config-only changes, the variation-authoring skills first for code changes, `chronicle-propose-experiment` for a child experiment. Nothing is committed or queued without your acceptance. |
| `evaluate-results` | "what do the results say", "did it work", "judge the variations against their hypotheses" | Enumerates variations + runs, pulls the real metrics (`chronicle.wandb_*` mediation tools, `execution_log` assets, attached reports), judges each variation against its pre-registered hypothesis / expected outcome, and presents the what-worked / what-didn't / what's-unexplained read. Reading-only is first-class; on request it persists findings (`chronicle.record_finding`), lessons (`chronicle.record_lesson`), and a durable report via `chronicle-distill` (review-gated takeaways) or `chronicle-write-report`. |
| `literature-review` | "do a literature review on X", "what does the field say about Y", "ground this in prior art" | The survey workflow over `chronicle-research-survey` (internal corpus + external literature MCP) and `chronicle-publications`: scope the question, run both sources, read the load-bearing sources deeply, register + cite what's worth keeping, synthesize prior art + the gap, optionally persist a `research_report`. No experiment required — "read for yourself" works standalone; anchored to an experiment it links citations as inputs (citation types stay linkable until conclude). |
| `paper-authoring` | "draft the paper", "write this up as a LaTeX paper", "attach the paper to the experiment" | Gathers the approved record (takeaways + variation reports, figure image assets, lessons, linked citations), authors the LaTeX **locally** in your own working tree / template, and attaches the source (`latex_source` upload + `POST /v1/experiments/{id}/papers`) so Chronicle compiles it (chronicle-tex) into an `imported_report` on the experiment — re-attach on meaningful revisions; each attach is a recorded snapshot. Publishing is yours: Overleaf is just a git remote you hold credentials for; Chronicle records the paper, it is not the venue. |

### The `chronicle` plugin (mechanics layer)

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `chronicle-prep-variation` | "create a new variation", "start a fresh variation off this experiment" | Mints a git token, clones the experiment repo, creates a new agent branch with scaffolding, registers it as an open variation. |
| `chronicle-fork-variation` | "fork variation 2", "branch from this and let me edit" | Clones+branches off an existing committed variation as a *new* user-owned variation under the same experiment. Cannot push to `agent/*` directly. |
| `chronicle-mint-git-token` | "I need a git token", "give me push access to the repo" | One-shot token mint for manual git workflows. Returns an install token + clone URL. |
| `chronicle-status` | "what's running on experiment X", "any failures recently" | Snapshot of recent runs, current status, and any retracted ancestors that affect this experiment's lineage. |
| `chronicle-feed` | "check my feed", "what needs my attention", "any agents blocked on me", "what's in my inbox", "anything awaiting approval", "what happened on my experiments", "what's new" | Reads the unified event feed across everything the caller can read — the needs-you queue (`actionable=true&open=true`: blocked agents + report approvals + invites), the inbox (`recipient=me`), activity, new reports, and ranked research recs. For an agent draining it as a work queue, advances the per-section read pointer **explicitly** with `chronicle.feed_seen` — only after acting (at-least-once; the web UI auto-advances on view). MCP-direct: `chronicle.feed` / `chronicle.feed_seen`. |
| `chronicle-research-survey` | "survey the literature on X", "what's been tried", "research \<topic\>" | Surveys prior art across two corpora — Chronicle's internal experiment history + research docs (`search.history`, lineage) and external arxiv/papers via the configured literature MCP — then synthesizes gaps and optionally saves a `research_report`. Papers and prior work that inform the survey are registered (`register_publication`) and attached as citations on the anchor experiment. |
| `chronicle-propose-experiment` | "propose an experiment", "create an experiment for this hypothesis" | Turns a hypothesis into a new Chronicle experiment: creates it, attaches the full `hypothesis_report`, links a research prompt, registers + cites the papers behind the hypothesis, and optionally commits. |
| `chronicle-import-repo` | "import this repo into Chronicle", "set up an experiment from this repo", "how do I connect my local directory" | Turns an **existing local repository** into an open Chronicle experiment: evaluates the checkout (README, paper sources, scripts, deps), confirms title/hypothesis/research-prompt with the user, creates the experiment, pushes the tree to an `import/<slug>` branch of the managed repo and binds it to variation 0 (`set_variation_git_ref`; bundle-path `code_artifact` fallback), attaches LaTeX sources / docs / datasets, writes the `hypothesis_report`, and anchors the primary research prompt. Never commits — the on-ramp from existing work. See [`import.md`](../runes/chronicle/designs/import.md). |
| `chronicle-reproduce-arxiv` | "reproduce this arxiv paper", "replicate arXiv:2301.12345", "import this paper and its code" | Registers an arxiv paper (`chronicle.register_publication`, deduped `arxiv` asset), locates its public code repo (agent judgment, **user-confirmed** — official vs re-implementation), clones it, and runs the `chronicle-import-repo` core with the paper pre-linked as an input and a reproduction-framed research prompt — all locally in this session; paper-without-code falls back to a paper-only import. |
| `chronicle-author-variation` | "make a variation that doubles the width", "author a variation" | Like prep-variation, but the agent *authors* the new config from your requested change (not a verbatim copy): clone + branch, edit `config.yaml` in-context, push, register the variation. |
| `chronicle-bundle-variation` | "bundle my code and run it on a worker", "package this external repo or scripts as the variation's code", "ship my training to a managed worker" | Snapshots **external** training code — an external git checkout (`.git` rides along as provenance) or packaged code not under Chronicle's managed repo — into a tarball, registers it as the variation's `code_artifact` input, and creates the variation, so a managed Menlo Park worker pulls the bundle, `pip install`s it, and trains. Prefer over a git-repo + ref when the ref isn't durable (external repos can be deleted or force-pushed); prep/author/fork-variation handle the internal managed repo. |
| `sagemaker` | "prepare this variation for SageMaker", "run this on SageMaker", "train on spot", "make it resumable on SageMaker" | Makes a variation's training project SageMaker-ready and launches it as a Chronicle-managed SageMaker training job: declares `requirements.txt`, points checkpoints at `/opt/ml/checkpoints` for free Layer-1 S3-sync/spot resume while still pushing the canonical checkpoint to GCS (Layer 2), reads the injected `CHRONICLE_*` lifecycle/metrics env, then bundles as `code_artifact` and provisions with `runner_type: managed_sagemaker` (spot, region, optional customer integration). The SageMaker sibling to `chronicle-bundle-variation`. |
| `chronicle-rebind-variation-git` | "switch this variation to git", "bind my pushed branch to the variation", "use the git branch instead of the bundle", "rebind variation to a git ref and drop the bundle" | Switches an **open** variation from a bundled `code_artifact` to git-managed code: binds an already-pushed branch/ref via `set_git_ref`, then unlinks + deletes the now-stale bundle (the worker uses the latest `code_artifact`, so the git code wins on commit). Open variations only — git-ref binding and input cleanup freeze at commit. Pairs with `chronicle-bundle-variation`. MCP-direct: `chronicle.set_variation_git_ref` / `list_variation_inputs` / `unlink_variation_input` / `delete_asset`. |
| `chronicle-write-report` | "write up the findings", "document what we learned", "summarize this variation's results" | Attaches a Markdown + LaTeX-math research write-up (rendered inline with MathJax) to an experiment or variation, with figures uploaded as image assets and embedded by reference. Always includes an explicit "What didn't work" section, and registers + attaches citations for the papers and prior experiments the write-up leaned on. |
| `chronicle-dataset` | "upload this dataset", "register the training data", "attach this .npz to the variation", "load the dataset" | Uploads **local** dataset bytes (a file → one component; a directory → one component per file, the GB-scale sharding path) as a binary asset with a recorded provenance record (per-component sha256 + size), and links it as an experiment- or variation-level input. Also loads/downloads an existing dataset. One upload per component (presigned PUT to GCS, or multipart through Scribe on the R2 route where Chronicle enables it). For data already in a bucket + its searchable metadata, see `chronicle-register-dataset`. |
| `chronicle-register-dataset` | "register the dataset already in gs://…", "catalog this corpus we wrote to the bucket", "describe this dataset — its PDE, boundary conditions, variables", "make this dataset searchable", "fix the dataset's metadata", "what fp64 Navier–Stokes datasets do we have" | Registers a dataset that **already lives at a `gs://`/`s3://` URI** (no byte upload — created `ready` in one call, like `hf_dataset`) and authors its searchable, author-declared **metadata layer**: a LaTeX-bearing description, the governing PDE, boundary/initial conditions, domain geometry, a per-variable shape·dtype·units table, and a free-form `key=value` `properties` facet bag. Also updates that metadata (mutable annotation) and lists/filters the catalog (Postgres-side facets — `n_dims`, `precision`, `pde_family`, `geometry`, size). MCP-direct: `chronicle.{register_dataset,update_dataset_metadata,list_datasets}`. The byte-moving counterpart is `chronicle-dataset`. |
| `chronicle-collections` | "make a collection for X", "add these papers to the structural-loads collection", "associate this experiment with \<topic\>", "search only within the \<topic\> collection" | Curate a named, ACL'd topic grouping of ANY assets + experiments (overlapping). Associate a collection with an experiment to boost its members in that experiment's searches, or scope a search to a collection as a hard filter. Existence-only ACL; user-request-driven (agents search broadly by default). |
| `chronicle-tags` | "tag this as \<keyword\>", "tag these experiments turbulence", "find assets tagged X", "search only things tagged Y" | Attach lightweight, scope-namespaced keyword tags to ANY asset or experiment, and filter search by tag (`tags: ANY(...)`). Tags aren't access controls (need `Write` on the object). User-request-driven; the lighter sibling of collections. |
| `chronicle-publications` | "cite this paper", "add this DOI as a citation", "register this BibTeX", "reference arXiv:… in this experiment", "cite the paper this builds on" | Register a published work by **DOI, BibTeX, or arXiv id** as a public, shared, immutable reference record (resolved via Crossref→doi.org / the arXiv API, deduped by DOI or arxiv id+version; a no-DOI BibTeX match offers existing candidates to reuse), then cite it by linking it to an experiment as an input — works on committed experiments too (citation links lock only at conclusion, and world-readable references need only Read). For not-yet-published work, register a private **draft** you own and finalize it later — citation links stay intact. MCP: `chronicle.{register_publication,search_publications}` + `chronicle.link_asset`. |
| `chronicle-import-reports` | "import these papers", "add this folder of PDFs to the org library", "bulk import research reports" | Imports third-party research-report PDFs as **org-scoped** `imported_report` assets — presigned PUT per file, sha256 provenance with per-org dedup, then server-side extraction (math-capable OCR for image-only scans) and role-filtered search indexing. Org context is required; superadmin cross-org imports/listing are audited. See [`bulk-pdf-import.md`](../runes/chronicle/designs/bulk-pdf-import.md). |
| `chronicle-review-imports` | "review the imported reports", "which imported equations were flagged", "approve the imports" | Triages imported research reports after server-side processing: surfaces extraction/enrichment state, the table/equation objects flagged for human review (with unified annotations + explicit model disagreements), and routes actions — accept, deprecate/invalidate, approve/reject review-gated imports, or re-enqueue the extraction/enrichment jobs. |
| `chronicle-history-explorer` | "what experiments exist about X", "show the lineage", "explore history" | Read-only exploration of experiment history — semantic search (`search.history`), status-filtered browsing, the lineage DAG, and upstream retractions. |
| `chronicle-move-experiment` | "move this experiment into the org", "transfer it to the team" | Transfers a personal experiment into an organization (optionally a team), materializing the org-admin grants and requested visibility. |
| `chronicle-share` | "share this report with @alice", "give my team read on this dataset", "make this report public", "who can see this asset", "stop sharing with bob" | Shares a single asset (report, dataset, figure) independent of its experiment — per-person/per-team read grants and visibility (private / organization / public), via the bundled MCP tools. Additive over the experiment's own access; `Administer` on the asset required (its creator, or the owning experiment's admins). MCP: `chronicle.{grant,revoke,list}_asset_access` / `share_asset_with_scope` / `set_asset_visibility`. |
| `chronicle-delete-experiment` | "delete this draft", "clean up the experiments I'm not using" | Hard-deletes **open (uncommitted)** experiments and their cascade after explicit confirmation. Committed/concluded work is refused and routed to retraction. MCP: `chronicle.delete_experiment` (creator-guarded). |
| `chronicle-retract-experiment` | "retract this experiment", "this result turned out to be wrong", "withdraw those findings" | Soft-retracts a **committed/concluded** experiment (or one variation) with a required reason: row/lineage/audit preserved, output assets invalidated, repo archived read-only. MCP: `chronicle.retract_experiment`. |
| `chronicle-delete-asset` | "delete these datasets", "clean up the orphaned uploads", "purge the assets I uploaded by mistake" | Hard-deletes **unlinked** assets (no experiment/variation input or output links) after explicit confirmation — row, ACLs, storage bytes, search doc. Linked assets are refused (409) and stay deprecate/invalidate-only. MCP: `chronicle.delete_asset` (creator-guarded). |
| `triage-error-queue` | "triage the error queue", "process incoming bugs" | Drains the Chronicle error-report triage queue locally. Claims one report, gathers context, decides match/new/noise, submits a structured verdict. Run repeatedly with your agent's loop/automation runner. Cost win: the LLM call stays local instead of using Chronicle's metered server-side LLM key. See [`automated-error-reporting.md`](../runes/chronicle/designs/automated-error-reporting.md) §5.5. |
| `fix-error-queue` | "fix the next error", "work on a queued bug" | Drains the fix queue locally. Claims one open root_cause, reads the triage agent's writeup, fixes on a branch in your methodic checkout, opens a PR (no autonomous merging). Run repeatedly with your agent's loop/automation runner. See [`automated-error-reporting.md`](../runes/chronicle/designs/automated-error-reporting.md) §8.2. |
| `methodic-feedback` | "file feedback", "report this", "request a feature" — and **proactively**, whenever the agent hits a gap or issue mid-task | Records feedback to Chronicle's private feedback endpoint the moment it's encountered (Markdown body; `gap` / `feedback` / `feature_request`), then — end of turn, with your confirmation — offers to mirror it as a public GitHub issue on `methodic-research/skills` via your own `gh` (searching for duplicates first). Reproducible errors route to the error pipeline instead of plain feedback. |

Skills reach Chronicle two ways — the **bundled MCP server** (`chronicle.*` tools, no install; preferred for read/CRUD, leaner on tokens) and the [`methodic-research`](https://pypi.org/project/methodic-research/) Python SDK (preferred when importable for the byte-heavy paths — multi-file dataset uploads, agent-side W&B). Neither constructs raw HTTP from the skill itself; if something's missing, add an MCP tool and/or SDK method (and probably an API endpoint), not a network call in the skill.

> The two `*-error-queue` skills currently use raw `requests` calls because the underlying `/v1/admin/triage-queue` and `/v1/admin/fix-queue` endpoints are not yet wrapped in the SDK. Move them to `methodic.admin.*` namespaces once those endpoints stabilize (tracked in the implementation plan in `automated-error-reporting.md` §13).

## Publishing

How releases reach users:

1. **The repo is public.** `/plugin marketplace add methodic-research/skills` and `codex plugin marketplace add methodic-research/skills` resolve with the user's git credentials, so anyone can add the marketplace and install — no extra access setup.
2. **Manifests stay correct.** Claude uses `.claude-plugin/marketplace.json` plus each plugin's manifest (`.claude-plugin/plugin.json` for `chronicle` at the repo root, `research-plugin/.claude-plugin/plugin.json` for `research`); Codex uses `.agents/plugins/marketplace.json` and `plugins/{chronicle,research}/.codex-plugin/plugin.json`. Both expose the same skills; the `mcp/server.js` launcher ships with `chronicle` only (the research plugin has no MCP server of its own).
3. **Versioning drives updates.** Each plugin.json's `version` is its release knob: bump it to publish a new version of that plugin (users get it via `/plugin marketplace update`). Omit `version` instead to treat every push as a new version during active development.
4. Users then run the two commands in [step 2](#2-install-the-plugins-the-skills).

## Local development

Point Claude Code at your checkout so edits land without pushing:

```bash
claude --plugin-dir ./skills
```

`/reload-plugins` picks up edits to `SKILL.md` files mid-session.

For SDK changes alongside skill changes, install the SDK from your local
checkout instead of PyPI (`pip install -e <path-to-sdk>`); the skills only
require that `from methodic import Chronicle` resolves.

## Skill conventions

- **One skill per user-visible verb.** Keep skills small and named after what the user is trying to do, not after the API endpoint they hit.
- **Skills depend on `methodic-research`.** Skills assume `methodic` is importable in the user's Python environment. Skills surface a clear "install methodic-research first" message if the import fails.
- **No secrets in skills.** Auth tokens come from `methodic`'s standard config (env var `CHRONICLE_API_KEY` or `~/.methodic/credentials.yaml`). Skills never prompt for raw API keys, and never read `credentials.yaml` into context. If the config is missing entirely, stop and send the user to the Methodic UI's create-API-key flow — account signup at [methodiclabs.ai/chronicle/signup](https://methodiclabs.ai/chronicle/signup), then **API keys** in the sidebar; the UI prints the setup command that writes `~/.methodic` — an agent has no credential or JWT to bootstrap with, so it cannot do this step on the user's behalf.
- **Organization scope is explicit, with a recorded default.** An operation that belongs to an org names it on the request — the org-bearing field on the call (e.g. an experiment's `organization_id`); omit it for personal work. There is no ambient "active scope" to set on the client. The one allowed default: the API-key setup command records `organization_id:` in `~/.methodic/config.yaml` when the key was created in an organization context. When the user doesn't name an org, fill the org-bearing field from that recorded value and say which org was used in the output; an org the user names explicitly always wins. Read the default from `config.yaml` only — never `credentials.yaml`. List endpoints return everything your key can read; narrowing the view to a single org is the caller's/UI's concern, not a required parameter — so don't gate a listing on a scope.
- **Skill ↔ SDK ↔ API alignment.** Every skill must be expressible as a sequence of SDK calls. If a skill diagrams a workflow that the SDK can't currently support end-to-end, file it with `methodic-feedback` (which auto-files a `gap` report to the private feedback endpoint and offers a public issue at end of turn) rather than papering over the gap.
- **Gaps get reported, not papered over.** Any skill that hits a missing capability, wrong instruction, or confusing API behavior mid-task invokes `methodic-feedback` proactively — backend report at the moment of encounter, public-issue offer once the task has made maximum progress (immediately if blocking).
- **Variation naming.** Variations carry an optional plaintext `name` (unique per experiment). When referring to a variation in chat or in skill output, prefer the name; fall back to `v{variation_index}` only when name is unset. When *creating* variations (e.g. `prep-variation`, `fork-variation`), accept an optional `name` argument and pass it through to the SDK — don't synthesize one server-side without the user's input. Pattern:
  ```python
  handle = v.name or f"v{v.variation}"
  ```
- **Operational LLM calls.** Some future skills will want to ask an LLM something on the user's behalf — a hypothesis-extract, a summarization, a structured-output prompt. Two paths exist; pick deliberately:
    1. **Use the local agent session** the skill is running in. This is the obvious default for one-shot reasoning the skill itself does, and it uses the user's current agent environment rather than Chronicle's server-side LLM key.
    2. **Route through chronicle-server's resolved-LLM endpoint** (`/v1/operational/extract-hypothesis` and friends — the resolver walks the principal's scope hierarchy for a configured Anthropic/OpenAI key, falling back to a Methodic-managed key). Use this when the call needs to be billed to the user's organization, audited as a Chronicle action, or reproduced server-side from a Cloud Function or scheduled job.
  
  **Never construct a direct Anthropic/OpenAI HTTP call from a skill.** That bypasses both the user's chosen LLM (the org's Anthropic vs OpenAI default) and Chronicle's audit log.

## What this is not (yet)

- **Cloud agents.** Cloud-hosted agents that prep variations without any local checkout are tracked separately; their design intentionally avoids needing these client-side skills.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
