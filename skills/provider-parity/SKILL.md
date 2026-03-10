---
name: provider-parity
description: >
  Mail provider parity enforcement for UnleashedMail. Activates automatically when
  working on Gmail-specific or Microsoft Graph-specific code, MailProviderProtocol
  implementations, sync services, or any code touching email fetching, sending,
  folder/label management, attachments, or push notification handling.
  Ensures both providers stay feature-aligned.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
---

# Provider Parity — Gmail ↔ Microsoft Graph

## Why This Exists

UnleashedMail supports two mail backends behind a shared protocol layer. Every time
you add, modify, or remove a capability in one provider, the other must be updated
to match — or the gap must be explicitly tracked. This skill fires automatically to
prevent silent parity drift.

## Shared Abstraction Layer

All provider-specific code lives behind these protocols. ViewModels and UI code
**never** reference `GmailMailProvider` or `GraphMailProvider` directly.

```swift
// MARK: - Core mail operations
protocol MailProviderProtocol {
    var providerType: MailProviderType { get }

    // Inbox & message list
    func fetchInbox(pageToken: String?) async throws -> MailPage
    func fetchMessage(id: String) async throws -> MailMessage
    func searchMessages(query: String, pageToken: String?) async throws -> MailPage

    // Actions
    func send(_ draft: MailDraft) async throws -> MailMessage
    func reply(to messageId: String, body: String) async throws -> MailMessage
    func forward(messageId: String, to: [String]) async throws -> MailMessage

    // State changes
    func markRead(id: String) async throws
    func markUnread(id: String) async throws
    func star(id: String) async throws
    func unstar(id: String) async throws
    func archive(id: String) async throws
    func moveToTrash(id: String) async throws
    func move(id: String, to folderId: String) async throws

    // Folders / Labels
    func fetchFolders() async throws -> [MailFolder]
    func createFolder(name: String, parentId: String?) async throws -> MailFolder

    // Attachments
    func fetchAttachment(messageId: String, attachmentId: String) async throws -> MailAttachment
    func uploadAttachment(_ data: Data, filename: String, mimeType: String, to draftId: String) async throws -> MailAttachment
}

// MARK: - Sync / push
protocol SyncServiceProtocol {
    func performInitialSync() async throws
    func performIncrementalSync() async throws
    func startPushNotifications() async throws
    func stopPushNotifications() async throws
    func renewPushSubscription() async throws
}

// MARK: - Auth
protocol AuthProviderProtocol {
    func signIn(from window: NSWindow) async throws
    func signOut() async throws
    func validAccessToken() async throws -> String
    var isSignedIn: Bool { get }
}

enum MailProviderType: String, Codable {
    case gmail
    case microsoftGraph
}
```

## Parity Mapping Reference

Use this table when implementing a feature to find the counterpart:

| Capability | Gmail Implementation | Graph Implementation |
|---|---|---|
| **Auth** | Manual OAuth 2.0 + custom `TokenManager` actor | MSAL `MSALPublicClientApplication` + silent/interactive |
| **Fetch inbox** | `GET /messages?labelIds=INBOX` | `GET /me/mailFolders/inbox/messages` |
| **Get message** | `GET /messages/{id}?format=full` → MIME decode | `GET /me/messages/{id}` → JSON with HTML body |
| **Send** | `POST /messages/send` with base64url RFC 2822 | `POST /me/sendMail` with JSON envelope |
| **Reply** | Build RFC 2822 with `In-Reply-To` + `References` headers | `POST /me/messages/{id}/reply` |
| **Forward** | Build RFC 2822 with forwarded MIME | `POST /me/messages/{id}/forward` |
| **Mark read** | `POST /messages/{id}/modify` remove `UNREAD` label | `PATCH /me/messages/{id}` set `isRead: true` |
| **Star** | `POST /messages/{id}/modify` add `STARRED` label | `PATCH /me/messages/{id}` set `flag.flagStatus: "flagged"` |
| **Archive** | Remove `INBOX` label | `POST /me/messages/{id}/move` to `archive` |
| **Trash** | `POST /messages/{id}/trash` | `POST /me/messages/{id}/move` to `deleteditems` |
| **Move** | `POST /messages/{id}/modify` add/remove labels | `POST /me/messages/{id}/move` to folder ID |
| **Folders** | `GET /labels` (flat, multi-assign) | `GET /me/mailFolders` (hierarchical, single-parent) |
| **Create folder** | `POST /labels` | `POST /me/mailFolders` (or child of parent) |
| **Attachments (small)** | Inline in multipart MIME (<5MB) | Inline in JSON (<3MB) |
| **Attachments (large)** | Multipart upload (<35MB) | Upload session (<150MB) |
| **Push** | Pub/Sub `watch()` → historyId | Webhook subscription → resource ID |
| **Incremental sync** | `GET /history?startHistoryId=` | `GET /me/mailFolders/inbox/messages/delta` |
| **Push renewal** | Every 7 days | Every ~2.9 days |
| **Pagination** | `pageToken` / `nextPageToken` | `@odata.nextLink` |
| **Batch** | Gmail batch API (multipart) | `POST /$batch` (JSON, max 20 requests) |
| **Search** | Gmail search syntax (`from:`, `subject:`, etc.) | `$filter` and `$search` OData parameters |
| **Rate limits** | 250 quota units/sec per user | 10,000 requests / 10 min per mailbox |

## Workflow: Implementing a New Capability

### Step 1: Protocol First

Add the method signature to the appropriate shared protocol (`MailProviderProtocol`, `SyncServiceProtocol`, or `AuthProviderProtocol`) **before** writing either implementation.

```swift
// Add to MailProviderProtocol
func snooze(id: String, until: Date) async throws
```

### Step 2: Implement the First Provider

Pick the provider you're most familiar with. Follow TDD (invoke `swift-tdd` skill).

### Step 3: Implement the Second Provider

**Before marking the task as done**, implement the counterpart. Use the mapping table above to find the equivalent API call.

If the second provider's API doesn't support the feature natively:
1. Check if it can be emulated (e.g., Gmail doesn't have native snooze — you could remove from inbox + schedule a re-label).
2. If it can't be emulated, add a stub with an explicit marker:

```swift
// GraphMailProvider.swift
func snooze(id: String, until: Date) async throws {
    // TODO: PARITY — Graph API does not support native snooze.
    // Tracked: https://github.com/npranson/UnleashedMail/issues/XXX
    throw MailProviderError.unsupportedOperation(provider: .microsoftGraph, operation: "snooze")
}
```

3. The `MailProviderError.unsupportedOperation` case lets the ViewModel gracefully disable the UI for that provider.

### Step 4: Shared Tests

For every protocol method, maintain parallel test cases:

```
Tests/
├── GmailTests/
│   └── GmailMailProviderTests.swift     ← tests with MockGmailAPI
├── GraphTests/
│   └── GraphMailProviderTests.swift     ← tests with MockGraphAPI
└── SharedTests/
    └── MailProviderParityTests.swift    ← tests that run against BOTH providers
```

The parity test file instantiates both providers with mocks and asserts identical behavior:

```swift
final class MailProviderParityTests: XCTestCase {
    let providers: [MailProviderProtocol] = [
        GmailMailProvider(api: MockGmailAPI()),
        GraphMailProvider(api: MockGraphAPI(), tokenManager: MockMSALTokenManager())
    ]

    func test_fetchInbox_returnsSameStructure() async throws {
        for provider in providers {
            let page = try await provider.fetchInbox(pageToken: nil)
            XCTAssertFalse(page.messages.isEmpty, "\(provider.providerType) inbox should return messages")
            for msg in page.messages {
                XCTAssertFalse(msg.subject.isEmpty, "\(provider.providerType) message should have subject")
                XCTAssertFalse(msg.sender.isEmpty, "\(provider.providerType) message should have sender")
                XCTAssertNotNil(msg.receivedAt, "\(provider.providerType) message should have date")
            }
        }
    }
}
```

### Step 5: Parity Audit Before Commit

Run this before committing any provider-related change:

```bash
# 1. Check protocol conformance — both providers compile
swift build 2>&1 | grep "does not conform to protocol" | head -10

# 2. Find TODO: PARITY markers
grep -rn "TODO: PARITY\|FIXME: PARITY" --include='*.swift' Sources/

# 3. Count public methods per provider (should be roughly equal)
echo "=== GmailMailProvider ==="
grep -c "func " Sources/**/GmailMailProvider.swift 2>/dev/null || echo "not found"
echo "=== GraphMailProvider ==="
grep -c "func " Sources/**/GraphMailProvider.swift 2>/dev/null || echo "not found"

# 4. Check for provider-specific types leaking outside the provider layer
grep -rn "GmailMailProvider\|GraphMailProvider\|MSALResult\|GmailAPI\." --include='*.swift' Sources/ViewModels/ Sources/Views/
```

Step 4 should return **zero results**. If a ViewModel or View references a concrete provider, that's a parity violation.

## Shared Error Type

Both providers map their errors to a common type:

```swift
enum MailProviderError: Error {
    case notAuthenticated
    case tokenExpired
    case interactionRequired                         // Graph-specific, but shared
    case permissionDenied(scope: String)
    case messageNotFound(id: String)
    case folderNotFound(id: String)
    case rateLimited(retryAfter: TimeInterval?)
    case serverError(code: Int, message: String)
    case networkError(underlying: Error)
    case unsupportedOperation(provider: MailProviderType, operation: String)
}
```

The `unsupportedOperation` case is the **only** acceptable way to express a parity gap at the protocol level. It must always include a tracking issue URL in the comment at the call site.

## Domain Model Normalization

Both providers must produce identical domain model structs:

```swift
struct MailMessage: Identifiable, Codable {
    let id: String                    // provider-native ID
    let threadId: String?             // Gmail: threadId; Graph: conversationId
    let subject: String
    let sender: String                // display name + email
    let recipients: [String]
    let bodyHTML: String              // both providers normalize to HTML
    let snippet: String               // preview text
    let receivedAt: Date
    var isRead: Bool
    var isStarred: Bool               // Gmail: STARRED label; Graph: flag.flagStatus
    let hasAttachments: Bool
    let folderIds: [String]           // Gmail: labelIds; Graph: [parentFolderId]
    let provider: MailProviderType    // which backend this came from
}
```

If a field has different semantics per provider, document the normalization in a comment on the mapping code — not on the model itself.

## Hard Rules

1. **Protocol-first, always.** Never add a public method to one provider without adding it to the protocol.
2. **No provider types in ViewModels.** `import` only the protocol and shared domain models.
3. **Every parity gap gets a tracking issue.** No orphaned `// TODO: PARITY` without a link.
4. **Tests run against both.** A feature isn't done until both mock providers pass.
5. **The reviewer will flag it.** The `swift-reviewer` agent treats missing parity as a 🔴 BLOCKER.
