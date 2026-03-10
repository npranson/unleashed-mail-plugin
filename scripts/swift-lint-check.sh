#!/bin/bash
# Post-write hook: check if modified file is Swift and run basic validation
# This hook runs after Claude writes or edits a file

FILE_PATH="${CLAUDE_TOOL_ARG_file_path:-${CLAUDE_TOOL_ARG_path:-}}"

# Only process .swift files
if [[ "$FILE_PATH" != *.swift ]]; then
    exit 0
fi

# Quick syntax check via swiftc (if available)
if command -v swiftc &> /dev/null; then
    # Parse-only check — fast, catches syntax errors
    RESULT=$(swiftc -parse "$FILE_PATH" 2>&1)
    if [ $? -ne 0 ]; then
        echo "⚠️  Swift syntax issue in $FILE_PATH:"
        echo "$RESULT" | head -5
    fi
fi

# Check for common anti-patterns
if grep -n 'try!' "$FILE_PATH" 2>/dev/null | grep -v "Tests/" > /dev/null; then
    echo "⚠️  Found 'try!' in production code: $FILE_PATH"
    grep -n 'try!' "$FILE_PATH" | grep -v "Tests/"
fi

if grep -n '![[:space:]]*$\|[^!=]![^=]' "$FILE_PATH" 2>/dev/null | grep -v "Tests/" | grep -v '//' > /dev/null; then
    # This is a rough heuristic — may have false positives
    :
fi

exit 0
