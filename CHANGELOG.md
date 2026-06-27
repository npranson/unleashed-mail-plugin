# Changelog

All notable changes to the **unleashed-mail** Claude Code plugin are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Plugin
releases use the `MAJOR.MINOR.PATCH` version in `.claude-plugin/plugin.json` (distinct
from the host app's `MAJOR.MINORRELEASE.YYMMBB` scheme in `docs/VERSIONING.md`).

> **Maintenance:** add every change under `[Unreleased]` as you make it, grouped by
> *Added / Changed / Fixed / Removed*. When you bump `plugin.json`, move the
> `[Unreleased]` items under a new dated `[x.y.z]` heading and start a fresh
> `[Unreleased]`.

## [Unreleased]

### Added
- **`prompt-review` — static AI-prompt / call-site reviewer, fully wired into the review pipeline**
  (COREDEV-2330 agent + COREDEV-2329 wiring; under Epic COREDEV-2126 GARI safety). A read-only 5th
  specialist reviewer that statically audits AI prompts and provider call sites (jailbreak/injection
  surface, missing refusal paths, format/context leaks, unsanitized ingress of untrusted email/web
  content, inline prompts outside `PromptRegistry`, unscoped tools, PII-in-logs). It ends its report
  with a fenced ` ```json ` findings array + a `Status:` line and is now a first-class member of the
  deterministic pipeline: a new **`ai-safety`** category family (10 categories) + `DISPLAY_BUCKET`
  ("AI Prompt Safety") and `prompt-review` ownership in `mcp/review-synthesizer/` (`schema.py`,
  `synthesize.py`, the manual-fallback `README.md`); added to the `swift-reviewer` Step-2 panel
  (owner of the `ai-flow` structural subsystem), the status-read recipe, and the consolidated report;
  added to both SubagentStop/SubagentStart capture allowlists + `VALID_AGENTS`; and to
  `/unleashed-mail:pr-review`, `/unleashed-mail:implement`, `agent-orchestration`, `AGENT_CONTRACTS.md`,
  and the Codex review mirror. Agent count **20 → 21** (README + `plugin.json` already bumped with the
  agent; no plugin version bump — hooks/schema aren't asset-counted). Tests cover the capture, the
  category↔schema **exact-equality** invariant (guards the silent-drop trap), and `ai-safety`
  routing/render. Plan-review gate: codex `APPROVE_WITH_NOTES` + gemini `APPROVE_WITH_NITS`.
- **Reviewer-capture round binding — a stable per-cycle signal from `SubagentStart`** (COREDEV-2326,
  closes Epic COREDEV-2321). The SubagentStop reviewer capture's round was previously only *inferred*
  (`capture.py:select_round`), which cannot perfectly group cycles under interleaved timing — a late
  reviewer from an earlier cycle could mis-bucket into a later round. A new **`SubagentStart` producer
  hook** (`scripts/capture-reviewer-round-start.sh` + a `SubagentStart` entry in `hooks/hooks.json`)
  now *freezes* the round for each of the four specialist reviewers **at spawn**, keyed by its unique
  `agent_id`, in a per-checkout binding file under `.state/`; the SubagentStop capture
  (`scripts/capture-reviewer-verdict.sh`) looks it up by the **same** `agent_id` and exports
  `UNLEASHED_REVIEW_ROUND`, so each capture lands in its **originating** round regardless of
  completion order, then consume-once clears the binding. New `scripts/lib/context.sh` helpers
  (`context_highest_round` — decimal-normalized; `context_review_round_bind`/`_lookup`/`_clear`;
  TTL + bounded `.state` sweep). Observe-only and fail-open end-to-end: an absent/stale/foreign-slug
  binding, a missing `python3`/`date`, or `UNLEASHED_REVIEW_ROUND_SIGNAL=off` all fall back to the
  shipped `capture.py` inference; an explicitly-set `UNLEASHED_REVIEW_ROUND` is never clobbered. No
  change to `capture.py`'s consumption logic, the findings-array shape, or the SubagentStop contract.
  PII-free (only a slug token, opaque ids, an int, and an epoch are persisted). The round number
  mirrors `capture.select_round` (advance past a final prior slot, else reuse), so a same-round repair
  re-run overwrites the empty slot rather than splitting the cycle. Tests: `test-hooks.sh`
  104 → **132** (interleaving fix, repair/per-agent reuse, stale/cross-agent isolation, decimal
  arithmetic, consume-once, kill switch, explicit-not-clobbered, producer exclusions, zsh-NOMATCH) and
  `test_capture.py`
  143 → **144** (override↔dedup round-trip). Plan-review: codex `APPROVE_WITH_NOTES` + gemini
  `APPROVE` (`docs/planning/REVIEW_ROUND_PRODUCER_PLAN.md`). No version or asset-count change (hooks
  are not counted by the version-sync validator).

### Changed
- **Reviewer Output-Contract status is now persisted through the SubagentStop capture path**
  (`mcp/review-synthesizer/capture.py`, COREDEV-2328). Each captured reviewer's `Status:`
  (`COMPLETE | BLOCKED | PARTIAL` + BLOCKED/PARTIAL detail fields) is written to a self-describing
  **sibling `<agent>.status` JSON** beside its `<agent>.json` findings — PII-redacted, observe-only,
  fail-open; the findings-array shape and all its consumers (`is_final_capture`, `synthesize._load`)
  are unchanged. Extraction is **CommonMark-fence-aware** and constrained to the report's top-level
  Output-Contract trailer (a `Status:` inside a code fence or behind prose is never taken) and
  ReDoS-safe. `swift-reviewer` Step 2 now reads the sidecar from the same round as the findings (via
  a new portable, unit-tested `context_latest_round_dir` helper in `scripts/lib/context.sh`),
  validates the sidecar's `agent`+`status`, and honours `BLOCKED`/`PARTIAL` on the pre-collected
  capture path too — degrading to face value when the sidecar is absent/corrupt/unrecognized (never
  a false fail-closed). Closes the Item-12 gap where a captured `BLOCKED` reviewer could read as a
  clean `[]`. No version or asset-count change (the `synthesize.py`/`schema.py` interface and the
  SubagentStop hook contract are untouched).

### Fixed
- **`<agent>.status` sidecar write hardened** (`capture.py`, PR #16 review) — `_write_status` now
  builds the payload as `{**status, "agent": agent}` (explicit `agent` **last**) instead of
  `dict(agent=agent, **status)`, so the trusted hook-allowlisted `agent` can never be collided-over
  or silently overwritten by a future transcript-derived `status` key (today the pinned
  `_STATUS_FIELDS` carry none — behaviourally identical, just collision-proof). Added a regression
  test asserting a duplicate (skipped) SubagentStop **preserves** an existing `BLOCKED`/`PARTIAL`
  sidecar untouched (`test_capture.py`, 142 → 143), pinning the early-return ordering that the
  Item-12 guarantee depends on. Added a `context_latest_round_dir` leading-zero test
  (`test-hooks.sh`, 103 → 104) that locks the base-10 (non-octal) `[ -gt ]` round comparison —
  `round-08`/`round-09` order numerically and never raise a `value too great for base` error — so a
  future refactor to `(( … ))` arithmetic can't silently regress it.

## [2.3.1] — 2026-06-26

### Added
- **Plan-review synthesis skill** (`/unleashed-mail:review-synthesis`,
  `skills/review-synthesis/SKILL.md`) — a read-only skill that combines the two captured
  plan-review transcripts (gemini → `/tmp/agy-out.txt`, codex → `/tmp/codex-out.txt`) into one
  auditable **Combined verdict** block (`APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES |
  DISAGREEMENT`; normalizes the CLI's `NITS → NOTES`; references findings by location/topic, never
  echoing PII; surfaces a one-approve / one-reject split as `DISAGREEMENT` rather than averaging; a
  missing/empty transcript can never claim `APPROVE`). Kept **distinct** from the code-review
  `synthesize_review` MCP enum (`APPROVE_WITH_SUGGESTIONS` / `NEEDS_DISCUSSION`). Wired into
  `AGENT_CONTRACTS.md §2` as plan-review step 3a, with one-line pointers in `gemini-review` /
  `codex-review`.
- **Reviewer Output-Contract status enum** — the four specialist reviewers (`security`,
  `concurrency`, `ux-perf`, `accessibility`) now emit a `Status: COMPLETE | BLOCKED | PARTIAL` line
  (immediately before their JSON findings array, which stays the final block) that is **orthogonal**
  to the findings, so a reviewer that *couldn't run* returns `BLOCKED` + `[]` instead of an empty
  `[]` that reads as a clean pass.
- **Decision-support option tables** in `/unleashed-mail:brainstorm` — a design-phase **Step 4b**
  that, only on a genuine architectural fork, presents 2–4 options in a comparison table (with a
  mandatory **Parity-Impact** column, S/M/L effort, a `(Recommended)` row, no emoji) and calls
  `AskUserQuestion` to record the chosen fork before the plan document. `AskUserQuestion` added to the
  command's `allowed-tools`.

### Changed
- **`swift-reviewer` Step 5 consumes the reviewer status.** `BLOCKED` routes to NEEDS DISCUSSION as a
  Needs-Confirmation uncertainty — **not** a `category: verification` blocker (which is
  confirmed-by-construction → REQUEST CHANGES); `PARTIAL` keeps the completed-scope findings and
  records a non-gating `verification` warning (escalated to NEEDS DISCUSSION if a Remaining file is
  structural). No synthesizer (Python) change. `skills/agent-orchestration/SKILL.md` handoff and
  `AGENT_CONTRACTS.md §5` updated to match.
- **Plugin bumped to 2.3.1.** `README.md` (H1, the `20 agents · 18 skills · 3 commands · 1 MCP
  server` counts, What's-New, architecture skill list, and Skills table) and
  `.claude-plugin/marketplace.json` reflect the new `review-synthesis` skill (skills 17 → 18).

## [2.3.0] — 2026-06-25

### Added
- **Deterministic review synthesizer (MCP).** A local, zero-dependency stdio MCP
  server at `mcp/review-synthesizer/` that performs the orchestrator's Step-5
  synthesis in code instead of LLM prose: schema validation/quarantine, scope filter
  (changeset + `structural-pipeline` carve-out), category-aware dedup with line-range
  overlap and cross-family ownership routing (cluster-and-cross-link, never silently
  drop), a provisional verdict, and `blockersToVerify` for the agent to confirm.
  Declared in the root `.mcp.json`; exposed to `swift-reviewer` as
  `mcp__plugin_unleashed-mail_review-synthesizer__synthesize_review`.
- **Unit tests** for the synthesizer (`mcp/review-synthesizer/tests/`, 78 stdlib
  `unittest` cases): schema edge cases, dedup/ownership/scope/verdict, render
  (findings-only, no leaked verdict), tool-input validation, and the MCP JSON-RPC
  protocol (initialize / tools.list / tools.call / ping, non-object & non-JSON
  resilience, quarantine-not-crash). Run:
  `python3 -m unittest discover -s mcp/review-synthesizer/tests`.
- **Bundled test fixtures** at `mcp/review-synthesizer/samples/` (sample findings +
  `changed_files.txt`); the standalone `synthesize.py` CLI and the README examples use them.
- **Design notes** in `mcp/review-synthesizer/README.md` — the hybrid architecture, the
  server↔agent division of labour, and the authoritative dedup rules.

### Changed
- **`swift-reviewer` Step 5 now delegates synthesis to the MCP tool.** The agent
  passes the reviewers' JSON findings to the synthesizer (which dedups/merges in
  code), then owns the **verify gate** (open each `blockersToVerify` `file:line`,
  confirm) and the **final verdict** — a clean split, since the server has no repo
  access. Falls back to applying the documented rules manually if the tool is
  unavailable.
- **Review-agent system overhaul.** Reviewers (`security`, `concurrency`, `ux-perf`,
  `accessibility`) now end with a structured JSON findings array
  (`severity · confidence · sourceAgent · category · file · line · lineEnd · scope ·
  finding · evidence · fix`) instead of a prose/markdown table; `swift-reviewer`
  cross-references and deduplicates across them. `concurrency-reviewer` broadened to
  the **correctness owner** (logic/error-handling). Provider-parity, test-coverage,
  and build/lint/test now emit gating `verification` rows. Added a **verify gate**
  (confirm blockers against the code before REQUEST CHANGES; unconfirmable →
  NEEDS DISCUSSION) and **structural-pipeline** whole-pipeline review for changes to
  key subsystems. `accessibility-auditor` moved to `opus` (all five review agents now
  `opus`).
- **AGENT_CONTRACTS.md §5** (Code Review Pipeline) and the README architecture/agents
  sections document the synthesizer step and the verify-gate split.
- **`.gitignore`** now ignores Python bytecode (`__pycache__/`, `*.py[cod]`) for the
  bundled stdlib MCP server.

### Fixed (PR review — Codex / Gemini / Copilot)
- **`synthesize_review` validates its inputs and fails closed.** `findings` and
  `changed_files` are required and type-checked; a missing, non-array `findings` or a
  missing/non-`list[str]` `changed_files` is rejected with JSON-RPC `-32602` instead of
  being coerced or defaulted — previously a string (or omitted) `changed_files`
  collapsed the scope set, mis-scoping every finding to pre-existing and letting a real
  blocker reach a provisional APPROVE.
- **Malformed JSON-RPC `params` (e.g. an array) returns `-32602`**, not a `-32603` crash.
- **Protocol-version negotiation** — `initialize` returns a version the server actually
  supports instead of echoing an arbitrary client-supplied one.
- **`id: null` is a request, not a notification** — it now receives a reply (JSON-RPC).
- **The verify gate gates on ANY blocker in a cluster**, not just the ownership-routed
  lead (consistent with `blockersToVerify`).
- **The standalone CLI `_load` quarantines** unreadable / malformed / wrong-shape
  findings files instead of crashing; deterministic file-descriptor close
  (`with open(..., encoding="utf-8")`).
- **Consolidated-table cells are escaped** — a `|` or newline in a reviewer's
  `finding`/`fix` no longer injects spurious columns/rows into the Markdown table.
- **Accessibility ownership ties resolve to `accessibility-auditor`** regardless of
  input order — a `ux-perf` row tagged `a11y` no longer outranks the auditor.
- **Empty-array JSON-RPC `params` is rejected** (`-32602`) instead of being coerced to `{}`.
- **Quarantined findings fail closed** — a schema-invalid row (e.g. a typo'd `category`
  on a real blocker) forces `NEEDS_DISCUSSION` instead of letting the provisional verdict
  be a clean `APPROVE`, so a parse slip can't silently turn a blocker into an approval.
- **Corrected the plugin MCP tool name** to `mcp__plugin_unleashed-mail_review-synthesizer__synthesize_review`
  — Claude Code preserves hyphens in plugin/server names (only chars outside `[A-Za-z0-9_-]`
  become `_`), so the earlier all-underscore form would not have matched the real tool.
- **Orchestrator global gates always gate (P1).** `verification` (build/lint/test),
  `parity`, and `test-coverage` findings aren't tied to a changed file — their `file`
  is a scheme/target/label — so they now gate regardless of the diff. Previously a red
  build emitted as a `verification` blocker was scoped out to pre-existing and the
  provisional verdict came back `APPROVE` with no `blockersToVerify`. The `swift-reviewer`
  verify gate also now treats these self-emitted rows as confirmed-by-construction (it
  ran the command) — it gates them without trying to `Read` a scheme:0 location and never
  downgrades them to NEEDS DISCUSSION.
- **The consolidated row leads with the blocker's text** in an ownership-routed cluster
  (e.g. a security `keychain` warning that owns a `token-race` blocker) — a 🔴 row no
  longer reads as the lower-severity owner with the blocker hidden behind a category name.
- **A missing reviewer routes to NEEDS DISCUSSION as an uncertainty, not a `verification`
  blocker** — reconciles the fail-closed path with the verification-gate carve-out (which
  treats `verification` rows as confirmed-by-construction → REQUEST CHANGES).
- **MCP robustness (per spec):** the `findings` input schema is fully permissive
  (`items: {}` — accept any JSON) so a malformed row, even a non-object like
  `null`/string/array, reaches the server and is quarantined individually instead of
  being rejected client-side (which would defeat quarantine); the tool result mirrors the
  provisional verdict + `blockersToVerify` into the text `content` (not only
  `structuredContent`) for clients that don't surface structured output; and the stdio
  loop uses `readline()` to avoid the read-ahead buffering that can deadlock a pipe.
- **UTF-8 + doc consistency:** the stdio server (and its subprocess test) pin UTF-8 so
  the report emoji survive a non-UTF-8 locale (minimal CI containers); the server
  README's fallback scope rule and the `agent-orchestration` skill are updated to match
  the always-gate and missing-reviewer behaviours above.
- **Reviewer paths are canonicalised before scoping** — leading/trailing whitespace, a
  leading `./`, and Windows backslashes are normalised on both the finding's `file` and
  the `$CHANGED` set, so `./Unleashed Mail/…`, `A.swift `, or `Sources\A.swift` matches
  `git diff --name-only` output instead of mis-scoping a real changeset blocker to
  pre-existing.
- **CLI fails closed on a bad `--changed`** — an explicit but missing/typo'd path now
  exits `2` instead of scoping every finding to pre-existing and exiting `0` APPROVE. The
  stdio server also pins `stderr` and uses `errors="replace"` so a malformed byte on the
  pipe degrades to U+FFFD rather than crashing `readline()`.
- Removed the superseded `prototypes/hybrid-review-synthesizer/` sandbox — a buggier
  duplicate of the shipped server; its design is captured in the server's README.

## [2.2.4]

### Added
- Shared PTY capture wrapper (`scripts/pty-capture.py`) so the `codex-review` and
  `gemini-review` CLIs render reliably from non-TTY contexts; surfaced in the README
  skills table.
