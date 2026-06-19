#!/usr/bin/env node
'use strict';

/**
 * methodic-mcp — a stdio MCP launcher bundled in the methodic plugin.
 *
 * It lets skills call chronicle's `chronicle.*` MCP tools directly, with no
 * Python SDK install:
 *
 *   Claude Code  <--stdio JSON-RPC-->  this launcher  <--HTTPS-->  chronicle-server
 *                                                                  POST /v1/mcp/messages
 *
 * What it does:
 *  - Resolves the API key + server URL from ~/.methodic (same precedence as the
 *    Python SDK), so the existing `methodic auth login` credentials work as-is.
 *  - Transparently proxies MCP JSON-RPC (initialize / tools/list / tools/call /
 *    notifications) to the in-server transport with `Authorization: Bearer`.
 *  - Intercepts `upload_asset` / `upload_image` calls that carry a local `path`:
 *    reads the file, drives the presign -> PUT -> finalize dance over HTTP, and
 *    returns the finalized asset. The model only ever passes a *path*, so the
 *    bytes never transit the model context. Single-blob only; multi-file /
 *    directory uploads stay on the SDK (`chronicle.datasets.upload`).
 *
 * Pure Node stdlib (global `fetch`, Node >= 18 which Claude Code ships). No deps.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const readline = require('readline');

// ----------------------------------------------------------------------------
// Credential / server resolution — mirrors methodic SDK `chronicle.py`.
// ----------------------------------------------------------------------------
const DEFAULT_SERVER_URL = 'https://api.methodiclabs.ai';

/**
 * Minimal parser for the flat `key: value` `~/.methodic` files
 * (credentials.yaml -> api_key; config.yaml -> server_url / organization_id).
 * Avoids a YAML dependency. Ignores blank lines and `#` comments; strips one
 * layer of matching quotes.
 */
function parseFlatYaml(text) {
  const out = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.replace(/\s+#.*$/, '');
    const m = line.match(/^\s*([A-Za-z0-9_]+)\s*:\s*(.+?)\s*$/);
    if (!m) continue;
    let v = m[2].trim();
    if (
      (v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))
    ) {
      v = v.slice(1, -1);
    }
    out[m[1]] = v;
  }
  return out;
}

function methodicHome() {
  return process.env.HOME || os.homedir();
}

function readMethodicFile(name) {
  try {
    const p = path.join(methodicHome(), '.methodic', name);
    return parseFlatYaml(fs.readFileSync(p, 'utf8'));
  } catch {
    return {};
  }
}

function resolveConfig() {
  const creds = readMethodicFile('credentials.yaml');
  const cfg = readMethodicFile('config.yaml');
  const apiKey =
    process.env.CHRONICLE_API_KEY || creds.api_key || cfg.api_key || null;
  const serverUrl = (
    process.env.CHRONICLE_SERVER_URL ||
    cfg.server_url ||
    DEFAULT_SERVER_URL
  ).replace(/\/+$/, '');
  return { apiKey, serverUrl };
}

const { apiKey, serverUrl } = resolveConfig();
const MCP_URL = `${serverUrl}/v1/mcp/messages`;

// stderr only — stdout is the MCP channel.
function log(...parts) {
  process.stderr.write('[methodic-mcp] ' + parts.join(' ') + '\n');
}

// ----------------------------------------------------------------------------
// HTTP
// ----------------------------------------------------------------------------
async function postMcp(message) {
  const res = await fetch(MCP_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(message),
  });
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return jsonRpcError(
      message && message.id,
      -32603,
      `chronicle returned non-JSON (HTTP ${res.status}): ${text.slice(0, 200)}`
    );
  }
}

async function putBytes(url, body, contentType) {
  const headers = {};
  if (contentType) headers['Content-Type'] = contentType;
  return fetch(url, { method: 'PUT', headers, body });
}

async function finalizeAsset(assetId) {
  return fetch(`${serverUrl}/v1/assets/${assetId}/finalize`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${apiKey}` },
  });
}

// ----------------------------------------------------------------------------
// JSON-RPC helpers
// ----------------------------------------------------------------------------
function jsonRpcError(id, code, message, data) {
  const error = { code, message };
  if (data !== undefined) error.data = data;
  return { jsonrpc: '2.0', id: id === undefined ? null : id, error };
}

// Wrap a plain object as an MCP tools/call result (content[0].text = JSON).
function toolResult(id, payload, isError = false) {
  return {
    jsonrpc: '2.0',
    id,
    result: {
      content: [
        {
          type: 'text',
          text: typeof payload === 'string' ? payload : JSON.stringify(payload),
        },
      ],
      isError,
    },
  };
}

// Pull the JSON chronicle packs into a tools/call result's content[0].text.
function parseToolText(resp) {
  try {
    return JSON.parse(resp.result.content[0].text);
  } catch {
    return null;
  }
}

// ----------------------------------------------------------------------------
// Upload interception
// ----------------------------------------------------------------------------
const UPLOAD_TOOLS = new Set([
  'upload_asset',
  'upload_image',
  'chronicle.upload_asset',
  'chronicle.upload_image',
]);

const CONTENT_TYPES = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.html': 'text/html',
  '.pdf': 'application/pdf',
  '.json': 'application/json',
  '.csv': 'text/csv',
  '.txt': 'text/plain',
  '.md': 'text/markdown',
  '.parquet': 'application/octet-stream',
  '.safetensors': 'application/octet-stream',
  '.npy': 'application/octet-stream',
  '.npz': 'application/octet-stream',
  '.bin': 'application/octet-stream',
};

function guessContentType(p) {
  return CONTENT_TYPES[path.extname(p).toLowerCase()] || 'application/octet-stream';
}

function expandPath(p) {
  let out = p;
  if (out === '~' || out.startsWith('~/')) {
    out = path.join(methodicHome(), out.slice(1));
  }
  return path.resolve(out);
}

/**
 * Handle an upload_* tools/call that carries a local `path`. Returns a JSON-RPC
 * response (never null — the caller has already decided to intercept).
 */
async function handleUpload(req) {
  const id = req.id;
  const params = req.params || {};
  const args = Object.assign({}, params.arguments || {});

  const fpath = expandPath(args.path);
  let bytes;
  try {
    bytes = fs.readFileSync(fpath);
  } catch (e) {
    return toolResult(id, { error: `cannot read path '${args.path}': ${e.message}` }, true);
  }

  // The local-only `path` is ours; force the presign path server-side.
  delete args.path;
  delete args.base64_content;
  if (!args.filename) args.filename = path.basename(fpath);
  if (!args.content_type) args.content_type = guessContentType(fpath);

  // 1. presign
  const presignResp = await postMcp({
    jsonrpc: '2.0',
    id,
    method: 'tools/call',
    params: { name: params.name, arguments: args },
  });
  if (presignResp.error) return presignResp;

  const payload = parseToolText(presignResp);
  if (!payload || !payload.asset_id) return presignResp; // unexpected shape — pass through
  if (!payload.upload_url) return toolResult(id, payload); // inline-finalized already

  // 2. PUT the bytes (presigned GCS URL — no bearer)
  const put = await putBytes(payload.upload_url, bytes, args.content_type);
  if (!put.ok) {
    return toolResult(
      id,
      { error: `presigned PUT failed (HTTP ${put.status})`, asset_id: payload.asset_id },
      true
    );
  }

  // 3. finalize
  const fin = await finalizeAsset(payload.asset_id);
  if (!fin.ok) {
    const t = await fin.text().catch(() => '');
    return toolResult(
      id,
      {
        error: `finalize failed (HTTP ${fin.status}): ${t.slice(0, 200)}`,
        asset_id: payload.asset_id,
      },
      true
    );
  }

  const done = Object.assign({}, payload, {
    state: 'ready',
    uploaded_bytes: bytes.length,
  });
  delete done.upload_url;
  delete done.next_step;
  return toolResult(id, done);
}

// Advertise the launcher-handled `path` parameter on the upload tools so the
// model knows it can pass a local file instead of base64.
function augmentToolsList(resp) {
  const tools = resp && resp.result && resp.result.tools;
  if (!Array.isArray(tools)) return resp;
  for (const t of tools) {
    const short = String(t.name || '').replace(/^chronicle\./, '');
    if (short !== 'upload_asset' && short !== 'upload_image') continue;
    const schema = t.inputSchema || t.input_schema;
    if (schema && schema.properties) {
      schema.properties.path = {
        type: 'string',
        description:
          'Local file path to upload. The methodic launcher reads the file and ' +
          'runs presign -> PUT -> finalize over HTTP, so the bytes never pass ' +
          'through the model. Use INSTEAD of base64_content.',
      };
    }
  }
  return resp;
}

// ----------------------------------------------------------------------------
// Dispatch
// ----------------------------------------------------------------------------
function isNotification(req) {
  return req.id === undefined || req.id === null;
}

async function handleOne(req) {
  if (!req || typeof req !== 'object') return null;
  try {
    const name = req.params && req.params.name;
    const argPath = req.params && req.params.arguments && req.params.arguments.path;
    if (req.method === 'tools/call' && UPLOAD_TOOLS.has(name) && argPath) {
      return await handleUpload(req);
    }

    const resp = await postMcp(req);
    if (req.method === 'tools/list') return augmentToolsList(resp);
    if (isNotification(req)) return null; // notifications get no stdout reply
    return resp;
  } catch (e) {
    if (isNotification(req)) return null;
    return jsonRpcError(req.id, -32603, `launcher error: ${e && e.message}`);
  }
}

function writeOut(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

async function handleLine(line) {
  let req;
  try {
    req = JSON.parse(line);
  } catch {
    return; // ignore unparseable lines
  }
  if (Array.isArray(req)) {
    const out = [];
    for (const r of req) {
      const resp = await handleOne(r);
      if (resp) out.push(resp);
    }
    if (out.length) writeOut(out);
    return;
  }
  const resp = await handleOne(req);
  if (resp) writeOut(resp);
}

// ----------------------------------------------------------------------------
// main
// ----------------------------------------------------------------------------
function main() {
  if (typeof fetch !== 'function') {
    log('FATAL: global fetch unavailable — Node >= 18 is required.');
    process.exit(1);
  }
  if (!apiKey) {
    log(
      'WARN: no API key (CHRONICLE_API_KEY or ~/.methodic/credentials.yaml) — ' +
        'tool calls will 401. Run `methodic auth login`.'
    );
  }
  log(`ready -> ${MCP_URL}`);
  const rl = readline.createInterface({ input: process.stdin });
  rl.on('line', (line) => {
    if (line.trim()) handleLine(line).catch((e) => log('error', e && e.message));
  });
  rl.on('close', () => process.exit(0));
}

if (require.main === module) main();

module.exports = {
  parseFlatYaml,
  resolveConfig,
  guessContentType,
  expandPath,
  augmentToolsList,
  toolResult,
  parseToolText,
  handleOne,
  _setForTest: () => {}, // placeholder; tests drive via env + a mock server
};
