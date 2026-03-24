---
name: error-handling
description: >
  Error handling and logging patterns for UnleashedMail. Covers typed Swift errors,
  PII redaction, structured logging, recovery patterns, and testing error paths.
  Activates when implementing error handling, logging, or error recovery logic.
allowed-tools: Read, Write, Edit, Grep, Glob
---

# Error Handling and Logging Patterns — UnleashedMail

## Overview

UnleashedMail uses typed Swift errors with `do-catch` + `Logger` for all error handling.
No `try?` silently swallowing errors. All errors are logged with `PIIRedactor` for
email addresses, subjects, and content.

## Error Types

Define typed errors for each domain:

```swift
enum MailProviderError: Error, LocalizedError {
    case notAuthenticated
    case tokenExpired
    case interactionRequired
    case permissionDenied(scope: String)
    case messageNotFound(id: String)
    case rateLimited(retryAfter: TimeInterval?)
    case serverError(code: Int, message: String)
    case networkError(underlying: Error)
    case unsupportedOperation(provider: MailProviderType, operation: String)

    var errorDescription: String? {
        switch self {
        case .notAuthenticated:
            return "Not signed in to email account"
        case .tokenExpired:
            return "Authentication token has expired"
        case .interactionRequired:
            return "User interaction required for authentication"
        case .permissionDenied(let scope):
            return "Missing permission: \(scope)"
        case .messageNotFound(let id):
            return "Message not found: \(id)"
        case .rateLimited(let retryAfter):
            if let seconds = retryAfter {
                return "Rate limited. Try again in \(Int(seconds)) seconds"
            }
            return "Rate limited. Please wait before retrying"
        case .serverError(let code, let message):
            return "Server error (\(code)): \(message)"
        case .networkError(let underlying):
            return "Network error: \(underlying.localizedDescription)"
        case .unsupportedOperation(let provider, let operation):
            return "\(operation) is not supported by \(provider.rawValue)"
        }
    }
}
```

## Error Handling Patterns

### Service Layer

```swift
func fetchMessage(id: String) async throws -> MailMessage {
    do {
        let token = try await tokenManager.validAccessToken()
        let response = try await api.getMessage(id: id, token: token)
        return try response.toMailMessage()
    } catch let error as APIError {
        Logger.debug("API error fetching message \(id): \(error)", category: .network)
        throw MailProviderError(from: error)
    } catch {
        Logger.debug("Unexpected error fetching message \(id): \(error)", category: .network)
        throw MailProviderError.networkError(underlying: error)
    }
}
```

### ViewModel Layer

```swift
@Observable @MainActor
final class InboxViewModel {
    var state: ViewState<[MailMessage]> = .idle
    var error: MailProviderError?

    func fetchMessages() async {
        state = .loading
        do {
            let messages = try await emailService.fetchInbox()
            state = .loaded(messages)
            error = nil
        } catch let error as MailProviderError {
            state = .idle
            self.error = error
            Logger.debug("Failed to fetch inbox: \(error.localizedDescription)", category: .ui)
        } catch {
            state = .idle
            self.error = MailProviderError.networkError(underlying: error)
            Logger.debug("Unexpected error fetching inbox: \(error)", category: .ui)
        }
    }
}
```

### View Layer

```swift
struct InboxView: View {
    @State private var viewModel: InboxViewModel

    var body: some View {
        Group {
            switch viewModel.state {
            case .idle:
                EmptyStateView()
            case .loading:
                LoadingView()
            case .loaded(let messages):
                MessageListView(messages: messages)
            }
        }
        .alert(item: $viewModel.error) { error in
            Alert(
                title: Text("Error"),
                message: Text(error.localizedDescription),
                dismissButton: .default(Text("OK")) {
                    viewModel.error = nil
                }
            )
        }
    }
}
```

## Logging Patterns

### Logger Categories

```swift
extension Logger {
    static let network = Logger(subsystem: "com.unleashedservices.unleashedmail", category: "network")
    static let auth = Logger(subsystem: "com.unleashedservices.unleashedmail", category: "auth")
    static let ui = Logger(subsystem: "com.unleashedservices.unleashedmail", category: "ui")
    static let database = Logger(subsystem: "com.unleashedservices.unleashedmail", category: "database")
    static let storeKit = Logger(subsystem: "com.unleashedservices.unleashedmail", category: "storeKit")
    static let ai = Logger(subsystem: "com.unleashedservices.unleashedmail", category: "ai")
    static let general = Logger(subsystem: "com.unleashedservices.unleashedmail", category: "general")
}
```

### PII Redaction

Never log sensitive data directly:

```swift
// ❌ Bad — logs PII
Logger.debug("Sending email to \(recipient) with subject '\(subject)'", category: .network)

// ✅ Good — redacts PII
Logger.debug("Sending email to \(PIIRedactor.redactEmail(recipient)) with subject '\(PIIRedactor.redactSubject(subject))'", category: .network)
```

### PIIRedactor Implementation

```swift
struct PIIRedactor {
    static func redactEmail(_ email: String) -> String {
        let components = email.split(separator: "@")
        guard components.count == 2 else { return "[REDACTED]" }
        let local = String(components[0])
        let domain = String(components[1])
        let redactedLocal = String(local.prefix(2)) + String(repeating: "*", count: max(0, local.count - 2))
        return "\(redactedLocal)@\(domain)"
    }

    static func redactSubject(_ subject: String) -> String {
        guard subject.count > 10 else { return "[REDACTED]" }
        return String(subject.prefix(10)) + "..."
    }

    static func redactContent(_ content: String) -> String {
        guard content.count > 50 else { return "[REDACTED]" }
        return String(content.prefix(50)) + "..."
    }
}
```

## Recovery Patterns

### Retry Logic

```swift
func withRetry<T>(
    maxAttempts: Int = 3,
    operation: () async throws -> T
) async throws -> T {
    for attempt in 1...maxAttempts {
        do {
            return try await operation()
        } catch {
            if attempt == maxAttempts {
                throw error
            }
            Logger.debug("Operation failed (attempt \(attempt)), retrying: \(error)", category: .network)
            try await Task.sleep(for: .seconds(pow(2.0, Double(attempt - 1))))
        }
    }
    fatalError("Unreachable")
}
```

### Graceful Degradation

```swift
func loadMessages() async {
    do {
        // Try to load from API
        let messages = try await api.fetchMessages()
        self.messages = messages
    } catch MailProviderError.networkError {
        // Fall back to cached messages
        Logger.debug("Network unavailable, using cached messages", category: .network)
        self.messages = try await dbQueue.read { db in
            try MailMessage.fetchAll(db)
        }
    } catch {
        // Show error for other failures
        self.error = error
    }
}
```

## Testing Error Paths

```swift
func test_fetchMessages_handlesNetworkError() async throws {
    // Arrange
    mockService.shouldThrow = .networkError(underlying: URLError(.notConnectedToInternet))

    // Act
    await sut.fetchMessages()

    // Assert
    XCTAssertEqual(sut.state, .idle)
    XCTAssertNotNil(sut.error)
    XCTAssertEqual(sut.error, .networkError)
}
```