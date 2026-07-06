---
name: fix-error-queue
description: |
  Use this skill when the user wants to drain the Chronicle fix queue
  locally — phrases like "fix the next error", "work on a queued bug",
  "let me PR an error-report fix". Claims one open root_cause from the
  fix-queue, reads the triage agent's writeup from the linked GitHub
  issue, attempts a fix on a branch in the user's local methodic
  checkout, opens a PR (no autonomous merging), and marks the queue
  entry as in_fix. Run it repeatedly with the host agent's loop or
  automation runner to drain the queue.
---

# Fix error queue

One iteration of the local-mode fix loop documented in
[`runes/chronicle/designs/automated-error-reporting.md`](../../runes/chronicle/designs/automated-error-reporting.md)
§8.2. Each invocation:

1. Claims one open `root_cause` from the fix queue (lease-based; 2h default).
2. Reads the linked GitHub issue (triage agent already wrote the root-cause analysis there).
3. Works the fix on a `agent/fix-<n>` branch in the operator's local methodic checkout.
4. Opens a PR with `Closes #<n>` linkage.
5. POSTs `/complete` with the PR URL → root_cause transitions to `in_fix`.

Cost win: the LLM "design + write the fix" step runs in your local
agent session, not chronicle's metered operational LLM key. The operator
reviews the PR before merging — **no autonomous merging at any stage**.

## Inputs

- **None usually.** The skill picks the highest-severity open root_cause.
- **`pwd` must be a methodic-research/methodic checkout.** The skill
  branches + commits + pushes in-place; it does not clone. If the user
  is somewhere else, prompt them to `cd` first.

## Authentication

- **Chronicle**: superadmin Auth0 JWT or `sk_admin_*` API key.
  `CHRONICLE_SERVER_URL` + `CHRONICLE_API_KEY` env vars.
- **GitHub**: the operator's own `gh` CLI auth handles branch push +
  PR creation. The skill does not mint a chronicle-agent-app token
  for this path (tartarus does that in the autonomous mode; locally,
  the operator IS the agent).

## Workflow

```python
import json, os, sys, subprocess, pathlib
import requests

BASE = os.environ["CHRONICLE_SERVER_URL"].rstrip("/")
HEADERS = {"Authorization": f"Bearer {os.environ['CHRONICLE_API_KEY']}"}
HOST = os.uname().nodename
LEASE = 7200  # 2 hours

# Sanity: are we in a methodic checkout?
repo_root = pathlib.Path(
    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                   capture_output=True, text=True, check=True).stdout.strip()
)
# We expect this to be the methodic-research/methodic repo. Heuristic:
# look for a known top-level file.
if not (repo_root / "chronicle" / "Cargo.toml").exists():
    raise SystemExit(f"not in a methodic checkout (cwd={repo_root}); cd into the repo first")

# 1. Claim
resp = requests.post(
    f"{BASE}/v1/admin/fix-queue/claim",
    headers=HEADERS,
    json={"consumer": "local", "consumer_id": HOST, "lease_seconds": LEASE},
    timeout=10,
)
if resp.status_code == 204:
    print("fix queue empty")
    sys.exit(0)
resp.raise_for_status()
claim = resp.json()
rc = claim["root_cause"]
issue_url = claim["github_issue_url"]
issue_number = int(issue_url.rstrip("/").rsplit("/", 1)[-1])

# 2. Read the GitHub issue (triage already wrote the root-cause analysis)
issue_body = subprocess.run(
    ["gh", "issue", "view", str(issue_number), "--json", "title,body,labels"],
    capture_output=True, text=True, check=True,
).stdout

# 3. Branch
branch = f"agent/fix-{issue_number}"
subprocess.run(["git", "fetch", "origin", "main"], check=True)
subprocess.run(["git", "checkout", "-b", branch, "origin/main"], check=True)

# 4. WORK THE FIX (instructions to the agent follow, not Python).
```

## Fix reasoning (instructions to the agent)

You are now on a fresh `agent/fix-<n>` branch off `origin/main`. The
GitHub issue body (in `issue_body` above) was written by the triage
agent; it contains:

- A one-line summary
- A list of suspected files (with line numbers)
- A detailed root-cause analysis
- The first occurrence's stack trace (in a `<details>` block)

Work as follows:

1. **Read the suspected files at the cited line numbers first.** Don't
   just trust the triage agent's analysis — verify by reading the code.
   The triage agent's job is to point you at the right place; yours is
   to confirm and fix.
2. **Make the minimal correct fix.** If you find that the triage
   description is *wrong* (the bug is elsewhere, or the suspected files
   aren't actually involved), see "When triage was wrong" below.
3. **Verify locally**:
   - `cargo check -p chronicle-server` (or whichever crate you touched)
   - `cargo test` for whatever test suite is closest to the fix
   - `cargo fmt` per the repo convention (`AGENTS.md` or `CLAUDE.md`)
4. **Commit + push + PR**:
   ```python
   subprocess.run(["git", "add", "-A"], check=True)
   subprocess.run(
       ["git", "commit", "-m",
        f"Fix #{issue_number}: <one-line>\n\nCloses #{issue_number}"],
       check=True,
   )
   subprocess.run(["git", "push", "-u", "origin", branch], check=True)
   pr_url = subprocess.run(
       ["gh", "pr", "create",
        "--title", f"Fix #{issue_number}: <one-line>",
        "--body", f"Closes #{issue_number}\n\n<short summary of the fix + how you verified it>"],
       capture_output=True, text=True, check=True,
   ).stdout.strip()
   ```

## Submit the completion

```python
r = requests.post(
    f"{BASE}/v1/admin/fix-queue/{rc['id']}/complete",
    headers=HEADERS, json={"pr_url": pr_url}, timeout=10,
)
r.raise_for_status()
print(f"fix submitted: {pr_url}")
```

This flips the root_cause to `in_fix`. A human still has to review +
merge the PR. The eventual merge → GitHub webhook → root_cause closes
as `fixed`. PR closed unmerged → root_cause back to `open` (with
attempt counter incremented).

## When triage was wrong

The triage agent is fallible. If you realize, while reading the code:

- **Triage matched the wrong root_cause** (this is actually a different
  bug): release the claim with a note pointing at the real root_cause,
  and let triage re-classify:
  ```python
  requests.post(
      f"{BASE}/v1/admin/fix-queue/{rc['id']}/release",
      headers=HEADERS,
      json={"reason": "triage-mismatch; suspect this is rc <other-uuid> not this one"},
      timeout=5,
  )
  ```
- **Suspected files are wrong, but the bug is real and you can find it**:
  proceed with the fix, but in your PR body call out the discrepancy
  ("triage suggested files X, actual fix touched Y") so the reviewer
  can verify + the human can later tune the triage prompt.

## Long-running session: heartbeat

If the fix takes longer than the lease (uncommon — 2h is generous):

```python
requests.post(
    f"{BASE}/v1/admin/fix-queue/{rc['id']}/heartbeat",
    headers=HEADERS, timeout=5,
)
```

## Repeating

```
$ cd ~/repos/edison    # methodic checkout
$ claude /loop fix-error-queue        # Claude Code
$ codex exec "fix the next error"     # Codex, from an external shell loop
```

The skill returns "queue empty" cleanly on a 204 from claim, which
the runner should treat as terminate.

**Operator etiquette**: clean up branches after PR merge. The skill
doesn't delete `agent/fix-<n>` branches on its own — you can `git
branch -D` after the PR closes, or use a periodic cleanup pass.

## Failure modes

- **403 on /claim**: missing superadmin role. Same fix as triage skill.
- **409 on /complete** (or /heartbeat): your lease expired and another
  consumer claimed the root_cause. Abort the iteration; the loop will
  pick up the next item. Your local branch + PR persist — you may want
  to manually clean up (`git branch -D agent/fix-<n>`, `gh pr close`)
  since the queue row no longer references them.
- **Branch already exists** (`agent/fix-<n>`): delete the stale branch
  first (`git branch -D agent/fix-<n>`) and retry. The skill doesn't
  force-delete because a stale branch may have unmerged work.
- **`cargo check` fails after the fix**: stop. Don't push a broken
  build. Either keep working until it passes or release the claim.
- **`gh pr create` fails**: usually permission or network. Don't
  complete — the lease will expire and the queue gets the entry back.

## Concurrency: multiple operators

Safe to run on multiple machines simultaneously. `SKIP LOCKED` on the
server side guarantees no two operators claim the same root_cause.
Default lease is 2h — plenty of time for a real fix. If you step away
mid-fix without heartbeating, another operator may claim the row from
under you, in which case your eventual `/complete` returns **409
Conflict**. Treat the 409 as final; don't try to muscle the verdict in.

## Requires

- `python3` with `requests`
- `CHRONICLE_SERVER_URL` and `CHRONICLE_API_KEY` exported
- `gh` CLI authenticated against methodic-research org (`gh auth login`)
- `git` configured with push access to methodic-research/methodic
- `cargo` on `$PATH` for build verification
- Operator is `cd`'d into the methodic checkout
