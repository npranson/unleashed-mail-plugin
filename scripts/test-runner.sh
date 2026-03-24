#!/bin/bash
# Test runner script: run tests with coverage and reporting
# Used by hooks and CI

echo "🧪 Running UnleashedMail test suite..."

# Set up environment
export DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"

# Run tests with coverage
TEST_CMD="swift test --enable-code-coverage --parallel"

if [ "$CI" = "true" ]; then
    # In CI, be more verbose and generate reports
    TEST_CMD="$TEST_CMD --verbose"
fi

echo "Running: $TEST_CMD"
eval $TEST_CMD

TEST_EXIT=$?

if [ $TEST_EXIT -eq 0 ]; then
    echo "✅ All tests passed"

    # Generate coverage report if available
    if [ -d ".build/debug/codecov" ]; then
        echo "📊 Generating coverage report..."
        # Coverage data is in .build/debug/codecov/
        find .build/debug/codecov -name "*.json" -exec echo "Coverage file: {}" \;
    fi
else
    echo "❌ Tests failed with exit code $TEST_EXIT"
    echo "💡 Check the output above for failure details"
fi

exit $TEST_EXIT