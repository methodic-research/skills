---
name: methodic-feedback
description: |
  Use this skill in two situations. (1) The user asks to send feedback,
  report a problem, or request a feature — "file feedback", "report this",
  "request a feature", "this flow is confusing", "tell the Methodic team".
  (2) PROACTIVELY, without being asked, whenever a gap or issue is
  encountered mid-task: the SDK can't express a workflow a skill needs, an
  MCP tool is missing or misbehaves, a skill's instructions turn out wrong,
  an API behaves confusingly. Records the feedback to Chronicle's private
  feedback endpoint immediately (Markdown body), and offers — at the end of
  the turn, with the user's confirmation — to mirror it as a public GitHub
  issue on methodic-research/skills filed as the user via gh.
---

# Methodic feedback

Two sinks, one contract: the **private backend** always hears about it, the
**public tracker** only with the user's say-so.

## The proactive contract

This is not only a user-invoked skill. While doing *any* task:

1. **Auto-file to the backend at the moment of encounter.** When a gap or
   issue surfaces (SDK/MCP can't express what the task needs, a skill
   instruction is wrong, an API response is confusing), submit it
   immediately via the SDK (`category="gap"`) and say so in one line of
   output — `filed feedback: <one-line summary> (<id>)`. No confirmation
   needed: the sink is private to Methodic. **At most one report per
   distinct gap per session** — never re-file from a retry loop.
2. **Offer the public mirror at end of turn.** Once the task has made
   maximum progress, ask whether to also file a public GitHub issue (see
   below). If the gap is **task-blocking**, ask immediately instead —
   otherwise finish the work first.

## Markdown is the contract

The feedback body is Markdown and is rendered (sanitized GFM) in Methodic's
review UI — use it: short title line, what was attempted, what was missing
or wrong, a fenced code block for the call that fell short, a table if
comparing expected vs actual. Keep it self-contained; the reviewer has no
session context.

## Pick the sink by shape

- **Reproducible error** — a failing call with an error type/message (and
  maybe a stack): route it to the error pipeline, *not* plain feedback, so
  it gets fingerprinted and triaged:
  ```python
  chronicle.feedback.report_error(
      error_type="ConflictError",
      message=str(err),
      request_method="POST",
      request_path="/experiments/{id}/inputs",
      response_status=409,
  )
  ```
- **Everything else** — impressions, gaps, feature requests — is plain
  feedback (`submit`, below).

## Workflow (backend submit)

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()

feedback_id = chronicle.feedback.submit(
    body_md=body,                      # Markdown — see contract above
    category="gap",                    # or "feedback" / "feature_request"
    context={                          # identifiers ONLY — never content
        "skill": "chronicle-dataset",
        "experiment_id": experiment_id,
    },
)
print(f"filed feedback: {feedback_id}")
```

For user-invoked feedback, draft the body from what the user said, show it
to them if they want to review, and use `category="feedback"` (or
`"feature_request"` when it's an ask, `"gap"` when it's a capability hole).

## Public GitHub mirror (end of turn, always confirmed)

Posted **as the user** via their own `gh` auth — so it is always drafted and
confirmed first, never automatic.

1. Check availability: `gh auth status` — if missing or unauthenticated,
   skip silently (the backend report already stands).
2. Search for duplicates first:
   `gh issue list -R methodic-research/skills --search "<keywords>" --state open`
   — if a match exists, offer commenting on it instead of opening a new one.
3. Draft title + body (body embeds `Feedback-ID: <feedback_id>` so the team
   can cross-link), show the user, and on confirmation:
   `gh issue create -R methodic-research/skills --title "<title>" --body-file <tmp> --label <feedback|gap|feature-request>`
4. Declined / no `gh` / create fails → fine; say the private report stands.

## Privacy

- Bodies are agent-composed and user-visible. Never include secrets,
  tokens, raw API keys, or session transcripts. `context` carries
  identifiers only.
- Never read `~/.methodic/credentials.yaml` into context (house rule).

## Requires

- `pip install methodic-research` (a version that ships the
  `chronicle.feedback` namespace)
- `~/.methodic` credentials (the README's bootstrap — only the user can
  create them; if missing, send them to the create-API-key UI flow)
- `gh` (optional) — only for the public-mirror step

## Troubleshooting

- **`AttributeError: feedback` / 404 from the endpoint** — older SDK or
  server without the feedback surface. Skip the backend sink, offer the
  gh-only path, and note the version gap (that's feedback too).
- **401/403** — credentials missing/expired: route the user to the README
  bootstrap (create an API key in the Methodic UI, paste the setup
  command). Do not ask for the raw key in chat.
- **429** — rate-limited: do not retry; mention it and move on.
