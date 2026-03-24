#!/bin/bash
# Pre-commit checks: run linting, tests, and build verification
# Exits non-zero to BLOCK commits if critical issues are found

echo "🔍 Running pre-commit checks..."

EXIT_CODE=0

# --- 1. SwiftLint check ---
if command -v swiftlint >/dev/null; then
    echo "📏 Running SwiftLint..."
    LINT_OUTPUT=$(swiftlint --quiet 2>&1)
    LINT_EXIT=$?

    if [ $LINT_EXIT -ne 0 ]; then
        echo "❌ SwiftLint errors found:"
        echo "$LINT_OUTPUT"
        echo "💡 Run 'swiftlint --fix' to auto-fix some issues"
        EXIT_CODE=1
    else
        echo "✅ SwiftLint passed"
    fi
else
    echo "⚠️  SwiftLint not installed — install with 'brew install swiftlint'"
fi

# --- 2. Build check ---
echo "🔨 Running build check..."
BUILD_OUTPUT=$(swift build --quiet 2>&1)
BUILD_EXIT=$?

if [ $BUILD_EXIT -ne 0 ]; then
    echo "❌ Build failed:"
    echo "$BUILD_OUTPUT"
    EXIT_CODE=1
else
    echo "✅ Build succeeded"
fi

# --- 3. Test check (fast subset) ---
echo "🧪 Running test subset..."
# Run only critical tests that are fast
TEST_OUTPUT=$(swift test --filter "Database\|Mock" --quiet 2>&1)
TEST_EXIT=$?

if [ $TEST_EXIT -ne 0 ]; then
    echo "❌ Tests failed:"
    echo "$TEST_OUTPUT"
    EXIT_CODE=1
else
    echo "✅ Tests passed"
fi

# --- 4. PII check in new files ---
echo "🔒 Checking for PII in new/modified files..."
if command -v git >/dev/null; then
    # Check staged files for potential PII
    STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.swift$' || true)

    for file in $STAGED_FILES; do
        if [ -f "$file" ]; then
            # Check for hardcoded emails, API keys, etc.
            PII_PATTERNS=(
                "apikey\|api_key\|API_KEY"
                "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
                "Bearer [A-Za-z0-9_-]\{20,\}"
                "sk-\|pk_\|secret"
            )

            for pattern in "${PII_PATTERNS[@]}"; do
                if grep -n "$pattern" "$file" >/dev/null 2>&1; then
                    echo "⚠️  Potential PII found in $file (pattern: $pattern)"
                    echo "   Please review and use environment variables or secure storage"
                fi
            done
        fi
    done
fi

# --- Summary ---
if [ $EXIT_CODE -eq 0 ]; then
    echo "🎉 All pre-commit checks passed!"
else
    echo "❌ Pre-commit checks failed. Please fix the issues above."
fi

exit $EXIT_CODE