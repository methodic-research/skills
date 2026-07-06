'use strict';

// Tests for the methodic MCP launcher. Run: `node --test mcp/`
// Strategy: stand up a mock chronicle HTTP server, point the launcher at it via
// env BEFORE requiring it (the module resolves server URL + key at import), then
// drive `handleOne` in-process. No real ~/.methodic or network is touched.

const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

let mod; // the launcher module, required after env is set
let mock; // { server, port, captured }

function startMockChronicle() {
  const captured = { presignArgs: null, putLen: null, finalizeId: null, lastMethod: null, logSearchBody: null };

  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const buf = Buffer.concat(chunks);

      // presigned PUT (the launcher uploads bytes here — no bearer)
      if (req.method === 'PUT' && req.url.startsWith('/presigned/')) {
        captured.putLen = buf.length;
        res.writeHead(200).end('OK');
        return;
      }
      // finalize
      const fin = req.url.match(/^\/v1\/assets\/([^/]+)\/finalize$/);
      if (req.method === 'PUT' && fin) {
        captured.finalizeId = fin[1];
        res.writeHead(200, { 'content-type': 'application/json' }).end('{}');
        return;
      }
      // the MCP transport
      if (req.method === 'POST' && req.url === '/v1/mcp/messages') {
        const rpc = JSON.parse(buf.toString('utf8'));
        captured.lastMethod = rpc.method;
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify(dispatchMock(rpc, captured, server)));
        return;
      }
      // scribe log search (stand-in for Scribe; same mock host)
      if (req.method === 'POST' && req.url === '/v1/logs/search') {
        const body = JSON.parse(buf.toString('utf8'));
        captured.logSearchBody = body;
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(
          JSON.stringify({
            experiment_id: body.experiment_id,
            variation: body.variation,
            run: body.run,
            count: 1,
            entries: [{ timestamp: '2026-01-01T00:00:00Z', severity: 'ERROR', text: 'boom' }],
          }),
        );
        return;
      }
      res.writeHead(404).end('nope');
    });
  });

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({ server, port: server.address().port, captured });
    });
  });
}

function dispatchMock(rpc, captured, server) {
  const port = server.address().port;
  if (rpc.method === 'tools/list') {
    return {
      jsonrpc: '2.0',
      id: rpc.id,
      result: {
        tools: [
          { name: 'chronicle.upload_asset', description: 'u', inputSchema: { type: 'object', properties: { filename: { type: 'string' } } } },
          { name: 'chronicle.get_experiment', description: 'g', inputSchema: { type: 'object', properties: { experiment_id: { type: 'string' } } } },
        ],
      },
    };
  }
  if (rpc.method === 'tools/call') {
    const name = rpc.params.name;
    if (name === 'chronicle.upload_asset') {
      captured.presignArgs = rpc.params.arguments;
      const payload = {
        asset_id: 'A1',
        experiment_id: rpc.params.arguments.experiment_id,
        state: 'pending',
        upload_url: `http://127.0.0.1:${port}/presigned/A1`,
        next_step: 'PUT the bytes ...',
      };
      return { jsonrpc: '2.0', id: rpc.id, result: { content: [{ type: 'text', text: JSON.stringify(payload) }], isError: false } };
    }
    // passthrough echo
    return { jsonrpc: '2.0', id: rpc.id, result: { content: [{ type: 'text', text: JSON.stringify({ echoed: rpc.params }) }], isError: false } };
  }
  if (String(rpc.method).startsWith('notifications/')) {
    return { jsonrpc: '2.0', id: rpc.id, result: null };
  }
  if (rpc.method === 'initialize') {
    return { jsonrpc: '2.0', id: rpc.id, result: { protocolVersion: '2024-11-05', serverInfo: { name: 'chronicle-mcp' } } };
  }
  return { jsonrpc: '2.0', id: rpc.id, error: { code: -32601, message: 'method not found' } };
}

test.before(async () => {
  mock = await startMockChronicle();
  process.env.CHRONICLE_SERVER_URL = `http://127.0.0.1:${mock.port}`;
  process.env.CHRONICLE_SCRIBE_URL = `http://127.0.0.1:${mock.port}`;
  process.env.CHRONICLE_API_KEY = 'sk_test_key';
  mod = require('./server.js'); // resolves config from the env set above
});

test.after(() => {
  mock.server.close();
});

// ---- pure helpers ----------------------------------------------------------

test('parseFlatYaml reads key: value, strips quotes + comments', () => {
  const out = mod.parseFlatYaml('api_key: sk_user_abc   # secret\nserver_url: "http://x"\n# comment\n');
  assert.equal(out.api_key, 'sk_user_abc');
  assert.equal(out.server_url, 'http://x');
});

test('resolveConfig honors env precedence', () => {
  const cfg = mod.resolveConfig();
  assert.equal(cfg.apiKey, 'sk_test_key');
  assert.equal(cfg.serverUrl, `http://127.0.0.1:${mock.port}`);
});

test('guessContentType maps known extensions', () => {
  assert.equal(mod.guessContentType('/x/plot.png'), 'image/png');
  assert.equal(mod.guessContentType('/x/data.parquet'), 'application/octet-stream');
  assert.equal(mod.guessContentType('/x/notes.md'), 'text/markdown');
});

test('expandPath resolves ~', () => {
  const home = process.env.HOME || os.homedir();
  assert.equal(mod.expandPath('~/a/b'), path.join(home, 'a/b'));
});

// ---- proxy + interception (against the mock) -------------------------------

test('tools/list is augmented with a `path` param on upload tools', async () => {
  const resp = await mod.handleOne({ jsonrpc: '2.0', id: 1, method: 'tools/list' });
  const byName = Object.fromEntries(resp.result.tools.map((t) => [t.name, t]));
  assert.ok(byName['chronicle.upload_asset'].inputSchema.properties.path, 'upload_asset gains path');
  assert.ok(!byName['chronicle.get_experiment'].inputSchema.properties.path, 'non-upload untouched');
});

test('tools/list includes the launcher-served search_logs tool', async () => {
  const resp = await mod.handleOne({ jsonrpc: '2.0', id: 10, method: 'tools/list' });
  const byName = Object.fromEntries(resp.result.tools.map((t) => [t.name, t]));
  assert.ok(byName['search_logs'], 'search_logs advertised');
  assert.deepEqual(byName['search_logs'].inputSchema.required, [
    'experiment_id',
    'variation',
    'run',
  ]);
});

test('search_logs tools/call is served by Scribe, not proxied to chronicle', async () => {
  mock.captured.lastMethod = null;
  const resp = await mod.handleOne({
    jsonrpc: '2.0', id: 11, method: 'tools/call',
    params: { name: 'search_logs', arguments: { experiment_id: 'E7', variation: 2, run: 0, query: 'boom' } },
  });
  // Hit Scribe's /v1/logs/search with the run identity + query...
  assert.equal(mock.captured.logSearchBody.experiment_id, 'E7');
  assert.equal(mock.captured.logSearchBody.run, 0);
  assert.equal(mock.captured.logSearchBody.query, 'boom');
  // ...and was NOT proxied to chronicle's MCP transport.
  assert.equal(mock.captured.lastMethod, null);
  const payload = mod.parseToolText(resp);
  assert.equal(payload.count, 1);
  assert.equal(payload.entries[0].text, 'boom');
  assert.equal(resp.result.isError, false);
});

test('a non-upload tools/call is forwarded verbatim', async () => {
  const resp = await mod.handleOne({
    jsonrpc: '2.0', id: 2, method: 'tools/call',
    params: { name: 'chronicle.get_experiment', arguments: { experiment_id: 'E9' } },
  });
  const payload = mod.parseToolText(resp);
  assert.equal(payload.echoed.name, 'chronicle.get_experiment');
  assert.equal(mock.captured.lastMethod, 'tools/call');
});

test('upload_asset with a local path drives presign -> PUT -> finalize', async () => {
  const tmp = path.join(os.tmpdir(), `methodic-mcp-test-${process.pid}.bin`);
  const data = Buffer.from('hello-bytes-1234567890');
  fs.writeFileSync(tmp, data);

  const resp = await mod.handleOne({
    jsonrpc: '2.0', id: 3, method: 'tools/call',
    params: { name: 'chronicle.upload_asset', arguments: { experiment_id: 'E1', path: tmp, asset_type: 'dataset', link: 'output' } },
  });

  // presign call stripped the local path + forced presign mode, derived filename
  assert.ok(!('path' in mock.captured.presignArgs), 'path not forwarded to server');
  assert.ok(!('base64_content' in mock.captured.presignArgs), 'no base64 (presign forced)');
  assert.equal(mock.captured.presignArgs.filename, path.basename(tmp));
  // bytes PUT to the presigned URL, then finalized
  assert.equal(mock.captured.putLen, data.length);
  assert.equal(mock.captured.finalizeId, 'A1');
  // result is the finalized asset
  const payload = mod.parseToolText(resp);
  assert.equal(payload.asset_id, 'A1');
  assert.equal(payload.state, 'ready');
  assert.equal(payload.uploaded_bytes, data.length);
  assert.equal(resp.result.isError, false);
  assert.ok(!('upload_url' in payload), 'upload_url scrubbed from the result');

  fs.unlinkSync(tmp);
});

test('upload_asset without a path is NOT intercepted (passes through)', async () => {
  mock.captured.putLen = null;
  const resp = await mod.handleOne({
    jsonrpc: '2.0', id: 4, method: 'tools/call',
    params: { name: 'chronicle.upload_asset', arguments: { experiment_id: 'E1', base64_content: 'AAA=', filename: 'x.bin', asset_type: 'dataset' } },
  });
  // forwarded verbatim → mock recorded the args but no local PUT happened
  assert.equal(mock.captured.putLen, null, 'no presigned PUT for a non-path call');
  assert.ok(mod.parseToolText(resp).asset_id, 'server response returned');
});

test('notifications get no stdout reply', async () => {
  const resp = await mod.handleOne({ jsonrpc: '2.0', method: 'notifications/initialized' });
  assert.equal(resp, null);
});
