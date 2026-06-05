#!/usr/bin/env python3
"""End-to-end test of the methodic skills against the deployed **ci** instance.

Drives the third-party (BYO-agent) flow in
`runes/chronicle/designs/third-party-agent-flow.md`: a headless Claude Code
session, loaded with the methodic-skills plugin + the chronicle MCP server,
carries a short ideation prompt through propose-experiment → author-variation →
**runs its OWN tiny CPU training, logging loss curves to W&B and marking the run
via the SDK** (chronicle-run-variation) → write-report (agent-side distillation,
pulling W&B directly with its own key). There is **no Menlo Park worker** — the
agent owns the training; Chronicle records the runs. The driver authenticates,
provisions the W&B integration, runs the agent, and asserts the artifacts over
ci's REST API, then cleans up.

It talks to ci over plain REST (`requests`) for its own bookkeeping +
assertions; the *agent* uses the SDK + MCP via the skills. No local stack, no
worker, no docker, no GCP WIF.

Secrets (env): CHRONICLE_CI_AUTH_ACCOUNT (JSON), ANTHROPIC_API_KEY, WANDB_API_KEY.
Missing any → SKIP (exit 0), so keyless/fork CI stays green.

Exit: 0 = pass or skip; non-zero = a failed assertion (with the offending
response dumped). Phases are ordered so a failure points at the exact seam.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import uuid

import requests

# --- Hardcoded constants (not secrets — see the design doc) -----------------
CI_URL = "https://ci-api.methodiclabs.ai"
AUTH0_TOKEN_URL = "https://laplacian.us.auth0.com/oauth/token"
AUTH0_AUDIENCE = "https://api.thelaplacian.ai"
MCP_PATH = "/v1/mcp/messages"  # chronicle-server's MCP endpoint

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent  # the skills plugin dir
RUN_ID = uuid.uuid4().hex[:8]
SLUG_PREFIX = "skills-e2e"  # greppable for an orphan reaper
RUN_WAIT_SECS = int(os.environ.get("E2E_RUN_WAIT_SECS", "900"))  # agent runs train + marks runs
SEARCH_WAIT_SECS = int(os.environ.get("E2E_SEARCH_WAIT_SECS", "180"))  # index propagation

# The two variations the agent commits + runs. The driver scopes its run-wait to
# these names so the test does NOT depend on the agent's exact variation count —
# extra variations (the agent has over-produced when asked for N) just don't get
# a run and aren't waited on.
NAMED_VARIATIONS = ["hidden_dim_8", "hidden_dim_32"]
EXPECTED_RUNS = len(NAMED_VARIATIONS)


class Fail(Exception):
    """An assertion failure — message is surfaced as the test failure."""


def _skip(msg: str) -> None:
    print(f"SKIP skills-e2e: {msg}")
    sys.exit(0)


def _dump(label: str, resp: requests.Response) -> str:
    body = resp.text[:2000]
    return f"{label}: HTTP {resp.status_code}\n{body}"


# --- Phase 0: authenticate + mint a scoped API key --------------------------

def auth0_bearer(account: dict) -> str:
    """Auth0 password grant for one ci account → access token (no GCP WIF)."""
    (email, password), = account["accounts"].items()
    resp = requests.post(
        AUTH0_TOKEN_URL,
        json={
            "grant_type": "password",
            "client_id": account["client_id"],
            "client_secret": account["client_secret"],
            "username": email,
            "password": password,
            "audience": AUTH0_AUDIENCE,
            "scope": "openid profile email",
        },
        timeout=30,
    )
    if not resp.ok:
        raise Fail(_dump("Auth0 password grant failed", resp))
    return resp.json()["access_token"]


def mint_api_key(jwt: str) -> str:
    """Mint a personal `sk_user_*` key (full owner authority — no restriction)."""
    resp = requests.post(
        f"{CI_URL}/api-keys",
        headers={"Authorization": f"Bearer {jwt}"},
        json={"name": f"{SLUG_PREFIX}-{RUN_ID}", "key_type": "user"},
        timeout=30,
    )
    if not resp.ok:
        raise Fail(_dump("mint api key failed", resp))
    return resp.json()["key"]


def caller_sub(jwt: str) -> str:
    """The caller's principal id (sub) — the personal scope for the integration."""
    resp = requests.get(f"{CI_URL}/v1/me/scopes", headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    if not resp.ok:
        raise Fail(_dump("GET /v1/me/scopes failed", resp))
    scopes = resp.json().get("scopes", [])
    # Personal scope is first (kind == 'user').
    for s in scopes:
        if s.get("kind") == "user":
            return s["id"]
    raise Fail(f"no personal scope in /me/scopes: {scopes}")


# --- Phase 0b: ensure the W&B integration -----------------------------------

def ensure_wandb_integration(jwt: str, scope_id: str, wandb_key: str) -> None:
    """Provision EXACTLY ONE active wandb integration on the scope.

    The agent's training *logs* to W&B with this key (env) and write-report
    *pulls* from W&B with the same key — the integration is what links the
    scope to W&B so the `(exp,var,run) → W&B run` pointer resolves. Chronicle's
    resolver refuses to auto-pick when a scope has two-or-more active wandb
    integrations, and prior runs accumulate them — so delete every existing
    wandb integration on the scope first, then create one fresh."""
    h = {"Authorization": f"Bearer {jwt}"}
    existing = requests.get(f"{CI_URL}/v1/integrations", headers=h, params={"scope_id": scope_id}, timeout=30)
    if existing.ok:
        for it in existing.json() or []:
            if it.get("integration_type") == "wandb" and it.get("id"):
                d = requests.delete(f"{CI_URL}/v1/integrations/{it['id']}", headers=h, timeout=30)
                if not (d.ok or d.status_code == 404):
                    print(f"  warn: could not delete stale wandb integration {it['id']} (HTTP {d.status_code})")
    resp = requests.post(
        f"{CI_URL}/v1/integrations",
        headers=h,
        json={
            "scope_id": scope_id,
            "integration_type": "wandb",
            "display_name": f"{SLUG_PREFIX}-wandb",
            "key": wandb_key,
        },
        timeout=60,
    )
    if resp.ok or resp.status_code == 409:
        print(f"  W&B integration ensured (HTTP {resp.status_code}, deduped).")
        return
    raise Fail(_dump("provision W&B integration failed", resp))


# --- Phase 1-3: drive the agent through the skills --------------------------

# Two bounded turns. The CREATE+RUN turn proposes the experiment, commits two
# variations, and — for each — writes a tiny CPU training, logs the loss curve to
# W&B, and marks the run via chronicle-run-variation (start→succeed); it STOPS
# without writing a report. The driver then verifies the runs and the DISTILL
# turn writes the report. (Training is numpy-only + seconds each, so create+run
# fits one turn; split create/run if it ever crowds the budget.)
CREATE_PROMPT = """\
You are a researcher using the Methodic platform via the chronicle MCP tools and \
the methodic skills. You bring your OWN training code and run it yourself on this \
machine (CPU) — Methodic RECORDS the runs; it does NOT run training for you. Do \
exactly the following, then STOP — do NOT write any report yet:

1. Use the propose-experiment skill to create ONE experiment for the hypothesis: \
"A small MLP fits a damped-ripple function; a wider hidden layer fits it better." \
Use the experiment slug "{slug}". Attach the hypothesis as a hypothesis_report \
and create + link a research prompt.

2. Use the author-variation skill to create and COMMIT exactly TWO variations, \
named EXACTLY "hidden_dim_8" and "hidden_dim_32". There is no git repo here, so \
pass the config_yaml inline. The config is just the knob YOUR training reads — \
keep it minimal, e.g.:
    model:
      hidden_dim: 8
Give each a one-line hypothesis. Do NOT pass any launch_config or runner_type — \
you run these yourself; you are not dispatching to a Methodic worker.

3. For EACH of the two committed variations, run it yourself with the \
chronicle-run-variation skill (run number 0):
   - Write a tiny CPU training in Python, numpy ONLY (no torch, no GPU): a small \
     MLP with `hidden_dim` hidden units (read hidden_dim from the variation \
     config), fit it for ~50 gradient steps to the damped-ripple target \
     f(x) = exp(-x) * sin(5x) sampled on a small 1-D grid, computing a REAL MSE \
     each step.
   - Log the loss curve to Weights & Biases (the `wandb` package; WANDB_API_KEY \
     is in the env): wandb.init(project=..., name="{slug}/v<var>/r0"), \
     wandb.log({{"loss": mse, "step": i}}) each step, then wandb.finish(). \
     Capture the W&B run id / entity / project.
   - Use chronicle-run-variation to record the Methodic run: run.start(...) \
     passing the W&B run id/entity/project so the run is linked, then \
     run.succeed() when training finishes (run.fail(...) on error).
   Keep each training to a few seconds. The wider hidden_dim (32) should reach a \
   LOWER final loss than 8 — that contrast is the result the report will distill.

As your final line, print exactly: EXPERIMENT_ID=<the uuid>"""

DISTILL_PROMPT = """\
The two runs for Methodic experiment {exp_id} are complete. Use the write-report \
skill to write an experiment-level takeaways_report. First PULL the REAL W&B \
metrics yourself: for each variation's run, read the run's `wandb_run` pointer \
from Chronicle (the experiment's outputs include a `wandb_run` asset per run, \
carrying entity/project/run_id) and fetch the final loss from W&B DIRECTLY with \
your own WANDB_API_KEY — the write-report skill documents `wandb_metrics_for_run` \
for exactly this. Include each variation's ACTUAL final loss in the report body \
and state which hidden_dim reached the lower loss. When done, print exactly: DONE
"""


def _agent_turn(prompt: str, label: str, api_key: str, log_dir: pathlib.Path, timeout: int) -> str:
    """Run ONE headless Claude turn (skills plugin + chronicle MCP). Captures
    stdout/stderr to the log dir **even on timeout**, and returns the transcript
    `result` text. `--permission-mode auto` runs unattended so the skills'
    Bash/MCP calls (including running the agent's own training) don't block."""
    mcp_config = log_dir / "mcp.json"
    mcp_config.write_text(json.dumps({"mcpServers": {"chronicle": {
        "type": "http", "url": f"{CI_URL}{MCP_PATH}",
        "headers": {"Authorization": f"Bearer {api_key}"}}}}))
    cmd = [
        "claude", "-p", prompt, "--bare",
        "--plugin-dir", str(REPO_ROOT),
        "--mcp-config", str(mcp_config),
        "--permission-mode", "auto",
        # stream-json (+ --verbose, required in print mode) writes the transcript
        # incrementally: a timeout/kill still leaves a full NDJSON log to diagnose
        # from, unlike --output-format json which buffers a single object emitted
        # only at the very end (→ an empty stdout file when the turn is killed).
        "--output-format", "stream-json",
        "--verbose",
        # Sonnet, not Opus — a CI test doesn't need Opus, and it's ~5x cheaper
        # per turn. Still satisfies --permission-mode auto's "Sonnet 4.6+" floor.
        "--model", "claude-sonnet-4-6",
    ]
    env = {**os.environ, "CHRONICLE_SERVER_URL": CI_URL, "CHRONICLE_API_KEY": api_key}
    print(f"  agent turn '{label}' (timeout {timeout}s) …")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        timed_out = True
    (log_dir / f"agent.{label}.stdout").write_text(out or "")
    (log_dir / f"agent.{label}.stderr").write_text(err or "")
    if timed_out:
        raise Fail(f"agent turn '{label}' timed out after {timeout}s; transcript tail:\n{(out or '')[-2000:]}")
    # stream-json emits one JSON object per line; the final `type:"result"` event
    # carries the result text + is_error. Agent-side failures (API errors,
    # "Credit balance is too low", etc.) surface there, not via the exit code.
    result_text, is_error, subtype = None, False, None
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            result_text = ev.get("result", "")
            is_error = bool(ev.get("is_error"))
            subtype = ev.get("subtype")
    if is_error:
        raise Fail(f"agent turn '{label}' errored ({subtype}): {str(result_text or '')[-600:]}")
    if proc.returncode != 0:
        raise Fail(
            f"agent turn '{label}' exited {proc.returncode}; result/stderr tail:\n"
            f"{(out or '')[-800:]}\n{(err or '')[-800:]}"
        )
    return result_text if result_text is not None else (out or "")


def create_run_variations(api_key: str, slug: str, log_dir: pathlib.Path) -> str:
    """CREATE+RUN turn → returns the experiment_id from the EXPERIMENT_ID=<uuid> marker."""
    text = _agent_turn(CREATE_PROMPT.format(slug=slug), "create", api_key, log_dir, timeout=RUN_WAIT_SECS)
    for line in reversed(text.splitlines()):
        if line.strip().startswith("EXPERIMENT_ID="):
            return line.strip().split("=", 1)[1].strip()
    raise Fail(f"create turn did not emit EXPERIMENT_ID; result tail:\n{text[-2000:]}")


def distill(api_key: str, exp_id: str, log_dir: pathlib.Path) -> None:
    """Distill turn → write-report pulling W&B agent-side, after the runs complete."""
    _agent_turn(DISTILL_PROMPT.format(exp_id=exp_id), "distill", api_key, log_dir, timeout=900)


# --- Assertions over ci REST ------------------------------------------------

def _get(path: str, jwt: str) -> requests.Response:
    return requests.get(f"{CI_URL}{path}", headers={"Authorization": f"Bearer {jwt}"}, timeout=60)


def assert_experiment(jwt: str, exp_id: str) -> None:
    detail = _get(f"/experiments/{exp_id}", jwt)
    if not detail.ok:
        raise Fail(_dump(f"experiment {exp_id} not found", detail))
    print(f"  experiment {exp_id} exists.")

    # Variations are embedded in the experiment detail (no GET on
    # /experiments/{id}/variations — that path is POST-create; GET -> 405).
    rows = detail.json().get("variations", [])
    committed = [v for v in rows if (v.get("state") == "committed" or v.get("committed_at"))]
    if len(committed) < EXPECTED_RUNS:
        raise Fail(
            f"expected >={EXPECTED_RUNS} committed variations, got {len(committed)} "
            f"of {len(rows)}: {rows}"
        )
    print(f"  {len(committed)} committed variations (>= {EXPECTED_RUNS}).")

    # hypothesis_report is secondary — warn (don't fail) on placement, so it
    # can't false-fail the run; the runs + report are the load-bearing checks.
    if _has_asset_type(jwt, exp_id, "hypothesis_report"):
        print("  hypothesis_report present.")
    else:
        print("  WARN: hypothesis_report not found on experiment inputs/outputs.")


def _has_asset_type(jwt: str, exp_id: str, asset_type: str) -> bool:
    for endpoint in (f"/experiments/{exp_id}/outputs", f"/experiments/{exp_id}/inputs"):
        r = _get(endpoint, jwt)
        if r.ok:
            rows = r.json() if isinstance(r.json(), list) else r.json().get("assets", [])
            if any(a.get("asset_type") == asset_type for a in rows):
                return True
    return False


def wait_for_runs(jwt: str, exp_id: str) -> None:
    """Driver-side wait: poll until >= EXPECTED_RUNS committed variations have a
    *succeeded* run (the agent ran + marked them in the create turn, so this is
    quick verification). Fail fast on any terminal failure. NOT scoped to a fixed
    variation count — extra variations the agent over-produced have no run and are
    tolerated; only the succeeded count matters."""
    deadline = time.time() + RUN_WAIT_SECS
    failed = ("failed_crash", "failed_abandoned", "failed_lost")
    last = "no status"
    while time.time() < deadline:
        r = _get(f"/experiments/{exp_id}", jwt)
        if r.ok:
            rows = r.json().get("variations", [])
            statuses = [v.get("latest_status") for v in rows]
            bad = [s for s in statuses if s in failed]
            if bad:
                raise Fail(f"a run failed terminally: {statuses}")
            succeeded = sum(1 for s in statuses if s == "succeeded")
            if succeeded >= EXPECTED_RUNS:
                print(f"  {succeeded} variation runs succeeded (>= {EXPECTED_RUNS}).")
                return
            last = f"statuses: {statuses}"
        time.sleep(15)
    raise Fail(f"fewer than {EXPECTED_RUNS} runs succeeded within {RUN_WAIT_SECS}s; last {last}")


def assert_wandb_linked(jwt: str, exp_id: str) -> None:
    """Each succeeded run should carry a linked `wandb_run` output asset — the
    pointer write-report reads to pull metrics. This is the seam that proves the
    agent linked W&B at run-start (chronicle-run-variation → runs.start)."""
    r = _get(f"/experiments/{exp_id}/outputs", jwt)
    if not r.ok:
        raise Fail(_dump("list experiment outputs failed", r))
    wandb_runs = [a for a in r.json() if a.get("asset_type") == "wandb_run"]
    if len(wandb_runs) < EXPECTED_RUNS:
        raise Fail(
            f"expected >={EXPECTED_RUNS} linked wandb_run assets, got {len(wandb_runs)}: "
            f"{[a.get('asset_config') for a in wandb_runs]}"
        )
    print(f"  {len(wandb_runs)} wandb_run pointers linked (>= {EXPECTED_RUNS}).")


def wait_for_distillation(jwt: str, exp_id: str) -> dict:
    """Poll for a takeaways_report (the distillation output). Returns the asset."""
    deadline = time.time() + RUN_WAIT_SECS
    last = "none seen"
    while time.time() < deadline:
        r = _get(f"/experiments/{exp_id}/outputs", jwt)
        if r.ok:
            for a in r.json():
                if a.get("asset_type") == "takeaways_report":
                    print("  takeaways_report present.")
                    return a
            last = f"output types: {[a.get('asset_type') for a in r.json()]}"
        time.sleep(15)
    raise Fail(f"no takeaways_report within {RUN_WAIT_SECS}s (distillation); last: {last}")


def assert_report_pulled_wandb(report: dict) -> None:
    # `review_required` posture + a non-trivial body. The W&B-value check is
    # best-effort (the agent phrases freely) — we assert the body is substantial
    # and the review gate fired. ASSUMPTION to tighten in CI: pin a metric value.
    reasons = report.get("pending_reasons") or []
    if report.get("state") not in (None, "pending") and not reasons:
        print(f"  WARN: takeaways_report not pending/review_required: {report.get('state')}, {reasons}")
    body = json.dumps(report)
    if len(body) < 200:
        raise Fail(f"takeaways_report body suspiciously small: {body}")
    print("  takeaways_report looks distilled (pending/review-gated).")


def assert_searchable(jwt: str, exp_id: str) -> None:
    """POST /search and poll until the report surfaces — the one assertion that
    exercises the real Vertex push (indexing is eventually consistent). A `got
    []`/timeout here is Vertex propagation latency, not a code regression."""
    deadline = time.time() + SEARCH_WAIT_SECS
    last = "no hit"
    while time.time() < deadline:
        r = requests.post(
            f"{CI_URL}/search",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"query": "damped ripple hidden_dim takeaways", "asset_types": ["takeaways_report"]},
            timeout=60,
        )
        if r.ok:
            hits = r.json().get("results", r.json()) if isinstance(r.json(), dict) else r.json()
            if any(exp_id in json.dumps(h) for h in hits):
                print("  takeaways_report discoverable in search (real Vertex push).")
                return
            last = f"{len(hits)} hits, none for {exp_id}"
        else:
            last = _dump("search", r)
        time.sleep(15)
    raise Fail(f"takeaways_report not searchable within {SEARCH_WAIT_SECS}s; last: {last}")


def cleanup(jwt: str, exp_id: str) -> None:
    h = {"Authorization": f"Bearer {jwt}"}
    r = requests.delete(f"{CI_URL}/experiments/{exp_id}", headers=h, timeout=60)
    if r.ok:
        print(f"  cleanup: deleted experiment {exp_id}")
        return
    # A committed experiment (or one with variations) can't be deleted (409) —
    # retract it instead so the test leaves no live data behind.
    rr = requests.put(
        f"{CI_URL}/experiments/{exp_id}/retract",
        headers=h,
        json={"reason": "skills-e2e test cleanup"},
        timeout=60,
    )
    print(f"  cleanup: delete -> {r.status_code}, retract -> {rr.status_code}")


# --- Orchestration ----------------------------------------------------------

def main() -> int:
    raw = os.environ.get("CHRONICLE_CI_AUTH_ACCOUNT")
    if not raw or not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("WANDB_API_KEY"):
        _skip("CHRONICLE_CI_AUTH_ACCOUNT / ANTHROPIC_API_KEY / WANDB_API_KEY not all set")
    try:
        account = json.loads(raw)
    except json.JSONDecodeError as e:
        _skip(f"CHRONICLE_CI_AUTH_ACCOUNT is not valid JSON: {e}")

    log_dir = REPO_ROOT / "e2e" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    slug = f"{SLUG_PREFIX}-{RUN_ID}"
    wandb_key = os.environ["WANDB_API_KEY"]

    print("=== Methodic skills E2E against ci (agent-owned training) ===")
    jwt = auth0_bearer(account)
    print("  authenticated to ci (Auth0 password grant).")
    scope_id = caller_sub(jwt)
    ensure_wandb_integration(jwt, scope_id, wandb_key)
    api_key = mint_api_key(jwt)
    print("  minted sk_user_* key.")

    exp_id = None
    try:
        # The agent proposes the experiment, commits two variations, and runs
        # each itself (its own numpy CPU training → W&B → runs.start/succeed).
        exp_id = create_run_variations(api_key, slug, log_dir)
        print(f"=== created experiment {exp_id} ===")
        assert_experiment(jwt, exp_id)
        wait_for_runs(jwt, exp_id)         # agent already marked them; quick verify
        assert_wandb_linked(jwt, exp_id)   # the W&B pointers distillation will read
        distill(api_key, exp_id, log_dir)  # distill turn: write-report pulls W&B agent-side
        report = wait_for_distillation(jwt, exp_id)
        assert_report_pulled_wandb(report)
        assert_searchable(jwt, exp_id)
        print("\nPASS skills-e2e")
        return 0
    finally:
        if exp_id:
            cleanup(jwt, exp_id)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Fail as e:
        print(f"\nFAIL skills-e2e: {e}", file=sys.stderr)
        raise SystemExit(1)
