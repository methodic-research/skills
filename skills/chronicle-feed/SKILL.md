---
name: chronicle-feed
description: |
  Use this skill when the user (or an agent acting for them) wants to read
  their Chronicle activity feed — phrases like "check my feed", "what needs my
  attention", "anything waiting on me", "are any agents blocked on me", "what's
  in my inbox", "anything awaiting approval", "what happened on my experiments",
  "any new reports", "show research recommendations", "what's new since I last
  looked". The feed is the unified event stream: activity (run/experiment
  lifecycle), the "needs you" queue (blocked agents + report approvals +
  invites), new reports, and research recs — across everything the caller can
  read. Also use it when an agent consuming the feed as a work queue needs to
  advance its read pointer after processing events. Read is side-effect-free;
  advancing the pointer is a separate, explicit step.
---

# Feed

Read the caller's unified event feed and — for an agent draining it as a work
queue — advance the per-section pointer explicitly after acting. Answers "what's
happened / what needs me / what's new" without opening the web UI.

## Transport — MCP-direct (no SDK needed)

Uses the **bundled MCP tools** directly — no `pip install`. (If the `methodic`
SDK is installed and you prefer it, the SDK equivalents are noted inline.) The
bundled launcher resolves credentials from `~/.methodic` — see the repo README
"The MCP tools (bundled — zero config)".

- **`chronicle.feed`** — read a page of the feed. Read-only.
- **`chronicle.feed_seen`** — advance one section's pointer. The one mutation.

## The two lenses + the categories

Everything is one endpoint with preset filters — don't look for separate calls:

- **Needs you** (the work/attention queue): `chronicle.feed` with
  `{ "actionable": true, "open": true }` — blocked agents waiting on you,
  reports awaiting your approve/reject, and pending invites that are still open.
- **Inbox** (addressed to you): `{ "recipient": "me" }` — events targeted at
  you specifically (e.g. a run of yours that was reaped).
- **By category**: `{ "category": "activity" }` (lifecycle), `"new_report"`,
  `"blocked"`, `"report_approval"`, `"experiment_invite,organization_invite"`,
  or `"research"`. CSV accepted. Research recs rank by relevance — add
  `{ "order": "score" }`.
- Narrow further with `experiment`, `kind`, `severity`; scope a page with
  `limit` + `before` (older), or poll forward with `after_seq`.

Each event carries a `seq` (the cursor key) and rolls up into a **section**:
`blocked` · `approvals` · `research` · `passive` (activity + new_report). The
response is `{ events, has_more, unseen_count }` — `unseen_count` is that
section's badge (a live open-count for `blocked`/`approvals`, an unseen-since-
cursor count for `research`/`passive`).

## Workflow (just reading)

1. Pick the lens for what the user asked:
   - "what needs me / anything waiting on me" → `{ "actionable": true, "open": true }`
   - "my inbox / addressed to me" → `{ "recipient": "me" }`
   - "what happened" → `{ "category": "activity" }`
   - "new reports" → `{ "category": "new_report" }`
   - "research recommendations" → `{ "category": "research", "order": "score" }`
2. Call **`chronicle.feed`** with that filter (add `experiment` to scope to one
   experiment). The result's JSON is in the tool's text content.
3. Present a compact list, newest-first: per event — `kind` · the resource
   (`resource_type`/`resource_id` or `experiment_id`) · `created_at` ·
   `severity` when not `info`. Lead with the `unseen_count` / open-count, and
   call out anything `severity: "error"` or `actionable` + still open.

*(SDK equivalent: `chronicle.feed.list(actionable=True, open=True)` /
`chronicle.feed.iter(category="activity")`.)*

## Advancing the pointer — explicit, and only after you act

**Reading never advances the pointer.** When an *agent* consumes the feed as a
work queue, advance the pointer with **`chronicle.feed_seen`**
`{ "section": "<section>", "through_seq": <highest seq you handled> }` — but
**only after you have durably acted on those events**, never merely because you
read them. This is at-least-once: if you crash or error between reading and
acking, the events stay unseen and are re-delivered on the next read, so nothing
is silently dropped. `through_seq` is monotonic — a lower value is a no-op.

- Advance `passive` (activity + new reports) and `research` once you've
  processed them.
- The actionable sections (`blocked`, `approvals`) primarily clear by
  *resolving* their items (answer the blocked agent, approve/reject the report);
  advancing their cursor only marks "new since seen".
- This is the agent contract specifically. The web UI advances automatically on
  view (the human's glance is the acknowledgement) — so when a person is just
  browsing their feed, do **not** call `feed_seen` on their behalf unless they
  ask to mark things seen.

*(SDK equivalent: `chronicle.feed.seen(section="passive", through_seq=N)`.)*

## After the skill completes

If the feed surfaces something actionable (a blocked agent, a report awaiting
approval, an error-severity event), surface it prominently and offer the
follow-up (steer the blocked variation, approve/reject the report) rather than
burying it under the routine activity.

## Requires

Nothing to install — uses the bundled MCP tools. Reading is side-effect-free;
the only write is the explicit `chronicle.feed_seen` pointer advance.
