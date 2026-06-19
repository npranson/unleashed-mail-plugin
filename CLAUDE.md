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
- **AI**: Multi-provider AI agent (GARI) with `HTTPBasedAIProvider` (cloud) or `BaseAIProvider` (Apple Intelligence), `ToolRegistry`, `PromptRegistry`. `AISafetyPipeline` is **PLANNED, not yet shipped** — current safety is inline (`PIIRedactor`, `LLMInputSanitizer`).
- **CI**: GitHub Actions (Xcode 16.3+, Swift 6.1 toolchain), Xcode Cloud
- **Lint**: SwiftLint (enforced — `.swiftlint.yml`)
- **Project type**: Xcode project (`.xcodeproj`), package dependencies managed inside Xcode — **not** a SwiftPM package. Use `xcodebuild` (not `swift build`/`swift test`).

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

### Plan Review Gate (Mandatory before implementation)

Every plan or debug session must be reviewed by **both** Antigravity and Codex CLI before implementation begins:

- `/unleashed-mail:gemini-review` — uses `gemini-3.1-pro` via Antigravity CLI (`agy`)
- `/unleashed-mail:codex-review` — uses `codex exec -s read-only`

Both must produce APPROVE / APPROVE_WITH_NOTES before code edits start. Iterate (typically 2–6 rounds) until both converge. Diagnostic agents (`xcode-build-fixer`, `graph-api-debugger`) propose fixes for the user to apply — they don't gate auto-fixes since the user is in the loop.

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

## Path-Scoped Project Rules

The project loads `.claude/rules/*.md` automatically based on file path. When editing project files, the matching rule auto-loads — read it. Eight rules currently:

> Rule paths in `.claude/rules/*.md` use the project-rooted form `"Unleashed Mail/Sources/..."`.
> Globs match relative to the project root.

| Rule | When loaded (relative to project root) |
|------|-------------|
| `ai-architecture.md` | `Unleashed Mail/Sources/Services/AI/**`, `AIAgent*`, `ServiceContainer+Wiring*` |
| `api-endpoints.md` | `APIEndpoints*`, `*Service*`, `RateLimiter*`, `RetryPolicy*` |
| `code-style.md` | `**/*.swift` (always loaded) |
| `database.md` | `Unleashed Mail/Sources/Services/Database/**`, `*Migration*`, `*Repository*` |
| `provider-isolation.md` | `Gmail*`, `MicrosoftGraph*`, `AccountScoped*`, sync workers |
| `swift-regex-sendable.md` | `*Regex*`, `*Pattern*`, `PIIRedactor*` |
| `swiftui-views.md` | `Unleashed Mail/Sources/Views/**`, `Unleashed Mail/Sources/ViewModels/**`, `Unleashed Mail/Sources/Components/**` |
| `webview-editor.md` | `*WebView*`, `*EmailWeb*`, `HTML*` |

**Rule auto-load matches by filename, not content.** When extracting `+Feature.swift` files, preserve the parent type's name so the right rule continues to load.

## Service Resolution (Multi-Account)

- **Services obtain providers via `AccountScopedServiceProvider.activeService()`** — never reference `gmailService` or `microsoftGraphService` concretes in new service code
- Use `serviceProvider.gmailServiceGuarded()` for Gmail-only operations (throws if account is non-Google)
- Use `serviceProvider.validateSupported(.operation)` as a guard at the top of provider-specific methods
- **Views** resolve services via `@State` + `.task` + `.onChange` — **never** a computed property (TOCTOU race during account switches)

## Dual Implementations (Must Update Both)

Changes must be applied to both variants:
- **AI Agent (GARI):** Docked panel (`AskAIWindowContentView`) + Floating window (`AskAIView`)
- **Compose:** `NativeRichTextEditor` (macOS 26+) + `HTMLWebViewEditor` (macOS ≤25)
- **Email Detail:** `SimpleEmailWebView` (production) + `EmailWebView`

## Curator Design System

All views use Curator tokens, not hardcoded primitives. Reference: `docs/BRAND_STANDARDS.md`.

- Never hardcode fonts, colors, spacing, radii — use `CuratorTheme.*`, `Color.curator*`
- Sheets: `.curatorSheetBackground()` — never raw `.background()`
- Dividers: `CuratorDivider()` — never SwiftUI `Divider()`
- Selection rows: `CuratorRadioOption` — never hand-rolled selection cells
- Use `.foregroundStyle()` — `.foregroundColor()` is deprecated

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
- **When touching a file with SwiftLint violations, fix them as part of the change** — one exception: do **not** migrate legacy `NSRegularExpression` ("old regex") inline. All regex is moving to Swift `Regex`/`RegexBuilder` as a dedicated, tracked effort (see `.claude/rules/swift-regex-sendable.md`); piecemeal conversion risks Sendable-conformance regressions. If the `no_legacy_nsregex` rule flags such a site in a file you touch, suppress only that line with `// swiftlint:disable:next no_legacy_nsregex - <migration ticket>` — note the ` - ` rationale delimiter; a trailing `//` comment is parsed as bogus rule identifiers and fails `--strict`. (That rule is documented as a sample in the `swiftlint-config` skill but is **not yet enabled** in the app's `.swiftlint.yml` — rollout is tracked by the regex-migration epic.)

## AI Architecture Standards

- **HTTP providers (cloud LLMs)** inherit `HTTPBasedAIProvider`, override `prepareHeaders()`, `buildRequestBody()`, `parseResponse()`, `parseStreamChunk()` — no manual URLSession
- **On-device providers (Apple Intelligence)** inherit `BaseAIProvider` directly — they have no HTTP semantics. Project-sanctioned exception.
- **Single dispatch path** — `ToolRegistry` is the ONLY mechanism for tool execution
- **No inline prompts** — all prompts in `PromptRegistry`, versioned for A/B testing
- **Safety pipeline (transitional)** — `AISafetyPipeline` is **PLANNED, not yet shipped**. Until it ships, safety checks are inline (`PIIRedactor`, `LLMInputSanitizer`). New safety checks co-locate with existing inline validators and are documented for future migration. See `.claude/rules/ai-architecture.md` and COREDEV-833 audit finding SEC-4.
- **`AIService` is deprecated** — route new AI functionality through `AIAgentPipeline`. Do not add new methods to `AIService.swift`.

## Testing

- Run tests before commits with `xcodebuild test -scheme "Unleashed Mail" -destination 'platform=macOS'`
- New features require unit tests; bug fixes require regression tests
- Use mocks from `MockServices.swift`
- Test naming: `test_action_condition_expectedResult()`
- `KeychainManager` auto-uses in-memory store under XCTest (`TestEnvironment.isRunningTests`) — call `KeychainManager.resetInMemoryStore()` in `tearDown()`. Do not call `SecItem*` directly.
- Test databases: `DatabaseQueue` only (no `DatabasePool`), `kdf_iter=4000` for speed, `waitForInitialized()` calls `initializeDatabase()` directly to avoid MainActor starvation

## Repository Conventions

- **Branch naming**: `1.0X/COREDEV-XXXX-short-description` off the matching version branch (`1.0X.0000`); use the Epic ticket key when a branch covers multiple child tickets. Hotfixes off the version branch, merged to BOTH the version branch AND `main`
- **Versioning**: `MAJOR.MINORRELEASE.YYMMBB` per `docs/VERSIONING.md`. `MARKETING_VERSION` (e.g., `1.02`) is manual; `CURRENT_PROJECT_VERSION` (e.g., `1.02.260501`) has its `BB` byte **auto-bumped** by `scripts/bump-build-number.sh` (Scheme Pre-Action on Archive) and auto-committed by `scripts/post-archive-commit-bump.sh` (Post-Action). Current: `1.02.260501` (Beta).
- **Trunk**: `main` is the integration trunk
- **Commit messages**: `type(COREDEV-XXXX): description` — ticket is **mandatory**, not optional. Use the Epic ticket key when a commit spans multiple child tickets. Type prefixes: `feat`, `fix`, `chore`, `refactor`, `test`, `docs`
- **Build**: `xcodebuild -scheme "Unleashed Mail"` — quote the scheme name (it contains a space)
- **Source paths**: `Unleashed Mail/Sources/...` and `Unleashed MailTests/...` (also contain spaces; quote in shell)

## Cross-Agent Workflow Contracts

See [`AGENT_CONTRACTS.md`](AGENT_CONTRACTS.md) — defines the boundaries, handoffs, and shared conventions between agents (release/versioning, plan→implement, data→logic→ui handoff, AI pipeline ownership, code review, CI pinning, mandatory project gates, MCP tool prefixes).

When two agents disagree about a boundary, `AGENT_CONTRACTS.md` is the source of truth.
