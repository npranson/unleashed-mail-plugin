#!/bin/bash
# Pre-commit checks: run linting, tests, and build verification
# Exits non-zero to BLOCK commits if critical issues are found
#
# This script targets the UnleashedMail Xcode project (NOT a SwiftPM package).
# In other repos it does PII scanning only and skips Swift-build/test gracefully.

echo "🔍 Running pre-commit checks..."

EXIT_CODE=0

# Detect whether we're in the UnleashedMail Xcode project
HAS_XCODEPROJ=false
if [ -d "Unleashed Mail.xcodeproj" ]; then
    HAS_XCODEPROJ=true
fi

# --- 1. SwiftLint check (Xcode project only) ---
if [ "$HAS_XCODEPROJ" = true ]; then
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
else
    echo "⏭️  Skipping SwiftLint (not in Unleashed Mail Xcode project)"
fi

# --- 2. Build check (Xcode project only) ---
if [ "$HAS_XCODEPROJ" = true ]; then
    echo "🔨 Running build check..."
    BUILD_OUTPUT=$(xcodebuild build \
        -scheme "Unleashed Mail" \
        -destination 'platform=macOS' \
        -quiet 2>&1)
    BUILD_EXIT=$?

    if [ $BUILD_EXIT -ne 0 ]; then
        echo "❌ Build failed:"
        echo "$BUILD_OUTPUT" | tail -30
        EXIT_CODE=1
    else
        echo "✅ Build succeeded"
    fi
else
    echo "⏭️  Skipping build check (not in Unleashed Mail Xcode project)"
fi

# --- 3. Test subset check (Xcode project only) ---
if [ "$HAS_XCODEPROJ" = true ]; then
    echo "🧪 Running test subset (Database + Mock)..."
    TEST_OUTPUT=$(xcodebuild test \
        -scheme "Unleashed Mail" \
        -destination 'platform=macOS' \
        -only-testing:"Unleashed MailTests/DatabaseTests" \
        -only-testing:"Unleashed MailTests/MockServicesTests" \
        -quiet 2>&1)
    TEST_EXIT=$?

    if [ $TEST_EXIT -ne 0 ]; then
        echo "❌ Tests failed:"
        echo "$TEST_OUTPUT" | tail -30
        EXIT_CODE=1
    else
        echo "✅ Tests passed"
    fi
else
    echo "⏭️  Skipping tests (not in Unleashed Mail Xcode project)"
fi

# --- 3b. Plugin self-validation (plugin repo only — COREDEV-2322 Phase 0) ---
# Runs when NOT in the Xcode app project, i.e. in the unleashed-mail plugin repo.
# Warn mode here (advisory, never blocks the commit); CI runs these in --strict.
if [ "$HAS_XCODEPROJ" = false ]; then
    # Resolve via the repo root so a symlinked git hook ($0 = the symlink) still finds
    # the validators (gemini PR #11); fall back to the script's own dir (NOT
    # dirname+/scripts, which would double to scripts/scripts).
    if REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
        SCRIPTS_DIR="$REPO_ROOT/scripts"
    else
        SCRIPTS_DIR="$(dirname "$0")"
    fi
    if [ -f "$SCRIPTS_DIR/validate-version-sync.sh" ]; then
        echo "🧩 Validating plugin version sync..."
        VERSION_SYNC_ENFORCE=warn bash "$SCRIPTS_DIR/validate-version-sync.sh" || true
    fi
    if [ -f "$SCRIPTS_DIR/validate-plugin-assembly.py" ] && command -v python3 >/dev/null; then
        echo "🧩 Validating plugin assembly (frontmatter + manifests)..."
        python3 "$SCRIPTS_DIR/validate-plugin-assembly.py" || true
    fi
fi

# --- 4. PII check in staged files (universal) ---
echo "🔒 Checking for PII in new/modified files..."
if command -v git >/dev/null; then
    # Use null-delimited paths so "Unleashed Mail/..." with embedded spaces survives.
    # `for file in $VAR` would split on the spaces and skip real project files.
    PII_PATTERNS=(
        "apikey\|api_key\|API_KEY"
        "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        "Bearer [A-Za-z0-9_-]\{20,\}"
        "sk-\|pk_\|secret"
    )

    while IFS= read -r -d '' file; do
        case "$file" in *.swift) ;; *) continue ;; esac
        [ -f "$file" ] || continue
        for pattern in "${PII_PATTERNS[@]}"; do
            if grep -n "$pattern" "$file" >/dev/null 2>&1; then
                echo "⚠️  Potential PII found in $file (pattern: $pattern)"
                echo "   Please review and use environment variables or secure storage"
            fi
        done
    done < <(git diff --cached --name-only -z --diff-filter=ACM)
fi

# --- Summary ---
if [ $EXIT_CODE -eq 0 ]; then
    echo "🎉 All pre-commit checks passed!"
else
    echo "❌ Pre-commit checks failed. Please fix the issues above."
fi

exit $EXIT_CODE
