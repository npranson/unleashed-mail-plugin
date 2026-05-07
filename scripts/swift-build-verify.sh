#!/bin/bash
# PostToolUse hook for Bash: detect test/build commands and verify results.
# Runs after Bash tool invocations to catch failed builds and test runs.
#
# UnleashedMail is an Xcode project — `xcodebuild` is the canonical tool.
# `swift build`/`swift test` are flagged as warnings (likely user error invoking
# the wrong tool against this xcodeproj).

COMMAND="${CLAUDE_TOOL_ARG_command:-}"

case "$COMMAND" in
    *"xcodebuild"*"build"*)
        echo "🔨 xcodebuild build detected — verify BUILD SUCCEEDED in the output above."
        ;;
    *"xcodebuild"*"test"*)
        echo "🧪 xcodebuild test detected — verify all tests passed in the output above."
        echo "   If tests failed, fix the failures before proceeding."
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
