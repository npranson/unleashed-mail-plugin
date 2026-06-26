#!/usr/bin/env bash
# PostToolUseFailure build/test-failure log (Item 10, COREDEV-2325).
#
# A FAILED xcodebuild never reaches PostToolUse (which fires only on tool SUCCESS), so the
# build/test pass-marker path can't see failures. PostToolUseFailure (matcher Bash) is the
# failure side: when a Bash build/test command fails, append ONE bounded JSONL line with a
# derived command CLASS + failed=true — NEVER the raw command (it can carry a signing
# identity, `-archivePath`, or source strings) and never the error text.
#
# Pairs with scripts/swift-build-verify.sh, which logs the same class with failed=false on
# the PostToolUse (success) path.
#
# Output/exit are ignored by CC (the tool already failed); pure side-effect.
#
# Kill switch:  UNLEASHED_FAILURE_LOG=off  -> exit 0
set -uo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=scripts/lib/hook-io.sh
. "$_DIR/lib/hook-io.sh"
# shellcheck source=scripts/lib/log.sh
. "$_DIR/lib/log.sh"

[ "${UNLEASHED_FAILURE_LOG:-on}" = "off" ] && exit 0

hook_io_read

# Defensive: matcher already scopes to Bash, but ignore anything else. Read tool_name
# structurally top-level (hook_str, not hook_tool_name's grep fallback) so a nested
# tool_input value can never influence the gate.
TOOL="$(hook_str tool_name)"
case "$TOOL" in Bash|"") ;; *) exit 0 ;; esac

CMD="$(hook_command)"
# Derive the command CLASS only — the raw command is never read into the log.
CLASS=""
case "$CMD" in
    # The two xcodebuild actions that contain BOTH "build" and "test" keywords (Apple TN2339) must be
    # matched explicitly, before the generic arms, so a command can't change class on success vs.
    # failure (codex PR review) — keep this list identical to scripts/swift-build-verify.sh.
    *xcodebuild*build-for-testing*)     CLASS="xcodebuild-build" ;;  # builds tests, doesn't run them
    *xcodebuild*test-without-building*) CLASS="xcodebuild-test" ;;   # runs pre-built tests
    *xcodebuild*test*)                  CLASS="xcodebuild-test" ;;
    *xcodebuild*build*)                 CLASS="xcodebuild-build" ;;
    *xcodebuild*)                       CLASS="xcodebuild-other" ;;
    *"swift test"*)                     CLASS="swift-test" ;;
    *"swift build"*)                    CLASS="swift-build" ;;
    *)                                  exit 0 ;;
esac

log_append "build-log.jsonl" "$(printf '{"ts":"%s","kind":"build","class":"%s","failed":true}' "$(log_ts)" "$CLASS")"
exit 0
