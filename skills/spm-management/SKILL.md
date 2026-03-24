# SPM Dependency Management — UnleashedMail

## Overview

UnleashedMail uses Swift Package Manager for all dependencies. Dependencies are
pinned to specific versions for reproducibility. Security audits run regularly.
No CocoaPods or Carthage.

## Package.swift Structure

```swift
// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "UnleashedMail",
    platforms: [
        .macOS(.v15)
    ],
    products: [
        .executable(name: "UnleashedMail", targets: ["UnleashedMail"])
    ],
    dependencies: [
        .package(url: "https://github.com/groue/GRDB.swift", from: "7.0.0"),
        .package(url: "https://github.com/AzureAD/microsoft-authentication-library-for-objc", from: "1.4.0"),
        .package(url: "https://github.com/realm/SwiftLint", from: "0.55.0")
    ],
    targets: [
        .executableTarget(
            name: "UnleashedMail",
            dependencies: [
                "GRDB",
                .product(name: "MSAL", package: "microsoft-authentication-library-for-objc")
            ]
        ),
        .testTarget(
            name: "UnleashedMailTests",
            dependencies: ["UnleashedMail"]
        )
    ]
)
```

## Dependency Management

### Adding Dependencies

1. **Research**: Check GitHub for activity, stars, maintenance
2. **Security**: Review for known vulnerabilities
3. **Compatibility**: Ensure macOS 15+ support
4. **Licensing**: Verify acceptable license

```bash
# Add dependency
swift package add https://github.com/example/package --from 1.0.0

# Update Package.resolved
swift package resolve
```

### Version Pinning

```swift
// ✅ Pinned to specific version
.package(url: "https://github.com/groue/GRDB.swift", .upToNextMinor(from: "7.0.0"))

// ✅ Exact version for security
.package(url: "https://github.com/AzureAD/microsoft-authentication-library-for-objc", exact: "1.4.0")
```

### Updating Dependencies

```bash
# Check for updates
swift package update

# Update specific package
swift package update GRDB

# Check resolved versions
cat Package.resolved
```

## Security Auditing

### Vulnerability Scanning

```bash
# Use swift-package-manager-security
swift package plugin security

# Or manual check
swift package show-dependencies
```

### Dependency Review

```yaml
# .github/workflows/security.yml
name: Security Audit
on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  push:
    paths:
      - 'Package.swift'
      - 'Package.resolved'

jobs:
  audit:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - name: Audit dependencies
        run: |
          swift package plugin security --output security-report.json
      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: security-audit
          path: security-report.json
```

## Build Optimization

### Binary Dependencies

For large dependencies, use binary targets:

```swift
.binaryTarget(
    name: "GRDB",
    url: "https://github.com/groue/GRDB.swift/releases/download/v7.0.0/GRDB.xcframework.zip",
    checksum: "abc123..."
)
```

### Conditional Dependencies

```swift
.target(
    name: "UnleashedMail",
    dependencies: [
        "GRDB",
        .product(name: "MSAL", package: "microsoft-authentication-library-for-objc"),
        // Debug-only dependencies
        .product(name: "SwiftLint", package: "SwiftLint", condition: .when(configuration: .debug))
    ]
)
```

## Testing Dependencies

### Test-Only Dependencies

```swift
.testTarget(
    name: "UnleashedMailTests",
    dependencies: [
        "UnleashedMail",
        .product(name: "SnapshotTesting", package: "swift-snapshot-testing")
    ]
)
```

### Mock Frameworks

For complex mocking, consider:

```swift
.package(url: "https://github.com/uber/mockolo", from: "2.0.0")
```

Generate mocks automatically:

```bash
mockolo --sourcelibs UnleashedMail --destination Mocks.swift
```

## CI/CD Integration

### Caching

```yaml
# .github/workflows/ci.yml
- name: Cache SPM
  uses: actions/cache@v4
  with:
    path: |
      .build/repositories
      .build/checkouts
      .build/artifacts
    key: ${{ runner.os }}-spm-${{ hashFiles('**/Package.resolved') }}
```

### Dependency Submission

For Mac App Store, declare dependencies:

```xml
<!-- Info.plist -->
<key>SPMDependencies</key>
<array>
    <string>GRDB</string>
    <string>MSAL</string>
</array>
```

## Troubleshooting

### Resolution Issues

```bash
# Clean and resolve
rm -rf .build
swift package resolve

# Check for conflicts
swift package show-dependencies
```

### Build Issues

```bash
# Clean build
swift package clean
swift build

# Check platform compatibility
swift package dump-package
```

### Version Conflicts

```swift
// Resolve conflicts by specifying exact versions
.package(url: "https://github.com/example/A", exact: "1.0.0"),
.package(url: "https://github.com/example/B", exact: "2.0.0")
```

## Maintenance

- **Weekly**: Run security audit
- **Monthly**: Review for updates
- **Quarterly**: Audit for unused dependencies

Remove unused dependencies:

```bash
swift package plugin unused-dependencies
```