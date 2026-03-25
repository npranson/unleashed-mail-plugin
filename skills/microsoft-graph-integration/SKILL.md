---
name: microsoft-graph-integration
description: >
  Microsoft Graph API integration patterns for UnleashedMail. Activates when working
  with Outlook/Microsoft 365 email fetching, sending, folder management, MSAL OAuth
  flows, Graph webhook subscriptions for push notifications, or any Microsoft
  identity/mail API interaction.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Microsoft Graph API Integration — UnleashedMail

## Overview

Microsoft Graph is the unified API for Microsoft 365 services. For UnleashedMail,
the primary surface is the **Mail API** (`/me/messages`, `/me/mailFolders`), with
**MSAL (Microsoft Authentication Library)** handling OAuth 2.0 and token management.

Base URL: `https://graph.microsoft.com/v1.0`

## OAuth 2.0 with MSAL

UnleashedMail uses the **public client (desktop)** flow via MSAL for macOS.

### Dependency

Add the MSAL package via SPM:

```swift
// Package.swift
.package(url: "https://github.com/AzureAD/microsoft-authentication-library-for-objc", from: "1.4.0")
```

### App Registration (Azure AD)

1. Register at https://entra.microsoft.com → App registrations
2. Platform: **macOS / iOS** (public client, redirect URI: `msauth.<bundle-id>://auth`)
3. API permissions:
   - `Mail.Read` — read user mail
   - `Mail.ReadWrite` — read/write (move, delete, flag)
   - `Mail.Send` — send on behalf of user
   - `offline_access` — refresh tokens
   - `User.Read` — basic profile info
4. These are **delegated** permissions (user-consented), not application-level.

### MSAL Configuration

```swift
import MSAL

struct MSALConfig {
    static let clientId = "<your-client-id>"
    static let authority = "https://login.microsoftonline.com/common"
    static let redirectUri = "msauth.com.unleashedservices.unleashedmail://auth"
    static let scopes = [
        "Mail.ReadWrite",
        "Mail.Send",
        "User.Read",
        "offline_access"
    ]
}

func createMSALApplication() throws -> MSALPublicClientApplication {
    let config = MSALPublicClientApplicationConfig(
        clientId: MSALConfig.clientId,
        redirectUri: MSALConfig.redirectUri,
        authority: try MSALAuthority(url: URL(string: MSALConfig.authority)!)
    )
    return try MSALPublicClientApplication(configuration: config)
}
```

### Interactive Sign-In

```swift
func signIn(from window: NSWindow) async throws -> MSALResult {
    let application = try createMSALApplication()
    let webviewParams = MSALWebviewParameters()
    let interactiveParams = MSALInteractiveTokenParameters(scopes: MSALConfig.scopes, webviewParameters: webviewParams)

    return try await withCheckedThrowingContinuation { continuation in
        application.acquireToken(with: interactiveParams) { result, error in
            if let result { continuation.resume(returning: result) }
            else { continuation.resume(throwing: error ?? GraphAPIError.authenticationFailed) }
        }
    }
}
```

### Silent Token Refresh

MSAL handles token caching and refresh internally. Always attempt silent acquisition first:

```swift
actor MSALTokenManager {
    private let application: MSALPublicClientApplication
    private var account: MSALAccount?

    func validAccessToken() async throws -> String {
        guard let account else { throw GraphAPIError.notSignedIn }

        let silentParams = MSALSilentTokenParameters(scopes: MSALConfig.scopes, account: account)

        return try await withCheckedThrowingContinuation { continuation in
            application.acquireTokenSilent(with: silentParams) { result, error in
                if let result {
                    continuation.resume(returning: result.accessToken)
                } else if let nsError = error as NSError?,
                          nsError.domain == MSALErrorDomain,
                          nsError.code == MSALError.interactionRequired.rawValue {
                    continuation.resume(throwing: GraphAPIError.interactionRequired)
                } else {
                    continuation.resume(throwing: error ?? GraphAPIError.tokenRefreshFailed)
                }
            }
        }
    }
}
```

### Key Difference from Gmail OAuth

| Aspect | Gmail | Microsoft Graph |
|---|---|---|
| Library | Manual OAuth 2.0 | MSAL SDK (handles cache + refresh) |
| Token storage | Keychain (manual) | MSAL keychain (automatic) |
| Redirect URI | `http://localhost:<port>` | `msauth.<bundle-id>://auth` |
| Refresh logic | Custom `TokenManager` actor | MSAL silent acquisition |
| Multi-tenant | N/A | `common` authority for personal + work |

## Mail API Endpoints

### List Messages

```
GET /me/messages?$top=50&$orderby=receivedDateTime desc
    &$select=id,subject,from,receivedDateTime,isRead,hasAttachments,bodyPreview
    &$filter=parentFolderId eq 'inbox'
```

Use `$select` to minimize payload — Graph returns all fields by default.

### Get Single Message

```
GET /me/messages/{id}?$select=id,subject,from,toRecipients,ccRecipients,body,receivedDateTime,isRead,hasAttachments,flag
```

Body is returned as HTML by default (`body.contentType: "html"`).

### Send Message

```
POST /me/sendMail
Content-Type: application/json

{
    "message": {
        "subject": "Hello",
        "body": { "contentType": "html", "content": "<p>Hi there</p>" },
        "toRecipients": [
            { "emailAddress": { "address": "recipient@example.com" } }
        ]
    },
    "saveToSentItems": true
}
```

### Move / Copy Message

```
POST /me/messages/{id}/move
Body: { "destinationId": "deleteditems" }
```

Common folder IDs: `inbox`, `drafts`, `sentitems`, `deleteditems`, `archive`, `junkemail`.

### Update Message (Mark Read, Flag, etc.)

```
PATCH /me/messages/{id}
Body: { "isRead": true }
```

### List Folders

```
GET /me/mailFolders?$top=100
```

### Attachments

```
GET /me/messages/{id}/attachments
```

For large attachments (>3MB), use upload sessions:

```
POST /me/messages/{id}/attachments/createUploadSession
```

## Push Notifications via Subscriptions

Graph uses **webhooks** (not Pub/Sub like Gmail). You need a publicly accessible HTTPS endpoint.

### Create Subscription

```
POST /subscriptions
{
    "changeType": "created,updated,deleted",
    "notificationUrl": "https://your-backend.com/api/graph-webhook",
    "resource": "/me/messages",
    "expirationDateTime": "2025-04-01T00:00:00Z",
    "clientState": "your-secret-validation-token"
}
```

### Subscription Lifecycle

- **Max expiration**: 10080 minutes (~7 days) for mail resources.
- **Renewal**: Must call `PATCH /subscriptions/{id}` before expiry. Set a timer at 80% of the TTL.
- **Validation**: Graph sends a validation token on creation — your endpoint must echo it back.

### Processing Notifications

Notifications contain only the resource ID — you must fetch the full message:

```swift
struct GraphNotification: Codable {
    let subscriptionId: String
    let changeType: String            // "created", "updated", "deleted"
    let resource: String              // e.g. "me/messages/{id}"
    let resourceData: ResourceData?
    let clientState: String

    struct ResourceData: Codable {
        let id: String
    }
}
```

### Alternative: Delta Queries (Polling)

If running without a backend webhook endpoint, use delta queries for incremental sync:

```
GET /me/mailFolders/inbox/messages/delta?$select=subject,from,receivedDateTime,isRead
```

Returns a `@odata.deltaLink` — store it and use on the next poll to get only changes.

```swift
struct DeltaSyncState: Codable {
    var deltaLink: String?
    var nextLink: String?
}

func incrementalSync(state: inout DeltaSyncState) async throws -> [GraphMessage] {
    let url = state.deltaLink ?? state.nextLink ?? initialDeltaURL
    let response = try await graphRequest(url: url)

    if let nextLink = response.nextLink {
        state.nextLink = nextLink
        // More pages — keep fetching
    }
    if let deltaLink = response.deltaLink {
        state.deltaLink = deltaLink
        state.nextLink = nil
        // Sync complete for now
    }
    return response.messages
}
```

### Gmail vs. Graph Push Comparison

| Aspect | Gmail | Microsoft Graph |
|---|---|---|
| Mechanism | Pub/Sub (GCP) | Webhooks (HTTPS endpoint) |
| Payload | historyId only | resource ID + changeType |
| Max TTL | 7 days | ~7 days (mail) |
| Offline fallback | history.list | delta queries |
| Backend needed? | GCP project | HTTPS endpoint (or use delta polling) |

## Pagination

Graph uses `@odata.nextLink` for pagination:

```swift
func fetchAllMessages(folder: String = "inbox") async throws -> [GraphMessage] {
    var messages: [GraphMessage] = []
    var url: String? = "/me/mailFolders/\(folder)/messages?$top=50&$orderby=receivedDateTime desc"

    while let currentURL = url {
        let response: GraphMessageListResponse = try await graphRequest(url: currentURL)
        messages.append(contentsOf: response.value)
        url = response.nextLink
    }
    return messages
}
```

## Rate Limits

- **Per-app**: 10,000 requests per 10 minutes
- **Per-mailbox**: 10,000 requests per 10 minutes
- Throttled responses return `429 Too Many Requests` with a `Retry-After` header.

```swift
func withGraphRetry<T>(maxAttempts: Int = 5, _ operation: () async throws -> T) async throws -> T {
    for attempt in 0..<maxAttempts {
        do {
            return try await operation()
        } catch let error as GraphAPIError where error.isThrottled {
            let retryAfter = error.retryAfterSeconds ?? Double(1 << attempt)
            try await Task.sleep(for: .seconds(retryAfter))
        }
    }
    return try await operation()
}
```

## Error Handling

```swift
enum GraphAPIError: Error {
    case notSignedIn
    case authenticationFailed
    case interactionRequired       // silent token failed, need interactive
    case tokenRefreshFailed
    case forbidden(message: String) // 403 — insufficient permissions
    case notFound(resource: String) // 404
    case throttled(retryAfter: Int?) // 429
    case serverError(code: Int)    // 5xx
    case networkError(underlying: Error)
    case decodingError(underlying: Error)

    var isThrottled: Bool {
        if case .throttled = self { return true }
        return false
    }

    var retryAfterSeconds: Double? {
        if case .throttled(let seconds) = self { return seconds.map(Double.init) }
        return nil
    }
}
```

## Shared Abstractions

To support both Gmail and Graph behind a common interface:

```swift
protocol MailProviderProtocol {
    func fetchInbox(pageToken: String?) async throws -> MailPage
    func fetchMessage(id: String) async throws -> MailMessage
    func send(_ draft: MailDraft) async throws
    func markRead(id: String) async throws
    func moveToTrash(id: String) async throws
    func archive(id: String) async throws
}

struct MailPage {
    let messages: [MailMessage]
    let nextPageToken: String?
}
```

Both `GmailMailProvider` and `GraphMailProvider` conform to this protocol, letting
ViewModels remain provider-agnostic.
