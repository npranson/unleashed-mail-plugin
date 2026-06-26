#!/bin/bash
# PostToolUse hook: validate Swift files after Write/Edit operations.
# Exits non-zero to BLOCK the write if critical violations are found.
#
# COREDEV-2324: input read migrated to the shared hook-io helper (stdin-JSON first,
# CLAUDE_TOOL_ARG_* fallback) and a per-kind lint marker is written for the Stop-gate.

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=scripts/lib/hook-io.sh
[ -f "$_DIR/lib/hook-io.sh" ] && . "$_DIR/lib/hook-io.sh"
# shellcheck source=scripts/lib/marker.sh
[ -f "$_DIR/lib/marker.sh" ] && . "$_DIR/lib/marker.sh"

if command -v hook_io_read >/dev/null 2>&1; then
    hook_io_read
    FILE_PATH="$(hook_file_path)"
else
    FILE_PATH="${CLAUDE_TOOL_ARG_file_path:-${CLAUDE_TOOL_ARG_path:-}}"
fi

# Only process .swift files
if [[ "$FILE_PATH" != *.swift ]]; then
    exit 0
fi

EXIT_CODE=0

# --- 1. Syntax check (fast, catches parse errors) ---
if command -v swiftc &> /dev/null; then
    RESULT=$(swiftc -parse "$FILE_PATH" 2>&1)
    if [ $? -ne 0 ]; then
        echo "❌ Swift syntax error in $FILE_PATH — BLOCKED"
        echo "$RESULT" | head -10
        # Record the fail marker before the early exit so the Stop-gate sees it —
        # a syntax error is a real lint failure (codex PR #12).
        command -v marker_write >/dev/null 2>&1 && marker_write lint fail
        exit 1
    fi
fi

# --- 2. SwiftLint check (if available) ---
if command -v swiftlint &> /dev/null; then
    LINT_OUTPUT=$(swiftlint lint --path "$FILE_PATH" --quiet --force-exclude 2>&1)

    # Count errors vs warnings.
    # `grep -c PATTERN || echo 0` produces "0\n0" on no-match (the failing
    # grep AND the echo fallback both fire). Use `|| true` and rely on grep
    # printing a single line per file, then guard against empty with :-0.
    ERROR_COUNT=$(printf '%s' "$LINT_OUTPUT" | grep -c ": error:" 2>/dev/null || true)
    WARNING_COUNT=$(printf '%s' "$LINT_OUTPUT" | grep -c ": warning:" 2>/dev/null || true)
    ERROR_COUNT=${ERROR_COUNT:-0}
    WARNING_COUNT=${WARNING_COUNT:-0}

    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "❌ SwiftLint errors in $FILE_PATH — BLOCKED"
        echo "$LINT_OUTPUT" | grep ": error:" | head -10
        EXIT_CODE=1
    elif [ "$WARNING_COUNT" -gt 0 ]; then
        echo "⚠️  SwiftLint warnings in $FILE_PATH:"
        echo "$LINT_OUTPUT" | grep ": warning:" | head -5
        # Warnings don't block
    fi
fi

# --- 3. try! in production code (BLOCKS) ---
if [[ "$FILE_PATH" != *Tests/* ]] && [[ "$FILE_PATH" != *Test.swift ]]; then
    TRY_BANG=$(grep -n 'try!' "$FILE_PATH" 2>/dev/null | grep -v '^\s*//')
    if [ -n "$TRY_BANG" ]; then
        echo "❌ Found 'try!' in production code — BLOCKED: $FILE_PATH"
        echo "$TRY_BANG"
        EXIT_CODE=1
    fi
fi

# --- 4. Force cast detection (BLOCKS) ---
if [[ "$FILE_PATH" != *Tests/* ]] && [[ "$FILE_PATH" != *Test.swift ]]; then
    FORCE_CAST=$(grep -n 'as!' "$FILE_PATH" 2>/dev/null | grep -v '^\s*//')
    if [ -n "$FORCE_CAST" ]; then
        echo "❌ Found 'as!' (force cast) in production code — BLOCKED: $FILE_PATH"
        echo "$FORCE_CAST"
        EXIT_CODE=1
    fi
fi

# --- 5. Token/secret logging check (BLOCKS) ---
TOKEN_LOG=$(grep -n 'print.*[Tt]oken\|NSLog.*[Tt]oken\|Logger.*accessToken\|Logger.*refreshToken' "$FILE_PATH" 2>/dev/null | grep -v '^\s*//')
if [ -n "$TOKEN_LOG" ]; then
    echo "❌ Potential token value in log statement — BLOCKED: $FILE_PATH"
    echo "$TOKEN_LOG"
    EXIT_CODE=1
fi

# --- 6. Test file existence check (WARNING only, does not block) ---
# UnleashedMail layout: production code lives under "Unleashed Mail/Sources/",
# tests under "Unleashed MailTests/" (note the space). Swift package layout would be
# "Sources/" -> "Tests/"; we accept both forms so the hook is portable to other repos.
case "$FILE_PATH" in
    *"Unleashed Mail/Sources/"*.swift)
        TEST_PATH=$(echo "$FILE_PATH" | sed 's|Unleashed Mail/Sources/|Unleashed MailTests/|' | sed 's|\.swift$|Tests.swift|')
        if [ ! -f "$TEST_PATH" ]; then
            echo "⚠️  No test file found for $(basename "$FILE_PATH") (expected: $TEST_PATH)"
        fi
        ;;
    *Sources/*.swift)
        case "$FILE_PATH" in
            *Tests/*) ;;  # already a test file
            *)
                TEST_PATH=$(echo "$FILE_PATH" | sed 's|Sources/|Tests/|' | sed 's|\.swift$|Tests.swift|')
                if [ ! -f "$TEST_PATH" ]; then
                    echo "⚠️  No test file found for $(basename "$FILE_PATH") (expected: $TEST_PATH)"
                fi
                ;;
        esac
        ;;
esac

# --- COREDEV-2324: write the lint marker for the Stop-gate ---
# This is a per-FILE PostToolUse hook, so it must NOT write lint=pass: one clean file
# can't prove the whole repo lints, and overwriting a global fail would let the
# Stop-gate be bypassed (gemini + codex PR #12). Write only lint=fail — fail-closed is
# the safe default for a gate. The pass/clear comes from a full-project lint (the
# pre-commit build marker, which clears the sentinel) or when HEAD/TTL moves on.
if command -v marker_write >/dev/null 2>&1 && [ "$EXIT_CODE" -ne 0 ]; then
    marker_write lint fail
fi

exit $EXIT_CODE
