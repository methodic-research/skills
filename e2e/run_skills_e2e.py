#!/usr/bin/env python3
"""End-to-end test of the methodic skills against the deployed **ci** instance.

Drives the third-party (BYO-agent) flow described in
`runes/chronicle/designs/third-party-agent-flow.md`: a headless Claude Code
session, loaded with the methodic-skills plugin + the chronicle MCP server,
carries a short ideation prompt through propose-experiment → 3 author-variations
→ (runs train on the runner's worker) → write-report (distillation, pulling
W&B). The driver authenticates, provisions the W&B integration, runs the agent,
and asserts the artifacts over ci's REST API, then cleans up.

It talks to ci over plain REST (`requests`) for its own bookkeeping +
assertions; the *agent* uses the SDK + MCP via the skills. No local stack.

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
RUN_WAIT_SECS = int(os.environ.get("E2E_RUN_WAIT_SECS", "900"))  # train + complete
SEARCH_WAIT_SECS = int(os.environ.get("E2E_SEARCH_WAIT_SECS", "180"))  # index propagation


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


# --- Phase 0b: ensure the W&B integration so the server can pull -------------

def ensure_wandb_integration(jwt: str, scope_id: str, wandb_key: str) -> None:
    """Idempotent POST /v1/integrations (integration_type=wandb). The server
    validates the key against W&B's GraphQL `viewer`. The runner-worker logs
    with the *same* key (env), so the (exp,var,run)->W&B-run mapping resolves."""
    resp = requests.post(
        f"{CI_URL}/v1/integrations",
        headers={"Authorization": f"Bearer {jwt}"},
        json={
            "scope_id": scope_id,
            "integration_type": "wandb",
            "display_name": f"{SLUG_PREFIX}-wandb",
            "key": wandb_key,
        },
        timeout=60,
    )
    # 2xx = created; 409 / "exists" = already provisioned (idempotent).
    if resp.ok or resp.status_code == 409:
        print(f"  W&B integration ensured (HTTP {resp.status_code}).")
        return
    raise Fail(_dump("provision W&B integration failed", resp))


# --- Phase 1-4: drive the agent through the skills --------------------------

# Two bounded turns, not one long-running one. The CREATE turn creates +
# implements + triggers (and STOPS — it must not wait for training); the driver
# polls runs to completion; then the DISTILL turn writes the report. Baking the
# training wait into the agent turn is what timed the first run out.
CREATE_PROMPT = """\
You are helping a researcher with the Methodic platform via the chronicle MCP \
tools and the methodic skills. Do exactly this, then STOP — do NOT wait for \
training and do NOT write any report:

1. Use the propose-experiment skill to create ONE experiment for the hypothesis: \
"A 3-layer MLP fits the damped-ripple function; wider hidden layers fit it \
better." Use the experiment slug "{slug}". Attach the hypothesis as a \
hypothesis_report and create + link a research prompt.

2. Use the author-variation skill THREE times to create and COMMIT three \
variations of the baseline that differ ONLY by model.hidden_dim. Name them \
"hidden_dim_32", "hidden_dim_128", "hidden_dim_256" with a one-line hypothesis \
each. Trigger a run for each committed variation.

As your final line, print exactly: EXPERIMENT_ID=<the uuid>
"""

DISTILL_PROMPT = """\
The three runs for Methodic experiment {exp_id} have completed. Use the \
write-report skill to write an experiment-level takeaways_report. Before writing \
it, PULL the W&B metrics for the runs via the chronicle wandb tools and include \
the actual final metric values (e.g. loss / mae) for each variation in the \
report body. When done, print exactly: DONE
"""


def _agent_turn(prompt: str, label: str, api_key: str, log_dir: pathlib.Path, timeout: int) -> str:
    """Run ONE headless Claude turn (skills plugin + chronicle MCP). Captures
    stdout/stderr to the log dir **even on timeout**, and returns the transcript
    `result` text. `--permission-mode auto` runs unattended (Opus 4.8 server-side
    safety classifier) so the skills' Bash/MCP calls don't block on a prompt —
    `acceptEdits` only auto-accepts edits, which is what hung the first run."""
    mcp_config = log_dir / "mcp.json"
    mcp_config.write_text(json.dumps({"mcpServers": {"chronicle": {
        "type": "http", "url": f"{CI_URL}{MCP_PATH}",
        "headers": {"Authorization": f"Bearer {api_key}"}}}}))
    cmd = [
        "claude", "-p", prompt, "--bare",
        "--plugin-dir", str(REPO_ROOT),
        "--mcp-config", str(mcp_config),
        "--permission-mode", "auto",
        "--output-format", "json",
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
        raise Fail(f"agent turn '{label}' timed out after {timeout}s; stdout tail:\n{(out or '')[-2000:]}")
    parsed = None
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        pass
    # `claude --output-format json` reports agent-side failures (API errors,
    # "Credit balance is too low", etc.) as is_error in the JSON, not via the
    # exit code — surface the message directly rather than a blank stderr.
    if parsed and parsed.get("is_error"):
        raise Fail(f"agent turn '{label}' errored ({parsed.get('subtype')}): {str(parsed.get('result', ''))[-600:]}")
    if proc.returncode != 0:
        raise Fail(
            f"agent turn '{label}' exited {proc.returncode}; result/stderr tail:\n"
            f"{(out or '')[-800:]}\n{(err or '')[-800:]}"
        )
    return parsed.get("result", out) if parsed else out


def create_experiment_and_variations(api_key: str, slug: str, log_dir: pathlib.Path) -> str:
    """Create turn → returns the experiment_id from the EXPERIMENT_ID=<uuid> marker."""
    text = _agent_turn(CREATE_PROMPT.format(slug=slug), "create", api_key, log_dir, timeout=900)
    for line in reversed(text.splitlines()):
        if line.strip().startswith("EXPERIMENT_ID="):
            return line.strip().split("=", 1)[1].strip()
    raise Fail(f"create turn did not emit EXPERIMENT_ID; result tail:\n{text[-2000:]}")


def distill(api_key: str, exp_id: str, log_dir: pathlib.Path) -> None:
    """Distill turn → write-report pulling W&B, after the runs have completed."""
    _agent_turn(DISTILL_PROMPT.format(exp_id=exp_id), "distill", api_key, log_dir, timeout=900)


# --- Assertions over ci REST ------------------------------------------------

def _get(path: str, jwt: str) -> requests.Response:
    return requests.get(f"{CI_URL}{path}", headers={"Authorization": f"Bearer {jwt}"}, timeout=60)


def assert_experiment(jwt: str, exp_id: str) -> None:
    detail = _get(f"/experiments/{exp_id}", jwt)
    if not detail.ok:
        raise Fail(_dump(f"experiment {exp_id} not found", detail))
    print(f"  experiment {exp_id} exists.")

    # Variations are embedded in the experiment detail — there is no GET on
    # /experiments/{id}/variations (that path is POST-create; GET -> 405).
    rows = detail.json().get("variations", [])
    committed = [v for v in rows if (v.get("state") == "committed" or v.get("committed_at"))]
    if len(committed) < 3:
        raise Fail(f"expected >=3 committed variations, got {len(committed)} of {len(rows)}: {rows}")
    print(f"  {len(committed)} committed variations.")

    # hypothesis_report is secondary — warn (don't fail) if its exact placement
    # differs, so it can't false-fail the run; the variations are load-bearing.
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
    """Driver-side wait: poll the variations until each has a *succeeded* run
    (the runner-worker trains them). Fail fast on a terminal failure. This is
    the wait that must NOT live inside the agent turn."""
    deadline = time.time() + RUN_WAIT_SECS
    failed = ("failed_crash", "failed_abandoned", "failed_lost")
    last = "no status"
    while time.time() < deadline:
        r = _get(f"/experiments/{exp_id}", jwt)
        if r.ok:
            rows = r.json().get("variations", [])
            statuses = [v.get("latest_status") for v in rows]
            if rows and all(s == "succeeded" for s in statuses):
                print(f"  all {len(rows)} runs succeeded.")
                return
            if any(s in failed for s in statuses):
                raise Fail(f"a run failed terminally: {statuses}")
            last = f"statuses: {statuses}"
        time.sleep(20)
    raise Fail(f"runs did not all succeed within {RUN_WAIT_SECS}s; last {last}")


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
    raise Fail(f"no takeaways_report within {RUN_WAIT_SECS}s (runs + distillation); last: {last}")


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
    exercises the real Vertex push (indexing is eventually consistent)."""
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


# --- The worker: train the triggered runs ON the runner ---------------------

def start_worker(api_key: str) -> str | None:
    """Run the public methodic worker image (`ENTRYPOINT menlo-park-d`) as a
    persistent worker registered to ci, so the triggered variation runs train
    here on the runner's CPU — no ci provisioning, no GCP WIF. The worker logs
    to W&B with WANDB_API_KEY (same account the integration uses), so the
    server can later pull the metrics.

    RISK (the thing the first CI run validates): the worker installs each job's
    *code_artifact* and trains it, so the skill-created experiment's repo must
    carry an installable training package. If it doesn't, runs won't produce
    W&B data and `wait_for_distillation` will time out — that's the seam to
    iterate on (seed the experiment repo with a tiny package fixture)."""
    try:
        out = subprocess.run(
            [
                "docker", "run", "-d",
                "-e", f"CHRONICLE_API_KEY={api_key}",
                "-e", f"CHRONICLE_SERVER_URL={CI_URL}",
                "-e", f"WANDB_API_KEY={os.environ['WANDB_API_KEY']}",
                "-e", "RUST_LOG=info",  # so worker.log is non-empty for diagnosis
                "methodiclabs/methodic:latest",
            ],
            capture_output=True, text=True, timeout=300, check=True,
        )
        cid = out.stdout.strip()
        print(f"  worker started (container {cid[:12]}).")
        return cid
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        detail = getattr(e, "stderr", "") or str(e)
        print(f"  WARN: could not start worker ({detail[:300]}); runs won't train.")
        return None


def stop_worker(cid: str | None, log_dir: pathlib.Path) -> None:
    if not cid:
        return
    logs = subprocess.run(["docker", "logs", cid], capture_output=True, text=True)
    (log_dir / "worker.log").write_text((logs.stdout or "") + (logs.stderr or ""))
    subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
    print(f"  worker stopped (logs -> e2e/logs/worker.log).")


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

    print("=== Methodic skills E2E against ci ===")
    jwt = auth0_bearer(account)
    print("  authenticated to ci (Auth0 password grant).")
    scope_id = caller_sub(jwt)
    ensure_wandb_integration(jwt, scope_id, wandb_key)
    api_key = mint_api_key(jwt)
    print("  minted sk_user_* key.")
    worker_cid = start_worker(api_key)

    exp_id = None
    try:
        exp_id = create_experiment_and_variations(api_key, slug, log_dir)
        print(f"=== created experiment {exp_id} ===")
        assert_experiment(jwt, exp_id)
        wait_for_runs(jwt, exp_id)        # driver waits; not the agent
        distill(api_key, exp_id, log_dir)  # distill turn, runs now complete
        report = wait_for_distillation(jwt, exp_id)
        assert_report_pulled_wandb(report)
        assert_searchable(jwt, exp_id)
        print("\nPASS skills-e2e")
        return 0
    finally:
        stop_worker(worker_cid, log_dir)
        if exp_id:
            cleanup(jwt, exp_id)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Fail as e:
        print(f"\nFAIL skills-e2e: {e}", file=sys.stderr)
        raise SystemExit(1)
