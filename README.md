# methodic-skills

Claude Code plugin: skills for working with the [Chronicle](https://docs.methodiclabs.ai) experiment platform.

This repo is a Claude Code marketplace containing one plugin (`chronicle`). Backend lives in the `methodic-research/methodic` monorepo (private); skills live here so they can be public-facing without exposing the rest.

## What's inside

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `chronicle-prep-variation` | "create a new variation", "start a fresh variation off this experiment" | Mints a git token, clones the experiment repo, creates a new agent branch with scaffolding, registers it as an open variation. |
| `chronicle-fork-variation` | "fork variation 2", "branch from this and let me edit" | Clones+branches off an existing committed variation as a *new* user-owned variation under the same experiment. Cannot push to `agent/*` directly. |
| `chronicle-mint-git-token` | "I need a git token", "give me push access to the repo" | One-shot token mint for manual git workflows. Returns an install token + clone URL. |
| `chronicle-status` | "what's running on experiment X", "any failures recently" | Snapshot of recent runs, current status, and any retracted ancestors that affect this experiment's lineage. |
| `triage-error-queue` | "triage the error queue", "process incoming bugs" | Drains the Chronicle error-report triage queue locally. Claims one report, gathers context, decides match/new/noise, submits a structured verdict. Pair with `/loop`. Cost win: LLM call runs against your Claude Max, not chronicle's metered API key. See [`automated-error-reporting.md`](../runes/chronicle/designs/automated-error-reporting.md) §5.5. |
| `fix-error-queue` | "fix the next error", "work on a queued bug" | Drains the fix queue locally. Claims one open root_cause, reads the triage agent's writeup, fixes on a branch in your methodic checkout, opens a PR (no autonomous merging). Pair with `/loop`. See [`automated-error-reporting.md`](../runes/chronicle/designs/automated-error-reporting.md) §8.2. |
| `ideation-event-handler` | (inside a tartarus-d ideation agent) "I just received a `variation_completed` event", "stdin shows `distillation_completed`" | Behavior contract for the ideation agent's response to M11 continuous-exploration push events. Parses the event, fetches report bodies, decides whether to propose follow-up variations. Not user-invokable — the agent triggers it from its system prompt when an event lands on stdin. See [`agent-flows.md`](../runes/chronicle/designs/agent-flows.md) §17.8 and the [push design plan](../edison/shared_plans/m11-ideation-events-push.md). |

Every skill is a thin orchestration layer over the [`methodic-client`](https://pypi.org/project/methodic-client/) Python SDK — skills don't construct HTTP calls themselves. If a skill needs something the SDK can't do, that's a signal to add an SDK method (and probably an API endpoint), not to reach into the network layer from the skill.

> The two `*-error-queue` skills currently use raw `requests` calls because the underlying `/v1/admin/triage-queue` and `/v1/admin/fix-queue` endpoints are not yet wrapped in the SDK. Move them to `methodic.admin.*` namespaces once those endpoints stabilize (tracked in the implementation plan in `automated-error-reporting.md` §13).

## Installing (users)

> The repo is currently **private** while the SDK + git-integration backend stabilize. Public installation lights up once the underlying APIs ship.

```bash
# Add the marketplace
/plugin marketplace add methodic-research/methodic-skills

# Install the chronicle plugin
/plugin install chronicle@methodic-skills
```

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
- **Skills depend on `methodic-client`.** Skills assume `methodic` is importable in the user's Python environment. Skills surface a clear "install methodic-client first" message if the import fails.
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

- **MCP server.** Chronicle will eventually expose an MCP server for richer agent integration once the API surface stabilizes. That'll either live in a sibling plugin in this marketplace or be folded into this plugin once the API contract is firm.
- **Cloud agents.** Cloud-hosted agents that prep variations without any local checkout are tracked separately in the methodic monorepo; their design intentionally avoids needing these client-side skills.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
