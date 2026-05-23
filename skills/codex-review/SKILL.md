---
name: codex-review
description: Read-only Codex CLI review for plans, debug sessions, and post-implementation audits. Paired with /unleashed-mail:gemini-review.
---

# Codex CLI Review

All plans and debugging sessions must also be reviewed by Codex CLI — non-negotiable, runs alongside `/unleashed-mail:gemini-review` (not as a replacement). Post-implementation audits also run Codex.

Docs: https://developers.openai.com/codex/cli/reference

| Trigger | When |
|---------|------|
| New plan or architecture decision | BEFORE any code is written |
| Bug investigation or debugging | BEFORE proposing fixes |
| Post-implementation audit | AFTER code is written — read-only scan for security, concurrency, UX/perf, accessibility |

## Setup

- **Tool:** `codex` CLI.
- **Working directory:** always run from the project root (top-level workspace directory containing `Unleashed Mail.xcodeproj/`). Codex resolves relative paths against `$PWD`.
- **Model:** `~/.codex/config.toml` sets `model = "gpt-5.5"` and `model_reasoning_effort = "xhigh"` (verified 2026-04-29). Both inherited by every `codex exec` call — **do not pass `--model`** on this ChatGPT-auth'd install (`gpt-5-codex` silently fails with zero-byte output when backgrounded).
- **One-off override (rarely needed):** `codex exec -c model=gpt-5.5 -c model_reasoning_effort=xhigh -s read-only "PROMPT"` — no dedicated `--reasoning-effort` flag; use generic `-c key=value`.

## Monitor, not Bash background (user-confirmed preference)

> **Source:** user auto-memory `feedback_codex_monitor_pattern.md` — this is a project-specific operational preference the user has confirmed, not a rule from the original `.claude/prompts/codex-review.md` (workspace-only artifact).

For non-trivial `codex exec` runs, route the process through the `Monitor` tool. Reason on this project: `Bash run_in_background` has produced 0-byte outputs on long Codex runs, while `Monitor` has been reliable.

## Invocation patterns

```bash
# Plan / debug review (non-interactive, read-only)
codex exec -s read-only "PROMPT_HERE"

# Targeted agent-role audit (post-implementation) — see skill list below
codex exec -s read-only "/security-reviewer [FILES]"

# Full diff review — built-in mode, no custom prompt allowed
codex exec review --uncommitted -o /tmp/review-output.md
codex exec review --base main     -o /tmp/review-output.md
codex exec review --commit <SHA>  -o /tmp/review-output.md

# Save agent output to file
codex exec -s read-only -o /tmp/output.md "PROMPT_HERE"
```

## `codex exec` flags (non-interactive)

| Flag | Purpose |
|------|---------|
| `exec` | Non-interactive scripted execution (no TUI) |
| `-s read-only` / `--sandbox read-only` | Prevents file modifications — safe for audits |
| `-s workspace-write` | Allows writes within project directory |
| `-m MODEL` / `--model MODEL` | Override model selection (do not use on this install) |
| `-o PATH` / `--output-last-message PATH` | Write final response to file |
| `--ephemeral` | Run without persisting session files |

## `codex exec review` flags (built-in review mode)

| Flag | Purpose |
|------|---------|
| `--uncommitted` | Review staged, unstaged, and untracked changes (no custom prompt allowed) |
| `--base BRANCH` | Review changes against the given base branch |
| `--commit SHA` | Review changes introduced by a specific commit |
| `-o PATH` | Write final review to file |

`codex exec review --uncommitted` does NOT accept a custom prompt. For targeted reviews with specific instructions, use `codex exec -s read-only "PROMPT"`.

## Codex skills — mirror of the Unleashed Mail plugin

Codex has first-class skills that mirror every Unleashed Mail plugin agent, command, and skill. Invoke the skill by name inside `codex exec` — skills carry their own rubric and output contract.

General form: `codex exec -s read-only "/<skill-name> [ARGS or FILES]"`

**Review** (run the first four in parallel, then synthesize with `/swift-reviewer`):
- `/security-reviewer` — credential exposure, injection, insecure storage, entitlement misuse, OAuth flaws, supply-chain risks
- `/concurrency-reviewer` — race conditions, data races, actor isolation, unsafe threading, deprecated Swift/Apple APIs
- `/ux-perf-reviewer` — UI responsiveness, animation, memory, DB query perf, network optimization
- `/accessibility-auditor` — VoiceOver, keyboard nav, Dynamic Type, color contrast, a11y labels/hints/traits
- `/swift-reviewer` — orchestrator + provider-parity audit + synthesizer

**Implementation:** `/logic-engineer`, `/ui-engineer`, `/db-engineer`, `/ai-engineer`, `/tester`, `/code-simplifier`

**Planning & personas:** `/modern-standards-planner`, `/smb-entrepreneur`, `/enterprise-stakeholder`, `/unleashed-mail:brainstorm`, `/unleashed-mail:implement`, `/unleashed-mail:pr-review`

**Diagnostics:** `/xcode-build-fixer`, `/graph-api-debugger`, `/macos-debugging`

**CI / release / project:** `/ci-engineer`, `/release-manager`, `/jira-manager`, `/docs-engineer`

**Domain skills:** `/swiftui-mvvm`, `/microsoft-graph-integration`, `/gmail-api-integration`, `/keychain-security`, `/grdb-patterns`, `/webview-composer`, `/provider-parity`, `/swift-tdd`, `/error-handling`, `/accessibility-patterns`, `/swiftlint-config`, `/spm-management`

**Infrastructure:** `/agent-orchestration`

**Review tooling (v2.2.2):** `/unleashed-mail:gemini-review`, `/unleashed-mail:codex-review`, `/unleashed-mail:create-feature-plan`

If a skill is missing from a given install, list `~/.codex/skills/` before falling back to a free-form prompt.

## Example invocations

```bash
# Parallel audit — one codex exec per skill, run concurrently via Monitor
codex exec -s read-only "/security-reviewer [FILES]"
codex exec -s read-only "/concurrency-reviewer [FILES]"
codex exec -s read-only "/ux-perf-reviewer [FILES]"
codex exec -s read-only "/accessibility-auditor [FILES]"

# Synthesize after the four complete
codex exec -s read-only "/swift-reviewer [PRIOR_OUTPUTS or FILES]"

# Implementation consult
codex exec -s read-only "/grdb-patterns How should I add a ValueObservation for [TABLE]?"

# Plan / debug (unstructured — when no skill is a good fit)
codex exec -s read-only "PLAN_OR_DEBUG_CONTENT"
```

## Full workflow (plan or debug → implementation → post-impl audit)

1. **Plan review:** `codex exec -s read-only "PLAN_CONTENT"`
2. **Post-implementation audit:** run the four Codex audit skills in parallel (`/security-reviewer`, `/concurrency-reviewer`, `/ux-perf-reviewer`, `/accessibility-auditor`) with `-s read-only`
3. **Full diff review:** optionally also run `codex exec review --uncommitted`
4. **Synthesize:** run `/swift-reviewer` last, feeding it the four audit outputs
5. Incorporate feedback from both Gemini and Codex before considering work complete

## Safety rules

- **Always `-s read-only` for audits** — never `--full-auto`, `danger-full-access`, or `--dangerously-bypass-approvals-and-sandbox`
- `--dangerously-bypass-approvals-and-sandbox` is reserved for externally sandboxed CI environments only
- `codex exec -s read-only` with skill prompts is the preferred pattern for targeted reviews
- `codex exec review --uncommitted` is for general diff reviews only (no custom prompt)

Both Gemini and Codex must review plans before implementation begins. Neither review is optional.
