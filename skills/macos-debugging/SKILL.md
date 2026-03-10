---
name: macos-debugging
description: >
  Systematic debugging methodology for macOS/Swift issues in UnleashedMail.
  Activates when encountering crashes, memory leaks, performance issues,
  Xcode build failures, or unexpected runtime behavior.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
---

# Systematic macOS Debugging — UnleashedMail

## The Four Phases

Never jump to a fix. Follow this sequence every time.

### Phase 1: INVESTIGATE — Understand the Symptom

1. **Reproduce reliably.** Can you trigger the bug on demand? Document exact steps.
2. **Gather evidence:**
   - Console output / os_log messages
   - Crash logs (~/Library/Logs/DiagnosticReports/)
   - Xcode debug navigator (CPU, memory, disk, network gauges)
3. **Identify the scope:** Is this UI, data layer, networking, or system integration?

### Phase 2: HYPOTHESIZE — Form a Theory

1. State your hypothesis as a falsifiable claim:
   > "The memory leak occurs because the WKWebView's navigation delegate holds a strong reference to the ComposeViewModel."
2. Identify the minimum test to confirm or deny the hypothesis.
3. **Do NOT write any fix code yet.**

### Phase 3: VERIFY — Confirm Root Cause

1. Use the appropriate diagnostic tool (see below).
2. If the hypothesis is wrong, return to Phase 2 with new evidence.
3. If three consecutive hypotheses fail, **STOP and escalate:**
   - Run the `swift-reviewer` agent for a second opinion on the code area.
   - Consider whether the bug is in a dependency (GRDB, WKWebView, Gmail API).

### Phase 4: FIX — Implement and Prove

1. Write a failing test that reproduces the bug (invoke the `swift-tdd` skill).
2. Implement the minimal fix.
3. Confirm the test passes AND the original reproduction steps no longer trigger the bug.
4. Run the full test suite.

## Diagnostic Tools Reference

### Memory Leaks

```bash
# Xcode Instruments via CLI
xcrun xctrace record --template 'Leaks' --launch -- /path/to/UnleashedMail.app
```

**Common UnleashedMail leak sources:**
- WKWebView delegate cycles (always use `[weak self]` in closures)
- Combine/observation cancellables not stored or cancelled
- Timer.publish without cancellation
- Strong reference cycles in async closures captured by actors

### Xcode Build Failures

```bash
# Clean build and capture full output
xcodebuild clean build \
  -scheme UnleashedMail \
  -destination 'platform=macOS' \
  2>&1 | tee /tmp/build-output.log

# Search for the first error
grep -n "error:" /tmp/build-output.log | head -10
```

**Common build issues:**
- Swift tools version mismatch (SPM packages requiring newer Swift than CI toolchain)
- Missing entitlements for Keychain, network, or sandbox
- Code signing identity not found in CI (GitHub Actions needs `CODE_SIGN_IDENTITY=""`)

### Runtime Crashes

```bash
# Symbolicate a crash log
atos -arch arm64 -o /path/to/UnleashedMail.app.dSYM/Contents/Resources/DWARF/UnleashedMail -l 0x100000000 0x<address>
```

**Common crash patterns:**
- Force unwrap on optional (`!`) — search for these: `grep -rn '!' --include='*.swift' Sources/`
- Main thread assertion from background async context
- GRDB `DatabaseError` from schema mismatch after migration failure

### Performance Issues

```bash
# Profile with Instruments Time Profiler
xcrun xctrace record --template 'Time Profiler' --launch -- /path/to/UnleashedMail.app
```

**Common perf issues:**
- GRDB queries without indexes on filtered columns
- SwiftUI view redraws caused by over-broad `@Observable` property changes
- WKWebView evaluateJavaScript calls on every keystroke in composer

### Network / Gmail API Issues

```bash
# Check OAuth token status
# Look for 401/403 in network logs
# Verify Pub/Sub subscription is active
```

**Common API issues:**
- OAuth token refresh race condition
- Pub/Sub watch() expiration (must renew every 7 days)
- Rate limiting (Gmail API quota: 250 units/second per user)

## Anti-Patterns — Do NOT Do These

- **Do not** add `try?` or `try!` to silence errors without understanding them.
- **Do not** add `DispatchQueue.main.async` as a band-aid for threading issues.
- **Do not** disable sandbox entitlements to "fix" permission errors.
- **Do not** delete and recreate the database to fix migration issues.
