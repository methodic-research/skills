#!/usr/bin/env python3
"""Tests for the Python MCP launcher port. Run: `python3 mcp/server_test.py`.

Strategy mirrors server.test.js: stand up a mock chronicle HTTP server, point
the launcher at it via env BEFORE importing it (the module resolves server URL
+ key at import), then drive `handle_one` in-process. No real ~/.methodic or
network is touched.
"""

import http.server
import json
import os
import sys
import tempfile
import threading
import unittest

CAPTURED = {
    "presign_args": None,
    "put_len": None,
    "finalize_id": None,
    "last_method": None,
    "log_search_body": None,
}

server = None  # the launcher module, imported after env is set
_httpd = None
_port = None


def _dispatch_mock(rpc):
    if rpc.get("method") == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": rpc.get("id"),
            "result": {
                "tools": [
                    {
                        "name": "chronicle.upload_asset",
                        "description": "u",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"filename": {"type": "string"}},
                        },
                    },
                    {
                        "name": "chronicle.get_experiment",
                        "description": "g",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"experiment_id": {"type": "string"}},
                        },
                    },
                ]
            },
        }
    if rpc.get("method") == "tools/call":
        name = rpc["params"]["name"]
        if name == "chronicle.upload_asset":
            CAPTURED["presign_args"] = rpc["params"]["arguments"]
            payload = {
                "asset_id": "A1",
                "experiment_id": rpc["params"]["arguments"].get("experiment_id"),
                "state": "pending",
                "upload_url": "http://127.0.0.1:{}/presigned/A1".format(_port),
                "next_step": "PUT the bytes ...",
            }
            return {
                "jsonrpc": "2.0",
                "id": rpc.get("id"),
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "isError": False,
                },
            }
        # passthrough echo
        return {
            "jsonrpc": "2.0",
            "id": rpc.get("id"),
            "result": {
                "content": [{"type": "text", "text": json.dumps({"echoed": rpc["params"]})}],
                "isError": False,
            },
        }
    if str(rpc.get("method", "")).startswith("notifications/"):
        return {"jsonrpc": "2.0", "id": rpc.get("id"), "result": None}
    if rpc.get("method") == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rpc.get("id"),
            "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "chronicle-mcp"}},
        }
    return {
        "jsonrpc": "2.0",
        "id": rpc.get("id"),
        "error": {"code": -32601, "message": "method not found"},
    }


class MockChronicle(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n)

    def _reply(self, status, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        buf = self._body()
        # presigned PUT (the launcher uploads bytes here — no bearer)
        if self.path.startswith("/presigned/"):
            CAPTURED["put_len"] = len(buf)
            self._reply(200, "OK", "text/plain")
            return
        # finalize
        if self.path.startswith("/v1/assets/") and self.path.endswith("/finalize"):
            CAPTURED["finalize_id"] = self.path.split("/")[3]
            self._reply(200, "{}")
            return
        self._reply(404, "nope", "text/plain")

    def do_POST(self):
        buf = self._body()
        # the MCP transport
        if self.path == "/v1/mcp/messages":
            rpc = json.loads(buf.decode("utf-8"))
            CAPTURED["last_method"] = rpc.get("method")
            self._reply(200, json.dumps(_dispatch_mock(rpc)))
            return
        # scribe log search (stand-in for Scribe; same mock host)
        if self.path == "/v1/logs/search":
            body = json.loads(buf.decode("utf-8"))
            CAPTURED["log_search_body"] = body
            self._reply(
                200,
                json.dumps(
                    {
                        "experiment_id": body.get("experiment_id"),
                        "variation": body.get("variation"),
                        "run": body.get("run"),
                        "count": 1,
                        "entries": [
                            {
                                "timestamp": "2026-01-01T00:00:00Z",
                                "severity": "ERROR",
                                "text": "boom",
                            }
                        ],
                    }
                ),
            )
            return
        self._reply(404, "nope", "text/plain")


def setUpModule():
    global server, _httpd, _port
    _httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockChronicle)
    _port = _httpd.server_address[1]
    threading.Thread(target=_httpd.serve_forever, daemon=True).start()

    os.environ["CHRONICLE_SERVER_URL"] = "http://127.0.0.1:{}".format(_port)
    os.environ["CHRONICLE_SCRIBE_URL"] = "http://127.0.0.1:{}".format(_port)
    os.environ["CHRONICLE_API_KEY"] = "sk_test_key"

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import importlib

    server = importlib.import_module("server")  # resolves config from the env above


def tearDownModule():
    _httpd.shutdown()


# ---- pure helpers ------------------------------------------------------------


class PureHelpers(unittest.TestCase):
    def test_parse_flat_yaml_reads_kv_strips_quotes_and_comments(self):
        out = server.parse_flat_yaml(
            'api_key: sk_user_abc   # secret\nserver_url: "http://x"\n# comment\n'
        )
        self.assertEqual(out["api_key"], "sk_user_abc")
        self.assertEqual(out["server_url"], "http://x")

    def test_resolve_config_honors_env_precedence(self):
        cfg = server.resolve_config()
        self.assertEqual(cfg["api_key"], "sk_test_key")
        self.assertEqual(cfg["server_url"], "http://127.0.0.1:{}".format(_port))

    def test_guess_content_type_maps_known_extensions(self):
        self.assertEqual(server.guess_content_type("/x/plot.png"), "image/png")
        self.assertEqual(
            server.guess_content_type("/x/data.parquet"), "application/octet-stream"
        )
        self.assertEqual(server.guess_content_type("/x/notes.md"), "text/markdown")

    def test_expand_path_resolves_tilde(self):
        home = os.environ.get("HOME") or os.path.expanduser("~")
        self.assertEqual(server.expand_path("~/a/b"), os.path.join(home, "a/b"))


# ---- proxy + interception (against the mock) ---------------------------------


class ProxyAndInterception(unittest.TestCase):
    def test_tools_list_augmented_with_path_on_upload_tools(self):
        resp = server.handle_one({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        by_name = {t["name"]: t for t in resp["result"]["tools"]}
        self.assertIn(
            "path",
            by_name["chronicle.upload_asset"]["inputSchema"]["properties"],
            "upload_asset gains path",
        )
        self.assertNotIn(
            "path",
            by_name["chronicle.get_experiment"]["inputSchema"]["properties"],
            "non-upload untouched",
        )

    def test_tools_list_includes_launcher_served_search_logs(self):
        resp = server.handle_one({"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
        by_name = {t["name"]: t for t in resp["result"]["tools"]}
        self.assertIn("search_logs", by_name, "search_logs advertised")
        self.assertEqual(
            by_name["search_logs"]["inputSchema"]["required"],
            ["experiment_id", "variation", "run"],
        )

    def test_search_logs_served_by_scribe_not_proxied(self):
        CAPTURED["last_method"] = None
        resp = server.handle_one(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "search_logs",
                    "arguments": {
                        "experiment_id": "E7",
                        "variation": 2,
                        "run": 0,
                        "query": "boom",
                    },
                },
            }
        )
        # Hit Scribe's /v1/logs/search with the run identity + query...
        self.assertEqual(CAPTURED["log_search_body"]["experiment_id"], "E7")
        self.assertEqual(CAPTURED["log_search_body"]["run"], 0)
        self.assertEqual(CAPTURED["log_search_body"]["query"], "boom")
        # ...and was NOT proxied to chronicle's MCP transport.
        self.assertIsNone(CAPTURED["last_method"])
        payload = server.parse_tool_text(resp)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entries"][0]["text"], "boom")
        self.assertFalse(resp["result"]["isError"])

    def test_non_upload_tools_call_forwarded_verbatim(self):
        resp = server.handle_one(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "chronicle.get_experiment",
                    "arguments": {"experiment_id": "E9"},
                },
            }
        )
        payload = server.parse_tool_text(resp)
        self.assertEqual(payload["echoed"]["name"], "chronicle.get_experiment")
        self.assertEqual(CAPTURED["last_method"], "tools/call")

    def test_upload_with_local_path_drives_presign_put_finalize(self):
        data = b"hello-bytes-1234567890"
        fd, tmp = tempfile.mkstemp(suffix=".bin", prefix="methodic-mcp-test-")
        with os.fdopen(fd, "wb") as f:
            f.write(data)

        try:
            resp = server.handle_one(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "chronicle.upload_asset",
                        "arguments": {
                            "experiment_id": "E1",
                            "path": tmp,
                            "asset_type": "dataset",
                            "link": "output",
                        },
                    },
                }
            )

            # presign call stripped the local path + forced presign mode, derived filename
            self.assertNotIn(
                "path", CAPTURED["presign_args"], "path not forwarded to server"
            )
            self.assertNotIn(
                "base64_content",
                CAPTURED["presign_args"],
                "no base64 (presign forced)",
            )
            self.assertEqual(CAPTURED["presign_args"]["filename"], os.path.basename(tmp))
            # bytes PUT to the presigned URL, then finalized
            self.assertEqual(CAPTURED["put_len"], len(data))
            self.assertEqual(CAPTURED["finalize_id"], "A1")
            # result is the finalized asset
            payload = server.parse_tool_text(resp)
            self.assertEqual(payload["asset_id"], "A1")
            self.assertEqual(payload["state"], "ready")
            self.assertEqual(payload["uploaded_bytes"], len(data))
            self.assertFalse(resp["result"]["isError"])
            self.assertNotIn("upload_url", payload, "upload_url scrubbed from the result")
        finally:
            os.unlink(tmp)

    def test_upload_without_path_not_intercepted(self):
        CAPTURED["put_len"] = None
        resp = server.handle_one(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "chronicle.upload_asset",
                    "arguments": {
                        "experiment_id": "E1",
                        "base64_content": "AAA=",
                        "filename": "x.bin",
                        "asset_type": "dataset",
                    },
                },
            }
        )
        # forwarded verbatim → mock recorded the args but no local PUT happened
        self.assertIsNone(CAPTURED["put_len"], "no presigned PUT for a non-path call")
        self.assertTrue(server.parse_tool_text(resp)["asset_id"], "server response returned")

    def test_notifications_get_no_stdout_reply(self):
        resp = server.handle_one({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(resp)


if __name__ == "__main__":
    unittest.main(verbosity=1)
