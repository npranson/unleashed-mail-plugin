---
description: Run a multi-agent code review on the current branch (security + concurrency + UX/perf + accessibility + parity)
allowed-tools: Read, Bash, Grep, Glob, Task
disable-model-invocation: true
---

# PR Review: $ARGUMENTS

## Step 1: Identify the Changeset

```bash
# Get the diff against the base branch
echo "=== Changed files ==="
git diff main...HEAD --name-only 2>/dev/null || git diff HEAD~1 --name-only

echo ""
echo "=== Diff stats ==="
git diff main...HEAD --stat 2>/dev/null || git diff HEAD~1 --stat
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
5. Run **provider parity audit** — checks Gmail ↔ Graph implementation symmetry
6. Spawn **`jira-manager`** — logs the review on the corresponding ticket

All six streams run in parallel and produce independent reports.

The orchestrator synthesizes them into a unified review with deduplicated findings,
a consolidated issue table, and a single verdict.

## Step 3: Run the Test Suite

While the review agents work:

```bash
# Full test run
swift test 2>&1 | tail -40

# Check for test coverage of changed files
echo "=== Changed source files without test coverage ==="
for f in $(git diff main...HEAD --name-only 2>/dev/null | grep "^Sources/.*\.swift$"); do
    test_path=$(echo "$f" | sed 's|Sources/|Tests/|' | sed 's|\.swift$|Tests.swift|')
    [ -f "$test_path" ] || echo "⚠️  $f → missing $test_path"
done
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
| parity-audit | ✅/⚠️ | X blockers, Y warnings |

### [Full unified review from swift-reviewer orchestrator]

### Test Coverage Assessment
[Your analysis of test coverage gaps]

### Final Verdict: [APPROVE / REQUEST CHANGES / NEEDS DISCUSSION]
```

If $ARGUMENTS includes a PR number or URL, offer to post the review as a
GitHub PR comment via `gh pr review`.
