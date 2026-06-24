# skills

[![skills-e2e](https://github.com/methodic-research/skills/actions/workflows/skills-e2e.yml/badge.svg?branch=main)](https://github.com/methodic-research/skills/actions/workflows/skills-e2e.yml)

Claude Code plugin: skills for working with the [Chronicle](https://docs.methodiclabs.ai) experiment platform.

These skills help your agent track research hypotheses and experimental
results, and provide role-filtered search over past experimental results and
uploaded research documents. Hypotheses become first-class experiments;
variations and runs record what was tried and what it produced — metrics,
datasets, figures, write-ups, always including what *didn't* work. Search
respects your role's access: you find everything you're allowed to see and
nothing you aren't. And lineage travels with the record — parents,
retractions, invalidated outputs — so new work builds on results whose
provenance and current standing are explicit.

This repo is a Claude Code marketplace containing one plugin (`methodic`).

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
> # 2. Claude Code: install the plugin from the marketplace.
> /plugin marketplace add methodic-research/skills
> /plugin install methodic
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

### 2. Install the plugin (the skills)

Inside Claude Code:

```text
/plugin marketplace add methodic-research/skills
/plugin install methodic
```

That's it — with step 1 done, you can start immediately: the skills auto-trigger by intent ("survey the literature on …", "propose an experiment for …", "make a variation that …"). Pull new versions later with `/plugin marketplace update methodic`.

### 3. The MCP tools (bundled — zero config)

Chronicle hosts an **MCP server** (`/v1/mcp/messages`, served by `chronicle-server`) exposing native `chronicle.*` tools — internal search, experiment create/read/commit, move/delete/retract lifecycle, report-write, image + generic asset (dataset) upload + ACL management + orphan hard-delete, research prompts, session search. **The plugin bundles a launcher that wires these up for you** (`.mcp.json` → `mcp/server.js`): on install it registers a local stdio MCP server that reads the **same `~/.methodic/credentials.yaml`** and proxies to your Chronicle server — no manual config, no key pasted into a file. It also intercepts `upload_asset`/`upload_image` calls that pass a local `path`, doing presign → PUT → finalize over HTTP so the bytes never pass through the model. (`node` ≥18, already required by Claude Code; first tool use prompts for approval.) Calling these tools directly is leaner on tokens than the SDK — a structured tool call vs. reading + regenerating SDK code — so MCP-direct is the default for read/CRUD skills.

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
  "enabledPlugins": { "methodic@methodic": true }
}
```

## What's inside

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `chronicle-prep-variation` | "create a new variation", "start a fresh variation off this experiment" | Mints a git token, clones the experiment repo, creates a new agent branch with scaffolding, registers it as an open variation. |
| `chronicle-fork-variation` | "fork variation 2", "branch from this and let me edit" | Clones+branches off an existing committed variation as a *new* user-owned variation under the same experiment. Cannot push to `agent/*` directly. |
| `chronicle-mint-git-token` | "I need a git token", "give me push access to the repo" | One-shot token mint for manual git workflows. Returns an install token + clone URL. |
| `chronicle-status` | "what's running on experiment X", "any failures recently" | Snapshot of recent runs, current status, and any retracted ancestors that affect this experiment's lineage. |
| `chronicle-research-survey` | "survey the literature on X", "what's been tried", "research \<topic\>" | Surveys prior art across two corpora — Chronicle's internal experiment history + research docs (`search.history`, lineage) and external arxiv/papers via the configured literature MCP — then synthesizes gaps and optionally saves a `research_report`. |
| `chronicle-propose-experiment` | "propose an experiment", "create an experiment for this hypothesis" | Turns a hypothesis into a new Chronicle experiment: creates it, attaches the full `hypothesis_report`, links a research prompt, and optionally commits. |
| `chronicle-author-variation` | "make a variation that doubles the width", "author a variation" | Like prep-variation, but the agent *authors* the new config from your requested change (not a verbatim copy): clone + branch, edit `config.yaml` in-context, push, register the variation. |
| `chronicle-bundle-variation` | "bundle my code and run it on a worker", "package this external repo or scripts as the variation's code", "ship my training to a managed worker" | Snapshots **external** training code — an external git checkout (`.git` rides along as provenance) or packaged code not under Chronicle's managed repo — into a tarball, registers it as the variation's `code_artifact` input, and creates the variation, so a managed Menlo Park worker pulls the bundle, `pip install`s it, and trains. Prefer over a git-repo + ref when the ref isn't durable (external repos can be deleted or force-pushed); prep/author/fork-variation handle the internal managed repo. |
| `sagemaker` | "prepare this variation for SageMaker", "run this on SageMaker", "train on spot", "make it resumable on SageMaker" | Makes a variation's training project SageMaker-ready and launches it as a Chronicle-managed SageMaker training job: declares `requirements.txt`, points checkpoints at `/opt/ml/checkpoints` for free Layer-1 S3-sync/spot resume while still pushing the canonical checkpoint to GCS (Layer 2), reads the injected `CHRONICLE_*` lifecycle/metrics env, then bundles as `code_artifact` and provisions with `runner_type: managed_sagemaker` (spot, region, optional customer integration). The SageMaker sibling to `chronicle-bundle-variation`. |
| `chronicle-rebind-variation-git` | "switch this variation to git", "bind my pushed branch to the variation", "use the git branch instead of the bundle", "rebind variation to a git ref and drop the bundle" | Switches an **open** variation from a bundled `code_artifact` to git-managed code: binds an already-pushed branch/ref via `set_git_ref`, then unlinks + deletes the now-stale bundle (the worker uses the latest `code_artifact`, so the git code wins on commit). Open variations only — git-ref binding and input cleanup freeze at commit. Pairs with `chronicle-bundle-variation`. MCP-direct: `chronicle.set_variation_git_ref` / `list_variation_inputs` / `unlink_variation_input` / `delete_asset`. |
| `chronicle-write-report` | "write up the findings", "document what we learned", "summarize this variation's results" | Attaches a Markdown + LaTeX-math research write-up (rendered inline with MathJax) to an experiment or variation, with figures uploaded as image assets and embedded by reference. Always includes an explicit "What didn't work" section. |
| `chronicle-task` | "work on this task", "do the task", "generate a dataset for this experiment and register it", "gather and summarize this experiment's results" | Execute a Chronicle **task** — a generic, steered agent unit of work (designs/tasks.md) whose context (an experiment / dataset / asset) is **auto-injected**. Reads the injected context (`chronicle.get_task`), does the steered work by composing the purpose-built skills (chronicle-register-dataset / chronicle-write-report / chronicle-dataset), and records every produced asset back to the task (`chronicle.link_task_output`) + wires it to its experiment where the steer implies it (`chronicle.link_asset`). Generic — owns the task *mechanics*, not domain behavior; for an agent running *inside* a task (its id is in the launch env), not for launching one (that's the Tasks SPA / `POST /v1/tasks`). |
| `chronicle-dataset` | "upload this dataset", "register the training data", "attach this .npz to the variation", "load the dataset" | Uploads **local** dataset bytes (a file → one component; a directory → one component per file, the GB-scale sharding path) as a binary asset with a recorded provenance record (per-component sha256 + size), and links it as an experiment- or variation-level input. Also loads/downloads an existing dataset. Single presigned PUT per component — no multipart. For data already in a bucket + its searchable metadata, see `chronicle-register-dataset`. |
| `chronicle-register-dataset` | "register the dataset already in gs://…", "catalog this corpus we wrote to the bucket", "describe this dataset — its PDE, boundary conditions, variables", "make this dataset searchable", "fix the dataset's metadata", "what fp64 Navier–Stokes datasets do we have" | Registers a dataset that **already lives at a `gs://`/`s3://` URI** (no byte upload — created `ready` in one call, like `hf_dataset`) and authors its searchable, author-declared **metadata layer**: a LaTeX-bearing description, the governing PDE, boundary/initial conditions, domain geometry, a per-variable shape·dtype·units table, and a free-form `key=value` `properties` facet bag. Also updates that metadata (mutable annotation) and lists/filters the catalog (Postgres-side facets — `n_dims`, `precision`, `pde_family`, `geometry`, size). MCP-direct: `chronicle.{register_dataset,update_dataset_metadata,list_datasets}`. The byte-moving counterpart is `chronicle-dataset`. |
| `chronicle-collections` | "make a collection for X", "add these papers to the structural-loads collection", "associate this experiment with \<topic\>", "search only within the \<topic\> collection" | Curate a named, ACL'd topic grouping of ANY assets + experiments (overlapping). Associate a collection with an experiment to boost its members in that experiment's searches, or scope a search to a collection as a hard filter. Existence-only ACL; user-request-driven (agents search broadly by default). |
| `chronicle-tags` | "tag this as \<keyword\>", "tag these experiments turbulence", "find assets tagged X", "search only things tagged Y" | Attach lightweight, scope-namespaced keyword tags to ANY asset or experiment, and filter search by tag (`tags: ANY(...)`). Tags aren't access controls (need `Write` on the object). User-request-driven; the lighter sibling of collections. |
| `chronicle-publications` | "cite this paper", "add this DOI as a citation", "register this BibTeX", "reference arXiv:… in this experiment", "cite the paper this builds on" | Register a published work by **DOI or BibTeX** as a public, shared, immutable `publication` record (resolved via Crossref→doi.org, deduped by DOI; a no-DOI BibTeX match offers existing candidates to reuse), then cite it by linking it to an experiment as an input. For not-yet-published work, register a private **draft** you own and finalize it later — citation links stay intact. MCP: `chronicle.{register_publication,search_publications}` + `chronicle.link_asset`. |
| `chronicle-import-reports` | "import these papers", "add this folder of PDFs to the org library", "bulk import research reports" | Imports third-party research-report PDFs as **org-scoped** `imported_report` assets — presigned PUT per file, sha256 provenance with per-org dedup, then server-side extraction (math-capable OCR for image-only scans) and role-filtered search indexing. Org context is required; superadmin cross-org imports/listing are audited. See [`bulk-pdf-import.md`](../runes/chronicle/designs/bulk-pdf-import.md). |
| `chronicle-review-imports` | "review the imported reports", "which imported equations were flagged", "approve the imports" | Triages imported research reports after server-side processing: surfaces extraction/enrichment state, the table/equation objects flagged for human review (with unified annotations + explicit model disagreements), and routes actions — accept, deprecate/invalidate, approve/reject review-gated imports, or re-enqueue the extraction/enrichment jobs. |
| `chronicle-history-explorer` | "what experiments exist about X", "show the lineage", "explore history" | Read-only exploration of experiment history — semantic search (`search.history`), status-filtered browsing, the lineage DAG, and upstream retractions. |
| `chronicle-move-experiment` | "move this experiment into the org", "transfer it to the team" | Transfers a personal experiment into an organization (optionally a team), materializing the org-admin grants and requested visibility. |
| `chronicle-share` | "share this report with @alice", "give my team read on this dataset", "make this report public", "who can see this asset", "stop sharing with bob" | Shares a single asset (report, dataset, figure) independent of its experiment — per-person/per-team read grants and visibility (private / organization / public), via the bundled MCP tools. Additive over the experiment's own access; `Administer` on the asset required (its creator, or the owning experiment's admins). MCP: `chronicle.{grant,revoke,list}_asset_access` / `share_asset_with_scope` / `set_asset_visibility`. |
| `chronicle-delete-experiment` | "delete this draft", "clean up the experiments I'm not using" | Hard-deletes **open (uncommitted)** experiments and their cascade after explicit confirmation. Committed/concluded work is refused and routed to retraction. MCP: `chronicle.delete_experiment` (creator-guarded). |
| `chronicle-retract-experiment` | "retract this experiment", "this result turned out to be wrong", "withdraw those findings" | Soft-retracts a **committed/concluded** experiment (or one variation) with a required reason: row/lineage/audit preserved, output assets invalidated, repo archived read-only. MCP: `chronicle.retract_experiment`. |
| `chronicle-delete-asset` | "delete these datasets", "clean up the orphaned uploads", "purge the assets I uploaded by mistake" | Hard-deletes **unlinked** assets (no experiment/variation input or output links) after explicit confirmation — row, ACLs, storage bytes, search doc. Linked assets are refused (409) and stay deprecate/invalidate-only. MCP: `chronicle.delete_asset` (creator-guarded). |
| `triage-error-queue` | "triage the error queue", "process incoming bugs" | Drains the Chronicle error-report triage queue locally. Claims one report, gathers context, decides match/new/noise, submits a structured verdict. Pair with `/loop`. Cost win: LLM call runs against your Claude Max, not chronicle's metered API key. See [`automated-error-reporting.md`](../runes/chronicle/designs/automated-error-reporting.md) §5.5. |
| `fix-error-queue` | "fix the next error", "work on a queued bug" | Drains the fix queue locally. Claims one open root_cause, reads the triage agent's writeup, fixes on a branch in your methodic checkout, opens a PR (no autonomous merging). Pair with `/loop`. See [`automated-error-reporting.md`](../runes/chronicle/designs/automated-error-reporting.md) §8.2. |
| `synthesis-event-handler` | (inside a tartarus-d synthesis agent) "I just received a `variation_completed` event", "stdin shows `distillation_completed`" | Behavior contract for the synthesis agent's response to M11 continuous-exploration push events. Parses the event, fetches report bodies, decides whether to propose follow-up variations. Not user-invokable — the agent triggers it from its system prompt when an event lands on stdin. See [`agent-flows.md`](../runes/chronicle/designs/agent-flows.md) §17.8 and the [push design plan](../edison/shared_plans/m11-synthesis-events-push.md). |
| `methodic-feedback` | "file feedback", "report this", "request a feature" — and **proactively**, whenever the agent hits a gap or issue mid-task | Records feedback to Chronicle's private feedback endpoint the moment it's encountered (Markdown body; `gap` / `feedback` / `feature_request`), then — end of turn, with your confirmation — offers to mirror it as a public GitHub issue on `methodic-research/skills` via your own `gh` (searching for duplicates first). Reproducible errors route to the error pipeline instead of plain feedback. |

Skills reach Chronicle two ways — the **bundled MCP server** (`chronicle.*` tools, no install; preferred for read/CRUD, leaner on tokens) and the [`methodic-research`](https://pypi.org/project/methodic-research/) Python SDK (preferred when importable for the byte-heavy paths — multi-file dataset uploads, agent-side W&B). Neither constructs raw HTTP from the skill itself; if something's missing, add an MCP tool and/or SDK method (and probably an API endpoint), not a network call in the skill.

> The two `*-error-queue` skills currently use raw `requests` calls because the underlying `/v1/admin/triage-queue` and `/v1/admin/fix-queue` endpoints are not yet wrapped in the SDK. Move them to `methodic.admin.*` namespaces once those endpoints stabilize (tracked in the implementation plan in `automated-error-reporting.md` §13).

## Publishing

How releases reach users:

1. **The repo is public.** `/plugin marketplace add methodic-research/skills` resolves with the user's git credentials, so anyone can add the marketplace and install — no extra access setup.
2. **Manifests stay correct.** `.claude-plugin/marketplace.json` (the `methodic` plugin entry) and `.claude-plugin/plugin.json` are already in place; skills are auto-discovered from `skills/<name>/SKILL.md` — nothing else to register.
3. **Versioning drives updates.** `plugin.json`'s `version` (currently `0.4.0`) is the release knob: bump it to publish a new version (users get it via `/plugin marketplace update`). Omit `version` instead to treat every push as a new version during active development.
4. Users then run the two commands in [step 2](#2-install-the-plugin-the-skills).

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
    1. **Use the local Claude session** the skill is running in. Free under the user's Claude Max plan and the obvious default for one-shot reasoning the skill itself does.
    2. **Route through chronicle-server's resolved-LLM endpoint** (`/v1/operational/extract-hypothesis` and friends — the resolver walks the principal's scope hierarchy for a configured Anthropic/OpenAI key, falling back to a Methodic-managed key). Use this when the call needs to be billed to the user's organization, audited as a Chronicle action, or reproduced server-side from a Cloud Function or scheduled job.
  
  **Never construct a direct Anthropic/OpenAI HTTP call from a skill.** That bypasses both the user's chosen LLM (the org's Anthropic vs OpenAI default) and Chronicle's audit log.

## What this is not (yet)

- **MCP config bundled into the plugin.** Chronicle now *has* an MCP server (`/v1/mcp/messages`, exposing `chronicle.*` tools) — see [Getting started](#3-wire-the-chronicle-mcp-tools-recommended) for wiring it today via `.mcp.json`. A candidate next step is declaring it directly in `plugin.json` (`mcpServers` + a `userConfig` prompt for the server URL + API key) so `/plugin install` also wires the endpoint in one step.
- **Cloud agents.** Cloud-hosted agents that prep variations without any local checkout are tracked separately; their design intentionally avoids needing these client-side skills.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
