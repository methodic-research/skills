---
name: chronicle-research-lessons
description: |
  Use this skill in three situations. (1) PROACTIVELY, without being asked,
  the moment you realize you have REPEATEDLY made the same bad assumption
  while working an experiment, or the researcher EXPLICITLY OR IMPLICITLY
  corrects a wrong premise of yours ("no — the boundary mask is inverted",
  or a redirect that only makes sense if your premise was wrong): record it
  as a research lesson on the experiment. (2) The user asks — "record that
  as a lesson", "add a lesson", "what lessons do we have", "retire that
  lesson". (3) BEFORE drawing conclusions or proposing new work on an
  experiment: list its active lessons (own + inherited) and check your
  claims against them — contradicting one without addressing it is an
  error. Lessons are visible on the experiment's Lessons tab and injected
  into every future agent's context. NOT for platform bugs/gaps — that's
  methodic-feedback.
---

# Research lessons

A **research lesson** is a durable corrected assumption about *the
research* — recorded per experiment, shown to researchers on the Lessons
tab, inherited by descendant experiments, and injected into every future
agent's context. The whole point is that the next agent (or the next
variation, or you tomorrow) does not re-make the mistake.

**Lesson vs feedback:** a wrong assumption about *the research* (data,
methodology, environment, results) → lesson, here. Wrong behavior of *the
platform* (SDK gap, confusing API, broken tool) → `methodic-feedback`.

## The recording contract (proactive)

Record a lesson **at the moment of realization**, not at the end of the
session, when either arm fires:

1. **Repeated error** (`origin: "repeated_error"`) — you notice you have
   acted on the same wrong belief at least twice (the same wrong
   *assumption*, not the same typo).
2. **Researcher correction** (`origin: "researcher_correction"`) — a
   steer explicitly corrects a premise, **or implicitly does**: the
   researcher redirects work in a way that only makes sense if your
   premise was wrong. Capture what the correction implies, not just the
   literal words.

Self-caught wrong assumptions that didn't repeat use
`origin: "self_identified"`; human-typed additions from the tab are
`"manual"`.

Say so in-band, one line: `recorded lesson: <title> (<id>)` — the
researcher should see it land in the live thread.

## Dedup: refine, don't duplicate

Before recording, **list first**. If an existing lesson already covers
it, sharpen that one instead. **At most one recording per distinct lesson
per session** — never re-file from a retry loop.

```python
from methodic import Chronicle

chronicle = Chronicle.from_env()

existing = chronicle.experiments.list_lessons(experiment_id)  # active, own + inherited
# ... if one matches, refine:
chronicle.experiments.update_lesson(
    experiment_id, lesson_id,
    body_md=sharper_body,          # absent fields unchanged; retired lessons are immutable
)
# ... else record:
lesson = chronicle.experiments.record_lesson(
    experiment_id,
    title="Never trust post-4200 eval loss on dataset X",   # one line, imperative
    body_md=body,                  # see body contract below
    origin="researcher_correction",
    category="data",               # assumption (default) | methodology | environment | data | other
    variation=7,                   # when it arose from one variation
    evidence={"run": 3, "session_shard": shard_key},  # pointers ONLY, never content
)
print(f"recorded lesson: {lesson['title']} ({lesson['id']})")
```

MCP-native agents have the same four tools: `chronicle.record_lesson`,
`chronicle.list_lessons`, `chronicle.update_lesson`,
`chronicle.retire_lesson`.

## Body contract

The reader has no session context. `body_md` must be self-contained
Markdown carrying, in order: **the wrong assumption** (what was believed),
**the correction** (what is actually true), **the evidence** (cite the
run / metric / shard the `evidence` pointers name), and **what to do
instead**. Keep it to a short paragraph — the title carries the
imperative.

## The consultation contract (conclusions + proposals)

Any time you are about to **conclude** something (a report, a takeaways
section, a finding) or **propose** new work (a variation), list the
active lessons first (they are also injected into your
`~/.claude/CLAUDE.md` at spawn — the tool is the fresh source):

- A conclusion that **contradicts an active lesson without explicitly
  addressing it** is an error — reviewers raise it as a factual blocker.
  You may overturn a lesson, but only by naming it and arguing the
  evidence — and then retire/supersede it so the record moves with the
  conclusion.
- A proposal that **re-treads a lesson** must cite the lesson id and say
  what is different this time. Silent re-treads get rejected.

## Retiring

A lesson that turned out wrong or obsolete is **retired, never deleted**
(the wrong lesson is evidence too):

```python
chronicle.experiments.retire_lesson(
    experiment_id, lesson_id,
    reason="mask orientation fixed in dataset v5",
    superseded_by=new_lesson_id,   # optional
)
```

Only lessons owned by this experiment — inherited ones are retired at
their home experiment (record a local superseding lesson if you disagree
with an ancestor's).

## Privacy

Bodies are researcher-visible. Never include secrets, tokens, or raw
session transcripts; `evidence` carries identifiers only.

## Requires

- `pip install methodic-research` ≥ 0.41 (the lessons namespace), or the
  bundled MCP server (no SDK install).
- `Write` on the experiment to record/refine/retire; `Read` to list.

## Troubleshooting

- **`AttributeError: record_lesson` / 404** — older SDK or server without
  the lessons surface. Note the version gap (that's `methodic-feedback`
  material) and fall back to stating the lesson prominently in your
  report's Limitations section.
- **403 on record** — your key lacks `Write` here (e.g. the paper agent's
  read-only key — by design). Ask the researcher to record it, and state
  it in-band.
- **409 `lesson_retired` on update** — record a superseding lesson
  instead.
