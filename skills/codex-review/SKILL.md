---
name: codex-review
description: Read-only Codex CLI review for plans, debug sessions, and post-implementation audits. Paired with /gemini-review.
---

# Codex CLI Review

All plans and debugging sessions must also be reviewed by Codex CLI — non-negotiable, runs alongside `/gemini-review` (not as a replacement). Post-implementation audits also run Codex.

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

## ⚠️ Always capture output via the PTY wrapper (eliminates 0-byte / STDN failures)

`codex exec` only reliably emits its result to a **real terminal**. When stdout is piped, redirected (`> file`, `| tee`), or the process is backgrounded — Claude Code's Bash tool, `run_in_background`, CI — codex can finish successfully yet write **0 bytes**. That is the recurring failure: the run "worked" but nothing was captured. The `-o PATH` flag mitigates it but is easy to forget and does not cover every backgrounded case.

**Default to routing every `codex exec` through the shared PTY wrapper:** [`scripts/pty-capture.py`](../../scripts/pty-capture.py) (invoke as `${CLAUDE_PLUGIN_ROOT}/scripts/pty-capture.py`). It runs codex inside a pseudo-terminal so output always renders, ANSI-strips it, and writes it to `<out-path>`. There is **no flag to forget**, so capture cannot silently fail. This is the same wrapper [`gemini-review`](../gemini-review/SKILL.md) uses for `agy` — one PTY wrapper, both review CLIs.

```bash
# Put the prompt in a workspace file, then run codex through the wrapper.
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pty-capture.py" /tmp/codex-out.txt -- \
    codex exec -s read-only "$(cat .codex-prompt.md)"
# Captured output is in /tmp/codex-out.txt; the wrapper's exit code matches codex's.

# Skill-based audit through the wrapper:
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pty-capture.py" /tmp/security.txt -- \
    codex exec -s read-only "/security-reviewer [FILES]"
```

Interface: `pty-capture.py <out-path> -- <command> [args...]`. Read `<out-path>` back into context after the run. If `${CLAUDE_PLUGIN_ROOT}` is unset (skill running outside the plugin), use the repo-relative `scripts/pty-capture.py`.

## Monitor, not Bash background (user-confirmed preference)

> **Source:** user auto-memory `feedback_codex_monitor_pattern.md` — this is a project-specific operational preference the user has confirmed, not a rule from the original `.claude/prompts/codex-review.md` (workspace-only artifact).

For non-trivial `codex exec` runs, route the process through the `Monitor` tool. Reason on this project: `Bash run_in_background` has produced 0-byte outputs on long Codex runs, while `Monitor` has been reliable. **Combine the two:** run the PTY wrapper above *under* `Monitor` (`pty-capture.py /tmp/out.txt -- codex exec …`) so a long run is both reliably scheduled and reliably captured — the wrapper guarantees the bytes land in the file, `Monitor` guarantees you don't block on it.

## Invocation patterns

> **Capture:** the forms below show the codex *command shape*. From any non-TTY context (Claude Code's Bash tool, CI, backgrounded runs) wrap each with `pty-capture.py <out> -- …` per the PTY-wrapper section above so output is never lost. The `-o PATH` forms are the in-terminal fallback.

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

**Review** (run the first five in parallel, then synthesize with `/swift-reviewer`):
- `/security-reviewer` — credential exposure, injection, insecure storage, entitlement misuse, OAuth flaws, supply-chain risks
- `/concurrency-reviewer` — race conditions, data races, actor isolation, unsafe threading, deprecated Swift/Apple APIs
- `/ux-perf-reviewer` — UI responsiveness, animation, memory, DB query perf, network optimization
- `/accessibility-auditor` — VoiceOver, keyboard nav, Dynamic Type, color contrast, a11y labels/hints/traits
- `/prompt-review` — AI prompt/call-site safety: jailbreak/injection surface, refusal paths, unsanitized ingress, tool scoping, PII-in-logs
- `/swift-reviewer` — orchestrator + provider-parity audit + synthesizer

**Implementation:** `/logic-engineer`, `/ui-engineer`, `/db-engineer`, `/ai-engineer`, `/tester`, `/code-simplifier`

**Planning & personas:** `/modern-standards-planner`, `/smb-entrepreneur`, `/enterprise-stakeholder`, `/unleashed-mail:brainstorm`, `/unleashed-mail:implement`, `/unleashed-mail:pr-review`

**Diagnostics:** `/xcode-build-fixer`, `/graph-api-debugger`, `/macos-debugging`

**CI / release / project:** `/ci-engineer`, `/release-manager`, `/jira-manager`, `/docs-engineer`

**Domain skills:** `/swiftui-mvvm`, `/microsoft-graph-integration`, `/gmail-api-integration`, `/keychain-security`, `/grdb-patterns`, `/webview-composer`, `/provider-parity`, `/swift-tdd`, `/error-handling`, `/accessibility-patterns`, `/swiftlint-config`, `/spm-management`

**Infrastructure:** `/agent-orchestration`

**Review tooling (v2.4.1):** `/gemini-review`, `/codex-review`, `/create-feature-plan` (canonical bare workspace names; the plugin also bundles them namespaced as `/unleashed-mail:gemini-review` etc.)

If a skill is missing from a given install, list `~/.codex/skills/` before falling back to a free-form prompt.

## Example invocations

```bash
# Parallel audit — one codex exec per skill, run concurrently via Monitor
codex exec -s read-only "/security-reviewer [FILES]"
codex exec -s read-only "/concurrency-reviewer [FILES]"
codex exec -s read-only "/ux-perf-reviewer [FILES]"
codex exec -s read-only "/accessibility-auditor [FILES]"
codex exec -s read-only "/prompt-review [FILES]"

# Synthesize after the five complete
codex exec -s read-only "/swift-reviewer [PRIOR_OUTPUTS or FILES]"

# Implementation consult
codex exec -s read-only "/grdb-patterns How should I add a ValueObservation for [TABLE]?"

# Plan / debug (unstructured — when no skill is a good fit)
codex exec -s read-only "PLAN_OR_DEBUG_CONTENT"
```

## Full workflow (plan or debug → implementation → post-impl audit)

1. **Plan review:** `codex exec -s read-only "PLAN_CONTENT"` — **end the prompt asking Codex to finish with an explicit `VERDICT: APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES` line** so the synthesis step can parse it deterministically. Once gemini's paired transcript is also captured, run `/unleashed-mail:review-synthesis` to combine `/tmp/codex-out.txt` + `/tmp/agy-out.txt` into one auditable **Combined verdict** block before implementation.
2. **Post-implementation audit:** run the five Codex audit skills in parallel (`/security-reviewer`, `/concurrency-reviewer`, `/ux-perf-reviewer`, `/accessibility-auditor`, `/prompt-review`) with `-s read-only`
3. **Full diff review:** optionally also run `codex exec review --uncommitted`
4. **Synthesize:** run `/swift-reviewer` last, feeding it the five audit outputs
5. Incorporate feedback from both Gemini and Codex before considering work complete

## Safety rules

- **Always `-s read-only` for audits** — never `--full-auto`, `danger-full-access`, or `--dangerously-bypass-approvals-and-sandbox`
- `--dangerously-bypass-approvals-and-sandbox` is reserved for externally sandboxed CI environments only
- `codex exec -s read-only` with skill prompts is the preferred pattern for targeted reviews
- `codex exec review --uncommitted` is for general diff reviews only (no custom prompt)

Both Gemini and Codex must review plans before implementation begins. Neither review is optional.
