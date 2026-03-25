---
name: swift-tdd
description: >
  Test-driven development workflow for Swift/XCTest. Activates when implementing
  new features, writing tests, or refactoring existing code in UnleashedMail.
  Enforces red-green-refactor discipline with GRDB-aware test patterns.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
---

# Swift TDD — Red/Green/Refactor for UnleashedMail

## When This Skill Applies

Use this workflow whenever you are:
- Implementing a new feature or user story
- Adding test coverage to existing code
- Refactoring code that already has (or should have) tests
- Fixing a bug (write a failing test that reproduces it first)

## Workflow

### Phase 1: RED — Write a Failing Test First

1. **Identify the behavior** you're implementing. State it as a single sentence:
   > "When [condition], [component] should [expected behavior]"

2. **Create or locate the test file** in the `Tests/` directory mirroring the source path.
   - Source: `Sources/UnleashedMail/ViewModels/InboxViewModel.swift`
   - Test: `Tests/UnleashedMailTests/ViewModels/InboxViewModelTests.swift`

3. **Write the minimal failing test**:
   ```swift
   import XCTest
   @testable import UnleashedMail

   @MainActor
   final class InboxViewModelTests: XCTestCase {
       func test_fetchEmails_updatesMessageList() async throws {
           // Arrange
           let sut = InboxViewModel(emailService: MockEmailService())

           // Act
           await sut.fetchEmails()

           // Assert
           XCTAssertFalse(sut.messages.isEmpty, "Messages should be populated after fetch")
       }
   }
   ```

4. **Run the test and confirm it fails**:
   ```bash
   swift test --filter InboxViewModelTests.test_fetchEmails_updatesMessageList 2>&1 | tail -20
   ```
   - If it does NOT fail, your test is not testing new behavior. Rewrite it.

### Phase 2: GREEN — Minimal Implementation

1. Write the **minimum code** to make the failing test pass.
2. Do NOT add extra logic, optimizations, or edge-case handling yet.
3. Run the single test again and confirm it passes.
4. Run the full test suite to ensure no regressions:
   ```bash
   swift test 2>&1 | tail -30
   ```

### Phase 3: REFACTOR — Clean Up

1. Look for duplication, unclear naming, or structural issues.
2. Extract helpers, rename for clarity, simplify conditionals.
3. Run the full test suite after every refactor step — tests must stay green.

## GRDB Test Patterns

For database-related tests, use an in-memory database:

```swift
import GRDB

func makeTestDatabase() throws -> DatabaseQueue {
    let dbQueue = try DatabaseQueue()
    try dbQueue.write { db in
        try db.create(table: "email") { t in
            t.autoIncrementedPrimaryKey("id")
            t.column("subject", .text).notNull()
            t.column("sender", .text).notNull()
            t.column("receivedAt", .datetime).notNull()
        }
    }
    return dbQueue
}
```

## Mock Patterns

Use protocol-based dependency injection for testability:

```swift
protocol EmailServiceProtocol: Sendable {
    func fetchInbox() async throws -> [Email]
    func send(_ draft: Draft) async throws
}

@MainActor
final class MockEmailService: EmailServiceProtocol, @unchecked Sendable {
    var stubbedEmails: [Email] = []
    var sendCallCount = 0

    func fetchInbox() async throws -> [Email] { stubbedEmails }
    func send(_ draft: Draft) async throws { sendCallCount += 1 }
}
```

## Hard Rules

- **NEVER skip the RED phase.** If you cannot write a failing test first, you don't understand the requirement well enough.
- **ONE behavior per test.** If you need "and" in the test name, split it.
- **No production code without a corresponding test.**
- **If a test is flaky, fix it immediately** — do not mark it as skipped.
