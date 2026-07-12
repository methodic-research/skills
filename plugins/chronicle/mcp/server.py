#!/usr/bin/env python3
"""chronicle-mcp — the stdlib-Python port of the stdio MCP launcher.

`mcp/launch.sh` probes for a runtime and runs `server.js` under node/bun when
available; this file is the fallback for machines with no JavaScript runtime
(Claude Code does not bundle Node — only Claude Desktop does). It is a
line-for-line port of server.js and must behave identically:

  Agent client <--stdio JSON-RPC-->  this launcher  <--HTTPS-->  chronicle-server
                                                                 POST /v1/mcp/messages

What it does:
 - Resolves the API key + server URL from ~/.methodic (same precedence as the
   Python SDK), so the existing `methodic auth login` credentials work as-is.
 - Transparently proxies MCP JSON-RPC (initialize / tools/list / tools/call /
   notifications) to the in-server transport with `Authorization: Bearer`.
 - Intercepts `upload_asset` / `upload_image` calls that carry a local `path`:
   reads the file, drives the presign -> PUT -> finalize dance over HTTP, and
   returns the finalized asset. The model only ever passes a *path*, so the
   bytes never transit the model context. Single-blob only; multi-file /
   directory uploads stay on the SDK (`chronicle.datasets.upload`).
 - Serves a launcher-local `search_logs` tool backed by Scribe.

Pure Python stdlib (urllib), Python >= 3.8. No deps.
"""

import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request

# ------------------------------------------------------------------------------
# Credential / server resolution — mirrors methodic SDK `chronicle.py`.
# ------------------------------------------------------------------------------
DEFAULT_SERVER_URL = "https://api.methodiclabs.ai"

_FLAT_LINE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*:\s*(.+?)\s*$")


def parse_flat_yaml(text):
    """Minimal parser for the flat `key: value` `~/.methodic` files
    (credentials.yaml -> api_key; config.yaml -> server_url / organization_id).
    Avoids a YAML dependency. Ignores blank lines and `#` comments; strips one
    layer of matching quotes."""
    out = {}
    for raw_line in re.split(r"\r?\n", text):
        line = re.sub(r"\s+#.*$", "", raw_line)
        m = _FLAT_LINE.match(line)
        if not m:
            continue
        v = m.group(2).strip()
        if (v.startswith('"') and v.endswith('"')) or (
            v.startswith("'") and v.endswith("'")
        ):
            v = v[1:-1]
        out[m.group(1)] = v
    return out


def methodic_home():
    return os.environ.get("HOME") or os.path.expanduser("~")


def read_methodic_file(name):
    try:
        p = os.path.join(methodic_home(), ".methodic", name)
        with open(p, "r", encoding="utf-8") as f:
            return parse_flat_yaml(f.read())
    except OSError:
        return {}


def resolve_config():
    creds = read_methodic_file("credentials.yaml")
    cfg = read_methodic_file("config.yaml")
    api_key = (
        os.environ.get("CHRONICLE_API_KEY")
        or creds.get("api_key")
        or cfg.get("api_key")
        or None
    )
    server_url = (
        os.environ.get("CHRONICLE_SERVER_URL")
        or cfg.get("server_url")
        or DEFAULT_SERVER_URL
    ).rstrip("/")
    # Scribe serves run-log search (POST /v1/logs/search). No default — the
    # host/env differs per deployment; when unset the search_logs tool reports
    # how to configure it rather than guessing a URL.
    scribe_url = (
        os.environ.get("CHRONICLE_SCRIBE_URL") or cfg.get("scribe_url") or ""
    ).rstrip("/")
    return {"api_key": api_key, "server_url": server_url, "scribe_url": scribe_url}


_CONFIG = resolve_config()
API_KEY = _CONFIG["api_key"]
SERVER_URL = _CONFIG["server_url"]
SCRIBE_URL = _CONFIG["scribe_url"]
MCP_URL = SERVER_URL + "/v1/mcp/messages"


# stderr only — stdout is the MCP channel.
def log(*parts):
    sys.stderr.write("[chronicle-mcp] " + " ".join(str(p) for p in parts) + "\n")
    sys.stderr.flush()


# ------------------------------------------------------------------------------
# HTTP — fetch()-like semantics: a non-2xx response is a response, not an error.
# ------------------------------------------------------------------------------
def _request(method, url, headers=None, body=None):
    """Returns (status, bytes). Raises on network errors only (like fetch)."""
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def post_mcp(message):
    status, raw = _request(
        "POST",
        MCP_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(API_KEY),
        },
        body=json.dumps(message).encode("utf-8"),
    )
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except ValueError:
        return json_rpc_error(
            message.get("id") if isinstance(message, dict) else None,
            -32603,
            "chronicle returned non-JSON (HTTP {}): {}".format(status, text[:200]),
        )


def put_bytes(url, body, content_type):
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    status, _ = _request("PUT", url, headers=headers, body=body)
    return status


def finalize_asset(asset_id):
    """Returns (status, text)."""
    status, raw = _request(
        "PUT",
        "{}/v1/assets/{}/finalize".format(SERVER_URL, asset_id),
        headers={"Authorization": "Bearer {}".format(API_KEY)},
    )
    return status, raw.decode("utf-8", "replace")


def _ok(status):
    return 200 <= status < 300


# ------------------------------------------------------------------------------
# JSON-RPC helpers
# ------------------------------------------------------------------------------
def json_rpc_error(id, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": id, "error": error}


# Wrap a plain object as an MCP tools/call result (content[0].text = JSON).
def tool_result(id, payload, is_error=False):
    return {
        "jsonrpc": "2.0",
        "id": id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": payload if isinstance(payload, str) else json.dumps(payload),
                }
            ],
            "isError": is_error,
        },
    }


# Pull the JSON chronicle packs into a tools/call result's content[0].text.
def parse_tool_text(resp):
    try:
        return json.loads(resp["result"]["content"][0]["text"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------
# Upload interception
# ------------------------------------------------------------------------------
UPLOAD_TOOLS = {
    "upload_asset",
    "upload_image",
    "chronicle.upload_asset",
    "chronicle.upload_image",
}

CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".html": "text/html",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".parquet": "application/octet-stream",
    ".safetensors": "application/octet-stream",
    ".npy": "application/octet-stream",
    ".npz": "application/octet-stream",
    ".bin": "application/octet-stream",
}


def guess_content_type(p):
    ext = os.path.splitext(p)[1].lower()
    return CONTENT_TYPES.get(ext, "application/octet-stream")


def expand_path(p):
    out = p
    if out == "~" or out.startswith("~/"):
        out = os.path.join(methodic_home(), out[1:].lstrip("/"))
    return os.path.abspath(out)


def handle_upload(req):
    """Handle an upload_* tools/call that carries a local `path`. Returns a
    JSON-RPC response (never None — the caller has already decided to
    intercept)."""
    id = req.get("id")
    params = req.get("params") or {}
    args = dict(params.get("arguments") or {})

    fpath = expand_path(args["path"])
    try:
        with open(fpath, "rb") as f:
            data = f.read()
    except OSError as e:
        return tool_result(
            id, {"error": "cannot read path '{}': {}".format(args["path"], e)}, True
        )

    # The local-only `path` is ours; force the presign path server-side.
    args.pop("path", None)
    args.pop("base64_content", None)
    if not args.get("filename"):
        args["filename"] = os.path.basename(fpath)
    if not args.get("content_type"):
        args["content_type"] = guess_content_type(fpath)

    # 1. presign
    presign_resp = post_mcp(
        {
            "jsonrpc": "2.0",
            "id": id,
            "method": "tools/call",
            "params": {"name": params.get("name"), "arguments": args},
        }
    )
    if isinstance(presign_resp, dict) and presign_resp.get("error"):
        return presign_resp

    payload = parse_tool_text(presign_resp)
    if not payload or not payload.get("asset_id"):
        return presign_resp  # unexpected shape — pass through
    if not payload.get("upload_url"):
        return tool_result(id, payload)  # inline-finalized already

    # 2. PUT the bytes (presigned GCS URL — no bearer)
    put_status = put_bytes(payload["upload_url"], data, args["content_type"])
    if not _ok(put_status):
        return tool_result(
            id,
            {
                "error": "presigned PUT failed (HTTP {})".format(put_status),
                "asset_id": payload["asset_id"],
            },
            True,
        )

    # 3. finalize
    fin_status, fin_text = finalize_asset(payload["asset_id"])
    if not _ok(fin_status):
        return tool_result(
            id,
            {
                "error": "finalize failed (HTTP {}): {}".format(
                    fin_status, fin_text[:200]
                ),
                "asset_id": payload["asset_id"],
            },
            True,
        )

    done = dict(payload)
    done["state"] = "ready"
    done["uploaded_bytes"] = len(data)
    done.pop("upload_url", None)
    done.pop("next_step", None)
    return tool_result(id, done)


# ------------------------------------------------------------------------------
# Run-log search (launcher-served, backed by Scribe — not chronicle)
# ------------------------------------------------------------------------------

# A launcher-provided tool the model can call to view + search a training run's
# logs. It is served by Scribe (POST /v1/logs/search → Cloud Logging), so the
# launcher handles it locally instead of proxying to chronicle's MCP.
SEARCH_LOGS_TOOL = {
    "name": "search_logs",
    "description": (
        "View and search a training run's logs (from Cloud Logging, via Scribe) for "
        "troubleshooting. Returns log lines newest-first; pass `query` to filter to a "
        "case-insensitive substring (e.g. an error message). Error *detection* is also "
        "on the run record (status + failure reason); this is for full log detail."
    ),
    "inputSchema": {
        "type": "object",
        "required": ["experiment_id", "variation", "run"],
        "properties": {
            "experiment_id": {"type": "string", "description": "Experiment UUID."},
            "variation": {"type": "integer", "description": "Variation index."},
            "run": {"type": "integer", "description": "Run number within the variation."},
            "query": {
                "type": "string",
                "description": "Optional case-insensitive substring to match in the log text.",
            },
            "limit": {"type": "integer", "description": "Max lines (default 200, max 1000)."},
            "order": {
                "type": "string",
                "enum": ["asc", "desc"],
                "description": "asc = oldest first; desc = newest first (default).",
            },
        },
    },
}


def handle_search_logs(req):
    """Handle a `search_logs` tools/call by POSTing to Scribe with the caller's key."""
    if not SCRIBE_URL:
        return tool_result(
            req.get("id"),
            {
                "error": "log search unavailable: set CHRONICLE_SCRIBE_URL or "
                "scribe_url in ~/.methodic/config.yaml"
            },
            True,
        )
    a = (req.get("params") or {}).get("arguments") or {}
    body = {
        "experiment_id": a.get("experiment_id"),
        "variation": a.get("variation"),
        "run": a.get("run"),
    }
    for k in ("query", "limit", "order"):
        if k in a:
            body[k] = a[k]
    try:
        status, raw = _request(
            "POST",
            SCRIBE_URL + "/v1/logs/search",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(API_KEY),
            },
            body=json.dumps(body).encode("utf-8"),
        )
        text = raw.decode("utf-8", "replace")
        if not _ok(status):
            return tool_result(
                req.get("id"), {"error": "scribe {}: {}".format(status, text)}, True
            )
        try:
            payload = json.loads(text)
        except ValueError:
            payload = {"raw": text}
        return tool_result(req.get("id"), payload)
    except Exception as e:
        return tool_result(
            req.get("id"), {"error": "log search failed: {}".format(e)}, True
        )


def augment_tools_list(resp):
    """Advertise the launcher-handled `path` parameter on the upload tools so the
    model knows it can pass a local file instead of base64."""
    tools = (resp or {}).get("result", {}).get("tools") if isinstance(resp, dict) else None
    if not isinstance(tools, list):
        return resp
    for t in tools:
        short = re.sub(r"^chronicle\.", "", str(t.get("name") or ""))
        if short not in ("upload_asset", "upload_image"):
            continue
        schema = t.get("inputSchema") or t.get("input_schema")
        if schema and isinstance(schema.get("properties"), dict):
            schema["properties"]["path"] = {
                "type": "string",
                "description": (
                    "Local file path to upload. The methodic launcher reads the file and "
                    "runs presign -> PUT -> finalize over HTTP, so the bytes never pass "
                    "through the model. Use INSTEAD of base64_content."
                ),
            }
    # Inject the launcher-served search_logs tool (only when Scribe is configured,
    # and not if chronicle ever advertises one itself).
    if SCRIBE_URL and not any(t.get("name") == SEARCH_LOGS_TOOL["name"] for t in tools):
        tools.append(SEARCH_LOGS_TOOL)
    return resp


# ------------------------------------------------------------------------------
# Dispatch
# ------------------------------------------------------------------------------
def is_notification(req):
    return "id" not in req or req.get("id") is None


def handle_one(req):
    if not isinstance(req, dict):
        return None
    try:
        params = req.get("params") or {}
        name = params.get("name")
        arg_path = (params.get("arguments") or {}).get("path")
        if req.get("method") == "tools/call" and name in UPLOAD_TOOLS and arg_path:
            return handle_upload(req)
        # search_logs is launcher-served (Scribe-backed) — handle locally, never
        # proxy it to chronicle's MCP.
        if req.get("method") == "tools/call" and name == SEARCH_LOGS_TOOL["name"]:
            return handle_search_logs(req)

        resp = post_mcp(req)
        if req.get("method") == "tools/list":
            return augment_tools_list(resp)
        if is_notification(req):
            return None  # notifications get no stdout reply
        return resp
    except Exception as e:
        if is_notification(req):
            return None
        return json_rpc_error(req.get("id"), -32603, "launcher error: {}".format(e))


_WRITE_LOCK = threading.Lock()


def write_out(obj):
    with _WRITE_LOCK:
        sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def handle_line(line):
    try:
        req = json.loads(line)
    except ValueError:
        return  # ignore unparseable lines
    if isinstance(req, list):
        out = []
        for r in req:
            resp = handle_one(r)
            if resp:
                out.append(resp)
        if out:
            write_out(out)
        return
    resp = handle_one(req)
    if resp:
        write_out(resp)


# ------------------------------------------------------------------------------
# main
# ------------------------------------------------------------------------------
def _handle_line_logged(line):
    try:
        handle_line(line)
    except Exception as e:
        log("error", e)


def main():
    if not API_KEY:
        log(
            "WARN: no API key (CHRONICLE_API_KEY or ~/.methodic/credentials.yaml) — "
            "tool calls will 401. Run `methodic auth login`."
        )
    log("ready -> " + MCP_URL)
    # Handle each line on its own thread (the node launcher processes lines
    # concurrently too — a slow upload must not block other calls).
    while True:
        line = sys.stdin.readline()
        if line == "":
            break  # EOF — client hung up
        if line.strip():
            threading.Thread(target=_handle_line_logged, args=(line,), daemon=True).start()
    sys.exit(0)


if __name__ == "__main__":
    main()
