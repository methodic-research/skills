# methodic MCP launcher — implementation plan

**Goal.** Let methodic skills call chronicle's `chronicle.*` MCP tools **directly**
(no Python SDK install) with **token savings** (structured tool calls instead of
generated SDK code), while reusing the existing `~/.methodic` credentials and
keeping **local-file uploads** working.

## Why a launcher (not just a remote MCP config)

chronicle's MCP server is the **in-server HTTP transport** at
`POST /v1/mcp/messages` (Streamable-HTTP, ~45 tools, bearer-authed) — **not** a
stdio shim (the design doc's "stdio shim, separate binary" is stale; corrected in
runes). A remote MCP config alone can't (a) read `~/.methodic/credentials.yaml`
or (b) move local file bytes. A tiny **local stdio launcher** solves both.

## Decisions (from the design thread)

- **Node**, pure stdlib (Claude Code ships Node ≥18 → global `fetch`; no npm). A
  minimal flat-`key: value` parser reads the `~/.methodic` files (no YAML dep).
- **Cred/URL resolution mirrors the SDK** (`chronicle.py`): `api_key` =
  `$CHRONICLE_API_KEY` → `~/.methodic/credentials.yaml`; `server_url` =
  `$CHRONICLE_SERVER_URL` → `~/.methodic/config.yaml` → `https://api.methodiclabs.ai`.
- **Transparent proxy**: stdin newline-JSON-RPC → `POST {server_url}/v1/mcp/messages`
  (`Authorization: Bearer`) → stdout. Passes `initialize` / `tools/list` /
  `tools/call` / `notifications/*` through.
- **Upload interception** (chosen scope): `upload_asset` / `upload_image` called
  with a local `path` → launcher reads the file, calls the tool in **presign**
  mode (no `base64_content`), PUTs the bytes to the returned `upload_url`, then
  `PUT /v1/assets/{id}/finalize`. The model only passes a *path* (cheap); bytes go
  over HTTP. `tools/list` is augmented to advertise `path`. Single-blob only —
  multi-file/dir uploads stay on the SDK (`chronicle.datasets.upload`).
- **SDK-preference ("auto")**: when the Python SDK is importable, skills prefer it
  for uploads / multi-file / W&B (feature coverage — the SDK shards directories;
  it's not a perf thing, uploads are network-bound). Otherwise the MCP launcher.
  Documented convention; applied per-skill.

## Files / phases

1. `mcp/server.js` — the launcher (this PR).
2. `mcp/server.test.js` — `node:test` against a mock HTTP server: cred resolution,
   proxy passthrough, `tools/list` `path` augmentation, upload interception
   (presign→PUT→finalize), notification = no stdout.
3. MCP plugin config — Claude Code uses the root `.mcp.json` with
   `${CLAUDE_PLUGIN_ROOT}`; Codex uses `plugins/chronicle/.mcp.json` with
   `cwd: "."` and `args: ["./mcp/server.js"]`.
4. `plugin.json` 0.8.0 → **0.9.0** (off #23) + a "direct MCP transport" desc note.
5. `skills/status` → MCP-direct proof (drop the SDK `Requires`; add the auto note).
6. `README` / docs: the transport split (MCP-direct vs SDK-required) + SDK-preference.
7. **runes** `design.md` §21 fix (separate PR): correct the stdio-shim mislabel;
   document the in-server `/v1/mcp/messages` transport, the plugin launcher, the
   SDK-preference convention, and the transport split.

## Base / versioning

Off **#23 `feat/collections-and-tags-skills`** (highest open skills PR, plugin
0.8.0) → **0.9.0**; rebase to `main` after #23 merges. Runes design fix off `main`.

## Testing

`node --test mcp/` (mock server). Full e2e needs a running chronicle-server with
`/v1/mcp/messages`; **flag separately** whether that route is deployed to ci/prod
(gates real-world use, not the build).
