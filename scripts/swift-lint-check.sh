#!/bin/bash
# PostToolUse hook: validate Swift files after Write/Edit operations.
# Exits non-zero to BLOCK the write if critical violations are found.

FILE_PATH="${CLAUDE_TOOL_ARG_file_path:-${CLAUDE_TOOL_ARG_path:-}}"

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
        exit 1
    fi
fi

# --- 2. SwiftLint check (if available) ---
if command -v swiftlint &> /dev/null; then
    LINT_OUTPUT=$(swiftlint lint --path "$FILE_PATH" --quiet --force-exclude 2>&1)

    # Count errors vs warnings
    ERROR_COUNT=$(echo "$LINT_OUTPUT" | grep -c ": error:" 2>/dev/null || echo "0")
    WARNING_COUNT=$(echo "$LINT_OUTPUT" | grep -c ": warning:" 2>/dev/null || echo "0")

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
if [[ "$FILE_PATH" == *Sources/*.swift ]] && [[ "$FILE_PATH" != *Tests/* ]]; then
    TEST_PATH=$(echo "$FILE_PATH" | sed 's|Sources/|Tests/|' | sed 's|\.swift$|Tests.swift|')
    if [ ! -f "$TEST_PATH" ]; then
        echo "⚠️  No test file found for $(basename "$FILE_PATH") (expected: $TEST_PATH)"
    fi
fi

exit $EXIT_CODE
