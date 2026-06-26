#!/usr/bin/env bash
# Hook stdin-simulation tests for the Phase 1 safety hooks (Items 3 & 4, COREDEV-2324).
#
# Pure bash, no Xcode — runs in the plugin repo and in Linux CI. Each case pipes
# synthetic stdin to a hook and asserts on its stdout/exit. All hook state is
# isolated in a temp CLAUDE_PLUGIN_DATA so the real ~/.claude is never touched.
set -uo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$_DIR/sensitive-file-guard.sh"
STOP="$_DIR/stop-quality-marker-gate.sh"
BUILD_VERIFY="$_DIR/swift-build-verify.sh"

# Isolated, throwaway plugin-data dir for markers/logs/sentinels.
TMPROOT="$(mktemp -d 2>/dev/null || mktemp -d -t hooktests)"
export CLAUDE_PLUGIN_DATA="$TMPROOT/data"
cleanup() { rm -rf "$TMPROOT" 2>/dev/null || true; }
trap cleanup EXIT

# Marker helpers (same path math the hooks use) so tests and hooks agree on paths.
# shellcheck source=scripts/lib/marker.sh
. "$_DIR/lib/marker.sh"

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); }
fail() { FAIL=$((FAIL + 1)); printf 'FAIL: %s\n' "$1" >&2; }

assert_contains() {
    case "$2" in
        *"$3"*) ok ;;
        *) fail "$1 — expected to contain [$3], got [$2]" ;;
    esac
}
assert_not_contains() {
    case "$2" in
        *"$3"*) fail "$1 — should NOT contain [$3], got [$2]" ;;
        *) ok ;;
    esac
}
assert_empty() {
    if [ -z "$2" ]; then ok; else fail "$1 — expected empty, got [$2]"; fi
}

is_valid_json() {
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$1" | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1
        return $?
    elif command -v jq >/dev/null 2>&1; then
        printf '%s' "$1" | jq . >/dev/null 2>&1
        return $?
    fi
    return 0
}

reset_markers() {
    rm -f "$(marker_path lint)" "$(marker_path build)" \
          "$(marker_dir)/stop-last-blocked-$(marker_repo_hash)" 2>/dev/null || true
}

# Portably backdate a file's mtime by N seconds (GNU then BSD form).
backdate() {
    local f="$1" secs="$2" target stamp
    target=$(( $(date +%s) - secs ))
    if touch -d "@$target" "$f" 2>/dev/null; then return 0; fi
    stamp="$(date -r "$target" +%Y%m%d%H%M.%S 2>/dev/null)" || return 1
    touch -t "$stamp" "$f" 2>/dev/null
}

KEYCHAIN='Unleashed Mail/Sources/Services/KeychainManager.swift'

echo "== sensitive-file-guard (Item 3) =="

# 1. Sensitive .swift Edit, ask mode -> ask + valid JSON; the embedded space survives.
OUT="$(printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$KEYCHAIN" \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_contains "keychain edit -> ask" "$OUT" '"permissionDecision":"ask"'
assert_not_contains "ask never emits allow" "$OUT" '"allow"'
if is_valid_json "$OUT"; then ok; else fail "keychain ask -> valid JSON"; fi

# 2. Benign view Edit, ask mode -> no decision (omit permissionDecision).
OUT="$(printf '{"tool_name":"Edit","tool_input":{"file_path":"Unleashed Mail/Sources/Views/InboxView.swift"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_empty "benign edit -> no decision" "$OUT"

# 3. Read-only Bash (grep) on a sensitive path -> no decision.
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"grep KeychainManager src/KeychainManager.swift"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_empty "read-only grep -> no decision" "$OUT"

# 4. sed -i writing a sensitive file -> ask.
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"sed -i s/a/b/ KeychainManager.swift"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_contains "sed -i sensitive -> ask" "$OUT" '"permissionDecision":"ask"'

# 5. cp with the signature as SOURCE -> no decision (only writes are guarded).
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"cp KeychainManager.swift /tmp/copy.txt"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_empty "cp source -> no decision" "$OUT"

# 6. cp with the signature as DESTINATION -> ask.
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"cp template.swift KeychainManager.swift"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_contains "cp dest -> ask" "$OUT" '"permissionDecision":"ask"'

# 7. Quoted redirect target with a space -> ask (proves space survives parsing).
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"echo x >\\"%s\\""}}' "$KEYCHAIN" \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_contains "quoted redirect -> ask" "$OUT" '"permissionDecision":"ask"'

# 7b. Chained write (a later command would defeat a naive $NF) -> still ask.
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"cp template.swift KeychainManager.swift && git diff"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_contains "chained cp dest -> ask" "$OUT" '"permissionDecision":"ask"'

# 7c. mv renames a protected file AWAY (source is modified/removed) -> ask.
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"mv KeychainManager.swift backup.swift"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_contains "mv source -> ask" "$OUT" '"permissionDecision":"ask"'

# 7d. Trailing flag after the destination -> still ask (flag stripped, dest found).
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"cp template.swift KeychainManager.swift -v"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_contains "trailing flag -> ask" "$OUT" '"permissionDecision":"ask"'

# 7e. Benign mv (no signature) -> no decision.
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"mv a.swift b.swift"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_empty "benign mv -> no decision" "$OUT"

# 8. Warn mode -> systemMessage advisory, NO permissionDecision.
OUT="$(printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$KEYCHAIN" \
    | UNLEASHED_SENSITIVE_GUARD_MODE=warn bash "$GUARD" 2>/dev/null)"
assert_contains "warn -> systemMessage" "$OUT" '"systemMessage"'
assert_not_contains "warn -> no decision" "$OUT" 'permissionDecision'

# 9. Kill switch off -> nothing, even on a sensitive path.
OUT="$(printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$KEYCHAIN" \
    | UNLEASHED_SENSITIVE_GUARD=off UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_empty "kill switch off -> nothing" "$OUT"

# 10. *Tests.swift is excluded even with a sensitive stem.
OUT="$(printf '{"tool_name":"Edit","tool_input":{"file_path":"Unleashed MailTests/KeychainManagerTests.swift"}}' \
    | UNLEASHED_SENSITIVE_GUARD_MODE=ask bash "$GUARD" 2>/dev/null)"
assert_empty "tests file excluded -> no decision" "$OUT"

# 11. swift-build-verify input-read migration (stdin JSON) still fires its advisory.
OUT="$(printf '{"tool_name":"Bash","tool_input":{"command":"xcodebuild build -scheme X"}}' \
    | bash "$BUILD_VERIFY" 2>/dev/null)"
assert_contains "build-verify reads stdin command" "$OUT" "xcodebuild build detected"

echo "== stop-quality-marker-gate (Item 4) =="

# 12. Fresh failing marker, commit matches -> block (enforce).
reset_markers
marker_write lint fail
OUT="$(printf '{"stop_hook_active":false}' | UNLEASHED_STOP_GATE_MODE=enforce bash "$STOP" 2>/dev/null)"
assert_contains "fresh fail -> block" "$OUT" '"decision":"block"'
if is_valid_json "$OUT"; then ok; else fail "block -> valid JSON"; fi
assert_not_contains "block is root-level (not nested)" "$OUT" 'hookSpecificOutput'

# 13. Stale marker (mtime backdated past TTL) -> no block.
reset_markers
marker_write lint fail
backdate "$(marker_path lint)" 3700
OUT="$(printf '{"stop_hook_active":false}' | UNLEASHED_STOP_GATE_MODE=enforce bash "$STOP" 2>/dev/null)"
assert_empty "stale mtime -> no block" "$OUT"

# 14. Missing marker -> no block.
reset_markers
OUT="$(printf '{"stop_hook_active":false}' | UNLEASHED_STOP_GATE_MODE=enforce bash "$STOP" 2>/dev/null)"
assert_empty "missing marker -> no block" "$OUT"

# 15. stop_hook_active true -> no block (loop guard #1) even with a fresh fail.
reset_markers
marker_write lint fail
OUT="$(printf '{"stop_hook_active":true}' | UNLEASHED_STOP_GATE_MODE=enforce bash "$STOP" 2>/dev/null)"
assert_empty "stop_hook_active -> no block" "$OUT"

# 16. Pass marker -> no block.
reset_markers
marker_write lint pass
OUT="$(printf '{"stop_hook_active":false}' | UNLEASHED_STOP_GATE_MODE=enforce bash "$STOP" 2>/dev/null)"
assert_empty "pass marker -> no block" "$OUT"

# 17. Sentinel == HEAD -> no re-block (loop guard #2).
reset_markers
marker_write lint fail
printf '%s' "$(git rev-parse --short HEAD 2>/dev/null)" > "$(marker_dir)/stop-last-blocked-$(marker_repo_hash)"
OUT="$(printf '{"stop_hook_active":false}' | UNLEASHED_STOP_GATE_MODE=enforce bash "$STOP" 2>/dev/null)"
assert_empty "sentinel == HEAD -> no re-block" "$OUT"

# 18. Warn mode -> no stdout, but a diagnostic line is logged.
reset_markers
marker_write lint fail
OUT="$(printf '{"stop_hook_active":false}' | UNLEASHED_STOP_GATE_MODE=warn bash "$STOP" 2>/dev/null)"
assert_empty "warn mode -> no stdout" "$OUT"
if [ -s "$CLAUDE_PLUGIN_DATA/logs/stop-gate.log" ]; then ok; else fail "warn mode -> diagnostic logged"; fi

# 19. Kill switch off -> no block even with a fresh fail.
reset_markers
marker_write lint fail
OUT="$(printf '{"stop_hook_active":false}' | UNLEASHED_STOP_GATE=off UNLEASHED_STOP_GATE_MODE=enforce bash "$STOP" 2>/dev/null)"
assert_empty "kill switch off -> no block" "$OUT"

# 20. No heavy work: shim xcodebuild + swiftlint on PATH; the hook must block on a
#     build-fail marker yet NEVER invoke either binary (codex Nit #1 — assert no
#     invocation, not a text grep, since the block reason names the remedy command).
reset_markers
SHIMDIR="$TMPROOT/shims"
INVOKED="$TMPROOT/invoked"
mkdir -p "$SHIMDIR"
rm -f "$INVOKED"
for _t in xcodebuild swiftlint; do
    {
        printf '#!/bin/sh\n'
        printf 'echo %s >> "%s"\n' "$_t" "$INVOKED"
        printf 'exit 0\n'
    } > "$SHIMDIR/$_t"
    chmod +x "$SHIMDIR/$_t"
done
marker_write build fail
T0="$(date +%s 2>/dev/null || echo 0)"
OUT="$(printf '{"stop_hook_active":false}' \
    | PATH="$SHIMDIR:$PATH" UNLEASHED_STOP_GATE_MODE=enforce bash "$STOP" 2>/dev/null)"
T1="$(date +%s 2>/dev/null || echo 0)"
assert_contains "build fail -> block" "$OUT" '"decision":"block"'
if [ -f "$INVOKED" ]; then fail "Stop hook invoked a heavy tool: $(cat "$INVOKED" 2>/dev/null)"; else ok; fi
ELAPSED=$(( T1 - T0 ))
if [ "$ELAPSED" -lt 5 ]; then ok; else fail "Stop hook too slow (${ELAPSED}s) — must not run a build"; fi

echo ""
echo "hook tests: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
