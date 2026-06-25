# Octo Adoption Plan — Plugin Hardening & Hooks

**Status:** ✅ APPROVED (codex gate, round 5 — `APPROVE_WITH_NITS`; nits cleared) — ready for Phase 0   **Created:** 2026-06-25   **Last Updated:** 2026-06-25

## Overview

This plan ports 12 selected capabilities from `claude-octopus` into the `unleashed-mail` Claude Code plugin (v2.3.0). The deliverable is three things: (1) **plugin-asset validators + lightweight CI** that keep the plugin's own manifests, frontmatter, and version metadata honest; (2) a **real Claude Code hook layer** (PreToolUse sensitive-file guard, Stop-gate on a cached build/lint marker, PreCompact snapshot + SessionStart restore, SubagentStop reviewer-capture, and bounded diagnostic logs); and (3) **prompt-pattern refinements** to existing skills/agents/commands (a plan-review synthesis skill, decision-support option tables, and an agent Output-Contract status enum). The guiding principle is **harden the plugin's own assets and add a genuine hook layer — but keep octo's heavyweight orchestration (multi-LLM runner, provider routing, persona zoo, telemetry) firmly OUT.** Every borrowed mechanism is reduced to its smallest reusable core, retargeted onto unleashed's auto-discovery layout, no-PII rule, the literal space in `Unleashed Mail/Sources/`, and the non-SemVer `2.3.x` versioning. Every hook ships **warn-first with a kill-switch**, so the rollout can observe before it blocks.

## Approach

The work is phased by **runtime risk** and **dependency order**, not by item number.

- **Phase 0 — Foundation (zero runtime risk).** Validators (version-sync + plugin-assembly) and the CI workflow + synthesizer unit tests. These act on the **plugin repo itself** at commit/PR time; they cannot affect an app-dev session. They establish the `HAS_XCODEPROJ=false` validation branch and the first `.github/workflows/`. Ship these first as the opening PR.
- **Phase 1 — Safety hooks.** PreToolUse sensitive-file guard (`ask`-only) and the Stop-gate on a cached build/lint marker. These are the first net-new hook events; they only fire when the plugin is **active in an app-dev session driving the Swift repo**, never in the plugin repo. Both ship warn-first.
- **Phase 2 — Session / observability hooks.** PreCompact snapshot + SessionStart restore, SubagentStop reviewer-capture, and bounded diagnostic logs. These are observe-only or non-blocking; they enrich context and feed the review synthesizer.
- **Phase 3 — Prompt-pattern / process items.** Markdown-only changes: the plan-review synthesis skill, brainstorm decision-support tables, and the agent Output-Contract status enum. No hooks, no Python.

**Why this order:** Phase 0 is provably safe and unblocks CI for everything after it. Phase 1 introduces the new-event wiring pattern in `hooks/hooks.json` on the two highest-value safety hooks. Phase 2 reuses that wiring and the shared hook-IO library. Phase 3 is independent prose work that can land anytime but is sequenced last because it touches review/verdict vocabulary that should be defined once, coherently.

**Two distinct surfaces:** validators + CI operate on the **plugin repo** (commit/PR time, Linux CI, no Xcode). Hooks operate **only when the plugin is loaded into an app-dev session** against the separate `Unleashed Mail.xcodeproj` repo — in the plugin repo they are inert (no matching files, no xcodebuild). This split is intentional and mirrors how `scripts/pre-commit-checks.sh` already branches on `HAS_XCODEPROJ`.

## Milestones

**Phase 0 — Foundation**
- [x] Item 1 — Version-sync validator (`scripts/validate-version-sync.sh`) wired into `pre-commit-checks.sh` FALSE branch ✅ green at HEAD; catches drift in strict
- [x] Item 2 — Plugin-assembly validator (`scripts/validate-plugin-assembly.py`) wired into same branch ✅ green at HEAD; catches broken frontmatter in strict
- [x] Item 7 — Plugin CI workflow (`.github/workflows/plugin-ci.yml`, SHA-pinned actions) running the **existing** `mcp/review-synthesizer/tests` suite + both validators (strict) + shellcheck + py_compile ✅ local mirror green

**Phase 1 — Safety hooks**
- [ ] Item 3 — PreToolUse sensitive-file guard (`scripts/sensitive-file-guard.sh`), `ask`-only, warn-first
- [ ] Item 4 — Stop-gate on cached build/lint marker (`scripts/stop-quality-marker-gate.sh` + marker writers)

**Phase 2 — Session / observability hooks**
- [ ] Item 10 — Bounded diagnostic logs (`stop-failure-log.sh`, `permission-denied-log.sh`) — smallest, validates new-event wiring
- [ ] Item 5 — PreCompact snapshot + SessionStart(`source:"compact"`) restore (2 scripts)
- [ ] Item 6 — SubagentStop reviewer-verdict capture (`scripts/capture-reviewer-verdict.sh`), synthesizer-ingestible

**Phase 3 — Prompt-pattern / process**
- [ ] Item 12 — Agent Output-Contract status enum on the 4 reviewers (+ swift-reviewer/orchestration/contracts threading)
- [ ] Item 8 — Plan-review synthesis skill (`skills/review-synthesis/SKILL.md`) — bumps skills count 17→18
- [ ] Item 9 — Decision-support option tables in `commands/brainstorm.md` (+ `AskUserQuestion` allowed-tool)

## Progress Log

### 2026-06-25
- Plan authored from 5-agent research pass over `octo-repo` (source) and the live plugin repo (target).
- All octo source mechanisms read directly; all target current-state facts verified (auto-discovery manifest, PostToolUse-only `hooks.json`, `HAS_XCODEPROJ` branch, synthesizer schema, reviewer JSON emit contract).
- Rebased baseline to **v2.3.0** (plugin.json + README H1 + latest `### v2.3.0` all in sync; counts line now carries a 4th token `· 1 MCP server`). Item 1 updated to parse/validate the MCP-server count; the Item 8 skill addition now targets the `v2.3.1` bump.
- Gated through both reviewers (round 1): **gemini-review → APPROVE_WITH_NITS**, **codex-review → REQUEST_CHANGES** ⇒ combined **REQUEST_CHANGES**.

### 2026-06-25 — Round 2 (post-review revision)
Addressed every blocking item + nit from both reviewers (all claims verified against the repo first):
- **codex Critical #1 (Item 3):** no-match / warn / off paths now **omit** `permissionDecision` — never emit `"allow"` (which would auto-approve and skip the prompt).
- **codex Critical #2 (Item 5):** `PostCompact` has no decision channel (plain stdout); `SessionStart` uses `additionalContext`/plain stdout — dropped the wrong `{"decision":"continue",…}` shape.
- **codex Critical #3 (Item 10):** `StopFailure` reads `error`/`error_details`/`last_assistant_message` (not `error_type`/`error_message`); log a coarse **error class** only; corrected `PermissionDenied` scope (auto-mode classifier denials only — does **not** capture the Item 3 guard or manual denials).
- **codex Critical #4 (Item 7):** the synthesizer **already ships 46 passing tests** (`mcp/review-synthesizer/tests/`, README-documented) — reframed Item 7 from "write tests" to "CI runs the existing suite"; removed the new `tests/test_synthesizer.py` and the `filecmp` drift canary (the `mcp/`↔`prototypes/` copies already diverge by design).
- **codex Strong #1:** new `hook-io.sh` reads stdin-JSON-then-`CLAUDE_TOOL_ARG_*`; Phase 0 confirms the live contract via `claude --debug`; existing scripts migrate.
- **codex Strong #2 / gemini Strong #2:** PII hardening — markers store a repo **hash** not the abs path; reviewer `evidence` sanitized+capped; `StopFailure` logs a class, never raw error text.
- **codex Strong #3:** CI runs **both** validators in strict mode (not just assembly).
- **codex Strong #4 (Item 6):** dropped GNU-only `realpath -m` for a portable resolver; capture the **four specialists**, explicitly excluding `swift-reviewer`.
- **codex Strong #5 / gemini Critical:** quote `${CLAUDE_PLUGIN_ROOT}` in all hook commands; quote/standardize all state paths to the space-free `~/.claude/unleashed-mail` base.
- **codex Nice #1/#2:** removed `{"decision":"approve"}`; per-kind (lint/build) markers; flagged the root-vs-`hookSpecificOutput` Stop nesting to verify before enforce.
- **gemini #3/#5:** `wc -l` whitespace coercion (Item 1); broadened the PreCompact ticket fallback to app `1.0X/…` branches.
- Re-gated (round 2): **gemini → APPROVE_WITH_NITS** (3 nits), **codex → REQUEST_CHANGES** (1 Critical + 3 Strong) ⇒ combined **REQUEST_CHANGES**.

### 2026-06-25 — Round 3 (post-review revision)
Round-2 findings hinged on exact Claude Code hook contracts, so before editing I **verified them against the official docs ([code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks)) and octo's shipping hooks** — the claude-code-guide agent and codex had *contradicted each other* on field names, so neither was trusted blindly:
- **Item 5 (codex Critical):** confirmed `PostCompact` cannot inject context; restore restructured onto **`SessionStart` `source:"compact"`** (drops `postcompact-restore.sh`). This also collapses gemini's double-restore nit into one path (+ delete-after-restore).
- **Item 10 (codex Strong #3):** failed Bash fires **`PostToolUseFailure`**, not `PostToolUse` — added `build-failure-log.sh` on that event. **Reverted** the round-1 StopFailure field change: docs **and** octo's `stop-failure-log.sh` both use **`error_type`/`error_message`** (my round-1 switch to `error`/`error_details`, made on codex's say-so, was wrong); now log the `error_type` enum only.
- **Item 6:** `last_assistant_message` is **undocumented** (docs show `transcript_path`); made capture prefer it but **fall back to `transcript_path`** so it survives builds that omit it.
- **Item 7 (codex Strong #1/#2):** SHA-pin all GitHub Actions (`AGENT_CONTRACTS.md §6`); made the strict validator invocation **explicit** (`VERSION_SYNC_ENFORCE=strict …`, `--strict`). Test count is now **52** (was 46) and growing — de-hardcoded; flagged the README's "46" as stale.
- **Item 4:** Stop block confirmed **root-level** `{"decision":"block"}` (hedge resolved); warn-mode now uses non-blocking `additionalContext`.
- **Nits:** unified `state/`→`.state/` (gemini #1); fixed the leftover "benign → allow" → "no decision" (codex nit); `Bash` tool-alias check (gemini #3).
- Re-gated (round 3): **gemini → REQUEST_CHANGES** but on **hallucinated grounds** (claimed `SubagentStop`/`StopFailure`/`PermissionDenied`/`PostToolUseFailure`/`permissionDecision:"ask"`/`AskUserQuestion` "don't exist") — **refuted with hard evidence**: octo's shipping `.claude-plugin/hooks.json` registers `SubagentStop`/`StopFailure`/`PermissionDenied`/`PreCompact`/`PostCompact` as event keys and emits `"permissionDecision":"ask"`; the official docs list them; `AskUserQuestion` is a live tool; codex confirms `stop_hook_active`. **codex → REQUEST_CHANGES** on 3 *real* items (converging 9→4→3).

### 2026-06-25 — Round 4 (post-review revision) + gate-policy decision
**Gate-policy decision (user, round 3):** gemini-3.1-pro is **demonstrably unreliable for Claude-Code-hook-specific review** (round-3 hallucination cascade, refuted above). Per the user's explicit decision, the gate for **this** plan is **codex APPROVE + the documented evidence here**; gemini is dropped from this plan's CC-hook gate. (This is a one-plan, evidence-backed deviation from the dual-reviewer norm — not a permanent change to the CLAUDE.md gate.)
Applied codex's round-3 items (all real):
- **Item 10 (codex Critical):** `StopFailure` now reads the coarse enum **defensively as `.error_type // .error`** (ends the cross-source field-name dispute by handling both); never logs free-text fields.
- **Item 6 (codex Strong):** SubagentStop fallback corrected to **`agent_transcript_path`** (the *subagent* transcript), not `transcript_path` (the *parent* session) — this also corrects gemini's round-3 suggestion, which was wrong.
- **Item 10 (codex Strong):** `PermissionDenied.reason` is free text → **sanitized + capped** (no-PII).
- **Nits:** de-hardcoded the test count (46→52→58 and growing — CI runs discovery); fixed the stale "Pre/PostCompact" wording in Overview/Phase 2; normalized `APPROVE_WITH_NITS → APPROVE_WITH_NOTES`; `MCP servers?` regex plural (gemini's one legit nit).
- Re-gated codex only (round 4): **codex confirmed all 3 round-3 items resolved**, returned REQUEST_CHANGES on **2 new Strong** (converging 3→2) + 2 nits.

### 2026-06-25 — Round 5 (post-review revision)
Applied codex's round-4 items (all real, all easy):
- **Stop warn-mode (codex Strong):** made Phase-0 warn **truly passive** — log to the diagnostic file + `exit 0`, no stdout/`additionalContext` (on `Stop`, stdout is debug-only and `additionalContext` continues the turn, so neither is a passive "surface").
- **Item 8 (codex Strong):** added the **`.claude-plugin/plugin.json` `2.3.0`→`2.3.1` bump** to Files Changed — without it, Item 1's own strict version-sync validator would fail after Item 8 (plus a marketplace.json description-count refresh).
- **Nits:** removed the last hardcoded "46-case" (discovery now finds **61** — 46→52→58→61); reframed the CC version floors as **best-effort field-presence gates** (octo-sourced, not on the public hooks page).
- Re-gated codex only (round 5): **codex → `APPROVE_WITH_NITS`** (Critical: none; Strong: none) — both round-4 Strong items confirmed resolved; codex independently re-validated all hook contracts against the live docs. **GATE SATISFIED.**

### 2026-06-25 — Phase 0 IMPLEMENTED (COREDEV-2322)
- Filed **Epic COREDEV-2321** + child **Task COREDEV-2322**; work on branch `feat/COREDEV-2322-octo-phase0-validators-ci` (note: the working tree was later switched back to `feat/v2.3.0-review-synthesizer-mcp`, so the uncommitted Phase-0 files currently live there — git commit/branch placement left to the owner).
- **New:** `scripts/validate-version-sync.sh` (Item 1, `+x`), `scripts/validate-plugin-assembly.py` (Item 2, `+x`, stdlib-only), `.github/workflows/plugin-ci.yml` (Item 7, actions SHA-pinned to `actions/checkout@11bd719` v4.2.2 / `actions/setup-python@0b93645` v5.3.0).
- **Edited:** `scripts/pre-commit-checks.sh` — both validators run in the `HAS_XCODEPROJ=false` branch (warn mode).
- **Verified locally (full CI mirror, all green):** `py_compile` OK; `unittest discover` → **Ran 66 tests, OK** (suite grew 46→52→58→61→66 across this work — de-hardcode vindicated); version-sync strict ✅ (`20/17/3/1` match); plugin-assembly strict ✅; `shellcheck -s bash -S warning` ✅ (fixed an SC2034 in my own script); pre-commit FALSE-branch wiring ✅. Negative tests: version drift → exit 1; stripped `description` → exit 1.
- **Not committed** (per owner's "commit only when asked"). Next: commit Phase 0 on its branch → open PR (CI runs warn-first, not yet a required check) → then Phase 1 (safety hooks).

### 2026-06-25 — APPROVED
- Cleared codex's 3 round-5 cosmetic nits (risk-register warn-mode wording; stale `52`/`58`→`~61` count prose; stale Item-6 `transcript_path`→`agent_transcript_path` edge line).
- **Gate outcome:** codex `APPROVE_WITH_NITS` (≡ project `APPROVE_WITH_NOTES`). gemini excluded for this plan (documented round-3 hallucination cascade, refuted with octo `hooks.json` + docs evidence). Convergence: codex substantive findings 9→4→3→2→0.
- **Next:** create/link the COREDEV Jira ticket, then implement **Phase 0** (Items 1, 2, 7) as the opening PR on a dedicated branch.

## Detailed Item Specs

> `octo-repo/…` paths refer to the **claude-octopus** source repo ([github.com/nyldn/claude-octopus](https://github.com/nyldn/claude-octopus)); clone it locally to follow the citations.
> Target paths are relative to this plugin repo root (`unleashed-mail-plugin`).

---

### Item 1 — Version-sync validator

**Source:** `octo-repo/scripts/validate-release.sh` §"VERSION SYNC CHECK" (~lines 51–129) — the grep+sed version extractor, string compare, and `errors`-accumulator exit pattern. **Strip everything octo-specific:** the hardcoded `"octo"` name check, `package.json`/`codex-plugin`/`cursor-plugin`/`factory-*` loops, the `Version-X.Y.Z` README *badge* form, git-tag/zip/`claude plugin validate` sections, and the `jq` marketplace.json version extraction (unleashed's marketplace.json has **no** version field — asserting one would always fail).

**What it does:** Asserts the version is in sync across the three sources of truth and that README asset counts match disk:
1. `PLUGIN_VERSION` ← `.claude-plugin/plugin.json` `"version"`.
2. `README_H1_VERSION` ← `grep -m1 -oE 'Plugin v[0-9]+\.[0-9]+\.[0-9]+' README.md | sed 's/Plugin v//'` (anchor on ASCII `Plugin v` to dodge the em-dash in the H1).
3. `README_WHATSNEW_VERSION` ← `grep -m1 -oE '^### v[0-9]+\.[0-9]+\.[0-9]+' README.md | sed 's/^### v//'` (first/newest `### vX.Y.Z`).
4. **Asset counts** from the canonical bold counts line — as of v2.3.0 this is `**20 agents · 17 skills · 3 commands · 1 MCP server**` (note the **new 4th token** `· N MCP server`) — checked vs disk: `find agents -maxdepth 1 -name '*.md' | wc -l`, `find skills -mindepth 1 -maxdepth 2 -name SKILL.md | wc -l`, `find commands -maxdepth 1 -name '*.md' | wc -l`, and the MCP-server count from `python3 -c 'import json;print(len(json.load(open(".mcp.json"))["mcpServers"]))'` (currently 1). Anchor each README count regex independently on `[0-9]+ agents` / `[0-9]+ skills` / `[0-9]+ commands` / `[0-9]+ MCP servers?` (allow the optional plural `s`; gemini-review Nice, round 3) (do **not** put the UTF-8 middot `·` inside the regex — keep it `LC_ALL=C`-safe; match the bold line `^\*\*[0-9]+ agents` so historical "(up from X)" prose is never matched). The `MCP server` token is **optional** (treat absence as "skip", presence as "must match `.mcp.json`") so the check survives a future README that drops it.

**Target wiring:** New `scripts/validate-version-sync.sh` (`#!/usr/bin/env bash`, `set -euo pipefail`, self-locates root via `BASH_SOURCE`). Called from the `HAS_XCODEPROJ=false` branch of `scripts/pre-commit-checks.sh`, immediately before the universal PII section, using the existing `EXIT_CODE` accumulator. Lowest-risk insertion is a new top-level `if [ "$HAS_XCODEPROJ" = false ]; then …validators…; fi` block rather than restructuring the triple-guard.

**Hook contract:** N/A — shell validator invoked by the git pre-commit script; no stdin/stdout JSON.

**Edge cases:**
- Pick **one** drift direction and name it in the error ("README v2.3.0 != plugin.json 2.3.1 — bump README H1"). plugin.json is the comparison anchor.
- `set -e` + a non-matching `grep` exits 1 → guard each extraction with `|| true`, then explicitly error on empty ("could not parse version from README").
- Skill count is **directories** (`skills/<name>/SKILL.md`), `-maxdepth 2` prevents over-count from a stray nested SKILL.md. `prototypes/`/`mcp/` are out of the `find` scope.
- **BSD `wc -l` left-pads its count with leading spaces** — a raw string compare against the README token spuriously fails. Coerce both sides with `$(( ))` arithmetic or `tr -d ' '` before comparing. *(gemini-review nit, round 1.)*

**Kill-switch / rollout:** `SKIP_PLUGIN_VALIDATORS=1` hard-bypasses the whole new block. Per-validator `VERSION_SYNC_ENFORCE=${VERSION_SYNC_ENFORCE:-warn}` — `warn` prints mismatches but `exit 0`; flip to `strict` after one clean cycle. Mirrors the existing PII section's warn-don't-block house style.

**Verification:** Green at HEAD (plugin 2.3.0 == README H1 == latest `### v2.3.0`; 20/17/3/1 == disk). Drift injection on a scratchpad copy: bump plugin.json → exit 1 naming README mismatch; delete an `agents/*.md` → exit 1 naming agents drift.

**Effort:** S. **Depends on:** none, but shares the `pre-commit-checks.sh` FALSE-branch edit with Item 2 — author both insertions in one edit.

---

### Item 2 — Dependency-free plugin-assembly validator

**Source:** `octo-repo/scripts/validate-plugin-assembly.py` — port verbatim: `extract_frontmatter()` (hand-rolled YAML, no PyYAML; handles `#`, blanks, `|`/`>` block scalars), `KEBAB_RE = ^[a-z0-9]+(?:-[a-z0-9]+)*$`, `require_frontmatter()`, `validate_json()`, `validate_plugin_manifest()` with `REQUIRED_PLUGIN_FIELDS = ("name","version","description")`, `validate_json_files()`, and the `main()` accumulate + exit 0/1 contract. **`octo-repo/tests/test-command-registration.sh` is the anti-pattern** — do NOT port any registration cross-check.

**What it does (CRITICAL divergence — drop registration cross-checks):** Unleashed uses Claude Code **auto-discovery**; `plugin.json` enumerates **zero** asset arrays. So **drop** `validate_agent_config_refs` (no `agents/config.yaml`) and any "entry resolves on disk" / "file is registered" logic — both are wrong here. Retargeted checks:
1. **Manifest** — `.claude-plugin/plugin.json` exists, JSON-loads, has `name`/`version`/`description`.
2. **JSON loads cleanly** — `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json`, **`hooks/hooks.json`** (real JSON here; octo's lives at `.claude-plugin/hooks.json`). `if file.is_file()` guards for optionals.
3. **Agents** — `agents/*.md` (flat): `require_frontmatter(required=("name","description"), validate_name=True)`.
4. **Skills** — `skills/*/SKILL.md`: same required set + kebab `name`.
5. **Commands** — `commands/*.md`: `require_frontmatter(required=("description",))` — **no `name`, no kebab** (confirmed: all 3 commands carry only `description`/`allowed-tools`/`disable-model-invocation`).
6. **Summary** — `OK — plugin assembly: N skills, N commands, N agents`; exit 0/1.

**Target wiring:** New `scripts/validate-plugin-assembly.py` (`#!/usr/bin/env python3`, stdlib-only). Wired right after the version-sync call in the same `HAS_XCODEPROJ=false` block: `python3 "$(dirname "$0")/validate-plugin-assembly.py" --root "$(dirname "$0")/.." || EXIT_CODE=1`. `python3` is already the sanctioned interpreter (`.mcp.json` declares it). This script also becomes the single source of truth that Item 7's CI runs.

**Hook contract:** N/A — Python validator invoked by the pre-commit script.

**Edge cases:**
- **No registration assertion** (the #1 porting trap — restated).
- `description: >` / `|` block scalars store as truthy `">"`/`"|"` then absorb the next indented line → the truthiness check passes. Add a `description: >` fixture to lock this regression.
- CRLF/BOM: `extract_frontmatter` handles `\r\n` via `splitlines()` but not a UTF-8 BOM — optionally `text.lstrip("﻿")` (macOS files are LF/no-BOM, but Windows edits could trip it).
- Keep JSON candidate list **non-recursive** so `prototypes/**` intentionally-malformed fixtures and `mcp/**` are never validated.
- Drop octo's legacy `.claude/{skills,commands,agents}` branches (unleashed has only top-level dirs).
- `.mcp.json` uses `${CLAUDE_PLUGIN_ROOT}` — a plain string, valid JSON, no special handling.

**Kill-switch / rollout:** Same `SKIP_PLUGIN_VALIDATORS=1` master switch; per-validator `PLUGIN_ASSEMBLY_ENFORCE=${PLUGIN_ASSEMBLY_ENFORCE:-warn}` gates the `EXIT_CODE=1` in the shell wrapper. Flip to `strict` after one clean cycle and after CI adopts it.

**Verification:** Green: `OK — plugin assembly: 17 skills, 3 commands, 20 agents`. Negative fixtures (scratchpad copy): broken `.mcp.json` brace → invalid-JSON exit 1; non-kebab agent `name` → exit 1; command missing `description` → exit 1; `description: >` agent → still passes; plugin.json missing `version` → exit 1. Run twice → byte-identical (octo `sorted()` every glob — keep it).

**Effort:** M. **Depends on:** none at runtime; shares the FALSE-branch edit + kill-switch with Item 1 (single combined edit). CI (Item 7) consumes this script.

---

### Item 3 — PreToolUse sensitive-file guard → `permissionDecision: "ask"`

**Source:** `octo-repo/hooks/freeze-check.sh` (path extraction + trailing-slash prefix fix lines 68–69 that stops `/src` matching `/src-old`), `hooks/scheduler-security-gate.sh` (line 69 `jq -r '.tool_input.file_path // .tool_input.path // ""'`; line 73 `realpath` symlink-safety), `hooks/careful-check.sh` (the canonical **`ask`** template + kill-switch line 21). **Do NOT copy octo's flat legacy JSON** (`{"permissionDecision":"ask","message":...}` — wrong nesting, wrong key).

**What it does:** On Edit/Write/MultiEdit (and Bash for risky redirects), checks whether the target matches a **basename signature** of a CLAUDE.md "Ask Before Modifying" / Security-table asset, and if so emits `permissionDecision: "ask"` so the user confirms. Never `deny` — the user is always in the loop.

**Target wiring:** New `scripts/sensitive-file-guard.sh` (`chmod +x`). New `PreToolUse` block in `hooks/hooks.json` (currently PostToolUse-only) using the **string-matcher** form already used in that file:
```json
"PreToolUse": [
  { "matcher": "Write|Edit|MultiEdit", "hooks": [ { "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/sensitive-file-guard.sh\"" } ] },
  { "matcher": "Bash",                  "hooks": [ { "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/sensitive-file-guard.sh\"" } ] }
]
```
**Quote `${CLAUDE_PLUGIN_ROOT}`** in the command string (as above) on **every new hook entry** — an unquoted expansion misfires if the plugin is installed under a path containing a space. The **existing** `hooks/hooks.json` entries (`bash ${CLAUDE_PLUGIN_ROOT}/scripts/swift-*.sh`, currently unquoted) should be quoted in the same PR. *(codex-review Strong #5, round 1.)*
The script reads **stdin JSON** itself (the existing PostToolUse hooks read `CLAUDE_TOOL_ARG_*` env vars and block by exit code, which cannot express `ask`). Branch on `tool_name`; extract `file_path` (`// .tool_input.path` fallback) or Bash `command`; resolve to absolute then `realpath` (fall back to lexical path if it fails — advisory, never block-on-unresolvable). Match a **basename signature set** (not directory prefixes — sidesteps the embedded space in `Unleashed Mail/Sources/`): `Info.plist`, `*.entitlements`, `project.pbxproj`/`*.xcodeproj`, `KeychainManager`/`Keychain*`, high-signal auth stems (`MSAL`, `OAuth`, `TokenStore`, `AuthService`), `DatabaseService*`/`*Migration*`/`*Repository*`/`*SQLCipher*`, `*WebView*`/`*EmailWeb*`/`HTMLSanitiz*`, `*.mobileprovision`.

**Hook contract:**
- **Event:** `PreToolUse`. **Reads (stdin):** `tool_name`, `tool_input.file_path` (`// .tool_input.path`), `tool_input.command`.
- **Emits (stdout, exit 0) only on match:**
```json
{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "ask",
  "permissionDecisionReason": "Edits to KeychainManager.swift touch credential storage. CLAUDE.md requires confirmation before modifying auth/token handling. Proceed?" } }
```
- **No match:** emit **nothing** (`{}` / empty stdout / `exit 0`) — **do NOT emit `permissionDecision:"allow"`.** Per the current [Claude Code hooks reference](https://docs.anthropic.com/en/docs/claude-code/hooks), `"allow"` *bypasses the normal permission prompt*; an ask-only guard that returns `allow` on no-match would silently auto-approve every Write/Edit/Bash that didn't match a signature. Only the **match** case emits `permissionDecision:"ask"`. `permissionDecisionReason` carries **only the basename** — never file contents, never PII. *(codex-review Critical #1, round 1.)*

**Edge cases:**
- **`*Auth*` over-match / alert fatigue** — anchor to `.swift` basenames, exclude `*Tests.swift` and docs; prefer an explicit high-signal stem allowlist over broad `*auth*` (avoids `Author`/`Authorization`).
- **Bash bypass** — scan `tool_input.command` for `>`/`tee`/`sed -i`/`mv|cp` *targeting* a signature; a read-only `grep KeychainManager` must NOT trigger.
- **Plugin-repo reality** — the Swift app isn't checked out here, so the hook is essentially dormant in the plugin repo; tests must simulate stdin, not rely on real files.
- `MultiEdit`/future tools carry `file_path` too — include via the `// .tool_input.path` fallback.
- Never escalate to `deny`. Document that consecutive Edits each prompt (acceptable for `ask`).

**Kill-switch / rollout:** `UNLEASHED_SENSITIVE_GUARD=off` → emit nothing, `exit 0` (fall through to normal prompting — **never** `allow`). Two-phase via `UNLEASHED_SENSITIVE_GUARD_MODE=warn|ask` (default `warn` on first commit): **Phase 0 (warn)** emit only a non-deciding `systemMessage` advisory and **omit `permissionDecision`** (so the standard prompt still applies); **Phase 1 (ask)** emit `permissionDecision:"ask"` on a match once the signature set is tuned; `=off` overrides both. No mode ever emits `allow`. *(codex-review Critical #1, round 1.)*

**Verification:** stdin simulations (no app needed): a `KeychainManager.swift` path under `Unleashed Mail/Sources/…` → `ask` (also proves the space survives); an `InboxView.swift` → **no decision** (omit `permissionDecision`); `grep KeychainManager` Bash → **no decision**; `sed -i … KeychainManager.swift` Bash → `ask`. Assert valid JSON via `| jq .`. Add cases to `scripts/test-runner.sh`.

**Tool-name check (gemini-review Nice #3, round 2):** the matcher targets `Write|Edit|MultiEdit|Bash`. Confirm at implementation that no reviewer/agent aliases the shell tool (e.g. `BashCommand`/`Terminal`) that the string matcher would miss; the current CC tool name is `Bash`.

**Input-contract note (shared, codex-review Strong #1, round 1):** the **existing** PostToolUse scripts read tool input from `CLAUDE_TOOL_ARG_*` env vars (`swift-lint-check.sh:5` → `CLAUDE_TOOL_ARG_file_path`/`_path`; `swift-build-verify.sh:9` → `CLAUDE_TOOL_ARG_command`), whereas the current [hooks reference](https://docs.anthropic.com/en/docs/claude-code/hooks) defines **stdin JSON** as the command-hook input. **Phase 0 prerequisite:** empirically confirm (via `claude --debug`) whether the installed CC version still populates `CLAUDE_TOOL_ARG_*`. The new `scripts/lib/hook-io.sh` must read **stdin JSON first, fall back to `CLAUDE_TOOL_ARG_*`**, so it works regardless; the existing scripts (and the Item 4 marker writers bolted onto them) should be migrated to call it, or they risk being **silently inert**.

**Effort:** S–M. **Depends on:** the input-contract confirmation above. Build first; extract the shared `scripts/lib/hook-io.sh` (stdin-then-envvar read, extract, emit helpers) here for Item 4 to reuse.

---

### Item 4 — Stop-gate on a cached build/lint marker

**Source:** `octo-repo/hooks/quality-gate.sh` (read-marker-then-decide; never recompute — lines 15, 20–30), `hooks/workflow-verification.sh` (Stop-event + macOS/Linux `stat -f %m`/`-c %Y` freshness window, lines 47–60), `hooks/stop-failure-log.sh` (ISO-8601 UTC `date -u +"%Y-%m-%dT%H:%M:%SZ"`, atomic `>.tmp && mv`, lines 27/43), `scripts/lib/session-id.sh:59` (per-session path recipe). Octo wired `workflow-verification.sh` under **`SessionEnd`**, but `SessionEnd`'s output is ignored — to **block the agent from ending its turn** the correct event is **`Stop`**.

**What it does:** Two parts. **(1) Marker writers:** `swift-lint-check.sh` (which already computes a real lint verdict) writes a lint marker; `pre-commit-checks.sh` (which actually runs `xcodebuild build` with `BUILD_EXIT`) writes a build marker. The PostToolUse `swift-build-verify.sh` only sees the command string, not its exit status — **don't fake a verdict there.** **(2) Stop hook:** reads the **per-kind markers** (lint + build) and, if either says `fail` AND is fresh AND the commit matches, emits `{"decision":"block"}` — a fresh lint pass can never mask a stale failed build (codex Nice #2). It runs **zero** heavy work — no `xcodebuild`, no `swiftlint` (xcodebuild at Stop would add 13+ s/turn, antithetical to CLAUDE.md's "<2 s / never block" ethos).

**Marker format** (`scripts/lib/marker.sh`, shared writer; path `"${CLAUDE_PLUGIN_DATA:-$HOME/.claude/unleashed-mail}/.state/quality-marker-<kind>-<sha1(repoabspath)>.json"` — **`.state/`**, unified with Item 5 and the `.gitignore` entry; gemini-review Strong #1, round 2). **One marker per kind** (`lint` and `build`) — a fresh lint pass must never overwrite/mask a stale *failed build* marker (codex-review Nice #2). The base dir is space-free, but `CLAUDE_PLUGIN_DATA` may not be, so **quote the path in every `mkdir`/redirect** (gemini-review Critical, round 1):
```json
{ "status": "pass|fail", "kind": "lint|build", "ts": "2026-06-25T17:04:00Z", "commit": "a1b2c3d", "repo_hash": "<sha1 prefix>" }
```
`commit` via `git rev-parse --short HEAD`; per-repo-hashed filename so two checkouts don't clobber. Stored under `~/.claude/unleashed-mail/.state`, never `/tmp`, never the repo. **No PII** — status/kind/ts/short-sha + **repo *hash*** only; **never the absolute repo path** in the body (codex-review Strong #2).

**Target wiring:** New `scripts/stop-quality-marker-gate.sh`; new `Stop` block in `hooks/hooks.json` (`"matcher": ""`). Marker-write surgery into `scripts/swift-lint-check.sh` and `scripts/pre-commit-checks.sh` (build step). Add `scripts/lib/marker.sh`.

**Hook contract:**
- **Event:** `Stop`. **Reads (stdin):** `stop_hook_active` (bool), `session_id`, `cwd`.
- **Emits (stdout, exit 0) to block:** `{ "decision": "block", "reason": "Last build marker is FAILED (3 min ago, commit a1b2c3d). Fix the build before stopping. Run: xcodebuild build -scheme \"Unleashed Mail\" -destination 'platform=macOS'." }`
- **No-op:** empty / `{}` / `exit 0`. **Do NOT emit `{"decision":"approve"}`** — Stop control only recognizes an *omitted* decision or `"block"` (codex-review Nice #1).
- **Nesting confirmed (round 2, verified against [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks)):** `Stop` uses the **root-level** `{"decision":"block","reason":"…"}` form (NOT wrapped in `hookSpecificOutput`) — that hedge is resolved. Stop *also* accepts `hookSpecificOutput.additionalContext` for **non-blocking** feedback that continues the conversation.

**Edge cases:**
- **Stop-loop wedge (most important):** honor `stop_hook_active==true` → exit 0 (don't re-block); and/or a "last-blocked commit" sentinel so a genuinely broken build can still be abandoned.
- **Stale-marker false block:** TTL window (`UNLEASHED_STOP_GATE_TTL_SEC`, default 10 min) + `marker.commit != HEAD` → treat stale, exit 0.
- **No marker = no block** (unknown ≠ broken).
- **Portability:** BSD vs GNU `date` parsing of the ISO string differs — branch on `uname` (workflow-verification.sh precedent); guard with `2>/dev/null || age=999999` (fail-open).
- Plugin repo: no app build → no build marker → hook inert (correct). Favor gating primarily on the **lint** marker (continuously fresh via the PostToolUse hook); treat build as advisory.

**Kill-switch / rollout:** `UNLEASHED_STOP_GATE=off` → exit 0. **Phase 0 (warn) is TRULY passive (codex Strong, round 4):** the would-block reason is **only appended to the Item 10 diagnostic log** and the hook exits 0 with **no JSON / no stdout** — it does not block and does not inject. *(Contract note: on `Stop`, plain stdout is debug-only and may not surface, and `hookSpecificOutput.additionalContext` is **not** passive — it continues the conversation with a note under stop-hook-loop semantics. So warn mode must NOT use either to "surface"; it logs silently. If a visible-but-non-blocking nudge is ever wanted, that is `additionalContext` used deliberately as a non-error continuation — a distinct, opt-in mode, not the default warn.)* **Phase 1 (enforce):** emit root-level `{"decision":"block","reason":…}` once TTL/commit tuning proves no spurious blocks.

**Verification:** Writer test — force a lint error → marker `status:fail` with valid ts/commit. Gate tests (stdin sim): fresh fail → `block`; ts 1 h ago → exit 0; `stop_hook_active:true` → exit 0; pass marker → no block; missing marker → no block. `time` the hook → milliseconds (proves no xcodebuild); add a test that fails if the script references `xcodebuild`/`swiftlint`.

**Effort:** M. **Depends on:** marker writers must exist before the Stop read is meaningful (develop together). Reuses `scripts/lib/hook-io.sh` from Item 3 → build Item 3 first.

---

### Item 5 — PreCompact snapshot + SessionStart restore

> **⚠️ Round-2 correction (codex-review Critical, verified against [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks)):** `PostCompact` has decision-control **"None"** and **cannot inject context** — it is side-effect-only (logging/cleanup). The documented post-compaction context-delivery point is **`SessionStart` with `source == "compact"`** (the `source` enum is `startup` · `resume` · `clear` · `compact`), which injects via `hookSpecificOutput.additionalContext` *or* plain stdout. So restore moves entirely onto `SessionStart`; `PostCompact` is dropped from the restore path.

**Source:** `octo-repo/hooks/pre-compact.sh` (self-disarming `EXIT` trap lines 14–15 — port into every ported hook; `jq`-projected snapshot shape), `hooks/post-compact.sh` (reuse only its 10-min freshness check via `stat -f %m`/`-c %Y`, `age>600 → exit 0` — **deliver the re-inject from `SessionStart`, not PostCompact**), `hooks/context-reinforcement.sh:35,38` (reuse only the `python3 json.dumps` escaping helper). **Do NOT port octo's blocking path** (it gates on in-flight agents tracked in `session.json`, which unleashed lacks).

**What it does:** On `PreCompact`, snapshot the current work context (ticket, branch, newest plan, round) to a file. On `SessionStart` where `source == "compact"` (and also `resume`/`startup` as a bonus), if the snapshot is fresh (<10 min) inject a one-line resume hint via `additionalContext`, then **delete the snapshot** so it restores exactly once. Strictly non-blocking.

**Target wiring:** New `scripts/precompact-snapshot.sh` (`PreCompact`, `timeout:10`) and `scripts/sessionstart-restore.sh` (`SessionStart`, `timeout:10` — the **single** restore path; no `postcompact-restore.sh`). State dir `${CLAUDE_PLUGIN_DATA:-$HOME/.claude/unleashed-mail}/.state/work-context-snapshot.json` (never the repo). Snapshot (all PII-free — a branch name is not PII):
```json
{ "ticket": "COREDEV-1234 | v2.2.4 | unknown", "branch": "feat/v2.2.4-shared-pty-wrapper",
  "plan": "docs/planning/SHARED_PTY_PLAN.md", "round": "unknown", "snapshot_time": 1750000000 }
```
Ticket: `git rev-parse --abbrev-ref HEAD` → `grep -oE 'COREDEV-[0-9]+'` first, else the **app-repo release-branch** form `grep -oE '1\.0[0-9]/[^/]+'` (the app uses `1.0X/COREDEV-…` / `1.0X/…` branches when the plugin is loaded in an app-dev session; gemini-review Nice #5), else `grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+'` (plugin-repo branches like `feat/v2.2.4-…`), else `unknown` — never assume `COREDEV-`. Plan: `ls -t docs/planning/*_PLAN.md 2>/dev/null | head -1`, guarded by `[ -d docs/planning ]`.

**Hook contract:**
- **PreCompact:** ignores stdin (or reads `trigger: auto|manual`); writes the snapshot; output ignored (side-effect only).
- **SessionStart:** reads `source` (`startup`|`resume`|`clear`|`compact`). On `compact` (and optionally `resume`/`startup`), inject the resume hint via `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"…"}}` **or** plain stdout (both reach Claude for this event). Match narrowly with a `"matcher": "compact"` block in `hooks.json`, or read `source` in-script.

**Edge cases:**
- `docs/` absent → guard the plan read or `set -e` + non-matching `ls` aborts the hook.
- **Restore exactly once (gemini-review Nice #2, round 2):** with a single `SessionStart` restore path there's no double-fire, but **delete the snapshot after a successful restore** so a later `resume`/`startup` in the same window doesn't replay a stale hint. (No reliance on a `SUPPORTS_POST_COMPACT_HOOK` env var — CC doesn't inject one.)
- Snapshot is global (shared across checkouts) — the 10-min window + delete-after-restore are the cross-session guards; keep both.
- Wrap `git rev-parse` in `|| true`, default `unknown` (cwd may not be a repo).

**Kill-switch / rollout:** `UNLEASHED_COMPACT_SNAPSHOT=off` (snapshot), `UNLEASHED_COMPACT_RESTORE=off` (the SessionStart restore). Inherently warn-first: restore is a non-destructive `additionalContext`/stdout hint; **never** `decision:block`.

**Verification:** `git checkout -b feat/COREDEV-9999-test; mkdir -p docs/planning; touch docs/planning/TEST_PLAN.md; echo '{}' | bash scripts/precompact-snapshot.sh` → snapshot has ticket=`COREDEV-9999`, plan=`TEST_PLAN.md`. Restore within 10 min → one-liner; `touch -t` the snapshot 11 min into the past → silent exit.

**Effort:** M. **Depends on:** none, but the `round` field is best-quality after Item 6 exists (it counts captured reviewer files). Ship with `round:"unknown"` first, enrich after Item 6.

---

### Item 6 — SubagentStop capture of each reviewer's verdict

**Source:** `octo-repo/hooks/subagent-result-capture.sh` — port the **path-traversal guard** (lines 80–86: resolve result path + workspace, reject unless under workspace) and **dedup** (skip if already captured). **Do NOT port its `realpath -m`** — `-m` is a GNU coreutils flag; macOS/BSD `realpath` does not support it, and this plugin runs in **macOS** app-dev sessions, so the guard would error out. Use a portable resolver: `python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))'` (or pure-bash canonicalization). Drop the `agent-teams/` resolution (lines 53–77) and `progress.json` counter (111–150) — unleashed dispatches reviewers via the `Agent` tool, not octo teams. *(codex-review Strong #4, round 1.)*

**What it does:** On `SubagentStop`, if the subagent (matched on `agent_type`) is one of the **four specialist reviewers** — `security-reviewer`, `concurrency-reviewer`, `ux-perf-reviewer`, `accessibility-auditor` — get the reviewer's final message, extract the **last fenced ` ```json ` block** (the findings array), validate it parses as a list or `{"findings":[…]}` (the synthesizer's input shape from `mcp/review-synthesizer/schema.py`), and write it to a per-round, per-agent file directly consumable by `synthesize.py`. **Source of the message (round-3 fix, codex Strong):** prefer `last_assistant_message` (used by octo's shipping `subagent-result-capture.sh`); when absent, fall back to **`agent_transcript_path`** — the **subagent's** transcript. Do **NOT** fall back to `transcript_path`: that is the **parent session** transcript and would capture the orchestrator's turn, not the reviewer's findings. **Explicitly EXCLUDE `swift-reviewer`** — it is the orchestrator/*consumer* of the synthesizer, not a findings producer; capturing it would feed the synthesizer its own output (codex-review Strong #4). Observe-only; a missed capture never blocks (the orchestrator still collects findings in-session).

**Target wiring:** New `scripts/capture-reviewer-verdict.sh`; new `SubagentStop` block in `hooks/hooks.json` (`"matcher": ""`, `timeout:10`). Capture dir `${CLAUDE_PLUGIN_DATA:-$HOME/.claude/unleashed-mail}/reviews/<branch-slug>/round-<N>/<agent_type>.json`. Reuse the traversal guard (workspace = capture-dir root).

**Hook contract:**
- **Event:** `SubagentStop`. **Reads (stdin):** `agent_id`, `agent_type`, `agent_transcript_path` (the **subagent** transcript), `transcript_path` (the **parent** session transcript — do not use it for capture); `last_assistant_message` (best-effort). **Strategy:** use `last_assistant_message` if non-empty, else parse the final assistant message from **`agent_transcript_path`**. **Output:** none — `exit 0` (observe-only).

**Edge cases:**
- **PII (codex-review Strong #2):** don't assume `evidence`/`file` are PII-free — a reviewer can quote a code snippet containing an email fixture, a subject-line string constant, or a token. Before persisting, **sanitize each `evidence` value** (run the email/secret regex already in `pre-commit-checks.sh:89` and redact matches) and **cap its length** (e.g. 500 chars). Never write the raw `last_assistant_message` to a `.log` — only the validated, sanitized structured JSON.
- Extract the **last** ` ```json ` block (the reviewer's findings array is the report's final fence per `swift-reviewer.md`); validate, don't guess; if it doesn't parse, **don't write** (let swift-reviewer Step-5 recovery handle malformed blocks).
- Version skew: if neither `last_assistant_message` nor a readable `agent_transcript_path` yields a final message → bail silently; if `agent_type` is absent → can't filter → write to `unknown-agent-<ts>.json` only if the body is valid findings, else skip.
- Dedup must allow a **re-run** (fresh subagent) to overwrite a *bad* file → skip only if the existing file already parses as valid findings.

**Kill-switch / rollout:** `UNLEASHED_CAPTURE_REVIEWERS=off` → top-of-script exit 0. Inherently warn-first (writes a file, gates nothing).

**Verification:** Pipe a synthetic SubagentStop wrapping `prototypes/hybrid-review-synthesizer/sample_findings/security-reviewer.json` in a ` ```json ` fence with `agent_type:"security-reviewer"` → assert the hook writes `…/round-N/security-reviewer.json` byte-identical, and `python3 mcp/review-synthesizer/synthesize.py …/round-N/*.json` produces a report (proves direct consumability). Traversal: a `../../etc/x` path → no write outside the dir. Dedup: replay → no second write.

**Effort:** M–L. **Depends on:** Item 5 supplies `<branch-slug>`/round context (do Item 5 first for round bucketing; else bucket by timestamp). Closes the synthesizer's producer gap; pair with a small **stdlib `unittest`** case under `mcp/review-synthesizer/tests/` (the repo is pytest-free — keep the zero-dependency promise).

---

### Item 10 — Bounded, gitignored diagnostic logs

**Source:** `octo-repo/hooks/stop-failure-log.sh` (event `StopFailure`; JSONL line `{"ts","type","msg"}`, `jq -Rs` escaping; **500-line cap → `tail -250`**), `hooks/permission-denied-log.sh` (event `PermissionDenied`; **logs `tool_name` + `reason` only, never `tool_input`** — exactly unleashed's no-PII rule; **>100 KB → `tail -100`**). *(The `vX.Y.Z+` floors octo annotates for these events are best-effort — gate on field presence, not version; see Risk register.)*

**What it does:** Two observe-only telemetry hooks. `StopFailure` logs only the **coarse error enum**, read **defensively as `.error_type // .error`** (sources disagree on the field name across CC builds — octo's shipping hook + my docs fetch use `error_type`; codex's docs read shows `error`; the `//` fallback is correct for both — codex-review Critical, round 3). Both forms are a fixed enum (`rate_limit` · `overloaded` · `authentication_failed` · `billing_error` · `server_error` · `max_output_tokens` · `unknown` · …), so it is **PII-free by construction**; **never log the free-text `error_message`/`error_details`/`last_assistant_message`** (they can embed `/Users/<name>/…` paths or tokens). `PermissionDenied` logs `tool_name` + a **sanitized, capped `reason`** — `reason` is free-text classifier explanation (NOT an enum), so run it through the email/secret regex (`pre-commit-checks.sh:89`) and truncate (codex-review Strong, round 3); **never `tool_input`.** ⚠️ **Scope (codex Critical #3, round 1):** `PermissionDenied` fires **only for auto-mode permission-classifier denials** — NOT manual user denials, and NOT the Item 3 guard's prompts (which emit `ask`, not `deny`); it is a low-traffic auto-mode-denial audit, not a record of guard activity. **Build/test failure capture (codex Strong #3, round 2):** a failed `xcodebuild` does **not** reach `PostToolUse` (which fires only on tool *success*) — wire a separate **`PostToolUseFailure`** (matcher `Bash`) hook to log a bounded **command-class + failed** line. The existing `swift-build-verify.sh` PostToolUse path can still log a "build/test *attempted*" class on success, but pass/fail comes from `PostToolUseFailure` (failure) — never the full command (it may contain a signing identity or `-archivePath`).

**Target wiring:** New `scripts/stop-failure-log.sh` (`StopFailure`, `timeout:5`), `scripts/permission-denied-log.sh` (`PermissionDenied`, `timeout:5`), and `scripts/build-failure-log.sh` (`PostToolUseFailure`, matcher `Bash`, `timeout:5` — the build/test-failed class line). Logs under `${CLAUDE_PLUGIN_DATA:-$HOME/.claude/unleashed-mail}/logs/*.jsonl`. **Add `*.jsonl`, `.state/`, `reviews/`, `logs/` to `.gitignore`** — the existing `*.log` glob does **not** cover `error-log.jsonl`.

**Hook contract:**
- **`StopFailure`**: read the coarse enum **defensively as `.error_type // .error`** and log *only* that. *(Field-name saga, now resolved by dual-read: octo's shipping `stop-failure-log.sh:30-31` + my docs fetch show `error_type`/`error_message`; codex's docs read shows `error`/`error_details`. Rather than pick a side, read both — `.error_type // .error` — so it's correct on any build; codex-review Critical, round 3.)* **Never** log `error_message`/`error_details`/`last_assistant_message`. Output/exit **ignored** by CC (pure side-effect).
- **`PostToolUseFailure`** (matcher `Bash`): reads `tool_name`, `tool_input`, `error` (+ optional `error_code`); cannot block (tool already failed). Use it for the build/test-**failed** class line; read only the command *class*, never the raw command/error.
- **`PermissionDenied`**: reads `tool_name` and `reason` (free-text classifier explanation, **not** an enum) — **sanitize + cap `reason`** before logging (codex-review Strong, round 3); **`tool_input` deliberately NOT read**; `exit 0`. Fires for **auto-mode classifier denials only** (see What it does).

**Edge cases:**
- **No-PII is the crux.** For the build variant log a fixed class (`xcodebuild-build`/`xcodebuild-test`) + pass/fail boolean only; never `tail` raw build output (it can echo source strings). For `StopFailure`, log **only the coarse enum (`.error_type // .error`)** — a fixed enum, inherently PII-free; **never** store `error_message`/`error_details`/`last_assistant_message` (gemini Strong #2 / codex round 3).
- Drop octo's careful-mode gate on the denial log (unleashed has no careful mode); always log denials (safe — tool-name-only). Optional opt-in `UNLEASHED_DENY_LOG=on`.
- Keep each record a single atomic `printf >>`.

**Kill-switch / rollout:** `UNLEASHED_FAILURE_LOG=off`, `UNLEASHED_DENY_LOG=off`. Output is ignored by CC → zero behavior-change risk; safe to ship enabled.

**Verification:** Pipe `{"tool_name":"Edit","reason":"blocked path","tool_input":{"file_path":"/Users/x/secret"}}` → log contains `tool=Edit` + `reason=blocked path` and **does NOT contain** `/Users/x/secret` (load-bearing PII assertion). Rotation: append 600 lines → file is 250 after next write. Build-fail capture → a `{"kind":"build"}` line with no path/token.

**Effort:** S — smallest, fully independent. **Depends on:** none. Land first in Phase 2 to validate the new-event wiring pattern in `hooks/hooks.json`.

---

### Item 7 — Lightweight plugin CI (runs the EXISTING synthesizer suite + validators)

> **⚠️ Round-1 correction (codex-review Critical #4):** the synthesizer is **already tested** — `mcp/review-synthesizer/tests/` ships passing stdlib `unittest` cases (`test_synthesize.py`, `test_schema.py`, `test_mcp_server.py`), **growing across review rounds** (46→52→58→61 as tests were added — so the CI runs discovery and never hardcodes a count). The earlier "the synthesizer has zero tests / write `tests/test_synthesizer.py`" premise is **obsolete** (those tests were the v2.3.0 feature). This item is now **purely CI wiring** for the suite that exists — it creates **no** new test file and **no** `filecmp` drift canary (the `mcp/` and `prototypes/` copies already diverge by design — `prototypes/` is a throwaway prototype, not kept in sync). **Note:** `README.md:15`/`:260` still say "46 unit tests" — now **stale** vs the ~61 on disk; the README count should be refreshed (the version/count validator in Item 1 does **not** cover the test count, only agents/skills/commands/MCP).

**Source:** `octo-repo/.github/workflows/test.yml` — borrow the **portability-lint** (GNU-only `sed` address-range-grouping grep, their issue-#255 class), the **ShellCheck** step, `actions/checkout` + `permissions: contents: read` + `timeout-minutes` hardening, and a tiny `$GITHUB_STEP_SUMMARY` block. **Pin every `uses:` action to a full commit SHA** (with a trailing `# vX.Y.Z` comment), **not** a `@vN` tag — `AGENT_CONTRACTS.md §6` mandates SHA pins and `security-reviewer` flags `@vN` as 🟡 WARNING (codex-review Strong #1, round 2). **Omit** the tiered change-classifier (overkill for one small repo) and **do not port** `tests/helpers/test-framework.sh` (bash xUnit — wrong tool; the synthesizer is Python → stdlib `unittest`, which it already uses).

**What it does:** One `ubuntu-latest` job (no matrix, no Xcode — this repo has no `.xcodeproj`; Swift work is Xcode-Cloud-owned) that: `py_compile`s `mcp/review-synthesizer/*.py`; runs the **existing** suite `python3 -m unittest discover -s mcp/review-synthesizer/tests` (the count **keeps growing** — 46→52→58 across review rounds — so **never hardcode it** in the workflow; just run discovery); runs **both** validators with an **explicit strict invocation** — `VERSION_SYNC_ENFORCE=strict bash scripts/validate-version-sync.sh` (Item 1 defaults to `warn`, so CI MUST set this or drift won't fail the build — codex-review Strong #2/#3, round 2) **and** `python3 scripts/validate-plugin-assembly.py --root . --strict` (Item 2 must expose a `--strict`/non-zero-exit mode for CI); runs the portability `sed` lint; runs `shellcheck -s bash -S warning scripts/*.sh .githooks/*` (target scripts pass clean at `-S warning` today). Writes a `$GITHUB_STEP_SUMMARY` table.

**Target wiring:** New `.github/workflows/plugin-ci.yml` (first workflow; triggers `push`/`pull_request` to `main` + `workflow_dispatch`; `concurrency` cancel-in-progress; `actions/setup-python` **pinned to a commit SHA** with `python-version: '3.12'` — SHA pin per §6, *not* `@v5`). **No new test file** — point unittest at the shipped `mcp/review-synthesizer/tests` directory. Do **not** add a `prototypes/`↔`mcp/` drift canary: the two copies already diverge intentionally (`prototypes/` is a prototype, not kept in sync).

**Hook contract:** N/A — ships no Claude Code hook; pure repo CI + Python tests.

**Edge cases:**
- Scope `unittest discover` to `mcp/review-synthesizer/tests` (its own dir), so it never imports the `prototypes/` copies.
- Verify `.githooks/pre-commit` shebang before `-s bash` (if `#!/bin/sh`, lint it as POSIX or drop the bash flag for it).
- `sed` portability grep is a heuristic (targets `/pat/,/pat/{`) — suppress with a comment if a legitimate single-line `s///` trips it.
- Keep the workflow **version-agnostic** at the YAML level (the version *check* is Item 1's validator step, invoked here; the workflow file itself hardcodes no version) so `v2.3.x` bumps don't break CI.
- The existing suite already covers the subtle contracts (the `render_report` vs `render_markdown` verdict split, `schema._as_line` bool/float coercion, the JSON-RPC protocol via subprocess) — CI just runs them; no new assertions are authored in this item.

**Kill-switch / rollout:** The workflow's off-switches are its branch filters + `workflow_dispatch`. Warn-first: add `continue-on-error: true` (or `|| true` on shellcheck) for the first PR, observe, then remove; don't mark "required" in branch protection until after the warn-first window. (The validator *steps* run strict — Strong #3 — even while the overall job is warn-first on its first PR.)

**Verification:** Local mirror of CI (all gates green at HEAD today): `python3 -m unittest discover -s mcp/review-synthesizer/tests -v` (→ `Ran N tests … OK`, N growing over time) `&& shellcheck -s bash -S warning scripts/*.sh && python3 -m py_compile mcp/review-synthesizer/*.py && VERSION_SYNC_ENFORCE=strict bash scripts/validate-version-sync.sh && python3 scripts/validate-plugin-assembly.py --root . --strict`. Then open a draft PR introducing a deliberate failure (drop a frontmatter `description`) → confirm red; revert → green; don't mark required until after a warn-first PR.

**Effort:** S–M (just YAML now — the test suite already exists and passes). **Depends on:** Items 1 **and** 2 for the two validator steps — keep CI independently shippable by landing the unittest/shellcheck/py_compile steps first and adding each validator step in the PR that introduces it. No dependency on any hook item.

---

### Item 8 — Plan-review synthesis across gemini + codex (SCHEMA ONLY)

**Source:** `octo-repo/skills/skill-council/SKILL.md:106` — the chair-synthesis schema (agreement, disagreement, minority reports, risk register, implementation path, confidence, conditions-that-would-change). Lift the *spirit* of lines 99 ("if quorum is lost, stop and present partial artifacts, don't fake consensus") and 115 ("preserve disagreement, keep vetoes visible"). **Do NOT port** `orchestrate.sh`, quorum tiers, persona/member machinery, `AskUserQuestion` preflight, or Gates A/B/C — unleashed has exactly two fixed reviewers, no chair selection, no budgets.

**What it does:** A read-only skill the human/agent invokes **after both plan-review transcripts are captured**, that parses a verdict token out of each prose transcript and emits a fixed Markdown synthesis block (the auditable record that the `AGENT_CONTRACTS.md §2` "both must APPROVE" gate passed, surfacing any disagreement).

**Target wiring:** New `skills/review-synthesis/SKILL.md` (`/unleashed-mail:review-synthesis`). **Inputs default to the two transcript paths** the existing review skills already write: gemini → `/tmp/agy-out.txt`, codex → `/tmp/codex-out.txt` (both free-form plaintext). Output (plain markdown, **no octo emoji**): `## Plan-Review Synthesis`, `**Combined verdict:** APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES | DISAGREEMENT` (canonical project terms; `NITS` from the CLI is normalized to `NOTES`), then `### Agreement` / `### Disagreement` / `### Minority report` / `### Risk register` (table) / `### Conditions that would change the recommendation` / `### Confidence`. Add a step 3a to `AGENT_CONTRACTS.md §2`, plus a one-line pointer in `gemini-review/SKILL.md` and `codex-review/SKILL.md`. **README skills count 17→18.**

**Verdict-combination rule:** both APPROVE/APPROVE_WITH_NOTES → `APPROVE` (NOTES if either had notes); either REQUEST_CHANGES → `REQUEST_CHANGES`; opposite verdicts → `DISAGREEMENT` (surface, don't average); a missing/empty/0-byte transcript → cannot claim `APPROVE`, emit `DISAGREEMENT`/`REQUEST_CHANGES` + low confidence.

**Hook contract:** N/A — markdown skill, no stdin/stdout event.

**Edge cases:**
- **No-PII:** plan transcripts may quote addresses/subjects; the skill must reference findings by location/topic, never echo PII into the block.
- **Fuzzy verdict parsing:** gemini prose ("approve with a couple of nits") needs a normalization step → 4-token enum; when ambiguous, default to the conservative verdict + lower confidence.
- **Partial capture** is the known failure mode — treat empty/short transcript as "reviewer did not return," never silent APPROVE.
- Keep this **distinct** from the code-review MCP synthesizer (`mcp/review-synthesizer/`) — different inputs (2 prose transcripts vs 5 JSON arrays). **Vocabulary normalization (codex nit, round 3):** the `agy`/gemini CLI emits `APPROVE_WITH_NITS`, but the project's canonical gate term (CLAUDE.md, `AGENT_CONTRACTS.md §gate`) is **`APPROVE_WITH_NOTES`** — the synthesis maps `NITS → NOTES` and emits the canonical `APPROVE / APPROVE_WITH_NOTES / REQUEST_CHANGES / DISAGREEMENT`. Keep this separate from the code-review enum (`APPROVE_WITH_SUGGESTIONS`) so a reviewer doesn't "unify" them.

**Kill-switch / rollout:** None needed — passive read-only skill; gates nothing automatically (warn-first is inherent).

**Verification:** Stage two fixture transcripts (one APPROVE, one REQUEST_CHANGES) → emits `DISAGREEMENT` + lists conflicts. Two APPROVE → `APPROVE` + high confidence. One empty → refuses `APPROVE`.

**Effort:** S. **Depends on:** none; best defined alongside Item 12 so the three enums are documented together (see Sequencing).

---

### Item 9 — Decision-support option tables in `commands/brainstorm.md`

**Source:** `octo-repo/skills/skill-decision-support/SKILL.md` — the per-option trade-off block (lines 93–114: Pros/Cons + `Effort`/`Risk`/`Reversibility` + `Best for`), the starred-recommendation + Quick-Comparison table (lines 121–182), and guardrails (lines 184–191, 403–413: "2–4 options," "be honest about cons," red-flags). **Do NOT port** octo's cross-skill plumbing (`flow-probe`/`flow-tangle`/`skill-debug`) or its generic JS/TS examples.

**What it does:** Adds a design-phase "Step 4b: Decision-Support Options (for forks)" to the brainstorm command that, **only when the design has a genuine architectural fork**, presents 2–4 options with a comparison table (including a unleashed-specific **Parity-Impact** column) and a `**(Recommended)**` row, then calls `AskUserQuestion` to record the chosen fork before the plan doc is written.

**Target wiring:** Edit `commands/brainstorm.md` — insert Step 4b between Step 4 (Design Proposal) and Step 5; precede Step 9 (plan doc) so the chosen option feeds `docs/planning/FEATURE_NAME_PLAN.md`. Use **S/M/L** effort (matches Step 8's existing vocabulary), **no emoji** (`**Pros**`/`**Cons**`, `**(Recommended)**`). Canonical worked examples = real unleashed forks: Gmail historyId-incremental vs full resync; `NativeRichTextEditor` (macOS 26+) vs `HTMLWebViewEditor` (≤25); Pub/Sub push vs Graph delta-poll; migration CRITICAL vs DEFERRABLE. **Edit `allowed-tools` frontmatter to add `AskUserQuestion`** (currently `Read, Grep, Glob, Agent, WebFetch, WebSearch`; `AskUserQuestion` is used nowhere in the plugin today — flag as a command-interface change).

**Hook contract:** N/A — command markdown. The only contract change is the new `AskUserQuestion` tool in `allowed-tools`.

**Edge cases:**
- **Parity column can't be skipped** — every sync/compose/push fork has a provider-parity dimension (CLAUDE.md mandate); a "Gmail-only quick win" must show its Graph cost.
- **Composer fork is OS-gated** — `NativeRichTextEditor` is macOS 26+ only; encode as a hard precondition, not a peer alternative on macOS 25.
- **Migration default is DEFERRABLE** (CLAUDE.md "defer unless proven critical") — the starred recommendation defaults to DEFERRABLE and requires justification to star CRITICAL.
- `disable-model-invocation: true` means it only runs on explicit `/unleashed-mail:brainstorm` — option tables won't fire automatically (correct, design-phase only).

**Kill-switch / rollout:** None needed (command-scoped, design-only, writes nothing destructive). Warn-first inherent — produces a table for human choice.

**Verification:** Dry-run `/unleashed-mail:brainstorm "incremental Gmail sync"` → Step 4b emits a 2-option table with the parity column + starred recommendation, then `AskUserQuestion`. Grep the transcript → no emoji. Confirm the chosen option is referenced in the Step 9 plan doc.

**Effort:** S–M. **Depends on:** none. The `AskUserQuestion` frontmatter add is the only "Ask Before Modifying"-adjacent touch (a command interface, not project structure) — surface it but it doesn't block.

---

### Item 12 — Agent "Output Contract" status enum

**Source:** `octo-repo/agents/droids/*.md:36–52` — `## Output Contract` / `**Return status:** COMPLETE | BLOCKED | PARTIAL` with per-status fields. COMPLETE fields are domain-specific; **BLOCKED/PARTIAL are identical across all droids** (stable scaffold to standardize verbatim).

**What it does:** Appends a standardized status-enum block to the **4 specialist reviewers** so a reviewer that *couldn't run* returns `BLOCKED` + `[]` instead of an empty `[]` that looks like a clean pass. The status (did-it-finish) is **orthogonal** to the existing review verdict (is-code-OK).

**Target wiring:** Edit `agents/security-reviewer.md`, `agents/concurrency-reviewer.md`, `agents/ux-perf-reviewer.md`, `agents/accessibility-auditor.md` — append after each agent's existing Structured-Findings JSON section:
```markdown
## Output Contract
**Return status:** COMPLETE | BLOCKED | PARTIAL
- COMPLETE — review ran fully; the json findings array above is authoritative ([] if clean).
- BLOCKED  — could not review. Required: Blocker Description · What Was Attempted. Emit [] for findings.
- PARTIAL  — reviewed some files. Required: Completed · Remaining · Confidence: [0-100]. Findings cover ONLY completed scope.
```
Thread into `swift-reviewer.md` Step 5 (the fail-closed recovery, lines 352–364): `BLOCKED` → emit a `category: verification` blocker → route NEEDS DISCUSSION; `PARTIAL` → keep findings + record a verification warning that scope was incomplete. This maps onto the synthesizer's **existing** `verification` family + `NEEDS_DISCUSSION` verdict — **no Python change.** Add a `Status:` line to the "All reviewers → swift-reviewer" handoff in `skills/agent-orchestration/SKILL.md` and update `AGENT_CONTRACTS.md §5`. README counts unchanged (edits existing agents).

**Hook contract:** N/A — subagent prose contract returned in the subagent's final message.

**Edge cases:**
- **`[]` ambiguity is the whole point** — orchestrator must read **status first**, then the array; document that ordering or the change adds no safety.
- **Don't churn all 20 agents** — 4 reviewers only in phase 1; implementation agents (`db-engineer`/`logic-engineer`/`ui-engineer`) and `swift-reviewer` (which *consumes* the statuses) keep their semantics; defer the rest to a tracked follow-up.
- **`PARTIAL` + structural-pipeline:** must name which structural files were not reached (tie `PARTIAL.Remaining` to `scope: structural-pipeline`) or a missed structural finding looks clean.
- Keep COMPLETE pointing at the *existing* JSON array (don't re-specify a second divergent schema).

**Kill-switch / rollout:** Not a runtime hook → no env var. Warn-first equivalent = scope-limited rollout (4 reviewers) + swift-reviewer already fails-closed, so a reviewer not yet emitting status degrades to today's behavior (no regression).

**Verification:** Spawn one reviewer on a tiny changeset → ends with `## Output Contract` status + JSON array. Point a reviewer at a nonexistent file → `BLOCKED` routes to NEEDS DISCUSSION with a `verification` blocker. Confirm `synthesize_review` still accepts findings unchanged (no schema field added).

**Effort:** M (4 near-identical blocks + targeted edits to 3 more files; must keep three enums straight). **Depends on:** none, but land **before/with Item 8** so all three enums are defined together.

---

## Sequencing & dependencies

```text
Phase 0:  Item 1 ─┐                      (shared pre-commit FALSE-branch edit + kill-switch)
          Item 2 ─┴─► Item 7 (CI runs validate-plugin-assembly.py; tests land with/before CI)

Phase 1:  Item 3 ──► (extracts scripts/lib/hook-io.sh) ──► Item 4 (reuses hook-io + marker writers→Stop read)

Phase 2:  Item 10 (validates new-event wiring) ──► Item 5 (ticket/plan extractor + round ctx) ──► Item 6 (consumes round ctx, feeds synthesizer)

Phase 3:  Item 12 ──► Item 8 (define three enums together)   ;   Item 9 (independent)
```

Mini dependency rules:
- **Assembly-validator (2) before CI (7)** — CI's "Validate plugin assembly" step runs it (or land CI without that step and add it in the validators PR).
- **Build/lint marker writers before Stop-gate read (Item 4)** — the gate is meaningless without a marker; develop together.
- **Synthesizer unit tests with/before CI (Item 7)** — CI is the harness that runs them.
- **Item 3 before Item 4** — extract `scripts/lib/hook-io.sh` once in 3, reuse in 4.
- **Item 5 before Item 6** for round bucketing (else bucket by timestamp).
- **Item 12 before/with Item 8** so the three verdict/status enums are documented in one place.

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hook **alert-fatigue** (Item 3 `*Auth*` over-match) | Med | Anchor to `.swift` basenames; explicit high-signal stem allowlist; exclude `*Tests.swift`/docs; warn-first phase to tune before flipping to `ask`. |
| **Stop-gate false-block / session wedge** (Item 4) | Med | Honor `stop_hook_active`; TTL window + commit-sha match; "no marker = no block"; fail-open on `date` parse error; warn-first is **silent diagnostic logging only** (no stdout/`additionalContext`, no block). |
| **settings.json edit** needs user approval (statusline — *deferred*, see scope) / `AskUserQuestion` frontmatter (Item 9) | Low | Statusline is out of scope this round; Item 9's `allowed-tools` edit is a command interface (not project structure) — flagged, not auto-applied without review. |
| **CC-version-gated events** silently inert on older CC | Med | **Gate on field presence, not version** (the specific version floors are **best-effort, sourced from octo's hook comments — not the public hooks page**, codex nit round 4; treat them as advisory). Every hook bails silently when an expected field is absent; restore has a SessionStart path; no hard failure when unsupported. |
| **Agent churn** (Item 12 across many agents) | Low | Scope to 4 reviewers only; swift-reviewer already fails-closed → non-adopting agents degrade to today's behavior; rest deferred to a tracked follow-up. |
| **Marker / log PII leak** (Items 4, 6, 10) | Low | Markers store status/kind/ts/short-sha + **repo hash** (never the abs path); `StopFailure` logs the `error_type` enum only (never `error_message`); denial log = tool+reason only (never `tool_input`); build log = command-class only; reviewer capture writes **sanitized** structured JSON, never `.log`. |
| **Validator false-fail** on block-scalar frontmatter / BOM (Item 2) | Low | Block scalars stored truthy → pass; add `description: >` regression fixture; optional BOM strip. |
| **CI tests the wrong synthesizer copy** | Low | Point CI unittest at `mcp/review-synthesizer/tests` (the shipped copy). `prototypes/` is a divergent throwaway — **not** sync-checked (no `filecmp` canary; the copies already differ by design). |
| **Hook input-contract mismatch** — existing scripts read `CLAUDE_TOOL_ARG_*`, current docs say stdin JSON (codex Strong #1) | Med | `hook-io.sh` reads stdin-then-envvar; confirm via `claude --debug` in Phase 0; migrate existing scripts or marker writes go silently inert. |
| **`permissionDecision:"allow"` auto-approves** (Item 3, codex Critical #1) | High if shipped naively | No-match/warn/off paths **omit** `permissionDecision` entirely; only a signature match emits `"ask"`; covered by stdin-sim tests. |

## Files Changed

**New**
- `scripts/validate-version-sync.sh` (Item 1)
- `scripts/validate-plugin-assembly.py` (Item 2)
- `.github/workflows/plugin-ci.yml` (Item 7) — runs the **existing** `mcp/review-synthesizer/tests` suite + both validators; **no new test file**
- `scripts/sensitive-file-guard.sh` (Item 3)
- `scripts/lib/hook-io.sh` (Item 3, shared)
- `scripts/stop-quality-marker-gate.sh` (Item 4)
- `scripts/lib/marker.sh` (Item 4, shared)
- `scripts/precompact-snapshot.sh`, `scripts/sessionstart-restore.sh` (Item 5 — no `postcompact-restore.sh`; PostCompact can't inject)
- `scripts/capture-reviewer-verdict.sh` (Item 6)
- `scripts/stop-failure-log.sh`, `scripts/permission-denied-log.sh`, `scripts/build-failure-log.sh` (Item 10)
- `skills/review-synthesis/SKILL.md` (Item 8)
- `docs/planning/OCTO_ADOPTION_PLAN.md` (this plan)

**Edited**
- `scripts/pre-commit-checks.sh` — `HAS_XCODEPROJ=false` branch: call both validators (Items 1, 2); add build-marker write (Item 4)
- `scripts/swift-lint-check.sh` — write per-kind lint marker (Item 4); migrate input read to `hook-io.sh` (stdin-then-`CLAUDE_TOOL_ARG_*`) (Item 3 input-contract)
- `scripts/swift-build-verify.sh` — append bounded build-class log line (Item 10); migrate input read to `hook-io.sh` (Item 3 input-contract)
- `hooks/hooks.json` — add `PreToolUse` (Item 3), `Stop` (Item 4), `PreCompact` + `SessionStart` (Item 5 — **not** `PostCompact`), `SubagentStop` (Item 6), `StopFailure` + `PermissionDenied` + `PostToolUseFailure` (Item 10); **quote `${CLAUDE_PLUGIN_ROOT}` in the existing two entries** (Item 3, Strong #5)
- `.gitignore` — add `*.jsonl`, `.state/`, `reviews/`, `logs/` (Items 5/6/10)
- `.claude-plugin/plugin.json` — bump `version` `2.3.0`→`2.3.1` (Item 8) — **required** so Item 1's strict version-sync validator passes; plugin.json is the anchor (codex Strong, round 4)
- `README.md` — version/What's-New `### v2.3.1`; skills count 17→18 (preserve the `· 1 MCP server` token) (Item 8 only)
- `.claude-plugin/marketplace.json` — refresh the skills count in the description text if it states one (Item 8; no version field to bump)
- `commands/brainstorm.md` — Step 4b + `allowed-tools` add `AskUserQuestion` (Item 9)
- `agents/security-reviewer.md`, `agents/concurrency-reviewer.md`, `agents/ux-perf-reviewer.md`, `agents/accessibility-auditor.md` — Output Contract block (Item 12)
- `agents/swift-reviewer.md` — Step 5 status-enum threading (Item 12)
- `skills/agent-orchestration/SKILL.md` — handoff `Status:` line (Item 12)
- `AGENT_CONTRACTS.md` — §2 review-synthesis step 3a (Item 8); §5 status enum (Item 12)
- `skills/gemini-review/SKILL.md`, `skills/codex-review/SKILL.md` — one-line synthesis pointer (Item 8)

## Testing

- **Phase 0 validators (Items 1–2):** run each script at HEAD → green (plugin 2.3.0 == README; 20/17/3/1 == disk; `OK — plugin assembly`). Negative fixtures on a scratchpad copy (version drift, deleted agent, broken JSON, non-kebab name, missing `description`, `description: >` regression, missing `version`).
- **CI (Item 7):** local mirror — `python3 -m unittest discover -s mcp/review-synthesizer/tests -v` (the **existing suite**, count grows over time — ~61 at last check → `Ran N tests … OK`) `&& shellcheck -s bash -S warning scripts/*.sh && python3 -m py_compile mcp/review-synthesizer/*.py && VERSION_SYNC_ENFORCE=strict bash scripts/validate-version-sync.sh && python3 scripts/validate-plugin-assembly.py --root . --strict`. (No new test methods, no golden case, no filecmp canary — the suite already exists and covers the render/verdict split + bool/float coercion + protocol.) Open a draft PR that introduces a deliberate failure (drop a frontmatter `description`) → confirm red; revert → green; don't mark required until after a warn-first PR.
- **Phase 1 hooks (Items 3–4):** stdin-simulation cases (sensitive path → `ask`; **benign → no `permissionDecision` emitted** (normal prompt still applies); **read-only Bash → no decision**; `sed -i` Bash → `ask`; space-in-path survives; fresh-fail Stop marker → `block`; stale/missing/`stop_hook_active` → no block; `time` the Stop hook → ms). Add to `scripts/test-runner.sh`. Each phase ships warn-first; observe one session before flipping to enforce.
- **Phase 2 hooks (Items 5/6/10):** snapshot/restore freshness window (within/after 10 min); SubagentStop capture byte-identical to a sample fixture + `synthesize.py` consumes it + traversal-guard rejection; denial-log PII assertion (path absent) + rotation (600→250 lines). All observe-only/non-blocking → safe to ship enabled.
- **Phase 3 prose (Items 8/9/12):** manual skill/command dry-runs (DISAGREEMENT on conflicting transcripts; empty transcript refuses APPROVE; brainstorm emits parity-column table + `AskUserQuestion`, no emoji; reviewer ends with `## Output Contract`; `BLOCKED` routes to NEEDS DISCUSSION; `synthesize_review` unchanged).

## Explicitly out of scope

Restated so scope cannot creep — **none** of the following are ported:
- `octo-repo/scripts/orchestrate.sh` multi-LLM runner and any `flow-*`/`embrace`/`council` orchestration.
- Provider routing / model selection / chair-model machinery (`members: auto|3|5|7`, budget caps, preflight).
- Multi-surface packaging (`codex-plugin`/`cursor-plugin`/`factory-plugin`/`factory-marketplace`), plugin-zip / `--plugin-url` smoke tests, git-tag checks.
- "beads", telemetry webhooks, cost-attribution dashboards.
- `octopus-hud.mjs` (45 KB Node Tier-1 HUD) and the full 3-tier statusline — **only the bash Tier-2/Tier-3 statusline was researched, and even that is deferred** (it requires a user `settings.json` edit → "Ask Before Modifying"; ship as documented opt-in later, never auto-wired).
- The 50-persona / enterprise-zoo persona machinery.
- Octo's command-registration cross-checks and `agents/config.yaml` reference validation (incompatible with unleashed's auto-discovery manifest).
- Octo's legacy flat hook-output JSON shapes (`{"permissionDecision":"ask","message":...}`, `decision:"continue"`) — superseded by the nested `hookSpecificOutput` / `{"decision":"block"}` forms.

## Next steps / gates

1. **Create the COREDEV Jira ticket** (Task or Bug under the relevant Epic) for this adoption effort; every commit message must carry `type(COREDEV-XXXX): …`.
2. **Gate this plan.** Normally both reviewers must return APPROVE / APPROVE_WITH_NOTES (mandatory CLAUDE.md gate). **For this plan (user decision, round 3):** gemini-3.1-pro proved unreliable for CC-hook-specific review (round-3 hallucination cascade, refuted in the Progress Log with octo `hooks.json` + docs evidence), so the gate is **codex APPROVE + the documented evidence**. codex `/unleashed-mail:codex-review` must return APPROVE / APPROVE_WITH_NOTES before any code edits begin.
3. **First PR = Phase 0** (Items 1, 2, 7): the two validators + a CI workflow that runs the **already-shipped** synthesizer suite (via discovery — the count keeps growing, 46→52→58→61 across review rounds; never hardcode it), both validators (strict), shellcheck, and py_compile. Zero runtime risk, unblocks CI for everything after, and proves the `HAS_XCODEPROJ=false` validation branch end-to-end. Subsequent PRs follow the phase order above, each shipping its hooks warn-first behind kill-switches, flipping to enforce only after one clean observation cycle.
