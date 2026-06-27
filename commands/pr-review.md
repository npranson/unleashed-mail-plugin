---
description: Run a multi-agent code review on the current branch (security + concurrency + UX/perf + accessibility + AI-prompt-safety + parity)
allowed-tools: Read, Bash, Grep, Glob, Agent
disable-model-invocation: true
---

# PR Review: $ARGUMENTS

## Step 1: Identify the Changeset

```bash
# Base-branch detection per AGENT_CONTRACTS.md §1+§5 (matches swift-reviewer):
#   1. If on a 1.0X/feature-name branch, target the matching 1.0X.0000 version branch
#   2. Else fall back to `git merge-base $(current) origin/main`
detect_base() {
    local current prefix
    current=$(git rev-parse --abbrev-ref HEAD)
    prefix=$(echo "$current" | grep -oE '^1\.0[0-4]/' | tr -d '/')
    if [ -n "$prefix" ]; then
        if git rev-parse --verify "${prefix}.0000" >/dev/null 2>&1; then
            echo "${prefix}.0000"; return
        fi
        # Explicit refspec — bare `git fetch origin BRANCH` only writes
        # FETCH_HEAD, not refs/remotes/origin/BRANCH
        git fetch origin --quiet \
            "refs/heads/${prefix}.0000:refs/remotes/origin/${prefix}.0000" 2>/dev/null || true
        if git rev-parse --verify "origin/${prefix}.0000" >/dev/null 2>&1; then
            echo "origin/${prefix}.0000"; return
        fi
    fi
    git fetch origin --quiet \
        refs/heads/main:refs/remotes/origin/main 2>/dev/null || true
    if git merge-base "$current" origin/main >/dev/null 2>&1; then
        git merge-base "$current" origin/main
    else
        echo "main"
    fi
}
BASE_BRANCH=$(detect_base)
echo "Base: $BASE_BRANCH"

echo "=== Changed files ==="
git diff "$BASE_BRANCH"...HEAD --name-only 2>/dev/null || git diff HEAD~1 --name-only

echo ""
echo "=== Diff stats ==="
git diff "$BASE_BRANCH"...HEAD --stat 2>/dev/null || git diff HEAD~1 --stat
```

Categorize the changes:
- Database layer (models, migrations)
- Service/logic layer (providers, ViewModels, services)
- UI layer (views, components, WKWebView)
- Tests
- CI/pipeline
- Configuration

## Step 2: Launch the Multi-Agent Review

Invoke the **`swift-reviewer`** orchestrator agent. It will:

1. Spawn **`security-reviewer`** — scans for credential exposure, OAuth flaws,
   WKWebView injection, CI pipeline risks, entitlement issues
2. Spawn **`concurrency-reviewer`** — checks actor isolation, async/await correctness,
   GRDB threading, deprecated APIs, race conditions
3. Spawn **`ux-perf-reviewer`** — evaluates main-thread responsiveness, SwiftUI
   rendering efficiency, query performance, UX patterns
4. Spawn **`accessibility-auditor`** — VoiceOver, keyboard nav, Dynamic Type,
   dual-implementation a11y parity
5. Spawn **`prompt-review`** — AI prompt/call-site safety: jailbreak/injection surface,
   refusal paths, unsanitized ingress, tool scoping, PII-in-logs (static, read-only)
6. Run **provider parity audit** — checks Gmail ↔ Graph implementation symmetry
7. Spawn **`jira-manager`** — logs the review on the corresponding ticket

All seven streams run in parallel and produce independent reports.

The orchestrator synthesizes them into a unified review with deduplicated findings,
a consolidated issue table, and a single verdict.

## Step 3: Run the Test Suite

While the review agents work:

```bash
set -o pipefail   # without it, `| tail` returns 0 and masks a failing xcodebuild
# Full test run
xcodebuild test -scheme "Unleashed Mail" -destination 'platform=macOS' 2>&1 | tail -40
TEST_STATUS=$?   # capture immediately — the base-detection commands below clobber $?
[ "$TEST_STATUS" -eq 0 ] && echo "✅ tests passed" || echo "❌ tests FAILED (exit $TEST_STATUS) — resolve before merging"

# Re-detect base branch (each bash block is a fresh shell — can't rely on
# Step 1's variable surviving)
detect_base() {
    local current prefix
    current=$(git rev-parse --abbrev-ref HEAD)
    prefix=$(echo "$current" | grep -oE '^1\.0[0-4]/' | tr -d '/')
    if [ -n "$prefix" ]; then
        if git rev-parse --verify "${prefix}.0000" >/dev/null 2>&1; then
            echo "${prefix}.0000"; return
        fi
        # Explicit refspec — bare `git fetch origin BRANCH` only writes
        # FETCH_HEAD, not refs/remotes/origin/BRANCH
        git fetch origin --quiet \
            "refs/heads/${prefix}.0000:refs/remotes/origin/${prefix}.0000" 2>/dev/null || true
        if git rev-parse --verify "origin/${prefix}.0000" >/dev/null 2>&1; then
            echo "origin/${prefix}.0000"; return
        fi
    fi
    git fetch origin --quiet \
        refs/heads/main:refs/remotes/origin/main 2>/dev/null || true
    if git merge-base "$current" origin/main >/dev/null 2>&1; then
        git merge-base "$current" origin/main
    else
        echo "main"
    fi
}
BASE_BRANCH=$(detect_base)

# Check for test coverage of changed files
echo "=== Changed source files without test coverage ==="
while IFS= read -r -d '' f; do
    case "$f" in
        "Unleashed Mail/Sources/"*.swift)
            test_path=$(echo "$f" | sed 's|Unleashed Mail/Sources/|Unleashed MailTests/|;s|\.swift$|Tests.swift|')
            ;;
        *) continue ;;
    esac
    [ -f "$test_path" ] || echo "⚠️  $f → missing $test_path"
done < <(git diff -z "$BASE_BRANCH"...HEAD --name-only 2>/dev/null)
```

## Step 4: Compile the Final Report

Merge the orchestrator's unified review with the test coverage assessment:

```
## PR Review — UnleashedMail

**Branch**: [branch name]
**PR**: $ARGUMENTS
**Files Changed**: [count]
**Tests**: [pass/fail count]

### Review Agents
| Agent | Status | Findings |
|---|---|---|
| security-reviewer | ✅/⚠️ | X blockers, Y warnings |
| concurrency-reviewer | ✅/⚠️ | X blockers, Y warnings |
| ux-perf-reviewer | ✅/⚠️ | X blockers, Y warnings |
| accessibility-auditor | ✅/⚠️ | X blockers, Y warnings |
| prompt-review | ✅/⚠️ | X blockers, Y warnings |
| parity-audit | ✅/⚠️ | X blockers, Y warnings |

### [Full unified review from swift-reviewer orchestrator]

### Test Coverage Assessment
[Your analysis of test coverage gaps]

### Final Verdict: [APPROVE / REQUEST CHANGES / NEEDS DISCUSSION]
```

If $ARGUMENTS includes a PR number or URL, offer to post the review as a
GitHub PR comment via `gh pr review`.
