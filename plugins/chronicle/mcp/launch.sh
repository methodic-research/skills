#!/bin/sh
# chronicle-mcp runtime probe — pick the best available runtime and exec the
# launcher under it. Claude Code does NOT bundle Node (only Claude Desktop
# does, for .mcpb extensions), so `command: node` alone breaks on machines
# without a system Node — e.g. an ML workstation with only Python installed.
#
# Preference order:
#   1. node    — runs server.js, the reference implementation
#   2. bun     — Node-compatible, runs the same server.js
#   3. python3 — runs server.py, the dependency-free stdlib port
#
# POSIX sh only, no external commands (works under a stripped PATH: the
# `case`/`cd`/`pwd`/`command` used here are all shell builtins).

case "$0" in
  */*) here=$(CDPATH= cd -- "${0%/*}" && pwd) ;;
  *) here=$(pwd) ;;
esac

if command -v node >/dev/null 2>&1; then
  exec node "$here/server.js" "$@"
fi
if command -v bun >/dev/null 2>&1; then
  exec bun "$here/server.js" "$@"
fi
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$here/server.py" "$@"
fi

echo "[chronicle-mcp] no supported runtime found: need node (>= 18), bun, or python3 (>= 3.8) on PATH." >&2
echo "[chronicle-mcp] install one of them, or use the Claude Desktop bundle (ships its own runtime), or configure a remote HTTP MCP server (see the README)." >&2
exit 1
