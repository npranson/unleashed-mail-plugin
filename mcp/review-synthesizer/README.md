# review-synthesizer — MCP server

A **local stdio MCP server** that does the deterministic half of code-review
synthesis for `swift-reviewer`. Zero dependencies (stdlib `python3` only), no
network, no secrets. Declared in the plugin's root `.mcp.json`; Claude Code spawns
it as a subprocess when the plugin is enabled.

```
mcp_server.py   stdio JSON-RPC 2.0 wrapper (exposes the `synthesize_review` tool)
synthesize.py   deterministic dedup + ownership routing + scope filter + render
schema.py       canonical Finding schema (+ strict report_finding tool / structured output)
```

## Why it exists

An LLM doing row-by-row JSON dedup in prose can silently drop a real finding or
mis-merge two distinct ones. That logic is moved here, into plain Python, where it
is auditable, testable, and incapable of "forgetting" a finding. The reviewer
agents are unchanged — they still emit the same JSON findings array; only the
orchestrator's Step-5 *logic* calls this tool.

## Division of labour (the server has no repo access)

| Owns | Who |
|---|---|
| validate / quarantine, scope filter, dedup, ownership routing, consolidated report, **provisional** verdict | **this server** (pure compute) |
| **verify gate** — open each `blockersToVerify` `file:line`, confirm or downgrade — and the **final** verdict | **`swift-reviewer`** (has Read/Grep) |

The server returns `blockersToVerify` precisely because it cannot read the repo.

## The tool

`synthesize_review({ findings: Finding[], changed_files: string[] })` →

- `content[0].text` — the consolidated markdown report (Findings sections + table).
- `structuredContent`:
  - `provisionalVerdict` — `REQUEST_CHANGES | NEEDS_DISCUSSION | APPROVE_WITH_SUGGESTIONS | APPROVE`, computed **assuming every blocker is real**.
  - `blockersToVerify[]` — one entry per gating **blocker finding** (the actual
    blocker, not the routed display owner): `{file, line, lineEnd, category,
    sourceAgent, confidence, finding, clusterSeverity, clusterSize}`. The caller
    confirms each against the code.
  - `clusters`, `preExisting`, `quarantined` — counts.

`Finding` schema: `severity` (blocker|warning|suggestion) · `confidence` (high|medium|low)
· `sourceAgent` · `category` (reviewer vocabulary) · `file` · `line` · `lineEnd`
· `scope` (changeset|structural-pipeline, default changeset) · `finding` · `evidence` · `fix`.

## The deterministic rules (authoritative; also the prose fallback for swift-reviewer)

1. **Scope.** Gating set = findings whose `file` ∈ `$CHANGED`, **plus** any tagged
   `scope: "structural-pipeline"`, **plus** every orchestrator-owned global gate
   (`verification`, `parity`, `test-coverage` — their `file` is a scheme/target/label,
   not a diff path, so they gate regardless). Everything else is *Pre-existing*
   (surfaced, non-gating).
2. **Merge-candidate.** Two findings are candidates iff same `file`, **overlapping**
   `line..lineEnd`, **and** same category-family — except the deliberate cross-family
   ownership pairs (`token-race`↔credential/oauth/keychain; `perceived-perf`↔
   `html-sanitization`/`webview`). File-level (`line:0`) overlaps only other
   file-level findings. The category→family map:
   - *security* — `credential` `keychain` `oauth` `webview` `network` `privacy` `sqlcipher` `html-sanitization` `entitlements` `ci`
   - *concurrency* — `actor-isolation` `data-race` `async-await` `grdb-threading` `webview-threading` `token-race` `combine-lifecycle` `sendable`
   - *correctness* — `logic` `error-handling`
   - *deprecation* — `deprecation` `dependency`
   - *perf* — `main-thread` `rendering` `db-query` `image-budget` `network-efficiency` `memory` `perceived-perf` `error-ux` `animation`
   - *a11y* — `voiceover` `keyboard-nav` `dynamic-type` `curator-tokens` `color-contrast` `webview-a11y` `dual-impl-parity` `notifications` `macos-specific` `a11y`
   - *ai-safety* — `jailbreak-surface` `missing-refusal-path` `format-leak` `context-overflow-risk` `ambiguous-instruction` `evaluation-gap` `unsanitized-ingress` `inline-prompt-leak` `unscoped-tool` `pii-log-leak`
   - singletons — `parity` · `test-coverage` · `verification`
3. **Cluster, never collapse.** Candidates are clustered and **cross-linked** (every
   fix kept); headline severity = the max. Code can't prove "same defect", so it
   never silently deletes the second fix — an optional `same_defect` adjudicator may
   collapse further.
4. **Ownership routing** (re-route only, never drop): any a11y-relevant row →
   accessibility-auditor; any ai-safety row → prompt-review; credential-site
   `token-race` and sanitize/render → security.
5. **Verify gate** (caller, not server): confirm each `blockersToVerify` against the
   code → confirmed gates; unconfirmable → NEEDS DISCUSSION.
6. **Verdict:** any confirmed blocker → REQUEST CHANGES; only unconfirmable blockers
   → NEEDS DISCUSSION; only warnings/suggestions → APPROVE with suggestions; clean → APPROVE.

## Test

```bash
# smoke test the handshake (should print a JSON-RPC reply naming the server):
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \
  | python3 mcp_server.py
# run the synthesizer standalone (no MCP) against the bundled fixtures:
python3 synthesize.py samples/*.json --changed samples/changed_files.txt
# run the unit tests:
python3 -m unittest discover -s tests -v
# if the server fails to start under Claude Code, run `claude --debug` to see why.
```
