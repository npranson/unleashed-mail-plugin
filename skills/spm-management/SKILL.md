---
name: spm-management
description: >
  Xcode-managed Swift Package dependency management for UnleashedMail. Covers package
  resolution via Xcode, security auditing, version pinning in the project file, and
  CI integration. Activates when adding dependencies, updating packages, or managing
  package security.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Xcode Package Dependency Management — UnleashedMail

## Overview

UnleashedMail is an **Xcode project (`.xcodeproj`), not a SwiftPM package.** There is no
`Package.swift` at the project root. Package dependencies are managed inside Xcode and
resolved into the workspace at:

```
Unleashed Mail.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved
```

The `swift package …` CLI commands do **not** apply to this project. Use Xcode's package
management UI for adds/updates/removes; use `xcodebuild` (not `swift build`/`swift test`)
for builds and tests.

> **Ask-before checkpoint:** Adding, removing, or upgrading a package crosses the project's
> "Ask before" boundary (per CLAUDE.md). Surface the proposed change to the user before
> editing the project file.

## Inspecting Resolved Packages

```bash
# Show resolved package versions (read-only)
plutil -p "Unleashed Mail.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved" 2>/dev/null \
    | grep -B1 -A2 '"version"'

# Or convert to JSON for tooling
plutil -convert json -o - "Unleashed Mail.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
```

## Adding a Dependency

1. **Research**: GitHub activity, stars, maintenance, license
2. **Security**: scan for known CVEs (e.g., GitHub Dependabot, Snyk)
3. **Compatibility**: confirm macOS 15+ support and Swift 6 concurrency safety
4. **Surface to user**: this crosses Ask-before — confirm before adding
5. **Add via Xcode**: File → Add Package Dependencies… → enter the URL → choose the version rule (typically "Up to Next Major")
6. **Pin in Xcode** by selecting the resolved version once it lands; the version becomes part of `Package.resolved`
7. **Commit** `Unleashed Mail.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved` and the modified `project.pbxproj`

> Do NOT edit `Package.resolved` by hand. Xcode regenerates the file on every resolution
> and your edits will be overwritten.

## Version Pinning

Version rules live inside the xcodeproj's package references, not in a `Package.swift`.
The Xcode UI exposes them under **Project → Package Dependencies → (select package) →
Version**. Available rules:

| Rule | When to use |
|------|-------------|
| Up to Next Major (default) | Most dependencies — gets bug fixes and minor features |
| Up to Next Minor | Conservative; only patch-level updates |
| Range | Specific upper bound for a major version |
| Exact | Security-critical deps (MSAL, GRDB) where the project pins to a known-audited version |
| Branch | Development only — never ship a branch reference |
| Commit | Like Branch — never ship |

Project conventions:
- **MSAL**: typically pinned with `Up to Next Minor` or `Exact` because Microsoft's release
  cadence is fast and breaking changes are common
- **GRDB**: `Up to Next Major` from 7.0.0 — GRDB 7+ has the async APIs the project depends on
- **Other**: `Up to Next Major` unless audited otherwise

## Updating Dependencies

In Xcode: **File → Packages → Update to Latest Package Versions** (updates all)
or **right-click a package → Update Package** (single package).

> Xcode's "update single package" is more reliable than CLI alternatives. Don't try to
> update a single dependency by editing `Package.resolved` — Xcode will revert your edit.

After update:
1. Run full build (`xcodebuild build -scheme "Unleashed Mail"`) and full test suite
   (`xcodebuild test -scheme "Unleashed Mail" -destination 'platform=macOS'`)
2. Diff `Package.resolved` and review the new versions
3. Check release notes for breaking changes
4. Surface any major-version bumps to the user (Ask-before)

## Security Auditing

```bash
# Static audit — list all resolved versions
plutil -p "Unleashed Mail.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved" \
    | grep -E '"identity"|"version"' \
    | paste - -

# Cross-reference against advisories
# (use GitHub Dependabot, OSS Index, or Snyk via web)
```

GitHub's Dependabot supports SPM via `Package.resolved` — enable in repository settings
under **Security → Dependabot alerts**. The bot reads the workspace-internal
`Package.resolved` automatically when configured.

### CI security workflow (template)

```yaml
# .github/workflows/security.yml
name: Security Audit
on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  push:
    paths:
      - '**/Package.resolved'

jobs:
  audit:
    runs-on: macos-15
    steps:
      - uses: actions/checkout@<40-char-sha>  # actions/checkout v4.x — see AGENT_CONTRACTS.md §6
      - name: Inspect resolved packages
        run: |
          plutil -p "Unleashed Mail.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved" \
              | tee /tmp/packages.txt
      - uses: actions/upload-artifact@<40-char-sha>  # actions/upload-artifact v4.x
        with:
          name: package-audit
          path: /tmp/packages.txt
```

## CI/CD Integration

### Caching Xcode-resolved packages

CI should cache the workspace package state and the `~/Library/Developer/Xcode/DerivedData`
hot path. Cache key uses the workspace `Package.resolved`:

```yaml
- name: Cache Xcode SPM
  uses: actions/cache@<40-char-sha>  # actions/cache v4.x
  with:
    path: |
      ~/Library/Developer/Xcode/DerivedData/**/SourcePackages
    key: ${{ runner.os }}-xcspm-${{ hashFiles('**/swiftpm/Package.resolved') }}
```

### Dependency embedding

Xcode handles SPM embedding automatically during archive/export. No additional Info.plist
configuration is needed for Mac App Store submission.

## Troubleshooting

### Resolution failures

In Xcode:
- **File → Packages → Reset Package Caches** (purges resolved state)
- **File → Packages → Resolve Package Versions** (re-resolves from project rules)

CLI inspection only (cannot resolve from CLI for an xcodeproj):
```bash
set -o pipefail   # surface resolution failures through the `| tail` pipe
xcodebuild -resolvePackageDependencies -scheme "Unleashed Mail" \
    -destination 'platform=macOS' 2>&1 | tail -20
```

### Stale derived data

```bash
rm -rf ~/Library/Developer/Xcode/DerivedData/*
```

### Version conflicts between dependencies

If two transitive dependencies require incompatible versions of a third package, Xcode
surfaces the conflict in the project navigator. Resolution requires either:
- Pinning the offending package to a version both transitive deps accept, OR
- Upgrading one of the transitive consumers to a release that resolves the conflict

Don't try to force a resolution by editing `Package.resolved` — Xcode rejects manual edits.

## Maintenance Cadence

- **Weekly**: review Dependabot alerts (if enabled)
- **Monthly**: check for major-version updates in active deps
- **Quarterly**: audit unused dependencies — search the codebase for actual imports of each
  declared package; remove any with zero references (Ask-before)

```bash
# Find packages declared but not imported anywhere
# Read the workspace-internal Package.resolved (this is an Xcode project, not SwiftPM)
RESOLVED="Unleashed Mail.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
plutil -convert json -o - "$RESOLVED" 2>/dev/null \
    | python3 -c 'import json, sys; d = json.load(sys.stdin); [print(p["identity"]) for p in d.get("pins", d.get("object", {}).get("pins", []))]' \
    | while read -r pkg; do
        count=$(grep -rn "import $pkg" --include='*.swift' "Unleashed Mail/" 2>/dev/null | wc -l | tr -d ' ')
        echo "$pkg: $count imports"
      done
```
