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
    var gmailId: String
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
2. Use `Codable` for automatic column mapping — column names match property names.
3. Complex types (arrays, nested objects) stored as JSON columns with custom `Codable` conformance.
4. Set `databaseTableName` explicitly — do not rely on automatic naming.

## Migrations

Use `DatabaseMigrator` with versioned, **never-modified** migrations:

```swift
var migrator = DatabaseMigrator()

migrator.registerMigration("v1_createEmails") { db in
    try db.create(table: "email") { t in
        t.autoIncrementedPrimaryKey("id")
        t.column("gmailId", .text).notNull().unique()
        t.column("threadId", .text).notNull().indexed()
        t.column("subject", .text).notNull()
        t.column("sender", .text).notNull()
        t.column("snippet", .text).notNull().defaults(to: "")
        t.column("receivedAt", .datetime).notNull()
        t.column("isRead", .boolean).notNull().defaults(to: false)
        t.column("isStarred", .boolean).notNull().defaults(to: false)
        t.column("labelIds", .text).notNull().defaults(to: "[]")
    }
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
// Fetch all unread emails, newest first
let unread = try dbQueue.read { db in
    try Email
        .filter(Column("isRead") == false)
        .order(Column("receivedAt").desc)
        .fetchAll(db)
}
```

### Request types for observation

```swift
extension Email {
    static func inboxRequest() -> QueryInterfaceRequest<Email> {
        Email
            .filter(literal: "labelIds LIKE '%\"INBOX\"%'")
            .order(Column("receivedAt").desc)
    }
}
```

## Database Observation (ValueObservation)

For live UI updates, use `ValueObservation`:

```swift
let observation = ValueObservation.tracking { db in
    try Email.inboxRequest().fetchAll(db)
}

// In ViewModel
let cancellable = observation.start(in: dbQueue, onError: { error in
    // handle
}, onChange: { [weak self] emails in
    self?.messages = emails
})
```

### Observation Rules

1. Use `ValueObservation` for read-only UI bindings — not manual polling.
2. Store the cancellable and cancel it on deinit.
3. For write-heavy paths, use `.removeDuplicates()` to avoid excessive UI updates.

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
