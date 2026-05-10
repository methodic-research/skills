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

Every skill is a thin orchestration layer over the [`methodic-client`](https://pypi.org/project/methodic-client/) Python SDK — skills don't construct HTTP calls themselves. If a skill needs something the SDK can't do, that's a signal to add an SDK method (and probably an API endpoint), not to reach into the network layer from the skill.

## Installing (users)

> The repo is currently **private** while the SDK + git-integration backend stabilize. Public installation lights up once the underlying APIs ship.

```bash
# Add the marketplace
/plugin marketplace add geekbeast/methodic-skills

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

## What this is not (yet)

- **MCP server.** Chronicle will eventually expose an MCP server for richer agent integration once the API surface stabilizes. That'll either live in a sibling plugin in this marketplace or be folded into this plugin once the API contract is firm.
- **Cloud agents.** Cloud-hosted agents that prep variations without any local checkout are tracked separately in the methodic monorepo; their design intentionally avoids needing these client-side skills.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
