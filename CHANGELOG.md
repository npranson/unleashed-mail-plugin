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

_Nothing yet — add new changes here._

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
- **Unit tests** for the synthesizer (`mcp/review-synthesizer/tests/`, 52 stdlib
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
- **MCP robustness (per spec):** the `findings` input schema is permissive (`items:
  object`) so a malformed row reaches the server and is quarantined instead of being
  rejected client-side (which would defeat quarantine); the tool result mirrors the
  provisional verdict + `blockersToVerify` into the text `content` (not only
  `structuredContent`) for clients that don't surface structured output; and the stdio
  loop uses `readline()` to avoid the read-ahead buffering that can deadlock a pipe.
- Removed the superseded `prototypes/hybrid-review-synthesizer/` sandbox — a buggier
  duplicate of the shipped server; its design is captured in the server's README.

## [2.2.4]

### Added
- Shared PTY capture wrapper (`scripts/pty-capture.py`) so the `codex-review` and
  `gemini-review` CLIs render reliably from non-TTY contexts; surfaced in the README
  skills table.
