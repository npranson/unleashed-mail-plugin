# COREDEV-2326 — Reviewer-capture round context: wire a stable cycle signal from the orchestrator

**Status:** ✅ APPROVED — dual gate satisfied (codex `APPROVE_WITH_NOTES` + gemini `APPROVE`, rev 2) — ready to implement   **Created:** 2026-06-27
**Epic:** COREDEV-2321 (unleashed-mail plugin — octo-adoption hardening & hooks)
**Branch:** `feat/COREDEV-2326-review-round-producer` (worktree off `origin/main` @ `2b62c0e`)
**Scope:** the **plugin repo** only — no Swift app code.

---

## 1. Problem

The SubagentStop reviewer-verdict capture (Item 6, COREDEV-2325) buckets each specialist
reviewer's findings into `reviews/<repohash>/<slug>/round-<N>/<agent>.json`. The round number `N`
is chosen by `mcp/review-synthesizer/capture.py:select_round()`:

1. **Explicit override (already shipped):** if `UNLEASHED_REVIEW_ROUND` is a positive integer, that
   value is used verbatim.
2. **Inference (fallback):** otherwise the highest existing `round-N` dir, advanced to `N+1` only
   when this reviewer's slot in the highest round already holds a valid capture — plus a cross-round
   `agent_id` dedup so a duplicate SubagentStop never opens a polluting new round.

The inference is robust for the realistic flow and for duplicates, but **cannot perfectly group
cycles under interleaved timing**: if a late reviewer from cycle 1 stops *after* cycle 2 has begun,
the inference reads the current highest round and mis-buckets the straggler. This is the exact bug
the ticket exists to fix.

**The consumer side is done.** `select_round()` already honors `UNLEASHED_REVIEW_ROUND`
(`capture.py:216-218`, tested by `test_env_override` / `test_explicit_round_override`).
**This ticket is purely the producer-side wiring** — give the capture a stable signal so each
reviewer's `agent_id` binds to its **originating** round, deterministically and
timing-independently.

### Why a singleton "active round" signal is *not* enough (codex plan-review r1, Critical #1)

An earlier draft persisted one "current cycle round" file that the SubagentStop consumer read at
capture time. **That recreates the interleaving bug:** a late cycle-1 reviewer reading the file
*after* cycle 2 advanced it lands in cycle 2's round. The round must be **bound to each subagent at
the moment it is spawned**, then **looked up by that same subagent when it stops** — so each
capture uses its own *frozen* round regardless of what later cycles do.

### Why the orchestrator can't set the env var directly

`UNLEASHED_REVIEW_ROUND` is read in the **hook's** process (`capture-reviewer-verdict.sh` →
`capture.py`), which Claude Code spawns — not the orchestrator agent. So producer and consumer must
communicate through a small **state file** on disk (same IPC pattern as the Phase-2 snapshot).

---

## 2. Design — per-`agent_id` round binding via `SubagentStart` → `SubagentStop`

Claude Code's hook contract provides the exact primitive (verified against the official docs,
[code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks), 2026-06-27):

- **`SubagentStart`** fires when an Agent subagent is **spawned**; its input includes `agent_id`
  (*"Unique identifier for the subagent"*), `agent_type`, `session_id`, `transcript_path`, `cwd`.
- **`SubagentStop`** (already wired) fires when that subagent **stops**, carrying the **same**
  `agent_id` plus `agent_type`, `last_assistant_message`, `agent_transcript_path`.

The shared, stable `agent_id` is the binding key. Four additive pieces; **no change to `capture.py`
consumption logic**, no change to the findings-array shape.

### 2.1 `scripts/lib/context.sh` — binding helpers (new functions)

A per-checkout, per-**subagent** round **binding** file, namespaced by the repo-root hash (like
`reviews/` and the snapshot) and keyed by a hash of `agent_id`, under the **`.state/`** dir:

```
${CLAUDE_PLUGIN_DATA:-$HOME/.claude/unleashed-mail}/.state/review-round-<repohash>-<agentidhash>.json
```

Content (all PII-free — `slug` is a ticket token or branch **hash**; `agent_id`/`session_id` are
opaque CC ids; no branch text, paths, or message content):

```json
{ "round": 2, "agent": "security-reviewer", "slug": "COREDEV-2326",
  "session_id": "abc123", "time": 1750000000 }
```

New functions:

- **`context_highest_round <base>`** — highest existing `round-<N>` number under `<base>`
  (`<reviews_dir>/<slug>`), or `0`, returned as a **decimal-normalized integer** (a `round-09` dir
  yields `9`, so `+1` is `10`, never an octal mis-parse — codex r2 Nit A). Numeric-only, `<=5`
  digits, zsh-`NOMATCH`-safe — factored out of the proven `context_latest_round_dir` so both share
  the same hardened scan (leading-zero base-10 `[ -gt ]`, oversized-suffix skip, `setopt
  local_options no_nomatch`).

- **`context_round_binding_path <agent_id>`** — the binding path above (hashes `agent_id` via
  `_context_hash`, so it is path-safe + PII-free).

- **`context_review_round_bind <agent_type> <agent_id> [session_id]`** *(producer)* — compute the
  round by **mirroring `capture.select_round`'s non-override path** (reusing `capture.is_final_capture`
  so the predicate is single-sourced): first cycle = 1; advance to `highest + 1` **only** when the
  highest round's slot for this agent already holds a **final** capture; otherwise **reuse** the
  highest round — so a same-round **repair** re-run (swift-reviewer's recovery rule) overwrites the
  stale empty/dropped slot instead of splitting the cycle (codex PR #17 P2). When finality can't be
  determined (no `python3`/`capture.py`) it defaults to **advance** (never overwrites a real prior
  capture). Atomically persist the binding (tmp + `mv`); best-effort **sweep** binding files older than
  the TTL (bounded `.state/` GC). Prints the round. Fail-open.

- **`context_review_round_lookup <agent_type> <agent_id> [session_id]`** *(consumer-read)* — read
  this subagent's binding and print its `round` **only when it validates**: parses; `agent` matches
  `agent_type`; `slug` matches the current branch slug; `session_id` matches **when present on both
  sides**; `round` is a positive int; fresh within `UNLEASHED_REVIEW_ROUND_TTL` (default `3600`s,
  `0`=disabled). Otherwise prints nothing → consumer leaves `UNLEASHED_REVIEW_ROUND` unset →
  `capture.py` infers (shipped default). Stdlib `python3` (already a hard capture dependency).

- **`context_review_round_clear <agent_id>`** — best-effort delete the binding (consume-once).

### 2.2 `scripts/capture-reviewer-round-start.sh` — new `SubagentStart` producer hook

Mirrors `capture-reviewer-verdict.sh`'s shape and guards:

```bash
set -uo pipefail
. "$_DIR/lib/hook-io.sh"; . "$_DIR/lib/context.sh"
[ "${UNLEASHED_REVIEW_ROUND_SIGNAL:-on}" = "off" ] && exit 0
[ "${UNLEASHED_CAPTURE_REVIEWERS:-on}" = "off" ] && exit 0   # whole capture path off ⇒ no producer
command -v python3 >/dev/null 2>&1 || exit 0
hook_io_read
AGENT="$(hook_str agent_type)"
case "$AGENT" in
  security-reviewer|concurrency-reviewer|ux-perf-reviewer|accessibility-auditor) ;;
  *) exit 0 ;;                                   # exclude swift-reviewer + all non-reviewers
esac
AGENT_ID="$(hook_str agent_id)"; [ -n "$AGENT_ID" ] || exit 0   # no id ⇒ nothing to bind; inference covers it
context_review_round_bind "$AGENT" "$AGENT_ID" "$(hook_str session_id)" >/dev/null 2>&1 || true
exit 0
```

Observe-only, fail-open, `exit 0` always. No stdout (SubagentStart output is irrelevant here).

### 2.3 `hooks/hooks.json` — register the producer

A new `SubagentStart` block (`"matcher": ""`, `timeout: 10`) → `capture-reviewer-round-start.sh`,
with the quoted `"${CLAUDE_PLUGIN_ROOT}"` house style. (Filter by `agent_type` in-script, not via
matcher, mirroring the existing `SubagentStop` entry.)

### 2.4 `scripts/capture-reviewer-verdict.sh` — consumer lookup + consume-once

After deriving `AGENT`/`AGENT_ID`, before invoking `capture.py`:

```bash
# COREDEV-2326: bind this capture to the round frozen at its SubagentStart (timing-independent).
# Never clobber an explicit value; honor the kill switch; absent/stale/foreign -> inference.
if [ "${UNLEASHED_REVIEW_ROUND_SIGNAL:-on}" != "off" ] && [ -z "${UNLEASHED_REVIEW_ROUND:-}" ] && [ -n "$AGENT_ID" ]; then
    _RS_ROUND="$(context_review_round_lookup "$AGENT" "$AGENT_ID" "$(hook_str session_id)" 2>/dev/null || true)"
    case "$_RS_ROUND" in ''|*[!0-9]*) ;; *) export UNLEASHED_REVIEW_ROUND="$_RS_ROUND" ;; esac
fi
# … existing capture.py invocation (both last_assistant_message and transcript paths) …
[ -n "$AGENT_ID" ] && context_review_round_clear "$AGENT_ID" 2>/dev/null || true   # consume-once
```

`capture.py` already validates the value (`override.isdigit() and int(override) > 0`) — belt and
suspenders. Observe-only; the hook still `exit 0` on every path.

### Design decision: `SubagentStart` vs the recipe / `PreToolUse(Agent)` (codex r1, Strong)

- **Recipe-only (a prior draft):** rejected — a singleton round written by the orchestrator can't
  bind *per subagent*, so it can't fix interleaving (§1).
- **`PreToolUse(Agent)`:** depends on `tool_input.subagent_type` and the spawn tool name — the
  fragile CC-contract surface this repo has been burned by.
- **`SubagentStart` (chosen):** documented specifically for Agent-spawned subagents with
  `agent_id`/`agent_type` and **no `tool_input` dependency**; the `agent_id` matches `SubagentStop`'s.
  This is the deterministic, minimal-contract producer.

---

## 3. Files changed

| File | Change |
|---|---|
| `scripts/lib/context.sh` | +`context_highest_round`, +`context_round_binding_path`, +`context_review_round_bind`, +`context_review_round_lookup`, +`context_review_round_clear`, +TTL helper; refactor the round-dir scan shared with `context_latest_round_dir`. |
| `scripts/capture-reviewer-round-start.sh` | **New** `SubagentStart` producer hook. |
| `hooks/hooks.json` | **New** `SubagentStart` block → the producer hook. |
| `scripts/capture-reviewer-verdict.sh` | Lookup binding → export `UNLEASHED_REVIEW_ROUND`; consume-once clear. |
| `scripts/test-hooks.sh` | New bash cases (helpers + both hooks + interleaving + stale/cross-agent). |
| `mcp/review-synthesizer/tests/test_capture.py` | **Required** round-trip: a forced override drives bucketing; interleaving stays separated. |
| `CHANGELOG.md` | `[Unreleased] / Added` entry; bump the hook-test-count prose. |

**No version bump / no asset-count change** — asset counts cover agents/skills/commands/MCP, not
hooks (same precedent as COREDEV-2328). The strict version-sync validator is unaffected.

---

## 4. Edge cases & guarantees

- **Interleaving (the fix):** each capture uses the round **frozen at its own `SubagentStart`**, so
  a late cycle-1 straggler lands in round 1 even after cycle 2 advanced. Deterministic, not
  timing-dependent. *Invariant:* a subagent's `agent_id` is stable across its `SubagentStart` and
  `SubagentStop` (CC docs: *"Unique identifier for the subagent"*) — verified, load-bearing.
- **Round-number assignment** mirrors `capture.select_round` (advance past a **final** prior slot,
  else reuse): first-cycle = 1; each genuine re-review +1; a same-round **repair** re-run reuses the
  round and overwrites the empty/dropped slot (codex PR #17 P2 — keeps producer and capture
  consistent). The four reviewers of a cycle spawn in one parallel batch **before any of them
  captures**, so all four `SubagentStart`s read `highest = 0` (or a non-final slot) and bind the same
  round. A new cycle starts only after the prior panel completes (the orchestrator needs all four
  results to synthesize and decide to re-review), so the prior round's final dirs exist before the
  next cycle binds → clean advance.
  *Sole degradation:* if a re-review were somehow spawned **before any capture of the prior cycle
  existed**, the two cycles would share a round — observe-only, non-fatal, and not a flow the
  orchestrator produces (documented, not silently assumed).
- **Stale / crashed-subagent bindings:** keyed by the **unique** `agent_id`, so no live subagent
  ever reads another's binding; consumed-and-deleted at `SubagentStop`; a crashed subagent's orphan
  binding is harmless and TTL-swept by the producer. This closes codex r1 Strong #1 (a stale
  override can no longer overwrite a *different* cycle's valid slot — the binding is per-subagent,
  and a new `agent_id` carries the *new* round, writing its own slot).
- **Cross-checkout / cross-branch isolation:** repohash in the path + `slug` (and `session_id` when
  present) re-validated on read.
- **Never clobber an explicit value;** **no new PII surface;** **fail-open everywhere** (missing
  `python3`/`date`, unwritable dir, corrupt/absent binding → inference); both hooks always `exit 0`.

## 5. Kill switches

- `UNLEASHED_REVIEW_ROUND_SIGNAL=off` → disables **both** producer and consumer (pure inference).
- `UNLEASHED_CAPTURE_REVIEWERS=off` (existing) → disables producer **and** the whole capture path.
- `UNLEASHED_REVIEW_ROUND_TTL=<secs>` → tune the binding validity window (`0` = no TTL check).
- An explicitly-exported `UNLEASHED_REVIEW_ROUND` still wins (manual override).

## 6. Tests & verification (`scripts/test-hooks.sh` + `test_capture.py`)

1. `context_highest_round`: `0` empty; highest numeric; ignores non-numeric/oversized; base-10
   leading zeros; zsh-NOMATCH clean+empty. **Decimal-normalization (codex r2 Nit A):** an existing
   `round-09` makes `context_review_round_bind` produce round **10** (not `011`/octal).
2. `bind`/`lookup`/`clear`: bind writes round 1 on a fresh slug, 2 after a `round-1` dir exists;
   lookup honors a matching binding; rejects foreign `slug`, mismatched `agent`, stale (TTL=1
   backdated), missing file; clear removes it (consume-once).
3. **Interleaving (codex r1 Strong #3):** bind A,B,C,D at round 1; capture A; bind a re-spawned A at
   round 2; then stop a *cycle-1* peer (B) and assert it lands in **round 1**, not 2.
4. **Stale/cross-agent (codex r1 Strong #3):** a binding for one `agent_id` is never consumed by a
   different `agent_id`; a stale binding cannot overwrite an existing valid slot.
5. Hook-level: `capture-reviewer-round-start.sh` writes a binding for a reviewer `agent_type` and
   ignores non-reviewers; `capture-reviewer-verdict.sh` consumes it (capture lands in the bound
   round) and clears it; `UNLEASHED_REVIEW_ROUND_SIGNAL=off` → inference; explicit value not clobbered.
   **Invariant fixture (codex r2 Nit B):** a synthetic `SubagentStart` then `SubagentStop` carrying
   the **same** `agent_id` exercises the full bind→lookup→capture round-trip end-to-end, pinning the
   "Start and Stop share one `agent_id`" contract the design rests on (verified against the CC docs).
6. **Required (codex r1 Nit #1)** python round-trip in `test_capture.py`: a forced override routes a
   re-review's capture into the next round's file; the agent_id dedup still skips true duplicates.

Run: `bash scripts/test-hooks.sh`, `python3 -m unittest discover -s mcp/review-synthesizer/tests`,
`python3 scripts/validate-plugin-assembly.py --root . --strict`,
`VERSION_SYNC_ENFORCE=strict bash scripts/validate-version-sync.sh`,
`shellcheck -s bash -S warning scripts/*.sh` (the CI gates in `plugin-ci.yml`).

## 7. Context7 note

Internal plugin bash/python + Claude-Code hook wiring — no third-party library/API surface, so
Context7 does not apply. The one external contract (`SubagentStart`/`SubagentStop` fields) was
verified against the live CC hooks docs (see §2); any contract claim is re-checked at the gate.

## 8. Plan-review log

- **rev 1 → codex r1: REQUEST_CHANGES** (2 Critical, 3 Strong, 2 Nit). Critical: the singleton
  active-round signal recreated the interleaving bug and the "idempotent within a cycle" claim was
  false. **Adopted in full** — pivoted to per-`agent_id` `SubagentStart` binding (codex's suggested
  primitive), verified `SubagentStart` exists with `agent_id`/`agent_type` against the official docs.
  Strong #1 (stale overwrite) resolved by per-subagent keying + consume-once; Strong #2 (better hook)
  = `SubagentStart`; Strong #3 + Nit #1 folded into §6 tests.
- **rev 2 → codex r2: APPROVE_WITH_NOTES** (0 Critical, 0 Strong, 2 Nit). Codex confirmed every r1
  item resolved and independently re-verified the `SubagentStart`/`SubagentStop` contract against the
  live docs. Nit A: `context_highest_round` must return a decimal-normalized int (a `round-09` → bind
  10) — pinned in §2.1 + a §6.1 bind test. Nit B: pin the Start/Stop same-`agent_id` invariant with a
  hook fixture — added as §6.5. **Codex gate satisfied.**
- **PR #17 bot review → codex `COMMENTED` (1 × P2), gemini clean.** codex P2: the producer's naive
  `highest + 1` regressed `capture.py`'s `is_final_capture` reuse — a same-round repair re-run would
  split the cycle into `round-2` instead of overwriting the empty `round-1` slot. **Fixed:**
  `context_review_round_bind` now mirrors `capture.select_round` (advance only past a final slot;
  reuse otherwise), reusing `capture.is_final_capture` via a new `_context_round_advance` helper.
  Added a repair-reuse + per-agent-reuse regression test (hook tests 130 → **132**). gemini posted
  two summary-only passes with no findings.
- **rev 2 → gemini: APPROVE** (after the user re-authed `agy`). Confirmed every r1 item resolved and
  validated the design (interleaving elimination, `agent_id` stability, round assignment,
  consume-once + TTL, read-side validation, capture.py dedup interaction), raising **no new issues**.
  Notably gemini did **not** hallucinate the hook contract this round — it correctly affirmed
  `SubagentStart`/`agent_id` (consistent with the docs in §2), reinforcing that the gemini-on-hooks
  risk is intermittent, not guaranteed. **Both gates satisfied — clear to implement.**

## 9. Plan-review gate (mandatory, before implementation)

- `/unleashed-mail:codex-review` — primary for the `SubagentStart`/`SubagentStop` contract.
- `/unleashed-mail:gemini-review` — run per process; this rev **does** touch a CC hook contract, so
  weigh per the documented gemini-on-hooks caution and refute any hallucination with the §2 docs
  evidence.

Both APPROVE / APPROVE_WITH_NOTES before code edits.
