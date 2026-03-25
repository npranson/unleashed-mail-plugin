# UnleashedMail — Claude Code Plugin v2.1.1

A multi-agent development plugin for **UnleashedMail**, a native macOS 15+ email client supporting Gmail and Microsoft Graph, built with Swift 6, SwiftUI, AppKit, WKWebView, GRDB.swift (SQLCipher), and MVVM architecture.

**15 agents · 10 skills · 3 commands**

## Installation

```bash
# From GitHub
/plugin install https://github.com/npranson/unleashed-mail-plugin

# Local development
claude --plugin-dir /path/to/unleashed-mail-plugin
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          SLASH COMMANDS                                      │
│    /brainstorm → /implement → /pr-review                                     │
└────────┬────────────────────┬───────────────────────────┬────────────────────┘
         │                    │                           │
         ▼                    ▼                           ▼
 ┌────────────────┐  ┌────────────────┐  ┌──────────────────────────────────────┐
 │    PLANNER     │  │    CODING      │  │      REVIEW ORCHESTRATOR             │
 │                │  │    AGENTS      │  │      (swift-reviewer)                │
 │ modern-        │  │                │  │                                      │
 │ standards-     │  │ db-engineer    │  │  ┌─ security-reviewer                │
 │ planner        │  │ logic-engineer │  │  ├─ concurrency-reviewer             │
 │ (Context7 +    │  │ ui-engineer    │  │  ├─ ux-perf-reviewer                 │
 │  web search)   │  │                │  │  ├─ accessibility-auditor            │
 │                │  │                │  │  └─ provider parity audit            │
 └────────────────┘  └────────────────┘  └──────────────────────────────────────┘
         │                    │                           │
         ▼                    ▼                           ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  jira-manager (ALWAYS parallel — ticket creation, updates, Epic linking)     │
 └──────────────────────────────────────────────────────────────────────────────┘
         │                    │                           │
         ▼                    ▼                           ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                     AUTO-TRIGGERING SKILLS                                   │
 │  swift-tdd · swiftui-mvvm · grdb-patterns · macos-debugging ·               │
 │  webview-composer · keychain-security · gmail-api · graph-api ·             │
 │  provider-parity · agent-orchestration                                      │
 └──────────────────────────────────────────────────────────────────────────────┘
```

## Agents (15)

### Review Agents (run in parallel via orchestrator)

| Agent | Specialization |
|---|---|
| `swift-reviewer` | **Orchestrator** — spawns all 4 reviewers, runs parity audit, synthesizes unified verdict |
| `security-reviewer` | Credential exposure, OAuth/MSAL flaws, WKWebView injection, CI pipeline, entitlements, SQLCipher |
| `concurrency-reviewer` | Data races, actor isolation, async/await, GRDB threading, deprecated APIs (Swift 6 enforced) |
| `ux-perf-reviewer` | Main-thread responsiveness, SwiftUI rendering, query perf, perceived speed, error UX |
| `accessibility-auditor` | VoiceOver, keyboard nav, Dynamic Type, color contrast, focus management, dual-impl a11y parity |

### Coding Agents (invoked per-layer during implementation)

| Agent | Domain |
|---|---|
| `db-engineer` | GRDB 7+ schema, SQLCipher, migrations (CRITICAL/DEFERRABLE), Record types, async observation |
| `logic-engineer` | Service protocols, Gmail + Graph impls, ViewModels, AI pipeline routing, sync, mocks |
| `ui-engineer` | SwiftUI views (macOS 15+), AppKit bridging, WKWebView composer, a11y, dual-impl updates |
| `ai-engineer` | GARI AI pipeline — HTTPBasedAIProvider, ToolRegistry, PromptRegistry, AISafetyPipeline, AIAgentPipeline |

### Stakeholder Persona Agents (used during brainstorming)

| Agent | Perspective |
|---|---|
| `smb-entrepreneur` | SMB founder (15-person firm, 150 emails/day) — evaluates speed, workflow, cost, keyboard-first UX |
| `enterprise-stakeholder` | IT director (500-5000 person org) — evaluates compliance, admin control, scale, SSO/MDM, security |

### Planning, Tracking & Diagnostic Agents

| Agent | Purpose |
|---|---|
| `modern-standards-planner` | Researches current best practices via Context7 (pre-loaded library IDs) + web search; creates planning docs |
| `jira-manager` | Ticket lifecycle — creation, Epic linking, milestone updates, follow-up tickets (uses Atlassian MCP) |
| `xcode-build-fixer` | Diagnoses and fixes Xcode/SPM/CI build failures |
| `graph-api-debugger` | Microsoft Graph / MSAL auth troubleshooting |

## Skills (10) — Auto-activate based on context

| Skill | Triggers When |
|---|---|
| `swift-tdd` | Implementing features, writing tests, refactoring |
| `swiftui-mvvm` | Building views, view models, navigation, state management |
| `grdb-patterns` | Database models, migrations, queries, observation |
| `macos-debugging` | Crashes, memory leaks, performance issues, build failures |
| `webview-composer` | Email composition UI, contenteditable, JS bridge code |
| `keychain-security` | OAuth tokens, credential storage, encryption |
| `gmail-api-integration` | Gmail email fetching, sending, labels, Pub/Sub, OAuth flows |
| `microsoft-graph-integration` | Outlook/M365 email, MSAL auth, Graph webhooks, delta queries |
| `provider-parity` | Any code touching provider-specific implementations or protocols |
| `agent-orchestration` | Coordinating multi-agent workflows, determining parallel execution strategy |

## Commands (3)

| Command | Usage |
|---|---|
| `/unleashed-mail:brainstorm` | Design feature → Context7 research → spec → plan document → Jira ticket |
| `/unleashed-mail:implement` | Plan → db → logic → ui (layered agents) → multi-agent review → Jira updates |
| `/unleashed-mail:pr-review` | All 4 reviewers + a11y + parity in parallel → unified verdict → Jira logged |

## Parallel Execution

Agents are designed for **flexible parallel execution** in any combination. The `agent-orchestration` skill defines dependency rules:

- **Always parallel**: All review agents run simultaneously. `jira-manager` runs alongside everything.
- **Layered coding**: `db-engineer` → `logic-engineer` → `ui-engineer` (chained by dependency, but each can parallelize with `jira-manager`)
- **Any subset**: Request any combination — "just run security and accessibility reviewers", "only the db-engineer", etc.
- **Reactive agents**: `xcode-build-fixer` and `graph-api-debugger` fire on demand, not as part of standard pipeline.

## Mandatory Processes (from project CLAUDE.md)

The plugin enforces these non-negotiable processes:

1. **Planning document** — `docs/planning/FEATURE_NAME_PLAN.md` for every feature (no exceptions)
2. **Context7 usage** — Mandatory for code generation, setup, config, API docs lookup
3. **Jira ticket hygiene** — Every change tracked, updated throughout, with Epic association
4. **Provider parity** — Gmail ↔ Graph implementations stay in sync
5. **Accessibility** — Every UI element gets a11y support (mandatory per CLAUDE.md)
6. **Security invariants** — SQLCipher encryption, Keychain-only tokens, `account_email` filtering, PIIRedactor, HTML sanitization
7. **SwiftLint compliance** — Fix violations when touching files (functions ≤50 lines, files ≤600 lines)
8. **Dual implementations** — Changes applied to both variants (native + WebKit compose, simple + full email detail, docked + floating AI)

## Environment Setup

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

The `.env` file is gitignored and will not be distributed with the plugin.

## Hooks

The plugin includes PostToolUse hooks that run automatically:

| Hook | Trigger | Behavior |
|---|---|---|
| `swift-lint-check.sh` | After Write/Edit | Syntax check, SwiftLint, `try!`/`as!` detection, token logging — **blocks on critical violations** |
| `swift-build-verify.sh` | After Bash | Detects build/test commands and reminds to verify results |

## Baked-In Knowledge

Agents come pre-loaded with Context7 research for the stack:

- **GRDB 7+**: Async read/write, `ValueObservation.trackingConstantRegion`, Swift 6 concurrency safety, `for try await` observation
- **SwiftUI macOS 15+**: `@Observable` + `@Environment`, `NavigationSplitView`, `ContentUnavailableView`, `@AccessibilityFocusState`, modern toolbar API
- **MSAL**: Public client desktop flow, silent/interactive acquisition, keychain access groups
- **Context7 library IDs**: Pre-resolved (`/groue/grdb.swift`, `/azuread/microsoft-authentication-library-for-objc`, `/websites/developer_apple_swiftui`, `/avdlee/swiftui-agent-skill`) — agents skip the resolve step

## License

MIT
