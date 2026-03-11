---
name: grdb-patterns
description: >
  GRDB.swift database patterns for UnleashedMail. Activates when working with
  database models, migrations, queries, or any SQLite/GRDB-related code.
  Covers Record types, migrations, associations, and observation.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# GRDB.swift Patterns — UnleashedMail

## Model Definitions

All database models use GRDB's Record protocols. Define models as structs:

```swift
import GRDB

struct Email: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var accountEmail: String
    var gmailId: String?
    var graphMessageId: String?
    var threadId: String
    var subject: String
    var sender: String
    var snippet: String
    var receivedAt: Date
    var isRead: Bool
    var isStarred: Bool
    var labelIds: [String] // stored as JSON

    static let databaseTableName = "email"

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}
```

### Rules for Models

1. Always implement `Identifiable` with `id: Int64?` for autoincrement primary keys.
2. Every model must include `accountEmail: String` for account scoping — queries without it risk cross-account data leaks.
3. Use `Codable` for automatic column mapping — column names match property names.
4. Complex types (arrays, nested objects) stored as JSON columns with custom `Codable` conformance.
5. Set `databaseTableName` explicitly — do not rely on automatic naming.
6. Provider-specific IDs (e.g., `gmailId`, `graphMessageId`) should be nullable since a record belongs to only one provider.

## Migrations

Use `DatabaseMigrator` with versioned, **never-modified** migrations:

```swift
var migrator = DatabaseMigrator()

migrator.registerMigration("v1_createEmails") { db in
    try db.create(table: "email") { t in
        t.autoIncrementedPrimaryKey("id")
        t.column("accountEmail", .text).notNull()
        t.column("gmailId", .text)
        t.column("graphMessageId", .text)
        t.column("threadId", .text).notNull().indexed()
        t.column("subject", .text).notNull()
        t.column("sender", .text).notNull()
        t.column("snippet", .text).notNull().defaults(to: "")
        t.column("receivedAt", .datetime).notNull()
        t.column("isRead", .boolean).notNull().defaults(to: false)
        t.column("isStarred", .boolean).notNull().defaults(to: false)
        t.column("labelIds", .text).notNull().defaults(to: "[]")
    }
    // Composite index for account-scoped queries ordered by date
    try db.create(
        index: "idx_email_accountEmail_receivedAt",
        on: "email",
        columns: ["accountEmail", "receivedAt"]
    )
}

migrator.registerMigration("v2_addAttachmentsTable") { db in
    try db.create(table: "attachment") { t in
        t.autoIncrementedPrimaryKey("id")
        t.belongsTo("email", onDelete: .cascade).notNull()
        t.column("filename", .text).notNull()
        t.column("mimeType", .text).notNull()
        t.column("size", .integer).notNull()
    }
}
```

### Migration Rules

1. **NEVER modify an existing migration.** Always add a new one.
2. Name migrations with a version prefix: `v1_`, `v2_`, etc.
3. Always specify `.notNull()` and `.defaults(to:)` where appropriate.
4. Foreign keys use `.belongsTo()` with explicit `onDelete` behavior.

## Query Patterns

### Simple fetches

```swift
// Fetch all unread emails for an account, newest first
let unread = try dbQueue.read { db in
    try Email
        .filter(Column("accountEmail") == accountEmail)
        .filter(Column("isRead") == false)
        .order(Column("receivedAt").desc)
        .fetchAll(db)
}
```

> **Mandatory**: Every query MUST filter by `accountEmail` to prevent cross-account data leaks.

### Request types for observation

```swift
extension Email {
    static func inboxRequest(accountEmail: String) -> QueryInterfaceRequest<Email> {
        Email
            .filter(Column("accountEmail") == accountEmail)
            .filter(literal: "labelIds LIKE '%\"INBOX\"%'")
            .order(Column("receivedAt").desc)
    }
}
```

## Database Observation (ValueObservation)

For live UI updates, use `ValueObservation`. Prefer the modern GRDB 7+ async `for try await` pattern:

```swift
// In ViewModel — modern GRDB 7+ async observation (preferred)
func startObserving(accountEmail: String) async {
    let observation = ValueObservation.tracking { db in
        try Email.inboxRequest(accountEmail: accountEmail).fetchAll(db)
    }
    do {
        for try await emails in observation.values(in: dbQueue) {
            self.messages = emails
        }
    } catch {
        Logger.debug("Observation failed: \(error)", category: .database)
    }
}
```

Callback-based alternative (legacy, use only when async context is unavailable):

```swift
let observation = ValueObservation.tracking { db in
    try Email.inboxRequest(accountEmail: accountEmail).fetchAll(db)
}

let cancellable = observation.start(in: dbQueue, onError: { error in
    // handle
}, onChange: { [weak self] emails in
    self?.messages = emails
})
```

### Observation Rules

1. **Prefer the async `for try await` pattern** (GRDB 7+) — it integrates naturally with Swift concurrency and structured task cancellation.
2. Use `ValueObservation` for read-only UI bindings — not manual polling.
3. When using the callback-based API, store the cancellable and cancel it on deinit.
4. For write-heavy paths, use `.removeDuplicates()` to avoid excessive UI updates.

## DatabaseQueue vs DatabasePool

- **DatabaseQueue**: Use for single-writer scenarios (current default for UnleashedMail).
- **DatabasePool**: Use if you need concurrent reads while writing. Requires WAL mode.

Stick with `DatabaseQueue` unless profiling shows read contention.

## Testing

Always test database code with an in-memory `DatabaseQueue`:

```swift
func makeTestDB() throws -> DatabaseQueue {
    let db = try DatabaseQueue()
    var migrator = AppDatabase.migrator // reuse production migrations
    try migrator.migrate(db)
    return db
}
```
