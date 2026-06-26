#!/usr/bin/env bash
# validate-version-sync.sh — Phase 0, Item 1 (COREDEV-2322)
#
# Asserts the plugin's version + asset counts are in sync across their sources of
# truth, so a bump to one place can't silently drift from the others:
#   1. .claude-plugin/plugin.json  "version"
#   2. README.md  H1            "… Plugin vX.Y.Z"
#   3. README.md  newest         "### vX.Y.Z"  (What's New)
#   4. README.md  bold counts    "**N agents · N skills · N commands · N MCP server(s)**"
#                                vs the files actually on disk + .mcp.json
#
# Scope: the unleashed-mail PLUGIN repo only (run from the HAS_XCODEPROJ=false
# branch of pre-commit-checks.sh). marketplace.json has no version field — not asserted.
#
# Modes (env):
#   VERSION_SYNC_ENFORCE=warn   (default) — print mismatches, exit 0  (pre-commit)
#   VERSION_SYNC_ENFORCE=strict           — print mismatches, exit 1  (CI)
#   SKIP_PLUGIN_VALIDATORS=1              — hard bypass, exit 0
set -euo pipefail

[[ "${SKIP_PLUGIN_VALIDATORS:-0}" == "1" ]] && { echo "⏭️  validate-version-sync: skipped (SKIP_PLUGIN_VALIDATORS=1)"; exit 0; }

# Self-locate the repo root (parent of scripts/) so it runs from any CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENFORCE="${VERSION_SYNC_ENFORCE:-warn}"

errors=0
fail() { echo "❌ $*"; errors=$((errors + 1)); }

PLUGIN_JSON="$ROOT/.claude-plugin/plugin.json"
README="$ROOT/README.md"
MCP_JSON="$ROOT/.mcp.json"

[[ -f "$PLUGIN_JSON" ]] || fail "missing .claude-plugin/plugin.json"
[[ -f "$README" ]]      || fail "missing README.md"

# --- versions ---------------------------------------------------------------
# plugin.json is the comparison anchor.
PLUGIN_VERSION="$(grep -m1 -oE '"version"[[:space:]]*:[[:space:]]*"[0-9]+\.[0-9]+\.[0-9]+"' "$PLUGIN_JSON" 2>/dev/null \
                  | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)"
README_H1="$(grep -m1 -oE 'Plugin v[0-9]+\.[0-9]+\.[0-9]+' "$README" 2>/dev/null | sed 's/Plugin v//' || true)"
README_WHATSNEW="$(grep -m1 -oE '^### v[0-9]+\.[0-9]+\.[0-9]+' "$README" 2>/dev/null | sed 's/^### v//' || true)"

[[ -n "$PLUGIN_VERSION"  ]] || fail "could not parse version from plugin.json"
[[ -n "$README_H1"       ]] || fail "could not parse 'Plugin vX.Y.Z' from README H1"
[[ -n "$README_WHATSNEW" ]] || fail "could not parse newest '### vX.Y.Z' from README"

[[ "$PLUGIN_VERSION" == "$README_H1" ]] \
  || fail "version drift: README H1 v$README_H1 != plugin.json $PLUGIN_VERSION — bump README H1"
[[ "$PLUGIN_VERSION" == "$README_WHATSNEW" ]] \
  || fail "version drift: newest README '### v$README_WHATSNEW' != plugin.json $PLUGIN_VERSION — add a What's-New entry"

# --- asset counts (README bold line vs disk) --------------------------------
# Anchor on the bold counts line so historical "(up from X)" prose never matches.
COUNTS_LINE="$(grep -m1 -E '^\*\*[0-9]+ agents' "$README" 2>/dev/null || true)"
[[ -n "$COUNTS_LINE" ]] || fail "could not find the '**N agents · N skills · N commands …**' line in README"

# BSD wc left-pads with spaces — coerce to an integer via arithmetic ($(( )) ).
count_files() { local n; n="$(find "$1" -mindepth "${3:-1}" -maxdepth "${4:-1}" -name "$2" 2>/dev/null | wc -l || true)"; echo "$(( n ))"; }
readme_count() { grep -oE "[0-9]+ $1" <<<"$COUNTS_LINE" | head -1 | grep -oE '^[0-9]+' || true; }

DISK_AGENTS="$(count_files "$ROOT/agents" '*.md')"
DISK_SKILLS="$(count_files "$ROOT/skills" 'SKILL.md' 1 2)"
DISK_COMMANDS="$(count_files "$ROOT/commands" '*.md')"

check_count() { # readme_token  disk_value
  local token="$1" disk="$2" rd
  rd="$(readme_count "$token")"
  [[ -n "$rd" ]] || { fail "README counts line missing '$token'"; return; }
  [[ "$rd" == "$disk" ]] || fail "count drift: README says $rd $token, disk has $disk"
}
check_count "agents"   "$DISK_AGENTS"
check_count "skills"   "$DISK_SKILLS"
check_count "commands" "$DISK_COMMANDS"

# MCP-server count: whenever .mcp.json is part of the plugin, the README token must
# be present AND match — a dropped token is real drift (codex PR #11). utf-8-sig is
# BOM-safe (gemini PR #11). (allow the optional plural "servers")
README_MCP="$(grep -oE '[0-9]+ MCP servers?' <<<"$COUNTS_LINE" | head -1 | grep -oE '^[0-9]+' || true)"
if [[ -f "$MCP_JSON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    DISK_MCP="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1], encoding="utf-8-sig")).get("mcpServers",{})))' "$MCP_JSON" 2>/dev/null || echo "")"
    if [[ -z "$DISK_MCP" ]]; then
      fail ".mcp.json present but unparseable for MCP-server count"
    elif [[ "$DISK_MCP" -gt 0 && -z "$README_MCP" ]]; then
      fail "count drift: .mcp.json defines $DISK_MCP MCP server(s) but the README counts line has no 'N MCP server' token"
    elif [[ -n "$README_MCP" && "$README_MCP" != "$DISK_MCP" ]]; then
      fail "count drift: README says $README_MCP MCP server(s), .mcp.json defines $DISK_MCP"
    fi
  fi
elif [[ -n "$README_MCP" && "$README_MCP" != "0" ]]; then
  fail "count drift: README says $README_MCP MCP server(s), but .mcp.json is missing"
fi

# --- result -----------------------------------------------------------------
if [[ "$errors" -eq 0 ]]; then
  echo "✅ version-sync OK — plugin $PLUGIN_VERSION == README (H1 & What's-New); counts ${DISK_AGENTS}/${DISK_SKILLS}/${DISK_COMMANDS}${README_MCP:+/${README_MCP}} match disk"
  exit 0
fi

echo "—"
if [[ "$ENFORCE" == "strict" ]]; then
  echo "❌ version-sync: $errors problem(s) (strict) — failing."
  exit 1
fi
echo "⚠️  version-sync: $errors problem(s) (warn mode — not blocking; set VERSION_SYNC_ENFORCE=strict to enforce)."
exit 0
