# Agent Workflow Contracts

This document defines the **contracts between agents** — the boundaries, handoffs, and shared
conventions that must stay aligned across every agent in this plugin. Individual agents reference
this file in their bodies; conflicts between agents and this document are bugs.

> **Why this exists:** without a shared contract, release-manager / docs-engineer / ci-engineer
> independently invent versioning, branching, and changelog conventions. Without fleet-wide rule
> adoption, code from logic-engineer hands off to ui-engineer using patterns that ui-engineer
> doesn't know about — fragmenting architectural rules at every boundary.

## 1. Release & Versioning Contract

**Owner:** `release-manager` · **Consumers:** `ci-engineer`, `docs-engineer`, `jira-manager`, `swift-reviewer`

### Version format: `MAJOR.MINORRELEASE.YYMMBB`

Authoritative source: [`docs/VERSIONING.md`](../Unleashed%20Mail/docs/VERSIONING.md) and `Config/Base.xcconfig`.

- `MAJOR` = breaking redesigns (e.g., `1`)
- `MINOR` = new features, backwards compatible (e.g., `0`)
- `RELEASE` ∈ {`0`=Pre-alpha, `1`=Alpha, `2`=Beta, `3`=RC, `4`=Release} — concatenated to MINOR (e.g., `02` = Minor 0, Beta)
- `YYMMBB` = year + month (UTC) + build counter within the month (e.g., `260501`)

Two xcconfig fields:
- `MARKETING_VERSION` = `MAJOR.MINORRELEASE` (manual, e.g., `1.02`)
- `CURRENT_PROJECT_VERSION` = full `MARKETING_VERSION.YYMMBB` (e.g., `1.02.260501`)

Current state: `1.02.260501` (Beta).

> **BB byte is automated.** [`scripts/bump-build-number.sh`](../Unleashed%20Mail/scripts/bump-build-number.sh)
> runs as a Scheme Pre-Action on Archive and increments BB; the Post-Action
> [`post-archive-commit-bump.sh`](../Unleashed%20Mail/scripts/post-archive-commit-bump.sh) commits
> and pushes the bump. `release-manager` MUST NOT manually edit BB — racing the script
> corrupts the `.bump-build-number.pending` sentinel.

### Branch convention

- **Feature branches**: `1.0X/feature-name` off the matching version branch (`1.0X.0000`)
  where `X` is the RELEASE stage digit (e.g., `1.02/coredev-1899-foo` for Beta features)
- **Hotfix branches**: off the version branch, merged to BOTH the version branch AND `main`
- **Trunk**: `main` is the integration trunk

> ❌ Never use `feature/desc`, `fix/desc`, or `claude/desc-sessionId` patterns. Those don't carry
> the version-stage signal needed for release routing.

### Commit format

Conventional commits with optional Jira ticket: `feat(COREDEV-1234): ...`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.

### Changelog ownership

`docs-engineer` writes/maintains `CHANGELOG.md`. `release-manager` triggers updates at version-bump
time; `jira-manager` provides ticket summaries.

### Mandatory release gates

A PR cannot merge to `main` (or to the version branch) without:
1. Build green (xcodebuild)
2. SwiftLint green (`swiftlint --strict`)
3. Tests green (xcodebuild test)
4. `swift-reviewer` verdict: APPROVE
5. Provider parity audit: PASS or `// TODO: PARITY` with tracked Jira ticket

## 2. Plan → Implement Contract

**Owner:** `modern-standards-planner` · **Consumers:** all implementation agents

### Plan creation

Every feature, refactor, or multi-step development requires `docs/planning/FEATURE_NAME_PLAN.md`.
Use the plugin's `/unleashed-mail:create-feature-plan` skill to scaffold.

### Plan review gate (mandatory)

Before any implementation begins:

1. Plan author runs `/unleashed-mail:gemini-review` (uses `gemini-3.1-pro` via Antigravity CLI `agy`)
2. Plan author runs `/unleashed-mail:codex-review` (uses `codex exec -s read-only`)
3. **Both must produce APPROVE / APPROVE_WITH_NOTES** before implementation starts
4. Iterate (typically 2–6 rounds) until both converge

### Diagnostic agent scope (`xcode-build-fixer`, `graph-api-debugger`)

Diagnostic agents do have `Write` and `Edit` tools — they apply **mechanical, low-risk fixes**
(e.g., correcting a typo'd import, adjusting a Bash invocation, generating a missing log
helper). They do NOT auto-fix changes that cross the project's "Ask before" boundaries:

| Edit | Diagnostic auto-applies | Diagnostic must Ask first |
|------|-------------------------|---------------------------|
| Local Bash command tweak | ✅ | — |
| Adding/changing Swift Package dependency | — | ✅ (xcode-build-fixer) |
| Editing `.entitlements` file | — | ✅ (graph-api-debugger, xcode-build-fixer) |
| Editing `Info.plist` / xcconfig | — | ✅ (xcode-build-fixer) |
| Editing auth/token-handling code | — | ✅ (graph-api-debugger) |
| Editing menus, toolbar, keyboard shortcuts | — | ✅ (any) |
| Disabling sandbox or weakening security | ❌ NEVER | ❌ NEVER |
| Generating a debug logger or diagnostic script | ✅ | — |

When in doubt, propose and wait. The user is always in the loop for diagnostic work — if the
fix is non-trivial, surface it.

### Implementation handoff

Implementation agents read the plan, work milestone-by-milestone, and update the plan's progress
log as they go. `jira-manager` mirrors plan state to Jira ticket status.

## 3. Data → Logic → UI Handoff Contract

**Owners:** `db-engineer` → `logic-engineer` → `ui-engineer`

### Database layer (db-engineer)

- All tables include `account_email` column (snake_case in SQL, `accountEmail` in Swift Record types)
- Every query filters by `account_email`
- Migrations categorized CRITICAL (rare) or DEFERRABLE (default)

### Service / ViewModel layer (logic-engineer)

- Services obtain providers via `AccountScopedServiceProvider.activeService()`. **Never** reference
  `gmailService` or `microsoftGraphService` concretes in new service code.
- `serviceProvider.gmailServiceGuarded()` for Gmail-only ops; `validateSupported(.operation)` as
  guard at top of provider-specific methods
- ViewModels: `@Observable @MainActor final class`, dependencies injected via `init`
- Concurrency caps: respect `APIRequestCoordinator.shared.maxConcurrentRequests = 4` —
  TaskGroup fan-out must not exceed this
- Provider-specific error types **never** leak across the ViewModel boundary

### View layer (ui-engineer)

- Resolve services via `@State` + `.task` + `.onChange` — **never** a computed property that
  calls `serviceProvider.activeService()` (TOCTOU race during account switches)
- Use Curator design system: `CuratorTheme.*`, `Color.curator*`, `CuratorDivider`,
  `.curatorSheetBackground()`. Never hardcode fonts/colors/spacing/radii.
- `.foregroundStyle()` (not deprecated `.foregroundColor()`)
- File-split access control: when extracting `+Feature.swift`, `private` becomes `internal` for
  members read across the split

## 4. AI Pipeline Ownership

**Owner:** `ai-engineer` · **Consumer:** `logic-engineer`

### Provider abstraction

- HTTP-based providers (cloud LLMs) inherit `HTTPBasedAIProvider`, override `prepareHeaders()`,
  `buildRequestBody()`, `parseResponse()`, `parseStreamChunk()`
- **On-device providers (Apple Intelligence) inherit `BaseAIProvider` directly** — they don't have
  HTTP semantics. This is an explicit project-sanctioned exception.

### Tool dispatch

- `ToolRegistry` is the **only** authorized tool execution path
- New tools implement `ToolHandlerProtocol`, registered with `ToolRegistry`
- No legacy `switch` blocks in `ExecutionService`

### Prompts

- All prompts live in `PromptRegistry`, versioned for A/B testing
- No inline prompt strings in services or ViewModels

### Safety pipeline

- **`AISafetyPipeline` is PLANNED — not yet implemented** (see project rule
  `.claude/rules/ai-architecture.md`). Until it ships, safety checks are applied **inline** via
  `PIIRedactor` and `LLMInputSanitizer`. New safety checks co-locate with existing inline
  validators and are documented for future migration.
- When `AISafetyPipeline` ships, all validation MUST flow through it (COREDEV-833 audit finding SEC-4)

### Routing

- All AI operations route through `AIAgentPipeline`
- `AIService` is deprecated — do **not** add new methods to `AIService.swift`

## 5. Code Review Pipeline

**Owner:** `swift-reviewer` · **Sub-reviewers:** `security-reviewer`, `concurrency-reviewer`, `ux-perf-reviewer`, `accessibility-auditor`

### Order of operations

1. `code-simplifier` runs first (clean before review)
2. `swift-reviewer` orchestrates: spawns 4 sub-reviewers in parallel + `jira-manager`
3. `swift-reviewer` runs provider parity audit itself
4. `swift-reviewer` synthesizes verdict
5. `jira-manager` logs verdict to Jira

### Base branch detection

`swift-reviewer` must detect the correct base — feature PRs target the matching `1.0X.0000` version
branch, not `main`. Default to `git merge-base $(git rev-parse --abbrev-ref HEAD) origin/main` only
as fallback.

### Path safety

All `xargs grep`, `find`, etc. must handle paths with spaces (`Unleashed Mail/...`). Use
null-delimited (`-print0` / `-0`) or quoted paths.

### Required checks

`swift-reviewer` must verify:
- Build green (`xcodebuild build`)
- SwiftLint green (`swiftlint --strict`)
- Tests green (`xcodebuild test`)
- All sub-reviewer verdicts collected and synthesized

## 6. CI / GitHub Actions Pinning

**Owners:** `ci-engineer`, `release-manager`, `security-reviewer`

### Single stance

Pin GitHub Actions to **commit SHAs**, not version tags. `security-reviewer` flags `@vN`-pinned
actions as 🟡 WARNING. `ci-engineer` and `release-manager` MUST use SHAs in workflow examples.

> A previous version of this plugin had `security-reviewer` flagging `@v*` while `ci-engineer`
> and `release-manager` used `@v*` in examples — and `security-reviewer`'s grep filter
> `grep -v "@v\|@main\|@sha"` actually excluded the violation. All three now align: SHAs only.

## 7. Mandatory Project Gates

The project's CLAUDE.md defines "Ask before" checkpoints. Agents that touch these areas must surface
the change for user approval, not auto-edit:

- Xcode project structure, entitlements, Info.plist
- App lifecycle, menus, toolbar, keyboard shortcuts
- Authentication flows or token handling
- Adding frameworks, libraries, or SwiftPM dependencies

Affected agents: `release-manager` (Info.plist, entitlements), `xcode-build-fixer` (dependencies),
`graph-api-debugger` (auth/token), `ui-engineer` (toolbar/keyboard).

## 8. Path-Scoped Rule System (`.claude/rules/`)

The project uses path-scoped rule files in `.claude/rules/*.md`. They auto-load based on file path
match. Agents that edit Swift files should be aware:

> Rule paths in `.claude/rules/*.md` use the project-rooted form `"Unleashed Mail/Sources/..."`.
> Globs match relative to the project root.

| Rule | Trigger paths (summary, relative to project root) |
|------|------------------------|
| `ai-architecture.md` | `Unleashed Mail/Sources/Services/AI/**`, `AIAgent*`, `ServiceContainer+Wiring*` |
| `api-endpoints.md` | `APIEndpoints*`, `*Service*`, `RateLimiter*`, `RetryPolicy*` |
| `code-style.md` | `**/*.swift` (always loaded) |
| `database.md` | `Unleashed Mail/Sources/Services/Database/**`, `*Migration*`, `*Repository*` |
| `provider-isolation.md` | `Gmail*`, `MicrosoftGraph*`, `AccountScoped*`, sync workers |
| `swift-regex-sendable.md` | `*Regex*`, `*Pattern*`, `PIIRedactor*` |
| `swiftui-views.md` | `Unleashed Mail/Sources/Views/**`, `Unleashed Mail/Sources/ViewModels/**`, `Unleashed Mail/Sources/Components/**` |
| `webview-editor.md` | `*WebView*`, `*EmailWeb*`, `HTML*` |

**Naming convention matters:** rule auto-load matches by filename, not content. When `code-simplifier`
extracts a `+Feature.swift` extension, it must preserve the parent type's naming convention so the
correct rules continue to load.

## 9. Tool Capability Floor

Each agent type has minimum tool requirements:

| Agent kind | Required tools |
|------------|---------------|
| Reviewers (read-only) | Read, Bash, Grep, Glob |
| Implementation | Read, Write, Edit, Bash, Grep, Glob |
| Orchestrator (swift-reviewer) | + Agent (subagent dispatch) |
| Diagnostic | + WebFetch (look up vendor docs mid-debug) |
| Planner (modern-standards-planner) | + WebFetch, WebSearch, Context7 MCP, Agent |
| Personas (read+search) | Read, Grep, Glob |
| Project (jira-manager) | + Atlassian MCP (multi-prefix whitelist) |

> The Claude Code subagent dispatcher tool is named `Agent`, **not** `Task`. `Task` is not a
> valid tool name in current Claude Code; older docs that say `Task` are stale.

## 10. MCP Tool Prefixes

MCP tool names are install-specific. Plugin agents that whitelist MCP tools should use a
**multi-prefix** whitelist to remain portable:

- Atlassian (jira-manager):
  - `mcp__claude_ai_Atlassian__*` (VSCode-shipped MCP)
  - `mcp__atlassian__*` (standalone MCP server)
  - `mcp__plugin_atlassian_atlassian__*` (Anthropic-marketplace plugin)
- Context7 (modern-standards-planner):
  - `mcp__claude_ai_Context7__*` (VSCode-shipped)
  - `mcp__context7__*` (standalone)
  - `mcp__plugin_context7_context7__*` (Anthropic-marketplace plugin)

If none of the prefixes resolve, agents must degrade gracefully (log to stdout for the user, do
not block implementation).

---

## Cross-references

> Cross-references below describe the **consumer project layout** (what UnleashedMail
> looks like when this plugin is loaded against it). Paths are repo-relative within the
> consumer's checkout — they are NOT clickable links from this plugin repo, since the
> plugin can be installed anywhere. Each agent reads these locations from inside the
> consumer's working tree at runtime.

- Project root CLAUDE.md: `<consumer-root>/CLAUDE.md` (top-level project rules)
- Project rules: `<consumer-root>/.claude/rules/*.md` (8 path-scoped rules — auto-load by file path)
- Nested CLAUDE.md (under `<consumer-root>/`):
  `Unleashed Mail/Sources/Services/CLAUDE.md`, `Unleashed Mail/Sources/Views/CLAUDE.md`,
  `Unleashed Mail/Sources/Models/CLAUDE.md`, `Unleashed Mail/Sources/Utilities/CLAUDE.md`,
  `Unleashed Mail/Sources/Components/CLAUDE.md`, `Unleashed Mail/Sources/ViewModels/CLAUDE.md`
- Review skills (v2.2.2+, shipped with plugin): `/unleashed-mail:gemini-review`,
  `/unleashed-mail:codex-review`. Skill sources at `skills/gemini-review/SKILL.md`,
  `skills/codex-review/SKILL.md`. The earlier workspace-only `.claude/prompts/*.md`
  files were retired when the skills moved into the plugin.
