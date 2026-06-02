# methodic-skills

Claude Code plugin: skills for working with the [Chronicle](https://docs.methodiclabs.ai) experiment platform.

This repo is a Claude Code marketplace containing one plugin (`chronicle`). Backend lives in the `geekbeast/methodic` monorepo (private); skills live here so they can be public-facing without exposing the rest.

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
| `chronicle-history-explorer` | "what experiments exist about X", "show the lineage", "explore history" | Read-only exploration of experiment history — semantic search (`search.history`), status-filtered browsing, the lineage DAG, and upstream retractions. |
| `triage-error-queue` | "triage the error queue", "process incoming bugs" | Drains the Chronicle error-report triage queue locally. Claims one report, gathers context, decides match/new/noise, submits a structured verdict. Pair with `/loop`. Cost win: LLM call runs against your Claude Max, not chronicle's metered API key. See [`automated-error-reporting.md`](../runes/chronicle/designs/automated-error-reporting.md) §5.5. |
| `fix-error-queue` | "fix the next error", "work on a queued bug" | Drains the fix queue locally. Claims one open root_cause, reads the triage agent's writeup, fixes on a branch in your methodic checkout, opens a PR (no autonomous merging). Pair with `/loop`. See [`automated-error-reporting.md`](../runes/chronicle/designs/automated-error-reporting.md) §8.2. |
| `ideation-event-handler` | (inside a tartarus-d ideation agent) "I just received a `variation_completed` event", "stdin shows `distillation_completed`" | Behavior contract for the ideation agent's response to M11 continuous-exploration push events. Parses the event, fetches report bodies, decides whether to propose follow-up variations. Not user-invokable — the agent triggers it from its system prompt when an event lands on stdin. See [`agent-flows.md`](../runes/chronicle/designs/agent-flows.md) §17.8 and the [push design plan](../edison/shared_plans/m11-ideation-events-push.md). |

Every skill is a thin orchestration layer over the [`methodic-research`](https://pypi.org/project/methodic-research/) Python SDK — skills don't construct HTTP calls themselves. If a skill needs something the SDK can't do, that's a signal to add an SDK method (and probably an API endpoint), not to reach into the network layer from the skill.

> The two `*-error-queue` skills currently use raw `requests` calls because the underlying `/v1/admin/triage-queue` and `/v1/admin/fix-queue` endpoints are not yet wrapped in the SDK. Move them to `methodic.admin.*` namespaces once those endpoints stabilize (tracked in the implementation plan in `automated-error-reporting.md` §13).

## Getting started

### Prerequisites

1. **Claude Code** — the plugin host.
2. **The methodic SDK** — skills orchestrate it (they never make raw HTTP calls):
   ```bash
   pip install methodic-research              # once published to PyPI
   # …or, for local dev against the monorepo:
   pip install -e path/to/methodic/conductor
   ```
3. **Chronicle credentials**, read by the SDK from the environment:
   ```bash
   export CHRONICLE_SERVER_URL="https://api.methodiclabs.ai"   # your Chronicle server
   export CHRONICLE_API_KEY="sk_user_..."                      # your API key
   ```

### 1. Install the plugin (the skills)

```bash
/plugin marketplace add geekbeast/methodic-skills   # register this repo as a marketplace
/plugin install chronicle@methodic-skills           # install the plugin
```

That's it — the skills auto-trigger by intent ("survey the literature on …", "propose an experiment for …", "make a variation that …"). Pull new versions later with `/plugin marketplace update methodic-skills`.

> **Repo access.** `/plugin marketplace add` uses your existing git credentials, so this already works for anyone with access to `geekbeast/methodic-skills`. To make it installable by *anyone*, the repo must be **public** — see [Publishing](#publishing). The `marketplace.json` + `plugin.json` are already in place.

### 2. Wire the Chronicle MCP tools (recommended)

The skills run on the SDK alone, but Chronicle also hosts an **MCP server** (`/v1/mcp/messages`, served by `chronicle-server`) exposing native `chronicle.*` tools — internal search, experiment create/read/commit, report-write, research prompts, session search. Point Claude Code at it with a project-scoped `.mcp.json` at your repo root:

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

(or `claude mcp add`). The tools must be deployed on your Chronicle server — they ship with `chronicle-server`.

### 3. Literature search (external MCP)

Literature/arxiv search is **not** in Chronicle — Chronicle search is internal-only (experiment history + research docs). The `chronicle-research-survey` skill pulls papers from a separate **external literature MCP** (e.g. Paperclip); add that server the same way (`.mcp.json` / `claude mcp add`) to enable the literature leg. Without it, the survey runs Chronicle-internal only.

### Team / repo pre-config

To give a whole team a one-trust setup, commit a `.claude/settings.json` to the project — teammates are prompted to add the marketplace and enable the plugin when they trust the folder:

```json
{
  "extraKnownMarketplaces": {
    "methodic-skills": { "source": { "source": "github", "repo": "geekbeast/methodic-skills" } }
  },
  "enabledPlugins": { "chronicle@methodic-skills": true }
}
```

## Publishing

To make the plugin easily installable by users:

1. **Make the repo accessible.** `/plugin marketplace add geekbeast/methodic-skills` resolves with the user's git credentials, so a **public** repo is installable by anyone; a private repo only by those with access. *(This is the current gate — the repo is private while the SDK + git-integration backend stabilize.)*
2. **Manifests stay correct.** `.claude-plugin/marketplace.json` (the `chronicle` plugin entry) and `.claude-plugin/plugin.json` are already in place; skills are auto-discovered from `skills/<name>/SKILL.md` — nothing else to register.
3. **Versioning drives updates.** `plugin.json`'s `version` (currently `0.1.0`) is the release knob: bump it to publish a new version (users get it via `/plugin marketplace update`). Omit `version` instead to treat every push as a new version during active development.
4. Users then run the two commands in [step 1](#1-install-the-plugin-the-skills).

## Local development

The repo is a sibling of the `methodic` monorepo by convention — same pattern as `runes/`. Local layout:

```
~/repos/
  methodic/          (backend monorepo: chronicle, conductor, menlo-park, scribe, chronicle-web)
  runes/             (designs + terraform — private)
  methodic-skills/   (this repo)
```

Point Claude Code at the local path so edits land without pushing:

```bash
claude --plugin-dir ./methodic-skills
```

`/reload-plugins` picks up edits to `SKILL.md` files mid-session.

## Skill conventions

- **One skill per user-visible verb.** Keep skills small and named after what the user is trying to do, not after the API endpoint they hit.
- **Skills depend on `methodic-research`.** Skills assume `methodic` is importable in the user's Python environment. Skills surface a clear "install methodic-research first" message if the import fails.
- **No secrets in skills.** Auth tokens come from `methodic`'s standard config (env var `CHRONICLE_API_KEY` or `~/.config/methodic/credentials`). Skills never prompt for raw API keys.
- **Skill ↔ SDK ↔ API alignment.** Every skill must be expressible as a sequence of SDK calls. If a skill diagrams a workflow that the SDK can't currently support end-to-end, file an issue on the SDK rather than papering over the gap.
- **Variation naming.** Variations carry an optional plaintext `name` (unique per experiment). When referring to a variation in chat or in skill output, prefer the name; fall back to `v{variation_index}` only when name is unset. When *creating* variations (e.g. `prep-variation`, `fork-variation`), accept an optional `name` argument and pass it through to the SDK — don't synthesize one server-side without the user's input. Pattern:
  ```python
  handle = v.name or f"v{v.variation}"
  ```
- **Operational LLM calls.** Some future skills will want to ask an LLM something on the user's behalf — a hypothesis-extract, a summarization, a structured-output prompt. Two paths exist; pick deliberately:
    1. **Use the local Claude session** the skill is running in. Free under the user's Claude Max plan and the obvious default for one-shot reasoning the skill itself does.
    2. **Route through chronicle-server's resolved-LLM endpoint** (`/v1/operational/extract-hypothesis` and friends — the resolver walks the principal's scope hierarchy for a configured Anthropic/OpenAI key, falling back to a Methodic-managed key). Use this when the call needs to be billed to the user's organization, audited as a Chronicle action, or reproduced server-side from a Cloud Function or scheduled job.
  
  **Never construct a direct Anthropic/OpenAI HTTP call from a skill.** That bypasses both the user's chosen LLM (the org's Anthropic vs OpenAI default) and Chronicle's audit log.

## What this is not (yet)

- **MCP config bundled into the plugin.** Chronicle now *has* an MCP server (`/v1/mcp/messages`, exposing `chronicle.*` tools) — see [Getting started](#2-wire-the-chronicle-mcp-tools-recommended) for wiring it today via `.mcp.json`. A candidate next step is declaring it directly in `plugin.json` (`mcpServers` + a `userConfig` prompt for the server URL + API key) so `/plugin install` also wires the endpoint in one step.
- **Cloud agents.** Cloud-hosted agents that prep variations without any local checkout are tracked separately in the methodic monorepo; their design intentionally avoids needing these client-side skills.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
