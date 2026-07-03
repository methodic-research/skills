#!/usr/bin/env bash
# Build the Chronicle Claude Desktop bundle: desktop/dist/chronicle-<version>.mcpb
#
# Single-sourced by design — no duplicated server code, no version drift:
#   - the server is a COPY of ../mcp/server.js (the exact file the Claude Code
#     plugin runs; pure Node stdlib, zero npm deps), and
#   - the version is read from ../.claude-plugin/plugin.json and injected into
#     the staged manifest (the committed manifest.json version is only a
#     fallback for a raw `mcpb pack`).
#
# Requires: node (>=18) and network access for `npx @anthropic-ai/mcpb`.
# Usage: bash desktop/build.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
stage="$here/build"
dist="$here/dist"

version="$(node -e "process.stdout.write(require('$root/.claude-plugin/plugin.json').version)")"

rm -rf "$stage" "$dist"
mkdir -p "$stage" "$dist"

# MCP server — single source of truth is mcp/server.js.
cp "$root/mcp/server.js" "$stage/server.js"

# Stage the manifest with the plugin.json version injected.
node -e "
  const fs = require('fs');
  const m = JSON.parse(fs.readFileSync('$here/manifest.json', 'utf8'));
  m.version = '$version';
  fs.writeFileSync('$stage/manifest.json', JSON.stringify(m, null, 2) + '\n');
"

out="$dist/chronicle-$version.mcpb"
npx --yes @anthropic-ai/mcpb@2.1.2 pack "$stage" "$out"
echo "Built $out"
