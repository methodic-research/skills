---
name: ideation-event-handler
description: |
  Use this skill when you (the ideation agent running inside a Methodic
  experiment's container) just received an event on stdin describing a
  variation outcome or a distillation report — typically marker lines
  with `"kind": "variation_completed"` or `"kind": "distillation_completed"`
  wrapped in the standard user-message envelope. The skill is the
  behavior contract: parse the event, fetch any referenced report
  bodies, decide whether to propose follow-up variations under the
  experiment's continuous-exploration policy, and call the SDK to
  enqueue them. Do not invoke for user-typed messages or for events
  the skill doesn't recognize — fall back to your normal reasoning.
---

# Ideation event handler

This is the consumption half of M11 closed-loop continuous exploration
(see [`runes/chronicle/designs/agent-flows.md`][af] §17.8 +
[`edison/shared_plans/m11-ideation-events-push.md`][push]). Chronicle
pushes one event per variation outcome and one (coalesced) event per
distillation-report finalization onto your stdin via the tartarus-d
relay client; this skill says what to do with each.

[af]: ../../../runes/chronicle/designs/agent-flows.md
[push]: ../../../edison/shared_plans/m11-ideation-events-push.md

## Wire shape (what your stdin actually sees)

tartarus-d's relay client wraps the C2 control frame in
`frame_user_message` before pushing to your stdin queue. After the
envelope unwrap (Claude Code handles this transparently — you see it
as a normal user turn) the inner payload is one JSON object per
event:

```jsonc
// VariationCompleted — fired on every terminal run transition
//   (succeed_run, fail_run, watchdog's failed_lost).
{
  "kind": "variation_completed",
  "experiment_id": "01923abc-…",
  "variation": 4,
  "outcome": "succeeded"  // or "failed_crash" | "failed_abandoned" | "failed_lost"
}

// DistillationCompleted — fired after the cooldown window closes.
//   asset_ids is omitted on the coalesced-sweep path; carries one id
//   inline when the experiment's cooldown_minutes = 0.
{
  "kind": "distillation_completed",
  "experiment_id": "01923abc-…",
  "asset_ids": ["asset-xyz-…"]  // may be []
}
```

Both kinds carry `experiment_id`. Anything else on stdin — operator
nudges, sibling-agent commands, your own turn budget warnings — uses
a different shape; if `kind` doesn't match the two strings above,
fall through to your normal reasoning.

## What to do per event kind

### `variation_completed`

1. **Read the experiment's continuous_exploration block** via
   `client.experiments.get_agent_config(experiment_id)`. If
   `continuous_exploration.enabled` is `false`, log "exploration
   disabled; ignoring" and return. The researcher opted out; do not
   propose anything.
2. **Check the trigger_scope filter.** If `trigger_scope` is
   `"experiment"`, ignore variation-level events (those are only
   actionable when the per-variation report lands as a
   `distillation_completed`). For `"variation"` and `"both"`,
   proceed.
3. **Skim the variation's outputs** to ground a proposal. The
   variation_report (when it lands) is the richer signal; the
   succeed/fail outcome is the early signal. For `succeeded`: the
   variation worked — does that suggest a follow-up tweak (wider
   width, longer training, alternate dataset)? For
   `failed_crash`/`failed_abandoned`/`failed_lost`: the variation
   broke — is there a tweak that addresses the failure (smaller
   batch, fewer epochs, different optimizer)?
4. **Decide whether to propose.** Don't auto-propose on every
   outcome — that's a runaway. Propose IF AND ONLY IF you have a
   *specific* tweak in mind that you'd defend to the researcher.
   When in doubt, wait for the distillation report.

### `distillation_completed`

1. **Read the experiment's continuous_exploration block** (same as
   above). Return early if disabled.
2. **Check the trigger_scope filter.** If `trigger_scope` is
   `"variation"` and the report set was experiment-level, skip.
   (You can tell from the asset's `output_of` — a
   `variation_report` is variation-level; a `takeaways_report` /
   `research_report` is experiment-level.)
3. **Fetch the report bodies.** For each id in `asset_ids` (or for
   the empty case, fetch the experiment's recent outputs via
   `client.experiments.detail(experiment_id)` and pick the
   distillation-typed ones since your last seen timestamp):
   ```python
   for aid in event["asset_ids"]:
       asset = client.assets.get(aid)
       body = client.assets.download(aid, Path("/tmp/distill"))
       # body is the report — markdown, JSON, or LaTeX depending on type
   ```
4. **Reason about what the report says.** A
   `variation_report` is a per-variation analysis (outcome
   summary, failure RCA, notable plots). A `takeaways_report` is
   the experiment-level synthesis (gates conclude). A
   `research_report` is the longer-form research write-up.
   Distillation already did the heavy lifting of comparing across
   variations; you're consuming its conclusions, not re-deriving
   them.
5. **Decide whether to propose follow-up variations.** Concrete
   triggers for proposing:
   - The report identifies an unresolved direction the existing
     variations didn't cover.
   - The report flags an interaction between two variables that
     hasn't been ablated.
   - The report concludes the current hypothesis is dead but
     names a specific neighboring hypothesis worth trying.
   Do NOT propose if:
   - The report concludes the experiment is done. The researcher
     wants to conclude when distillation closes the question.
   - You'd propose something semantically duplicate of an
     existing variation.

## Decision: propose vs. wait

The default IS to wait. Continuous exploration ≠ relentless
exploration — it's "if the next move is obvious, take it; otherwise
defer to the human." The token budget cap
(`sub_agent_token_budget_usd_per_experiment`) will eventually trip
and hard-stop you, but you should be terminating yourself well
before that on intent.

When you do propose, name what's specifically different and why:

```python
from methodic import Chronicle
chronicle = Chronicle.from_env()  # uses CHRONICLE_API_KEY in container env

var = chronicle.variations.create(
    experiment_id=event["experiment_id"],
    config_yaml=parent_config_with_my_tweak,   # mutated from a sibling variation
    description=(
        "Continuous-exploration follow-up to v4 (succeeded): "
        "doubling the model width to test whether the loss plateau "
        "in the takeaways_report is capacity-limited."
    ),
    name="v4-width-doubled",  # plaintext handle; unique per experiment
)
print(f"proposed variation {var.name or f'v{var.variation}'}")
```

Mirror `chronicle-prep-variation`'s pattern: name the variation if
you have a meaningful short handle; pass `None` if you don't.

## Failure modes

- **`get_agent_config` returns 404**: the experiment doesn't exist
  or you don't have Read on it. Should not happen — Chronicle
  pushed the event because *you* are the active research-agent for
  that experiment. Log and ignore; the next event will come.
- **`variations.create` returns 403**: your sk_agent_* key isn't
  scoped to this experiment. Should not happen — see above.
- **Malformed event JSON**: the envelope is corrupt or
  Chronicle/tartarus drifted on the wire format. Log the full
  line + the parse error and fall through to your normal reasoning;
  do NOT crash the agent.
- **Same event id seen twice**: tartarus-d delivers downlink frames
  at-least-once; idempotency is *your* responsibility. Track the
  most-recent `(experiment_id, asset_ids)` you handled and skip
  exact duplicates. Variation outcomes are harder to dedup (the
  event carries no unique id) — gate on
  `(experiment_id, variation, outcome)` and skip if you've handled
  that triple within the current session.

## Budget awareness

`sub_agent_token_budget_usd_per_experiment` (§5.5 + §13) is the
backstop, not your steering signal. Two soft checks before
proposing:

- If the experiment has > 5 variations already in flight (pending +
  running): wait. The queue is backed up; adding more variations
  pre-empts existing work without new signal.
- If your last 3 proposals all came back `failed_crash` /
  `failed_abandoned`: stop proposing this session and report the
  pattern in your next steering response so the researcher can
  intervene.

## Concurrency

Only one ideation agent runs per experiment at a time — tartarus-d
routes events to `AgentJob::Ideation` (variation=None), which is
1-to-1 per experiment. You don't need to worry about racing
yourself.

## Requires

- `methodic-research` (Python) — already installed in the tartarus-d
  image alongside the other agent dependencies. Import is
  `from methodic import Chronicle`.
- `CHRONICLE_API_KEY` and `CHRONICLE_SERVER_URL` are set in the
  container env at agent spawn — `Chronicle.from_env()` picks them
  up. Don't read raw API keys from prompts.
- The ideation agent's stdin is fed by tartarus-d's relay client.
  No skill-side stdin reading needed; the harness deposits each
  event as a user-message turn.

## Pair with the prompt update

The ideation system prompt
(`tartarus/prompts/multi-agent-loop.system.md` or its successor)
should reference this skill in a one-paragraph behavior contract:

> When you receive a `variation_completed` or `distillation_completed`
> event on stdin, use the `ideation-event-handler` skill. The skill
> describes how to parse the event, fetch report bodies, and decide
> whether to propose follow-up variations. Default to waiting — only
> propose when you have a concrete tweak you'd defend to the
> researcher.

The prompt describes the *behavior intent*; this skill carries the
*tool-call mechanics*.
