#!/bin/bash
# PostToolUse hook for Bash: detect test/build commands and verify results.
# Runs after Bash tool invocations to catch failed builds and test runs.
#
# UnleashedMail is an Xcode project — `xcodebuild` is the canonical tool.
# `swift build`/`swift test` are flagged as warnings (likely user error invoking
# the wrong tool against this xcodeproj).
#
# COREDEV-2324: input read migrated to the shared hook-io helper (stdin-JSON first,
# CLAUDE_TOOL_ARG_* fallback) so this hook is not silently inert if the installed
# Claude Code build delivers stdin JSON only.
#
# COREDEV-2325 (Item 10): on the PostToolUse (non-failure) path, also append a bounded
# build-CLASS line with failed=false — the "attempted/non-failure" side that pairs with
# scripts/build-failure-log.sh (PostToolUseFailure, failed=true). Class only, never the
# raw command. Gated by UNLEASHED_FAILURE_LOG.

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=scripts/lib/hook-io.sh
[ -f "$_DIR/lib/hook-io.sh" ] && . "$_DIR/lib/hook-io.sh"
# shellcheck source=scripts/lib/log.sh
[ -f "$_DIR/lib/log.sh" ] && . "$_DIR/lib/log.sh"

if command -v hook_io_read >/dev/null 2>&1; then
    hook_io_read
    COMMAND="$(hook_command)"
else
    COMMAND="${CLAUDE_TOOL_ARG_command:-}"
fi

# Append the "attempted" build-class line (failed=false). Class only — never the command.
_log_build_attempt() {
    [ "${UNLEASHED_FAILURE_LOG:-on}" = "off" ] && return 0
    command -v log_append >/dev/null 2>&1 || return 0
    log_append "build-log.jsonl" "$(printf '{"ts":"%s","kind":"build","class":"%s","failed":false}' "$(log_ts)" "$1")"
}

case "$COMMAND" in
    # The two xcodebuild actions containing BOTH "build" and "test" (TN2339) are matched explicitly
    # before the generic arms, kept in lockstep with scripts/build-failure-log.sh so a command can't
    # change class on success vs. failure.
    *"xcodebuild"*"build-for-testing"*)
        echo "🔨 xcodebuild build-for-testing detected — verify BUILD SUCCEEDED in the output above."
        _log_build_attempt "xcodebuild-build"
        ;;
    *"xcodebuild"*"test-without-building"*)
        echo "🧪 xcodebuild test-without-building detected — verify all tests passed in the output above."
        _log_build_attempt "xcodebuild-test"
        ;;
    *"xcodebuild"*"build"*)
        echo "🔨 xcodebuild build detected — verify BUILD SUCCEEDED in the output above."
        _log_build_attempt "xcodebuild-build"
        ;;
    *"xcodebuild"*"test"*)
        echo "🧪 xcodebuild test detected — verify all tests passed in the output above."
        echo "   If tests failed, fix the failures before proceeding."
        _log_build_attempt "xcodebuild-test"
        ;;
    *"swift build"*)
        echo "⚠️  'swift build' detected — but this project is an Xcode project, not a SwiftPM package."
        echo "   Use: xcodebuild build -scheme \"Unleashed Mail\" -destination 'platform=macOS'"
        ;;
    *"swift test"*)
        echo "⚠️  'swift test' detected — but this project is an Xcode project, not a SwiftPM package."
        echo "   Use: xcodebuild test -scheme \"Unleashed Mail\" -destination 'platform=macOS'"
        ;;
    *)
        # Not a build/test command — no action
        exit 0
        ;;
esac

exit 0
