#!/bin/bash
# PostToolUse hook for Bash: detect test/build commands and verify results.
# Runs after Bash tool invocations to catch failed builds and test runs.

COMMAND="${CLAUDE_TOOL_ARG_command:-}"

# Only process swift build/test commands
case "$COMMAND" in
    *"swift build"*|*"xcodebuild"*"build"*)
        # Check if the build command was run and capture exit status
        # The hook runs AFTER the command, so we check the output
        if echo "$COMMAND" | grep -q "swift build\|xcodebuild.*build"; then
            echo "🔨 Build command detected — verify BUILD SUCCEEDED in the output above."
        fi
        ;;
    *"swift test"*)
        echo "🧪 Test run detected — verify all tests passed in the output above."
        echo "   If tests failed, fix the failures before proceeding."
        ;;
    *)
        # Not a build/test command — no action
        exit 0
        ;;
esac

exit 0
