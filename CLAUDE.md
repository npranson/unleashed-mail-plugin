# UnleashedMail Development Plugin

You are working on **UnleashedMail**, a native macOS email client.

## Tech Stack

- **Language**: Swift 6.0+ (Swift 6 concurrency safety enforced)
- **UI**: SwiftUI + AppKit (hybrid), WKWebView for email composition & rendering
- **Database**: GRDB.swift 7+ with **SQLCipher (AES-256)** encryption — never unencrypted SQLite
- **Architecture**: MVVM with `@Observable` · Actors for thread safety · async/await over Combine
- **Platform**: macOS 15.0+ (Sequoia), ARM64 only
- **Auth**: Google OAuth 2.0 (manual), MSAL for Microsoft (automatic token cache), Keychain storage
- **APIs**: Gmail REST API with Pub/Sub push; Microsoft Graph Mail API with webhook subscriptions / delta queries
- **AI**: Multi-provider AI agent (GARI) with `HTTPBasedAIProvider`, `ToolRegistry`, `PromptRegistry`, `AISafetyPipeline`
- **CI**: GitHub Actions (Xcode 16.3+, Swift 6.1 toolchain), Xcode Cloud
- **Lint**: SwiftLint (enforced — `.swiftlint.yml`)
- **Package Manager**: Swift Package Manager

## Source Layout

```
Unleashed Mail/Sources/
├── Components/     # Reusable UI components
├── Models/         # Data structures (Sendable structs)
├── Services/       # API clients, database, auth
│   ├── AI/         # AI agent stages and orchestration
│   ├── Database/   # Repositories, migrations, DatabaseService
│   ├── Drafting/   # ProofreadService, draft composition
│   └── Triage/     # Email triage and categorization
├── Utilities/      # Extensions, helpers, APIEndpoints.swift
├── ViewModels/     # @Observable classes with @MainActor
└── Views/          # SwiftUI views by feature
```

## Core Principles

- **Provider parity is mandatory**: any mail feature implemented for Gmail must have a Graph counterpart (or an explicit, tracked `// TODO: PARITY` stub), and vice versa. ViewModels never reference concrete provider types.
- Prefer value types (structs, enums) over reference types unless shared mutable state is required
- Use Swift concurrency (async/await, actors) — avoid raw GCD/DispatchQueue in new code
- All database access goes through GRDB's DatabaseQueue/DatabasePool — never raw SQLite, always SQLCipher-encrypted
- **Filter by `account_email`** — every database query must scope to account (prevents cross-account data leaks)
- WKWebView ↔ Swift communication uses WKScriptMessageHandler, not evaluateJavaScript fire-and-forget
- **Never evaluate JS while user is typing** — check `isUserTyping` flag before WebView operations
- Error handling must use typed Swift errors with `do-catch` + `Logger` — no `try?` silently swallowing
- **No PII in logs** — use `PIIRedactor` for email addresses, subjects, content
- Every public API surface gets documentation comments (`///`)
- Tests use XCTest; aim for red-green-refactor TDD when building new features
- **First emails within 3 seconds** — cache-first architecture, then API
- **Never block main thread** — all I/O via async/await
- **No work in SwiftUI `body`** — no networking, DB calls, or heavy computation

## Mandatory Processes

### Ask Before Modifying

- Xcode project structure, entitlements, or Info.plist
- App lifecycle, menus, toolbar, or keyboard shortcuts
- Authentication flows or token handling
- Adding frameworks, libraries, or SwiftPM dependencies

### Planning (No Exceptions)

Create `docs/planning/FEATURE_NAME_PLAN.md` for any feature, refactoring, or multi-step development.

### Context7 Usage (Mandatory)

When performing code generation, setup/installation steps, configuration instructions, or library/API documentation lookup — you **must** use Context7 MCP tools. Do not rely on prior knowledge.

### Jira Ticket Hygiene (Mandatory)

- Update corresponding Jira ticket with development notes and status changes throughout implementation — not just at the end
- If a fix or change has no existing Jira ticket, create one (Task or Bug) before starting work
- Associate new tickets with a parent Epic if one exists for the feature area
- Include in ticket updates: what was changed, key decisions made, files affected, follow-up work identified

### Parallel Operations (Preferred)

- Prefer parallel tool calls for independent operations
- When exploring a feature area, read related files (model, service, view, tests) simultaneously
- Agents should run in parallel when their outputs are independent

## Security (Non-Negotiable)

| Data | Storage | Never |
|------|---------|-------|
| OAuth tokens | Keychain | UserDefaults, files |
| API keys | Keychain | Source code, Config.json |
| Email database | SQLCipher (AES-256) | Unencrypted SQLite |
| Encryption key | Keychain (`let`) | `var`, re-derivation |

- Always sanitize HTML before WKWebView; preserve CID image refs first
- Never remove or weaken security measures (Keychain, HTML sanitization, encryption)

## Dual Implementations (Must Update Both)

Changes must be applied to both variants:
- **AI Agent (GARI):** Docked panel (`AskAIWindowContentView`) + Floating window (`AskAIView`)
- **Compose:** Native editor + WebKit editor
- **Email Detail:** `SimpleEmailWebView` + `EmailWebView`

## Database Migrations

Categorize as **CRITICAL** (runs at startup) or **DEFERRABLE** (background after UI loads). Default assumption: defer unless proven critical. Startup migrations block UI for 13+ seconds — deferring non-critical reduces launch to <2s.

## Code Style (SwiftLint Enforced)

- Explicit `internal`/`private` access control
- `@MainActor` on UI code, `Sendable` on data crossing boundaries
- `@Observable` over `ObservableObject` for new ViewModels
- One type per file; functions ≤40 lines (warning), ≤50 lines (error)
- Files >400 lines (warning), >600 lines (error) — split into `+Feature.swift` extensions
- Types ≤300 lines (warning), ≤500 lines (error)
- Logging: `Logger.debug("msg", category: .network)` — categories: `.network`, `.auth`, `.ui`, `.database`, `.storeKit`, `.ai`, `.general`
- **When touching a file with SwiftLint violations, fix them as part of the change**

## AI Architecture Standards

- **No manual URLSession in AI Providers** — inherit `HTTPBasedAIProvider`, override `prepareHeaders()`, `buildRequestBody()`, `parseResponse()`, `parseStreamChunk()`
- **Single dispatch path** — `ToolRegistry` is the ONLY mechanism for tool execution
- **No inline prompts** — all prompts in `PromptRegistry`, versioned for A/B testing
- **Unified safety pipeline** — all validation through `AISafetyPipeline`
- **`AIService` is deprecated** — route new AI functionality through `AIAgentPipeline`

## Service Initialization Order

```
DatabaseService → GmailService → AuthService → GmailService.setAuthService()
→ SearchService → ContactsService → AIService → PushNotificationService
```

## Testing

- Run tests before commits; new features require unit tests; bug fixes require regression tests
- Use mocks from `MockServices.swift`
- Test naming: `test_action_condition_expectedResult()`
- `KeychainManager` auto-uses in-memory store under XCTest — call `resetInMemoryStore()` in `tearDown()`

## Repository Conventions

- Branch naming: `feature/desc`, `fix/desc`, `claude/desc-sessionId`
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`)
