#!/bin/bash
# Test runner script: run tests with coverage and reporting.
#
# This script is for **CI and manual invocation only** — NOT wired into the
# Bash PostToolUse hook. (Earlier versions of the plugin wired it as a hook,
# which caused the full test suite to run after every Bash command. Removed
# in v2.2.0.)
#
# Targets the UnleashedMail Xcode project (`.xcodeproj`), not a SwiftPM
# package. Uses xcodebuild test. Skips silently if invoked outside the
# project root.

set -uo pipefail

if [ ! -d "Unleashed Mail.xcodeproj" ]; then
    echo "ℹ️  test-runner.sh: not in UnleashedMail Xcode project root — skipping" >&2
    exit 0
fi

echo "🧪 Running UnleashedMail test suite..."

export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

# Result-bundle and coverage paths — configurable so the script works in
# environments where /tmp is unwritable (sandboxed CI, ephemeral runners)
TMPDIR_RESOLVED="${TMPDIR:-/tmp}"
RESULT_BUNDLE="${UNLEASHED_TEST_RESULTS:-${TMPDIR_RESOLVED}/UnleashedMail-TestResults.xcresult}"
COVERAGE_OUT="${UNLEASHED_COVERAGE_OUT:-${TMPDIR_RESOLVED}/UnleashedMail-coverage.txt}"

# Verify the result-bundle parent is writable; abort early with a useful error
# if not (avoids cryptic xcodebuild failures deep in the run)
RESULT_DIR=$(dirname "$RESULT_BUNDLE")
if [ ! -w "$RESULT_DIR" ]; then
    echo "❌ Result-bundle directory '$RESULT_DIR' is not writable." >&2
    echo "   Set UNLEASHED_TEST_RESULTS to a writable path." >&2
    exit 2
fi

TEST_CMD=(xcodebuild test
    -scheme "Unleashed Mail"
    -destination 'platform=macOS'
    -enableCodeCoverage YES
    -resultBundlePath "$RESULT_BUNDLE")

if [ "${CI:-}" = "true" ]; then
    TEST_CMD+=(-quiet)
fi

echo "Running: ${TEST_CMD[*]}"
"${TEST_CMD[@]}"
TEST_EXIT=$?

if [ $TEST_EXIT -eq 0 ]; then
    echo "✅ All tests passed"

    if [ -d "$RESULT_BUNDLE" ]; then
        echo "📊 Generating coverage report..."
        if xcrun xccov view --report "$RESULT_BUNDLE" > "$COVERAGE_OUT" 2>/dev/null; then
            if [ -s "$COVERAGE_OUT" ]; then
                echo "Coverage summary (first 20 lines):"
                head -20 "$COVERAGE_OUT"
            fi
        fi
    fi
else
    echo "❌ Tests failed with exit code $TEST_EXIT"
    echo "💡 Check the output above for failure details"
fi

exit $TEST_EXIT
