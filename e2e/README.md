# Skills E2E

End-to-end test of the skills against the deployed **ci** instance — the
third-party (BYO-agent) flow from
[`runes/chronicle/designs/third-party-agent-flow.md`](../../runes/chronicle/designs/third-party-agent-flow.md).

A headless Claude Code session, loaded with this plugin + the chronicle MCP
server, carries a short ideation prompt through the real skills:

`propose-experiment` → `author-variation` ×3 (commit + trigger runs) → the
runner's worker trains them → `write-report` distills, pulling W&B metrics →
asserted over ci's REST API, then the experiment is deleted.

There is **no local stack and no mock** — it runs against deployed ci with real
training (on the runner) and real W&B, which is the point: it catches
local-green-but-deployed-red drift.

## What runs where

- **`lint_skills.py`** — every push. Static, no secrets: SKILL.md frontmatter +
  no stale API surface (`active_org`, `X-Chronicle-Active-Owner`,
  `<capability>:<verb>`).
- **`run_skills_e2e.py`** — PRs into `main` (`.github/workflows/skills-e2e.yml`).
  Authenticates to ci (Auth0 password grant, **no GCP WIF**), mints a key,
  provisions the W&B integration, starts a `menlo-park` worker on the runner
  (`docker run methodiclabs/methodic:latest`), drives the agent, asserts, cleans
  up. **SKIPs cleanly** if secrets are absent (fork PRs stay green).

## Secrets (set on the repo)

| Secret | Value |
|--------|-------|
| `CHRONICLE_CI_AUTH_ACCOUNT` | One account from `ci-auth-accounts.json`: `{"client_id","client_secret","accounts":{"<email>":"<password>"}}` |
| `ANTHROPIC_API_KEY` | Anthropic key for the headless Claude turns |
| `WANDB_API_KEY` | W&B account key — worker logs with it **and** it provisions the ci W&B integration (same account both sides) |

The ci URL, Auth0 domain, and audience are hardcoded constants in
`run_skills_e2e.py` (not secrets).

## Run locally

```bash
export CHRONICLE_CI_AUTH_ACCOUNT='{"client_id":"…","client_secret":"…","accounts":{"ci_user0@thelaplacian.ai":"…"}}'
export ANTHROPIC_API_KEY=…
export WANDB_API_KEY=…
pip install requests && npm i -g @anthropic-ai/claude-code
python3 e2e/run_skills_e2e.py
```

## Known iteration points (first CI run validates these)

This is the first cut; the seams most likely to need a fix, in order:

1. **Training a fresh experiment.** The worker installs each job's *code_artifact*
   and trains it, so the skill-created experiment's repo must carry an installable
   training package. If runs don't produce W&B data, `wait_for_distillation`
   times out — the fix is to seed the experiment repo with a tiny package fixture
   (or have `propose-experiment` do so). This is the linchpin.
2. **Headless Claude flags.** `--permission-mode` / `--allowedTools` may need
   tuning so the skills run fully unattended.
3. **REST/response shapes.** Assertions parse defensively and dump the real
   response on mismatch — adjust the field names to ci's actual payloads.
4. **W&B-value assertion.** Currently asserts the report is distilled +
   review-gated; tighten to pin a specific pulled metric value once the flow is
   green.
