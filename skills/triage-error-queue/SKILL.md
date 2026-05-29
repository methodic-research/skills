---
name: triage-error-queue
description: |
  Use this skill when the user wants to drain the Chronicle error-report
  triage queue locally — phrases like "triage the error queue", "process
  one error report", "let me look at incoming bugs". Claims one
  pending_triage error_report, gathers context (GitHub Issues search,
  Vertex semantic matches, code excerpts), reasons about whether it
  matches an existing root cause or is genuinely new, and submits a
  structured verdict back to Chronicle. The server persists root_causes
  and files GitHub issues on the operator's behalf — this skill never
  writes to GitHub directly. Pair with `/loop` to drain the queue.
---

# Triage error queue

One iteration of the local-mode triage loop documented in
[`runes/chronicle/designs/automated-error-reporting.md`](../../runes/chronicle/designs/automated-error-reporting.md)
§5.5. Each invocation:

1. Claims one `pending_triage` error_report (lease-based; 30 min default).
2. Pulls pre-fetched search context from chronicle.
3. Reasons about the report against that context.
4. POSTs a structured `TriageVerdict` (`match_existing_root_cause` /
   `new_root_cause` / `noise`).

The cost win: the LLM "reason" step happens in your local Claude Code
session, so it runs against your Claude Max subscription rather than
chronicle-server's metered Anthropic API key.

## Inputs

- **None usually.** The skill picks the next pending row off the queue.
- **`lease_seconds`** (optional, default 1800) — how long the claim
  lease lasts. Bump it up if you're going to step away mid-triage.

The skill does *not* take an explicit error_report_id — to triage a
specific one, the operator can use the bridge UI or curl the verdict
endpoint directly. This skill is for the "give me the next one"
streaming workflow.

## Authentication

Requires a superadmin Auth0 JWT or `sk_admin_*` API key. The skill
reads:

- `CHRONICLE_SERVER_URL` (e.g. `https://chronicle.thelaplacian.ai`)
- `CHRONICLE_API_KEY` (an `sk_admin_*` key) — preferred, since the
  triage path is server-to-server-ish and Auth0 tokens expire faster
  than a long triage session

If neither is set, prompt the operator before starting.

## Workflow

```python
import json, os, sys
import requests

BASE = os.environ["CHRONICLE_SERVER_URL"].rstrip("/")
HEADERS = {"Authorization": f"Bearer {os.environ['CHRONICLE_API_KEY']}"}
HOST = os.uname().nodename
LEASE = 1800

# 1. Claim
resp = requests.post(
    f"{BASE}/v1/admin/triage-queue/claim",
    headers=HEADERS,
    json={"consumer": "local", "consumer_id": HOST, "lease_seconds": LEASE},
    timeout=10,
)
if resp.status_code == 204:
    print("triage queue empty")
    sys.exit(0)
resp.raise_for_status()
claim = resp.json()
er = claim["error_report"]
er_id = er["id"]
print(f"claimed error_report {er_id} (fingerprint {er['fingerprint'][:12]})")

# 2. Context
ctx = requests.get(
    f"{BASE}/v1/admin/triage-context/{er_id}",
    headers=HEADERS, timeout=10,
).json()
# ctx fields:
#   github_search_results: [{"number", "title", "url", "labels", "state"}, ...]
#   vertex_matches: [{"root_cause_id", "summary", "score"}, ...]
#   code_excerpts: [{"file", "line", "context_lines"}, ...]

# 3. REASON (this is where Claude does the actual work — the section
#    below is shaped as instructions to Claude, not Python to execute).
```

## Triage reasoning (instructions to Claude)

Read the inputs and decide on a `TriageVerdict`. Order of operations:

1. **Skim the GitHub search results.** Are any of them obviously the
   same bug expressed in slightly different words? If so, the verdict
   is `match_existing_root_cause` with `matched_root_cause_id` set to
   that issue's linked root_cause (look up via the hidden marker in
   the issue body: `**Root cause ID:** \`<uuid>\``).
2. **Skim the Vertex semantic matches.** Embeddings catch
   not-obviously-the-same-string-but-same-bug cases. If a high-score
   match looks plausible, **read the matched root_cause's description**
   before concluding the same. False-positive matches are worse than
   missed matches — when in doubt, err toward declaring `new_root_cause`.
3. **Read the code excerpts.** Use the top stack frame's file + line.
   If you can quickly tell this is a known by-design behavior (a
   feature flag check that intentionally throws, etc.), the verdict
   is `noise`.
4. **If you reach `new_root_cause`:** write a real root-cause analysis.
   Don't just paste the error message back. Cite the suspected file(s)
   with line numbers. Set severity based on:
   - **high** — affects auth, payments, experiment commit, or core
     write paths. Or `hits_last_24h > 100` from the context.
   - **med** — affects read paths or non-critical features. Or many
     distinct users hit it.
   - **low** — cosmetic, edge case, rare path.

You MAY use additional tools to investigate — read more files, run
`cargo check` on a suspected crate, etc. Treat the `code_excerpts` as
a starting point, not an exhaustive context.

## Submit the verdict

```python
verdict = {
    "decision": "match_existing_root_cause",  # or "new_root_cause" / "noise"
    # match_existing_root_cause:
    "matched_root_cause_id": "...",
    # new_root_cause:
    # "summary": "...",
    # "description": "...",
    # "suspected_files": ["src/api/experiments.rs:412"],
    # "severity": "high",
    # noise:
    # "noise_reason": "by-design 403 on expired install token",
    "rationale": "why this decision",
}
r = requests.post(
    f"{BASE}/v1/admin/triage-queue/{er_id}/verdict",
    headers=HEADERS, json=verdict, timeout=15,
)
r.raise_for_status()
result = r.json()
# Server response includes the GitHub issue URL (whether newly created
# or matched) and the canonical root_cause_id.
print(f"verdict applied: root_cause={result['root_cause_id']} → {result['github_issue_url']}")
```

## Long-running session: heartbeat

If reasoning takes longer than the lease, send heartbeats:

```python
requests.post(
    f"{BASE}/v1/admin/triage-queue/{er_id}/heartbeat",
    headers=HEADERS, timeout=5,
)
```

Heartbeat once per ~5 minutes if you're still working. Skill-driven
short triages (under a few minutes) don't need to bother.

## If you can't decide

POST `/release` with a reason; the report goes back to the queue:

```python
requests.post(
    f"{BASE}/v1/admin/triage-queue/{er_id}/release",
    headers=HEADERS,
    json={"reason": "needs human eyes — possible regression of #142"},
    timeout=5,
)
```

Release is preferable to a low-confidence verdict. After 3 consecutive
releases on the same error_report, the server escalates to
`needs-human` and klaxons.

## Looping

Pair with `/loop`:

```
$ claude /loop triage-error-queue
```

The skill returns "queue empty" cleanly on a 204 from claim, which
`/loop` should detect and terminate on.

## After the skill completes

Print a one-liner: `<decision> · <root_cause_id> · <github_issue_url>`.
If `/loop` is driving, that's enough; if the operator ran the skill
manually, also print the rationale so they can review.

## Failure modes

- **403 on /claim**: missing superadmin role. Stop and tell the
  operator to either use an `sk_admin_*` key or get added to the
  `superadmin` role for their Auth0 sub.
- **409 on /verdict** (or /heartbeat): your lease expired and another
  consumer claimed the row. Abort the iteration silently — the loop
  will pick up the next row on its next call. Do not retry the verdict.
- **Server returns 5xx**: don't release; let the lease expire so the
  report is unclaimed when the server recovers.
- **JSON parse error on verdict response**: log and exit; don't loop on
  a corrupt server response.

## Concurrency: multiple operators

This skill is safe to run on multiple machines simultaneously. The
server's claim primitive (Postgres `SKIP LOCKED`) guarantees that two
operators won't claim the same error_report. If your local session
stalls (long Claude turn, network blip), heartbeats keep your lease
alive; if you fall too far behind, the lease expires and another
operator can claim the row from under you — at which point your
`/verdict` submission will return **409 Conflict** and you should
abort the iteration.

## Requires

- `python3` with `requests` (or use `urllib` from stdlib if `requests`
  isn't available — endpoints are simple JSON-over-HTTPS)
- `CHRONICLE_SERVER_URL` and `CHRONICLE_API_KEY` exported. The
  `sk_admin_*` key is in `secrets/admin-api-key.txt` after a server
  bootstrap; the operator copies it into their shell.
- **No `gh` CLI needed.** Triage never touches GitHub from the operator
  side — the server's `chronicle-agent-app` does all GitHub writes.
