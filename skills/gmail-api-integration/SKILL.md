---
name: gmail-api-integration
description: >
  Gmail REST API integration patterns for UnleashedMail. Activates when working
  with email fetching, sending, label management, OAuth flows, Pub/Sub push
  notifications, or any Google API interaction.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Gmail API Integration — UnleashedMail

## OAuth 2.0 Flow

UnleashedMail uses the installed application (desktop) OAuth flow:

1. Open system browser to Google's authorization endpoint.
2. User grants permission → redirect to `http://localhost:<port>` or custom URI scheme.
3. Exchange auth code for access + refresh tokens.
4. Store tokens via the `keychain-security` skill patterns.

### Token Lifecycle

```swift
struct OAuthTokens: Codable {
    var accessToken: String
    var refreshToken: String
    var expiresAt: Date
    var scope: String

    var isExpired: Bool { Date() >= expiresAt }
}
```

**Refresh logic:**
- Check `isExpired` before every API call.
- If expired, call `https://oauth2.googleapis.com/token` with the refresh token.
- If refresh fails with `invalid_grant`, the user must re-authenticate.
- **Serialize refresh calls** — use an actor to prevent concurrent refresh races.

```swift
actor TokenManager {
    private var tokens: OAuthTokens
    private var refreshTask: Task<OAuthTokens, Error>?

    func validAccessToken() async throws -> String {
        if !tokens.isExpired { return tokens.accessToken }

        if let existing = refreshTask {
            return try await existing.value.accessToken
        }

        let task = Task { try await performRefresh() }
        refreshTask = task
        defer { refreshTask = nil }
        tokens = try await task.value
        return tokens.accessToken
    }
}
```

## API Request Patterns

Base URL: `https://gmail.googleapis.com/gmail/v1/users/me`

### Fetch Message List

```
GET /messages?labelIds=INBOX&maxResults=50&pageToken={token}
```

Returns message IDs only. Follow up with batch get for full messages.

### Batch Get Messages

```
GET /messages/{id}?format=full
```

Use concurrent requests (max 5-10 parallel) with `TaskGroup`:

```swift
func fetchMessages(ids: [String]) async throws -> [GmailMessage] {
    try await withThrowingTaskGroup(of: GmailMessage.self) { group in
        for id in ids {
            group.addTask { try await self.fetchMessage(id: id) }
        }
        return try await group.reduce(into: []) { $0.append($1) }
    }
}
```

### Send Message

```
POST /messages/send
Content-Type: application/json
Body: { "raw": "<base64url-encoded RFC 2822 message>" }
```

Build the RFC 2822 message with proper MIME boundaries for attachments.

## Pub/Sub Push Notifications

Gmail pushes new message notifications via Google Cloud Pub/Sub.

### Setup

1. **Topic**: `projects/<your-gcp-project-id>/topics/gmail-push`
2. **Subscription**: Pull subscription for the backend, or push to a webhook endpoint.
3. **Watch request**:
   ```
   POST /watch
   Body: {
     "topicName": "projects/<your-gcp-project-id>/topics/gmail-push",
     "labelIds": ["INBOX"]
   }
   ```

### Renewal

- `watch()` expires after 7 days. Set a timer to renew at 6 days.
- The `historyId` in the watch response is the baseline for incremental sync.

### Incremental Sync

On push notification:

```
GET /history?startHistoryId={lastKnownHistoryId}&historyTypes=messageAdded,messageDeleted,labelAdded,labelRemoved
```

Process history records to update the local GRDB database incrementally.

## Rate Limits

- **Per-user quota**: 250 quota units/second
- `messages.list` = 5 units
- `messages.get` = 5 units
- `messages.send` = 100 units

Implement exponential backoff on 429 responses:

```swift
func withRetry<T>(maxAttempts: Int = 5, _ operation: () async throws -> T) async throws -> T {
    for attempt in 0..<maxAttempts {
        do {
            return try await operation()
        } catch let error as GmailAPIError where error.isRateLimited {
            let delay = Double(1 << attempt) + Double.random(in: 0...1)
            try await Task.sleep(for: .seconds(delay))
        }
    }
    return try await operation() // final attempt, let it throw
}
```

## OAuth Verification Note

- Development/testing: limited to 100 users without Google verification.
- Production: requires OAuth consent screen verification (submitted to Google).
- Sensitive scopes (`gmail.modify`, `gmail.send`) require additional review.

## Error Handling

Map Gmail API errors to typed Swift errors:

```swift
enum GmailAPIError: Error {
    case unauthorized           // 401 — token expired or revoked
    case forbidden              // 403 — insufficient scope
    case notFound(messageId: String) // 404
    case rateLimited            // 429
    case serverError(code: Int) // 5xx
    case networkError(underlying: Error)

    var isRateLimited: Bool {
        if case .rateLimited = self { return true }
        return false
    }
}
```
