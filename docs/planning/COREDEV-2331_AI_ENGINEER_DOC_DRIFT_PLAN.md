# COREDEV-2331 — Fix `ai-engineer` doc drift: `HTTPBasedAIProvider` / `AIToolDefinition` don't exist in source

**Ticket:** COREDEV-2331 (parent COREDEV-1834 *AI Architecture Consolidation*) · **Type:** Task · **Labels:** ai-architecture, docs, plugin, tech-debt
**Repo:** `unleashed-mail-plugin` (the plugin, NOT the Swift app) · **Branch:** `feat/COREDEV-2331-ai-engineer-doc-drift` off `origin/main` (`f276673`)
**Change class:** docs-only — no agent/skill/command count change, **no plugin version bump** (the 2.4.0 release is handled separately as the final run-through).

## 1. Problem (ground-truth verified)

Plugin docs describe the GARI provider + tool API using two symbols that **do not exist** anywhere in the Swift app source. An engineer — or the `ai-engineer` agent itself — following the docs literally writes non-compiling code. This is the exact "trust docs over source" failure the new `prompt-review` agent is designed to catch (it surfaced *during* prompt-review's own plan-review, when its draft inherited these bad symbols from `ai-engineer.md`).

Verification (grep over `/Users/nick/Downloads/Projects/Mail/**/*.swift`):
- `HTTPBasedAIProvider` → **0 source files**. It is a PLANNED Phase-3 consolidation target (tracked by **COREDEV-1837**, plan doc lives in the *app* repo). Today every cloud provider inherits `BaseAIProvider` + conforms to `AIProviderProtocol` and calls `URLSession` directly.
- `AIToolDefinition` → **0 source files**. Fabricated. The real tool model is `AITool` (schema) + `ToolHandlerProtocol` / `Set<AgentTool>` / `ToolCall`, dispatched via `ToolRegistry`.

## 2. Real API ground truth (source-cited — replacements must match these, not invent new drift)

Paths relative to `Unleashed Mail/Unleashed Mail/Sources/Services/AI/`:

- **Provider base/protocol:** `internal class BaseAIProvider` (`Providers/ProviderMetrics.swift:337`); `internal protocol AIProviderProtocol: Sendable` (`Providers/AIProviderProtocol.swift:17`) requires `complete(_:) async throws -> AIProviderResponse`, `stream(_:) -> AsyncThrowingStream<…>`, `completeStructured(_:)`.
- **Concrete providers:** `internal final class OpenAIProvider: BaseAIProvider, AIProviderProtocol, @unchecked Sendable` (`Providers/OpenAIProvider.swift:22`); same shape for `AnthropicProvider` (`:22`), `GeminiProvider` (`:23`). They hold `let session: URLSession` (default `NetworkService.shared.session`) and call it directly: `try await session.data(for:)` (`OpenAIProvider.swift:73`) / `session.bytes(for:)` (`:155`). The on-device `AppleIntelligenceProvider` conforms to `AIProviderProtocol` **without** `BaseAIProvider`.
- **Request assembly (per-provider, differing):** `private func buildRequestBody(from request: AIProviderRequest, streaming: Bool) -> [String: Any]` (OpenAI `:285` / Anthropic `:321`); `buildRequestBody(from:apiVersion:)` (Gemini `:194`). Returns a dict; there is **no** `prepareHeaders()/parseResponse()/parseStreamChunk()` override surface.
- **Tool model:** `internal struct AITool` (name, description, parameters: `[String: JSONValue]`) `AIProviderProtocol.swift:146`; `internal protocol ToolHandlerProtocol` (`ToolHandlerProtocol.swift:34`) with `var supportedTools: Set<AgentTool>` + `func execute(_ toolCall: ToolCall, context: WorkspaceContext, previousStepResults: [StepResult]) async throws -> ToolHandlerResult` + the shared helper `verifyEmailOwnership(emailId:accountEmail:databaseService:)` (`~:148`); `internal enum AgentTool: String` (`ExecutionPlan+Steps.swift:16`); `internal struct ToolCall { let tool: AgentTool; … }` (`ExecutionPlan.swift:168`).
- **Registry:** `internal final class ToolRegistry` (`ToolRegistry.swift:31`); registration is `func register(_ handler: any ToolHandlerProtocol)` — the handler declares `supportedTools` internally. Real example: `EmailActionToolHandler: ToolHandlerProtocol` with a `supportedTools` set and an `execute` switch (`EmailActionToolHandler.swift:22`); wired by `ToolRegistryFactory.create(deps:)`. There is **no** `ToolRegistry.shared.register(AIToolDefinition(...), handler: { … })` closure form.
- **PromptRegistry:** `internal actor PromptRegistry` (`Evaluation/PromptRegistry.swift:34`); `registerBody(_ body: String?, for id: PromptID)` (`:283`); `resolveBody(id: PromptID, fallback: () -> String) -> String` (`:291`, sanctioned fallback closures).
- **Pipeline:** `@MainActor internal final class AIAgentPipeline` singleton `.shared` (`AIAgentPipeline.swift:29`); empty `private init()` then `configure(aiService:databaseService:…)` (`:289`); entry `func execute(input: PipelineInput, configuration: PipelineConfiguration = .default) async -> PipelineResult` (`:346`). There is **no** `AIAgentPipeline(provider:toolRegistry:promptRegistry:)` initializer and **no** `execute(operation:accountEmail:)`.

## 3. Scope (decided with user)

- **Faithful + adjacent:** fix the two named symbols AND correct every adjacent fabricated example in `ai-engineer.md` (closure-handler registration, `AIAgentPipeline(provider:…)`/`execute(operation:…)`, test snippets) so **no example emits non-compiling code**. Where exact signatures would bloat the doc, examples are relabeled *illustrative* and grounded on real symbols.
- **CLAUDE.md edits are authorized** by the user for this PR (the ticket flags the "ask before modifying" gate; user said edit it in-PR).
- **Out of scope:** the Swift app itself; *implementing* `HTTPBasedAIProvider` (that's COREDEV-1837); the app-repo consolidation plan doc.

## 4. Drift-site inventory & fix (complete)

| File:line | Current (wrong) | Fix |
|---|---|---|
| `CLAUDE.md:14` | "GARI with `HTTPBasedAIProvider` (cloud) or `BaseAIProvider`…" | Reframe to reality: cloud providers inherit `BaseAIProvider` + `AIProviderProtocol`; `HTTPBasedAIProvider` is the PLANNED unified base (COREDEV-1837), not shipped. |
| `CLAUDE.md:164` | "HTTP providers inherit `HTTPBasedAIProvider`… no manual URLSession" | Split into **Target state (PLANNED, COREDEV-1837)** vs **Today** (BaseAIProvider+AIProviderProtocol, direct `URLSession` via `NetworkService.shared.session`). Mirror the existing `AISafetyPipeline` PLANNED caveat style already in this file. |
| `agents/ai-engineer.md:5` (frontmatter desc) | "HTTPBasedAIProvider implementations" | "AI provider implementations (`BaseAIProvider`/`AIProviderProtocol`)". |
| `agents/ai-engineer.md:28/32` (diagram) | "HTTPBasedAIProvider (cloud LLMs)" | "Cloud providers (`BaseAIProvider`+`AIProviderProtocol`) — unified `HTTPBasedAIProvider` base PLANNED". |
| `agents/ai-engineer.md:46-47` (rule 1) | present-tense HTTPBasedAIProvider rule | Target-state caveat + today's reality. |
| `agents/ai-engineer.md:62` (heading "### 1. AI Providers (HTTPBasedAIProvider)") | heading | "### 1. AI Providers (`BaseAIProvider` + `AIProviderProtocol`)". |
| `agents/ai-engineer.md:67-103` (code example) | `final class AnthropicProvider: HTTPBasedAIProvider { override prepareHeaders/buildRequestBody(messages:tools:[AIToolDefinition]?…)/parseResponse/parseStreamChunk }` | Rewrite to real shape: `final class AnthropicProvider: BaseAIProvider, AIProviderProtocol, @unchecked Sendable` holding `session`, real `buildRequestBody(from:streaming:) -> [String: Any]`, `complete(_:)`/`stream(_:)`; add a short "PLANNED: a future `HTTPBasedAIProvider` will absorb the URLSession boilerplate (COREDEV-1837)" note. |
| `agents/ai-engineer.md:78,119,289` (`AIToolDefinition`) | fabricated type | Replace with real `AITool` + `ToolHandlerProtocol`/`Set<AgentTool>`/`ToolCall`/`ToolRegistry.register(_:)` model; §2 example becomes a real handler class; line-289 test becomes a real handler registration. |
| `agents/ai-engineer.md:107` (URLSession rule) | "Never call `URLSession` directly — `HTTPBasedAIProvider` handles it" | "Today providers own their `URLSession` (default `NetworkService.shared.session`); the PLANNED `HTTPBasedAIProvider` will centralize it (COREDEV-1837)." |
| `agents/ai-engineer.md:216-235, 254-308` (`AIAgentPipeline(provider:…)`, `execute(operation:accountEmail:)`) | fabricated init/execute | Correct to `.shared` + `configure(…)` + `execute(input:configuration:)` (or relabel illustrative with real symbols). |
| `agents/ai-engineer.md:314` (handoff) | "HTTP providers inherit `HTTPBasedAIProvider`" | reality + PLANNED note. |
| `agents/logic-engineer.md:61` | "HTTP providers inherit `HTTPBasedAIProvider`" | reality + PLANNED note (concise). |
| `AGENT_CONTRACTS.md:146-147` (§4 Provider abstraction) | "HTTP-based providers inherit `HTTPBasedAIProvider`, override prepareHeaders/buildRequestBody/parseResponse/parseStreamChunk" | reality + PLANNED (COREDEV-1837) note; mirror the `AISafetyPipeline` PLANNED treatment that already sits in this same §4. |
| `README.md:160` (ai-engineer agent row) | "HTTPBasedAIProvider (cloud) + BaseAIProvider…" | "GARI AI pipeline — cloud providers (`BaseAIProvider`+`AIProviderProtocol`) + Apple Intelligence, `ToolRegistry`, `PromptRegistry`, inline safety…". |
| `skills/swiftlint-config/SKILL.md:282` (sample lint-rule message) | "Use HTTPBasedAIProvider or service protocols instead of direct URLSession" | "Use a provider conforming to `AIProviderProtocol` / a service protocol (`NetworkService`) instead of ad-hoc `URLSession`" — drop the nonexistent symbol; remains a sample. |
| `agents/prompt-review.md:25-27` (the new agent's own guardrail) | "Some project docs name types that do not exist in source (e.g. `HTTPBasedAIProvider`, `AIToolDefinition` appear in CLAUDE.md / .claude/rules but NOT in `Sources/`)…" | **Must edit** (gemini + codex blocker): keep `HTTPBasedAIProvider` as the canonical "doc-named / source-absent / **PLANNED** (COREDEV-1837)" example, and **drop the `AIToolDefinition` literal** — otherwise the §5 "0 `AIToolDefinition` matches" validation cannot pass. The guardrail's intent (anchor scans on grep-confirmed source symbols) is preserved; reword so the post-fix docs are internally consistent (HTTPBasedAIProvider is now explicitly PLANNED, not just "doc-only"). Leave the file's real-symbol references (`AITool`, `ToolHandlerProtocol`, `AgentTool`, `ToolCall`) untouched. |

**Note on `HTTPBasedAIProvider` retention:** we keep the *name* where it documents the planned target (clearly tagged PLANNED/COREDEV-1837), exactly as the file already does for `AISafetyPipeline`. We do **not** delete the aspiration; we stop presenting it as current. `AIToolDefinition` is deleted outright (it is not even a planned symbol).

## 5. Validation

- `python3 scripts/validate-plugin-assembly.py --strict` → OK (counts unchanged 21/18/3/1).
- `VERSION_SYNC_ENFORCE=strict bash scripts/validate-version-sync.sh` → OK (no version/count change).
- **Active guidance carries 0 `AIToolDefinition`:** `git grep -n "AIToolDefinition" -- agents skills CLAUDE.md AGENT_CONTRACTS.md README.md` → **0** matches (this is the reproducible invariant — `agents/prompt-review.md`'s mention is removed, hence the guardrail line is in the inventory). The symbol legitimately **survives** in `CHANGELOG.md` (the release note) and in this planning doc, which *describe* the removal — those are excluded by scope, not failures.
- `grep -rn "HTTPBasedAIProvider" .` → only PLANNED-tagged mentions remain (no present-tense "inherit/override … now" framing). The surviving hits — `ai-engineer.md`, `logic-engineer.md`, `AGENT_CONTRACTS.md`, `CLAUDE.md`, `README.md`, `prompt-review.md`'s guardrail — must each tag it PLANNED/COREDEV-1837 or doc-only; manually audit each.
- No unit tests (docs-only). Add a `CHANGELOG.md` `[Unreleased] → Fixed` entry (swept into 2.4.0 by the release PR).
- Spot-check: every rewritten Swift snippet references only grep-confirmed symbols.

## 6. Risks / mitigations

- **Introducing new drift** while "fixing" drift → mitigated by §2 source citations; every snippet uses confirmed symbols only.
- **Scope creep in `ai-engineer.md`** (the pipeline/registration rewrites) → bounded to making existing examples compile; no new conceptual content.
- **`HTTPBasedAIProvider` is genuinely planned** → we must not erase it as a target (would lose the COREDEV-1837 intent); we relabel, not delete.
- **CLAUDE.md is load-bearing** → keep edits minimal and reality-accurate; user pre-authorized.

## 7. Plan-review gate (mandatory) & Jira

- Dual gate (`/unleashed-mail:gemini-review` + `/unleashed-mail:codex-review`) on this plan BEFORE edits; iterate to APPROVE/APPROVE_WITH_NOTES.
- Jira: COREDEV-2331 → In Progress with dev notes; log files touched + decisions; → Done-pending-merge at PR.
