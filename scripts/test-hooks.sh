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
# Phase 2 (COREDEV-2325) observability hooks.
STOP_FAIL_LOG="$_DIR/stop-failure-log.sh"
DENY_LOG="$_DIR/permission-denied-log.sh"
BUILD_FAIL_LOG="$_DIR/build-failure-log.sh"
PRECOMPACT="$_DIR/precompact-snapshot.sh"
SESSION_RESTORE="$_DIR/sessionstart-restore.sh"
CAPTURE="$_DIR/capture-reviewer-verdict.sh"

# Isolated, throwaway plugin-data dir for markers/logs/sentinels.
TMPROOT="$(mktemp -d 2>/dev/null || mktemp -d -t hooktests)"
export CLAUDE_PLUGIN_DATA="$TMPROOT/data"
cleanup() { rm -rf "$TMPROOT" 2>/dev/null || true; }
trap cleanup EXIT

# Marker helpers (same path math the hooks use) so tests and hooks agree on paths.
# shellcheck source=scripts/lib/marker.sh
. "$_DIR/lib/marker.sh"
# Context helpers (Phase 2) so capture tests resolve the same reviews/<slug> path.
# shellcheck source=scripts/lib/context.sh
. "$_DIR/lib/context.sh"

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

echo "== Item 10 diagnostic logs (StopFailure / PermissionDenied / PostToolUseFailure) =="

# JSON-encode a string for safe embedding in a synthetic stdin payload.
json_str() { python3 -c 'import json,sys; sys.stdout.write(json.dumps(sys.argv[1]))' "$1"; }

# 21. StopFailure logs ONLY the coarse enum; raw error_message text never persists.
rm -rf "$CLAUDE_PLUGIN_DATA/logs" 2>/dev/null
printf '{"error_type":"rate_limit","error_message":"failed at /Users/john.doe/secret token sk-abc1234567"}' \
    | bash "$STOP_FAIL_LOG" 2>/dev/null
ERRLOG="$CLAUDE_PLUGIN_DATA/logs/error-log.jsonl"
assert_contains "stopfailure logs enum" "$(cat "$ERRLOG" 2>/dev/null)" '"type":"rate_limit"'
assert_not_contains "stopfailure no error_message PII" "$(cat "$ERRLOG" 2>/dev/null)" 'john.doe'
assert_not_contains "stopfailure no secret" "$(cat "$ERRLOG" 2>/dev/null)" 'sk-abc'

# 22. StopFailure defensive .error fallback.
printf '{"error":"overloaded"}' | bash "$STOP_FAIL_LOG" 2>/dev/null
assert_contains "stopfailure .error fallback" "$(tail -1 "$ERRLOG" 2>/dev/null)" '"type":"overloaded"'

# 22b. A path/email IN error_type itself is REDACTED (not just delimiter-stripped) — the
#      tr -cd clamp alone would keep the username/email payload, so it must redact first.
printf '{"error_type":"server_error /Users/john.doe/x contact nick@corp.com"}' | bash "$STOP_FAIL_LOG" 2>/dev/null
assert_not_contains "stopfailure redacts path in error_type" "$(tail -1 "$ERRLOG" 2>/dev/null)" 'john.doe'
assert_not_contains "stopfailure redacts email in error_type" "$(tail -1 "$ERRLOG" 2>/dev/null)" 'corp.com'

# 23. PermissionDenied logs tool + sanitized reason; tool_input is NEVER read.
printf '{"tool_name":"Edit","reason":"blocked path /Users/john.doe/x","tool_input":{"file_path":"/Users/john.doe/SECRETFILE"}}' \
    | bash "$DENY_LOG" 2>/dev/null
DENYLOG="$CLAUDE_PLUGIN_DATA/logs/denied-commands.jsonl"
assert_contains "denied logs tool" "$(cat "$DENYLOG" 2>/dev/null)" '"tool":"Edit"'
assert_not_contains "denied no tool_input value" "$(cat "$DENYLOG" 2>/dev/null)" 'SECRETFILE'
assert_not_contains "denied reason redacts /Users" "$(cat "$DENYLOG" 2>/dev/null)" 'john.doe'

# 23b. PermissionDenied: a spaced "API key: VALUE" secret in reason is redacted.
rm -f "$DENYLOG" 2>/dev/null
printf '{"tool_name":"Bash","reason":"denied API key: ABCDEFGHIJKLMNOP exposed"}' | bash "$DENY_LOG" 2>/dev/null
assert_not_contains "denied redacts spaced api key" "$(cat "$DENYLOG" 2>/dev/null)" 'ABCDEFGHIJKLMNOP'

# 23b2. An uppercase BEARER token in reason is redacted (case-insensitive).
rm -f "$DENYLOG" 2>/dev/null
printf '{"tool_name":"Bash","reason":"used BEARER opaqueTOKEN1234567890abcdef now"}' | bash "$DENY_LOG" 2>/dev/null
assert_not_contains "denied redacts uppercase BEARER" "$(cat "$DENYLOG" 2>/dev/null)" 'opaqueTOKEN'

# 23c. PermissionDenied: a NESTED tool_input.tool_name must never be read/persisted as the tool.
rm -f "$DENYLOG" 2>/dev/null
printf '{"tool_input":{"tool_name":"john.doe@corp.com"},"reason":"x"}' | bash "$DENY_LOG" 2>/dev/null
assert_not_contains "denied ignores nested tool_input.tool_name" "$(cat "$DENYLOG" 2>/dev/null)" 'john.doe'

# 23d. hook_str stays TOP-LEVEL-ONLY even with no jq/python3 (a grep fallback would read the
#      nested tool_input.tool_name — the exact leak path). command()->fail simulates no engines.
OUT="$(HOOK_STDIN='{"tool_input":{"tool_name":"john.doe@corp.com"}}' bash -c '. "'"$_DIR"'/lib/hook-io.sh"; command() { return 1; }; hook_str tool_name' 2>/dev/null)"
assert_empty "hook_str top-level-only without jq/py3" "$OUT"

# 23e. hook_str python fallback (no jq) reads+writes UNICODE under a non-UTF-8 locale (LC_ALL=C):
#      stdin.buffer in + stdout.buffer out, so neither the decode nor the encode raises.
OUT="$(HOOK_STDIN='{"reason":"café leak"}' LC_ALL=C PYTHONUTF8=0 bash -c '. "'"$_DIR"'/lib/hook-io.sh"; command() { if [ "$1" = "-v" ] && [ "$2" = "jq" ]; then return 1; fi; builtin command "$@"; }; hook_str reason' 2>/dev/null)"
assert_contains "hook_str unicode under C locale (no jq)" "$OUT" "café"

# 24. PermissionDenied: nested tool_input.reason must NOT be read as top-level reason.
rm -f "$DENYLOG" 2>/dev/null
printf '{"tool_name":"Bash","tool_input":{"reason":"NESTED_LEAK /Users/john.doe/z"}}' \
    | bash "$DENY_LOG" 2>/dev/null
assert_contains "denied no top reason -> unknown" "$(cat "$DENYLOG" 2>/dev/null)" '"reason":"unknown"'
assert_not_contains "denied does not read nested reason" "$(cat "$DENYLOG" 2>/dev/null)" 'NESTED_LEAK'

# 25. PostToolUseFailure logs only the build CLASS + failed=true; raw command never persists.
printf '{"tool_name":"Bash","tool_input":{"command":"xcodebuild build -archivePath /Users/john.doe/A.xcarchive CODE_SIGN_IDENTITY=secret"},"error":"BUILD FAILED"}' \
    | bash "$BUILD_FAIL_LOG" 2>/dev/null
BUILDLOG="$CLAUDE_PLUGIN_DATA/logs/build-log.jsonl"
assert_contains "build-fail class" "$(cat "$BUILDLOG" 2>/dev/null)" '"class":"xcodebuild-build","failed":true'
assert_not_contains "build-fail no archivePath" "$(cat "$BUILDLOG" 2>/dev/null)" 'archivePath'
assert_not_contains "build-fail no signing identity" "$(cat "$BUILDLOG" 2>/dev/null)" 'CODE_SIGN'

# 26. Log rotation: 600 lines -> capped to 250 after the next write.
ROT="$CLAUDE_PLUGIN_DATA/logs/error-log.jsonl"
rm -f "$ROT" 2>/dev/null
mkdir -p "$CLAUDE_PLUGIN_DATA/logs"
i=0; while [ "$i" -lt 600 ]; do printf '{"ts":"x","type":"unknown"}\n' >> "$ROT"; i=$((i+1)); done
printf '{"error_type":"server_error"}' | bash "$STOP_FAIL_LOG" 2>/dev/null
ROTN="$(wc -l < "$ROT" 2>/dev/null | tr -d '[:space:]')"
if [ "$ROTN" = "250" ]; then ok; else fail "rotation -> expected 250 lines, got $ROTN"; fi

# 27. Kill switches emit nothing.
assert_empty "failure-log off -> nothing" "$(printf '{"error_type":"server_error"}' | UNLEASHED_FAILURE_LOG=off bash "$STOP_FAIL_LOG" 2>/dev/null)"
assert_empty "deny-log off -> nothing" "$(printf '{"tool_name":"Edit","reason":"x"}' | UNLEASHED_DENY_LOG=off bash "$DENY_LOG" 2>/dev/null)"

# 27b. Open-failure must be STDERR-CLEAN: make the log path a directory so the append open
#      fails, and assert nothing (esp. the PII-bearing path) leaks to stderr.
rm -rf "$CLAUDE_PLUGIN_DATA/logs" 2>/dev/null
mkdir -p "$CLAUDE_PLUGIN_DATA/logs/error-log.jsonl"
ERROUT="$(printf '{"error_type":"server_error"}' | bash "$STOP_FAIL_LOG" 2>&1 1>/dev/null)"
assert_empty "open-fail -> stderr clean (no path leak)" "$ERROUT"
rm -rf "$CLAUDE_PLUGIN_DATA/logs" 2>/dev/null

# 27c. Append succeeds but the line-count READ fails (write-only log file) -> still stderr-clean
#      (the `wc -l 2>/dev/null < "$path"` read-open error must not leak the path).
rm -rf "$CLAUDE_PLUGIN_DATA/logs" 2>/dev/null
mkdir -p "$CLAUDE_PLUGIN_DATA/logs"
: > "$CLAUDE_PLUGIN_DATA/logs/error-log.jsonl"
chmod 200 "$CLAUDE_PLUGIN_DATA/logs/error-log.jsonl"   # write-only: append OK, read fails
ERROUT="$(printf '{"error_type":"overloaded"}' | bash "$STOP_FAIL_LOG" 2>&1 1>/dev/null)"
assert_empty "read-probe-fail -> stderr clean (no path leak)" "$ERROUT"
chmod 600 "$CLAUDE_PLUGIN_DATA/logs/error-log.jsonl" 2>/dev/null
rm -rf "$CLAUDE_PLUGIN_DATA/logs" 2>/dev/null

echo "== Item 5 PreCompact snapshot + SessionStart restore =="
SNAP="$(context_snapshot_path)"   # per-checkout: <base>/.state/work-context-snapshot-<repohash>.json
# Per-repo namespacing (codex PR review): the snapshot path + reviews dir carry the repo hash.
REPOHASH="$(context_repo_hash)"
assert_contains "snapshot path is repo-namespaced" "$SNAP" "$REPOHASH"
assert_contains "reviews dir is repo-namespaced" "$(context_reviews_dir)" "$REPOHASH"

# 28. Snapshot derives a PII-safe ticket/slug; raw branch is never persisted.
rm -f "$SNAP" 2>/dev/null
( cd "$_DIR/.." && printf '{"trigger":"auto"}' | bash "$PRECOMPACT" 2>/dev/null )
if [ -f "$SNAP" ]; then ok; else fail "precompact -> snapshot written"; fi
if is_valid_json "$(cat "$SNAP" 2>/dev/null)"; then ok; else fail "snapshot -> valid JSON"; fi
assert_contains "snapshot has ticket" "$(cat "$SNAP" 2>/dev/null)" '"ticket"'
assert_not_contains "snapshot no raw branch suffix" "$(cat "$SNAP" 2>/dev/null)" 'observability'

# 28b. Plan resolves from the REPO ROOT even when PreCompact fires from a subdirectory (codex PR).
rm -f "$SNAP" 2>/dev/null
( cd "$_DIR" && printf '{}' | bash "$PRECOMPACT" 2>/dev/null )   # cwd = scripts/ (a repo subdir)
assert_not_contains "plan found from repo root (cwd=subdir)" "$(cat "$SNAP" 2>/dev/null)" '"plan":"unknown"'

# 29. Restore on source=compact within 10 min -> additionalContext + snapshot deleted.
OUT="$(printf '{"source":"compact"}' | bash "$SESSION_RESTORE" 2>/dev/null)"
assert_contains "restore -> additionalContext" "$OUT" '"additionalContext"'
assert_contains "restore -> SessionStart event" "$OUT" '"hookEventName":"SessionStart"'
if is_valid_json "$OUT"; then ok; else fail "restore -> valid JSON"; fi
if [ -f "$SNAP" ]; then fail "restore-once -> snapshot deleted"; else ok; fi

# 30. Restore source=clear -> silent, no replay (clear not in restore set).
( cd "$_DIR/.." && printf '{}' | bash "$PRECOMPACT" 2>/dev/null )
OUT="$(printf '{"source":"clear"}' | bash "$SESSION_RESTORE" 2>/dev/null)"
assert_empty "restore clear -> silent" "$OUT"
if [ -f "$SNAP" ]; then ok; else fail "clear -> snapshot preserved"; fi

# 31. Stale snapshot (>10 min) -> silent exit, file left in place.
backdate "$SNAP" 660
OUT="$(printf '{"source":"compact"}' | bash "$SESSION_RESTORE" 2>/dev/null)"
assert_empty "stale snapshot -> silent" "$OUT"
if [ -f "$SNAP" ]; then ok; else fail "stale -> file left for next precompact"; fi

# 31b. Restore emits VALID JSON even with a unicode snapshot under a non-UTF-8 locale.
rm -f "$SNAP" 2>/dev/null
printf '{"ticket":"COREDEV-2325","branch_slug":"COREDEV-2325","plan":"docs/planning/café_PLAN.md","round":"1","snapshot_time":%s}\n' "$(date +%s)" > "$SNAP"
OUT="$(printf '{"source":"compact"}' | LC_ALL=C bash "$SESSION_RESTORE" 2>/dev/null)"
if is_valid_json "$OUT"; then ok; else fail "restore unicode under C locale -> valid JSON"; fi

# 32. Snapshot kill switch.
rm -f "$SNAP" 2>/dev/null
( cd "$_DIR/.." && printf '{}' | UNLEASHED_COMPACT_SNAPSHOT=off bash "$PRECOMPACT" 2>/dev/null )
if [ -f "$SNAP" ]; then fail "snapshot kill switch -> no write"; else ok; fi

echo "== Item 6 SubagentStop reviewer capture =="
SLUG="$(context_branch_slug "$(context_branch)")"
REVDIR="$(context_reviews_dir)/$SLUG/round-1"
SEC_MSG='Review done.

```json
[{"severity":"blocker","confidence":"high","sourceAgent":"SPOOFED","category":"keychain","file":"/Users/john.doe/App/TokenManager.swift","line":40,"lineEnd":52,"finding":"token","evidence":"secret at /Users/john.doe/.ssh/id_rsa","fix":"mail john.doe@corp.com"}]
```'

# 33. Capture a security-reviewer message -> sanitized, normalized, no PII, consumable.
rm -rf "$(context_reviews_dir)" 2>/dev/null
printf '{"agent_type":"security-reviewer","last_assistant_message":%s}' "$(json_str "$SEC_MSG")" \
    | bash "$CAPTURE" 2>/dev/null
SECF="$REVDIR/security-reviewer.json"
if [ -f "$SECF" ]; then ok; else fail "capture -> security-reviewer.json written"; fi
assert_not_contains "capture no PII path" "$(cat "$SECF" 2>/dev/null)" 'john.doe'
assert_not_contains "capture no email" "$(cat "$SECF" 2>/dev/null)" 'corp.com'
assert_contains "capture normalizes sourceAgent" "$(cat "$SECF" 2>/dev/null)" '"sourceAgent": "security-reviewer"'
assert_not_contains "capture drops spoofed sourceAgent" "$(cat "$SECF" 2>/dev/null)" 'SPOOFED'

# 34. Dedup: replay -> no second write. Backdate the file, replay; a skip leaves the
#     old mtime, a rewrite stamps it to ~now (multi-second delta is reliable).
file_mtime() { if [ "$(uname 2>/dev/null)" = "Darwin" ]; then stat -f %m "$1" 2>/dev/null; else stat -c %Y "$1" 2>/dev/null; fi; }
backdate "$SECF" 120
MT0="$(file_mtime "$SECF")"
printf '{"agent_type":"security-reviewer","last_assistant_message":%s}' "$(json_str "$SEC_MSG")" \
    | bash "$CAPTURE" 2>/dev/null
MT1="$(file_mtime "$SECF")"
if [ "$MT0" = "$MT1" ]; then ok; else fail "dedup -> replay must not rewrite (mtime changed $MT0 -> $MT1)"; fi

# 35. swift-reviewer is EXCLUDED (it consumes the synthesizer).
printf '{"agent_type":"swift-reviewer","last_assistant_message":"```json\\n[]\\n```"}' | bash "$CAPTURE" 2>/dev/null
if [ -e "$REVDIR/swift-reviewer.json" ]; then fail "swift-reviewer must be excluded"; else ok; fi

# 36. Capture kill switch.
rm -rf "$(context_reviews_dir)" 2>/dev/null
printf '{"agent_type":"security-reviewer","last_assistant_message":"```json\\n[]\\n```"}' \
    | UNLEASHED_CAPTURE_REVIEWERS=off bash "$CAPTURE" 2>/dev/null
if [ -e "$REVDIR/security-reviewer.json" ]; then fail "capture kill switch -> no write"; else ok; fi

echo ""
echo "hook tests: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
