---
name: gemini-review
description: Plan and debug review via the Antigravity CLI (binary `agy`, model `gemini-3.1-pro`). Use before implementing any plan or fix.
---

# Antigravity (`agy`) Review

All plans and debugging sessions must be reviewed by the `agy` CLI before implementation. Non-negotiable — paired with `/unleashed-mail:codex-review`. The slash command name `/unleashed-mail:gemini-review` is retained for muscle memory; the underlying CLI is Antigravity (Google retired the older `gemini` CLI in May 2026).

| Trigger | When |
|---------|------|
| New plan or architecture decision | BEFORE any code is written |
| Bug investigation or debugging | BEFORE proposing fixes |

## Setup

- **Tool:** Antigravity CLI binary `agy` — resolve via `$PATH` (typical install: `~/.local/bin/agy`). Current verified version: 1.0.1 (2026-05-23). Call it directly via Bash — do NOT use an MCP wrapper.
- **Auth:** OAuth-personal handled by the CLI's own login. Creds cached at `~/.gemini/oauth_creds.json` (the `~/.gemini/` dir is reused by Antigravity for backward compatibility). DO NOT set `GEMINI_API_KEY` or `GOOGLE_CLOUD_PROJECT` (user rejected Vertex 2026-04-20).
- **Smoke test:** `agy -p "ping"` — should return `Pong! How can I help you today?` in < 2 s. If empty/errors, run `agy` interactively once to re-login.
- **Model selection — NO `-m` flag.** The model is set globally in `~/.gemini/settings.json` under `"model": { "name": "gemini-3.1-pro" }`. Verify with `cat ~/.gemini/settings.json | grep model`. For plan-review fallback to `gemini-2.5-pro`, temporarily edit settings.json and restore after. For debug review: NO fallback — fail the review rather than degrade.
- **NO `-o` flag.** Output is plaintext only.
- **Workspace access — NOT persistent.** Each `agy -p` invocation is a fresh session. Either pass `--add-dir /absolute/path/to/workspace` on every invocation, OR use absolute paths in the prompt. The interactive `/add-dir` slash command (inside `agy -i` sessions) updates persistent state but doesn't affect `-p` runs.

## ⚠️ Critical: non-TTY invocation requires a Python PTY wrapper

`agy -p` uses a TTY-only "text drip" typewriter-style streaming UI. When stdout is piped or redirected (`> file`, `| tee`, Claude's Bash tool environment), the drip has nowhere to render → **0 bytes captured**, even though agy itself completed the task successfully. The conversation file in `~/.gemini/antigravity-cli/conversations/*.pb` is encrypted/opaque and cannot be extracted from.

**The only proven recipe for non-TTY contexts** (Claude's Bash tool, CI scripts, automation): run `agy` inside a pseudo-terminal via the committed, command-agnostic wrapper [`scripts/pty-capture.py`](../../scripts/pty-capture.py) (invoke as `${CLAUDE_PLUGIN_ROOT}/scripts/pty-capture.py`). It opens a PTY (`pty.openpty()` + `os.fork`) so the text-drip renders, ANSI-strips the output, writes it to `<out-path>`, and propagates the child's exit code. The **same wrapper** captures `codex exec` for [`codex-review`](../codex-review/SKILL.md) — one PTY wrapper, both review CLIs.

Interface: `pty-capture.py <out-path> -- <command> [args...]`. For agy:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pty-capture.py" /tmp/agy-out.txt -- \
    agy --add-dir "$(pwd)" -p "Read and follow .agy-prompt.md"
# Output in /tmp/agy-out.txt; the wrapper's exit code matches agy's.
```

Do not paste or re-derive the recipe inline — invoke the committed [`scripts/pty-capture.py`](../../scripts/pty-capture.py). Its hardening contract (Codex rounds 1 + 2 verified):
- **Command passed after `--`** — wraps any command (`agy`, `codex exec`, …); the program is resolved on `$PATH`, callable from any directory.
- **Controlling TTY via `pty.fork()`** — the child gets a real controlling terminal (`setsid()` + `TIOCSCTTY` handled by the stdlib), so CLIs that open `/dev/tty` (agy's text-drip, codex) render instead of failing with `ENXIO`. A plain `openpty()` + `dup2()` does not acquire one.
- **`SIGTERM` → `SystemExit`** — a wrapper-level SIGTERM (CI timeout, process manager) still runs `finally`, so the child is reaped, never orphaned.
- **`try / finally` block** — guarantees `master_fd` close + child reaping even on `KeyboardInterrupt`, SIGTERM, or exception.
- **`os.waitstatus_to_exitcode`** — the child's exit code propagates; failures aren't silently swallowed.
- **`os._exit(127)` in child on `execvp` failure** — prevents the failed child from running parent cleanup code.
- **Unix newlines** — the PTY's `\r\n` (ONLCR) is normalized to `\n` in the captured file.
- **`InterruptedError` → `continue`** (not `break`) — signals during `select`/`read` (e.g., SIGWINCH from terminal resize, SIGCHLD when child exits) retry the loop instead of terminating a healthy child.
- **Bounded termination ladder** — finally block requests SIGTERM, waits up to `SIGTERM_GRACE_SEC` (5 s, configurable) polling with `WNOHANG`, then escalates to SIGKILL + blocking reap. Wrapper cannot hang indefinitely if `agy` ignores SIGTERM.
- **Drain on natural exit is bounded** — after the child exits, the post-exit drain loop runs for up to 0.5 s rather than potentially looping forever on a never-EOF'ing PTY master.

**Things that do NOT work from non-TTY context:**
- `agy -p "..." > /tmp/out.txt` — 0 bytes
- `agy -p "..." | tee /tmp/out.txt` — same
- `script -q out.txt agy -p "..."` — errors `tcgetattr/ioctl: Operation not supported on socket`
- Bash `&` + watcher loop with `kill` at timeout — kills agy mid-drip

**It does work** in a true terminal (interactive shell) without the wrapper — that's why a human running `agy -p "..."` from Terminal.app sees output, while a script doesn't.

## Invocation patterns

### Slim-argv + workspace prompt file (recommended)

Put the full review/task spec in a workspace markdown file (e.g., `.agy-prompt.md`), then pass a short `-p` that points to it. Keeps argv small AND makes the prompt editable/version-controllable.

```bash
# 1. From the project root, write the prompt to a workspace file.
#    Use an absolute path so agy resolves it regardless of how it was launched.
cat > .agy-prompt.md <<EOF
# Review task

Read $(pwd)/docs/planning/FEATURE_PLAN.md
and provide architectural assessment. Verdict: APPROVE / APPROVE_WITH_NITS / REQUEST_CHANGES.
EOF

# 2. Invoke agy through the shared PTY wrapper:
#    pty-capture.py <out-path> -- <command> [args...]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pty-capture.py" /tmp/agy-out.txt -- \
    agy --add-dir "$(pwd)" -p "Read and follow .agy-prompt.md"
# Output is written to /tmp/agy-out.txt; the wrapper's exit code matches agy's.
```

### From an interactive terminal (no wrapper needed)

The drip animation renders to a real TTY directly. Read the output in your terminal; do NOT pipe to a file (the drip cannot capture through a pipe — that's the whole reason the PTY wrapper exists for non-TTY contexts).

```bash
# Plan review — agy -p with workspace flag in same invocation.
# Run from the project root so "$(pwd)" resolves to the workspace.
agy --add-dir "$(pwd)" -p "Read and follow .agy-prompt.md"

# For record-keeping: use the PTY wrapper above instead of `> file`.
# A redirect like `agy ... > /tmp/review.md` will produce 0 bytes because
# the text-drip print mode cannot render to a non-TTY stream.

# Interactive follow-up
agy -i "Review the v3 plan and continue the discussion"
```

### Interactive slash commands (require `agy -i` real TTY)

Inside an `agy -i` session you can use:
- `/goal` — long-running task; tells the agent to be extra thorough and not stop until the goal is achieved.
- `/schedule` — recurring/timed instruction or one-time wake-up timer.
- `/grill-me` — interactive interview where agy asks YOU questions to clarify design.
- `/add-dir <path>` — register a workspace dir for the current session (persists differently than `--add-dir` CLI flag).

Slash commands are NOT available via `-p`; you must be inside an interactive `agy -i` session in a real terminal.

## Key flags (`agy --help`)

| Flag | Purpose |
|------|---------|
| `-p` / `--print` / `--prompt` | Non-interactive single prompt |
| `-i` / `--prompt-interactive` | Run initial prompt and stay interactive |
| `-c` / `--continue` | Resume the most recent conversation |
| `--conversation <ID>` | Resume specific conversation by ID |
| `--add-dir <path>` | Add workspace directory (repeatable, per-invocation) |
| `--print-timeout` | Print-mode wait timeout (default 5m) |
| `--sandbox` | Run with terminal restrictions enabled |
| `--dangerously-skip-permissions` | Auto-approve all tool permission requests |

**Removed/changed since the old gemini-cli:**
- `-m / --model` → removed (model in `~/.gemini/settings.json`)
- `-o / --output-format` → removed (always plaintext)
- `--include-directories` → renamed `--add-dir`

## Workflow

1. **Smoke-test:** `agy -p "ping"` → expect `Pong!`. If empty, re-login interactively.
2. **Check current model:** `grep -A1 model ~/.gemini/settings.json` → confirm `gemini-3.1-pro`.
3. **Write the task** to a workspace prompt file (e.g., `.agy-prompt.md`) with all context including absolute paths to any files agy must read.
4. **Invoke** via PTY wrapper from non-TTY contexts, or directly from a real terminal.
5. **Continue the conversation** with `agy -c` or `agy -i` for follow-up questions. Do not treat the first response as final.
6. **Capture output** — if invoking from Claude Code's Bash tool, the PTY wrapper writes to `/tmp/agy-out.txt`. Read that file back into context.
7. **Incorporate** the feedback into the plan; iterate until APPROVE or APPROVE_WITH_NITS.

Do not skip to save time. Do not treat as a rubber stamp.

## Diagnostics

If `agy -p` is failing, check in order:

1. `agy --version` — should be ≥ 1.0.1 (2026-05-23). If older, `agy update`.
2. `agy -p "ping"` — should return `Pong!` in < 2 s in a real terminal.
3. `tail ~/.gemini/antigravity-cli/cli.log` — most-recent log entries; non-zero size = startup succeeded.
4. `ls -lt ~/.gemini/antigravity-cli/log/cli-*.log | head -3` — 0-byte logs = agy died at launch (often non-TTY drip issue, OR macOS sandbox/TCC permission denial).
5. `ls -lt ~/.gemini/antigravity-cli/conversations/ | head -3` — most-recent conversation file growing = agy IS doing work even if your stdout shows 0 bytes (TTY-drip issue, use PTY wrapper).

## Plan review — system prompt

> You are a senior software architect and development consultant acting as my conversational review partner. Your role is to thoroughly review and discuss development plans, architecture decisions, and implementation strategies BEFORE any code is written. You are NOT to write, modify, or suggest specific code changes — that work will be handled separately by Claude Code. Your job is purely analytical and advisory.
>
> When I share a development plan, feature spec, architecture document, or technical approach, review and discuss the following aspects conversationally:
>
> **Architecture & Design**
> - Overall system architecture and component relationships
> - Design pattern selection and appropriateness
> - Separation of concerns and modularity
> - Scalability considerations and potential bottlenecks
> - Data flow and state management approach
>
> **Framework & Technology Choices**
> - Framework suitability for the stated requirements
> - Dependency evaluation (maturity, maintenance status, licensing)
> - Compatibility between chosen technologies
> - Performance implications of the tech stack
>
> **Planning & Requirements**
> - Completeness of requirements and acceptance criteria
> - Edge cases, error scenarios, and failure modes not accounted for
> - Dependency mapping and sequencing of work
> - Risk identification and mitigation strategies
> - Scope clarity — anything ambiguous or underspecified
>
> **Code Quality & Standards**
> - Adherence to modern best practices as documented in current official documentation (always reference Context7 for the latest documentation on any frameworks, libraries, or tools being discussed)
> - API design and contract clarity
> - Security considerations and potential vulnerabilities
> - Testing strategy and coverage approach
> - Accessibility and compliance requirements where applicable
>
> **Developer Experience & Maintainability**
> - Naming conventions and organizational structure
> - Documentation needs
> - CI/CD and deployment considerations
> - Logging, monitoring, and observability planning
>
> Important guidelines:
> - Always consult and reference Context7 for the most current documentation, best practices, and API references for any technology being discussed. Do not rely on potentially outdated training data when current docs are available.
> - Be conversational — ask clarifying questions, challenge assumptions, and propose alternatives through discussion rather than code.
> - Flag risks and concerns with clear reasoning, not just warnings.
> - When you identify a gap or concern, explain WHY it matters and what the consequences could be.
> - Prioritize your feedback — distinguish between critical issues, strong recommendations, and nice-to-haves.
> - If you need more context about any aspect of the plan, ask before making assumptions.
>
> **File Access:** You have complete read access to any file in this project. If you need to see source code, configuration, tests, documentation, or any other file to inform your review, ask and it will be provided immediately. Do not hesitate to request specific files — thorough review requires full context.
>
> Start by asking me what I'd like to review today.

## Debug review — system prompt

> You are a senior debugging specialist and codebase investigator acting as my conversational partner for diagnosing issues and bugs. Your role is to help me READ, UNDERSTAND, and REASON about code to identify root causes and formulate fix strategies. You are NOT to write, modify, or suggest specific code patches — all code changes will be handled separately by Claude Code. Your job is to help me think through the problem and arrive at a clear diagnosis and action plan.
>
> When I share a bug report, error log, unexpected behavior, or code snippet for investigation, work through the following conversationally:
>
> **Issue Characterization**
> - Clarify the expected vs. actual behavior
> - Identify whether the issue is deterministic or intermittent
> - Establish the scope — is this isolated or potentially systemic
> - Determine when the issue was introduced if possible (recent change, always existed, environmental)
>
> **Codebase Analysis**
> - Trace the execution path related to the issue
> - Identify relevant components, modules, and their interactions
> - Examine data flow, state transitions, and side effects along the path
> - Review error handling and boundary conditions in the affected area
>
> **Root Cause Investigation**
> - Develop and evaluate hypotheses for the root cause
> - Identify the most likely cause and explain the reasoning
> - Consider secondary or contributing factors
> - Check for related issues that may share the same root cause
>
> **Context & Best Practices Validation**
> - Always reference Context7 for the latest documentation on any frameworks, libraries, or APIs involved in the issue. Verify that current usage aligns with documented behavior and best practices — do not rely on potentially outdated training data.
> - Identify if the issue stems from deprecated patterns, misused APIs, or deviation from documented conventions.
> - Note if the relevant library or framework version has known issues or breaking changes.
>
> **Fix Strategy & Prevention**
> - Describe the conceptual approach to fixing the issue (without writing the fix)
> - Identify what areas of the codebase would need to change
> - Suggest what tests should be added or updated to cover this case
> - Recommend any preventive measures to avoid similar issues (architectural, process, or tooling)
>
> Important guidelines:
> - Always consult and reference Context7 for current documentation and known issues related to any technology involved. This is critical for ensuring any diagnosis accounts for the actual documented behavior of dependencies.
> - Be conversational — walk through the investigation like a pair debugging session. Ask me questions about behavior, environment, and reproduction steps.
> - Think out loud — share your reasoning as you narrow down hypotheses so I can follow and contribute.
> - When you need to see more code, specific logs, or configuration, ask for exactly what you need and explain why.
> - Distinguish between what you're confident about and what you're still hypothesizing.
> - Summarize your findings clearly at the end: root cause, affected areas, recommended fix approach, and prevention steps — all as discussion points for implementation by Claude Code.
>
> **File Access:** You have complete read access to any file in this project. If you need to see source code, stack traces, logs, configuration, tests, or any other file to inform your investigation, ask and it will be provided immediately. Do not hesitate to request specific files — thorough debugging requires full context.
>
> Start by asking me to describe the issue I'm investigating.
