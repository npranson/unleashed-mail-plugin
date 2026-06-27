#!/usr/bin/env bash
# shellcheck shell=bash
# Shared, PII-safe work-context derivation for Item 5 (snapshot) + Item 6 (reviewer
# capture) — Phase 2, COREDEV-2325.
#
# This file is SOURCED, never executed.
#
# A git branch name is USER-CONTROLLED FREE TEXT (e.g. `fix/john.doe@corp.com-x`), so it
# is NEVER persisted, injected into model context, or used raw as a filesystem path.
# Everything downstream is derived from SAFE TOKENS only: a ticket key (COREDEV-NNNN),
# a release version (vX.Y.Z), the app version-line (1.0X), or — when none match — a
# stable 12-hex HASH of the branch (PII-free, never path characters). Every probe is
# `2>/dev/null` and fail-open.

# Plugin data base + Phase-2 state paths (shared by Item 5 snapshot & Item 6 capture).
# ${HOME:-} so a missing HOME under `set -u` never aborts a hook. Quoted by every caller
# (CLAUDE_PLUGIN_DATA may contain a space). Lives OUTSIDE the repo, never /tmp.
#
# Snapshot + reviews are NAMESPACED PER CHECKOUT via a repo-root hash (like Phase-1 marker.sh)
# so a PreCompact snapshot or reviewer capture in repo A can never be restored into / mixed with
# repo B, even when two checkouts share a branch/ticket slug (codex PR review). The repo-root path
# is hashed only — never written/emitted (the hash is PII-free; see _context_hash).
context_base()        { printf '%s' "${CLAUDE_PLUGIN_DATA:-${HOME:-}/.claude/unleashed-mail}"; }
context_state_dir()   { printf '%s/.state' "$(context_base)"; }

# The repo root (or $PWD when not in a repo). Used both as the per-checkout discriminator AND to
# resolve repo-relative paths (e.g. docs/planning) even when the session cwd is a subdirectory.
context_repo_root() {
    local root=""
    root="$(git rev-parse --show-toplevel 2>/dev/null)" || root=""
    [ -n "$root" ] || root="$PWD"
    printf '%s' "$root"
}

# 12-hex hash of the repo root — the per-checkout discriminator.
context_repo_hash() { _context_hash "$(context_repo_root)"; }

# Per-checkout reviews dir + snapshot file (both keyed by the repo hash).
context_reviews_dir()   { printf '%s/reviews/%s' "$(context_base)" "$(context_repo_hash)"; }
context_snapshot_path() { printf '%s/work-context-snapshot-%s.json' "$(context_state_dir)" "$(context_repo_hash)"; }

# Current branch name, or "" if cwd is not a git repo. Used ONLY internally to derive the
# safe tokens below — the raw value is never returned to a persisting/injecting caller.
context_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null || true
}

# A PII-safe ticket token from a branch name: COREDEV-NNNN, else vX.Y.Z, else the app
# version-line 1.0X (digits/dot only — NO free-text `/[^/]+` suffix), else "unknown".
# $1 = branch name.
context_ticket() {
    local b="${1:-}" t=""
    t="$(printf '%s' "$b" | grep -oE 'COREDEV-[0-9]+' 2>/dev/null | head -1)"
    [ -n "$t" ] || t="$(printf '%s' "$b" | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' 2>/dev/null | head -1)"
    [ -n "$t" ] || t="$(printf '%s' "$b" | grep -oE '1\.0[0-9]' 2>/dev/null | head -1)"
    [ -n "$t" ] || t="unknown"
    printf '%s' "$t"
}

# Pure-bash 32-bit djb2 hash (hex) of a string — final fallback so a hash (never path
# characters) is always available even with no hashing binary. Mirrors marker.sh's
# _marker_bash_hash but kept self-contained so Phase-1 marker.sh is untouched.
_context_bash_hash() {
    local s="${1:-}" i=0 len=${#1} h=5381 c=0 ch=""
    while [ "$i" -lt "$len" ]; do
        ch="${s:$i:1}"
        if [ "$ch" = "'" ]; then
            c=39
        else
            c=0
            printf -v c '%d' "'$ch" 2>/dev/null || true
        fi
        h=$(( (h * 33 + ${c:-0}) & 0xffffffff ))
        i=$(( i + 1 ))
    done
    printf '%x' "$h"
}

# 12-hex hash of an arbitrary string (PII-safe; never echoes input characters). $1 = string.
_context_hash() {
    local s="${1:-}" h=""
    if command -v shasum >/dev/null 2>&1; then
        h="$(printf '%s' "$s" | shasum 2>/dev/null | cut -d' ' -f1)"
    elif command -v sha1sum >/dev/null 2>&1; then
        h="$(printf '%s' "$s" | sha1sum 2>/dev/null | cut -d' ' -f1)"
    elif command -v openssl >/dev/null 2>&1; then
        h="$(printf '%s' "$s" | openssl dgst -sha1 2>/dev/null | awk '{print $NF}')"
    elif command -v python3 >/dev/null 2>&1; then
        h="$(printf '%s' "$s" | python3 -c 'import hashlib,sys; sys.stdout.write(hashlib.sha1(sys.stdin.buffer.read()).hexdigest())' 2>/dev/null)"
    fi
    [ -n "$h" ] || { command -v cksum >/dev/null 2>&1 && h="$(printf '%s' "$s" | cksum 2>/dev/null | tr -cd '0-9')"; }
    [ -n "$h" ] || h="$(_context_bash_hash "$s")"
    printf '%s' "${h:0:12}"
}

# A PII-safe slug for the reviews/<slug>/ bucket and the snapshot `branch_slug` field:
# the ticket token when it is a safe token, else a 12-hex hash of the branch (stable
# per-branch, never raw branch text). Guaranteed to contain no `/`, `..`, `@`, or
# whitespace, so it can never traverse or leak. $1 = branch name.
context_branch_slug() {
    local b="${1:-}" t=""
    t="$(context_ticket "$b")"
    if [ "$t" != "unknown" ]; then
        printf '%s' "$t"
        return 0
    fi
    if [ -n "$b" ]; then
        _context_hash "$b"
    else
        printf 'unknown'
    fi
}

# Highest round-<N> dir under $1 that holds $2's findings (`<agent>.json`), by NUMERIC round.
# Portable (no GNU sort/realpath; safe with spaces/hyphens in $1). Prints the dir, or nothing.
# $1 = <reviews_dir>/<slug>, $2 = agent. Used by swift-reviewer Step 2 to pair a reviewer's
# persisted `.status` with the SAME round's findings (COREDEV-2328); mirrors the producer side in
# mcp/review-synthesizer/capture.py.
context_latest_round_dir() {
    local base="${1:-}" agent="${2:-}" best="" best_n=-1 d n
    [ -n "$base" ] && [ -n "$agent" ] || return 0
    # zsh aborts an UNMATCHED glob (NOMATCH) before the loop body; under zsh, neutralize it
    # function-locally so an empty/round-less base is handled by the `[ -d ]` guard exactly as bash
    # does (the swift-reviewer Step-2 recipe is pasted into a zsh Bash-tool context). No-op in bash.
    [ -n "${ZSH_VERSION:-}" ] && setopt local_options no_nomatch 2>/dev/null || true
    for d in "$base"/round-*/; do
        [ -d "$d" ] || continue                              # unmatched glob stays literal -> skipped
        d="${d%/}"; n="${d##*/round-}"
        case "$n" in ''|*[!0-9]*|??????*) continue ;; esac    # numeric, <=5 digits (no huge-suffix -gt error)
        [ -f "$d/$agent.json" ] || continue
        [ "$n" -gt "$best_n" ] && { best_n="$n"; best="$d"; }
    done
    [ -n "$best" ] && printf '%s' "$best"
}

# ---------------------------------------------------------------------------------------------------
# COREDEV-2326: per-subagent review-round BINDING — a stable cycle signal for the SubagentStop capture.
#
# The producer (a SubagentStart hook, scripts/capture-reviewer-round-start.sh) freezes the round for
# each reviewer subagent AT SPAWN, keyed by its unique `agent_id`; the consumer (the SubagentStop
# capture, scripts/capture-reviewer-verdict.sh) looks that round up by the SAME `agent_id` and exports
# UNLEASHED_REVIEW_ROUND so capture.py buckets it deterministically — even when a late reviewer from an
# earlier cycle stops AFTER a later cycle advanced (the interleaving mcp/review-synthesizer/capture.py's
# round INFERENCE cannot perfectly handle). Absent/stale/foreign-slug binding -> capture.py infers
# (the shipped default). Observe-only, fail-open, PII-free (only a slug token, opaque ids, an int, and
# an epoch are persisted). See docs/planning/REVIEW_ROUND_PRODUCER_PLAN.md.

# Highest existing round-<N> number under $1 (a <reviews_dir>/<slug> dir), as a DECIMAL-normalized
# integer (0 if none). `10#$n` forces base-10 so a leading-zero dir like `round-09` yields 9 (never an
# octal parse), so a caller's `$(( … + 1 ))` is 10 — not an `09: value too great for base` error
# (codex PR r2 Nit A). Same hardened scan idioms as context_latest_round_dir (numeric, <=5 digits,
# zsh-NOMATCH-safe), minus the per-agent .json filter. $1 = base dir.
context_highest_round() {
    local base="${1:-}" best=0 d n
    [ -n "$base" ] || { printf '0'; return 0; }
    [ -n "${ZSH_VERSION:-}" ] && setopt local_options no_nomatch 2>/dev/null || true
    for d in "$base"/round-*/; do
        [ -d "$d" ] || continue
        d="${d%/}"; n="${d##*/round-}"
        case "$n" in ''|*[!0-9]*|??????*) continue ;; esac
        n=$(( 10#$n ))                                        # decimal-normalize (round-09 -> 9)
        [ "$n" -gt "$best" ] && best="$n"
    done
    printf '%s' "$best"
}

# Validity window (seconds) for a round binding: long enough for a reviewer panel, short enough that an
# orphaned binding (a crashed subagent whose SubagentStop never fired) can't steer a much later review.
# `0` disables the freshness check. Overridable for tests/tuning.
context_round_ttl() { printf '%s' "${UNLEASHED_REVIEW_ROUND_TTL:-3600}"; }

# Per-subagent binding path: <state_dir>/review-round-<repohash>-<agentidhash>.json. The repo hash
# isolates checkouts (like the snapshot/reviews dirs); the agent_id is HASHED (12-hex, PII-free, never
# path characters) so the unique subagent id is the key without ever touching the filesystem raw. $1 = agent_id.
context_round_binding_path() {
    printf '%s/review-round-%s-%s.json' "$(context_state_dir)" "$(context_repo_hash)" "$(_context_hash "${1:-}")"
}

# Portable file mtime (epoch secs): BSD/macOS `stat -f %m` first, GNU `stat -c %Y` fallback. "" on failure.
_context_file_mtime() {
    local m=""
    m="$(stat -f %m "$1" 2>/dev/null)" || m=""
    [ -n "$m" ] || m="$(stat -c %Y "$1" 2>/dev/null)" || m=""
    printf '%s' "$m"
}

# Best-effort GC of binding files in $1 older than the TTL (bounded .state housekeeping for orphaned
# bindings). Pure hygiene — correctness never depends on it (lookup rejects stale; consume deletes the
# live one). zsh-NOMATCH-safe; fail-open. $1 = state dir, $2 = now (epoch).
_context_round_sweep() {
    local dir="${1:-}" now="${2:-0}" ttl f mt
    [ -n "$dir" ] && [ -d "$dir" ] || return 0
    ttl="$(context_round_ttl)"
    case "$ttl" in ''|*[!0-9]*) return 0 ;; esac
    [ "$ttl" -gt 0 ] && [ "$now" -gt 0 ] || return 0
    [ -n "${ZSH_VERSION:-}" ] && setopt local_options no_nomatch 2>/dev/null || true
    for f in "$dir"/review-round-*.json; do
        [ -f "$f" ] || continue
        mt="$(_context_file_mtime "$f")"
        case "$mt" in ''|*[!0-9]*) continue ;; esac
        [ "$(( now - mt ))" -gt "$ttl" ] && rm -f "$f" 2>/dev/null
    done
}

# Locate the synthesizer package (capture.py + schema.py) relative to this lib, so the producer can
# REUSE capture.is_final_capture for its advance decision (single-sourcing that subtle predicate).
# BASH_SOURCE[0] is this file even inside a function (defining file). $0 fallback for non-bash sourcing.
_context_capture_dir() {
    local d
    d="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)" || d="."
    printf '%s/../../mcp/review-synthesizer' "$d"
}

# Should the producer ADVANCE past `$2` (the highest existing round) for `$3` (agent), or REUSE it?
# Echoes "0" (REUSE) ONLY when capture.is_final_capture confirms the highest round's slot for this
# agent is NON-final (empty / schema-dropped / missing) — mirroring capture.select_round's non-override
# path, so a same-round REPAIR re-run (swift-reviewer's recovery rule) overwrites the stale empty slot
# instead of splitting the cycle into a new round (codex PR #17 review). Echoes "1" (ADVANCE) otherwise,
# INCLUDING when finality can't be determined (no python3/capture.py) — the safe default never
# overwrites a genuine prior capture. $1 = base, $2 = highest, $3 = agent.
_context_round_advance() {
    local base="${1:-}" highest="${2:-0}" agent="${3:-}" capdir out
    command -v python3 >/dev/null 2>&1 || { printf '1'; return 0; }
    capdir="$(_context_capture_dir)"
    [ -f "$capdir/capture.py" ] || { printf '1'; return 0; }
    out="$(UNLEASHED_FC_CAPDIR="$capdir" python3 -c '
import os, sys
capdir = os.environ.get("UNLEASHED_FC_CAPDIR", "")
if capdir:
    sys.path.insert(0, capdir)
try:
    import capture
except Exception:
    sys.stdout.write("1"); sys.exit(0)   # cannot import -> ADVANCE (never overwrite a real capture)
sys.stdout.write("1" if capture.is_final_capture(sys.argv[1]) else "0")
' "$base/round-$highest/$agent.json" 2>/dev/null)"
    case "$out" in 0) printf '0' ;; *) printf '1' ;; esac   # any odd/empty output -> ADVANCE (safe)
}

# PRODUCER: freeze and persist the round for a reviewer subagent at spawn. The round MIRRORS
# capture.select_round's non-override path so the producer and the capture stay consistent: first cycle
# = 1; advance to highest+1 only when the highest round's slot for this agent already holds a FINAL
# capture; otherwise REUSE the highest round (a same-round repair re-run overwrites an empty/dropped
# slot rather than splitting the cycle — codex PR #17). The four reviewers of one cycle spawn in a
# single parallel batch BEFORE any capture, so all four read highest=0 and bind round 1. Atomic write
# (tmp + mv). Sweeps expired bindings first. Prints the round. Fail-open.
# $1 = agent_type, $2 = agent_id, $3 = session_id (optional).
context_review_round_bind() {
    local agent="${1:-}" agent_id="${2:-}" sid="${3:-}" slug base highest round now path dir
    [ -n "$agent" ] && [ -n "$agent_id" ] || return 0
    slug="$(context_branch_slug "$(context_branch)")"
    base="$(context_reviews_dir)/$slug"
    highest="$(context_highest_round "$base")"
    if [ "$highest" -eq 0 ]; then
        round=1
    elif [ "$(_context_round_advance "$base" "$highest" "$agent")" = "0" ]; then
        round="$highest"                                       # reuse: prior slot is empty/non-final
    else
        round=$(( highest + 1 ))                               # advance: prior slot is a final capture
    fi
    now="$(date +%s 2>/dev/null || echo 0)"
    # session_id is an opaque CC id; hard-restrict to a JSON-safe charset (and cap) so the bash-written
    # JSON can never be malformed by an unexpected value. agent is hook-allowlisted; slug is a safe token.
    sid="$(printf '%s' "$sid" | tr -cd 'A-Za-z0-9._-' | cut -c1-128)"
    path="$(context_round_binding_path "$agent_id")"
    dir="$(dirname "$path")"
    mkdir -p "$dir" 2>/dev/null || true
    _context_round_sweep "$dir" "${now:-0}"
    if printf '{"round":%d,"agent":"%s","slug":"%s","session_id":"%s","time":%s}\n' \
        "$round" "$agent" "$slug" "$sid" "${now:-0}" > "$path.tmp.$$" 2>/dev/null; then
        mv -f "$path.tmp.$$" "$path" 2>/dev/null || rm -f "$path.tmp.$$" 2>/dev/null
    else
        rm -f "$path.tmp.$$" 2>/dev/null
    fi
    printf '%s' "$round"
}

# CONSUMER-READ: print this subagent's frozen round, or nothing. Honors the binding ONLY when it
# parses AND `agent` matches AND `slug` matches the current branch slug AND `session_id` matches (soft:
# only when BOTH sides are non-empty) AND `round` is a positive int AND it is fresh within the TTL.
# Anything off -> nothing -> the caller leaves UNLEASHED_REVIEW_ROUND unset -> capture.py infers.
# Stdlib python3 (already a hard capture dependency). $1 = agent_type, $2 = agent_id, $3 = session_id.
context_review_round_lookup() {
    local agent="${1:-}" agent_id="${2:-}" sid="${3:-}" path slug
    [ -n "$agent" ] && [ -n "$agent_id" ] || return 0
    path="$(context_round_binding_path "$agent_id")"
    [ -f "$path" ] || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    slug="$(context_branch_slug "$(context_branch)")"
    UNLEASHED_RB_AGENT="$agent" UNLEASHED_RB_SLUG="$slug" UNLEASHED_RB_SID="$sid" \
    UNLEASHED_RB_TTL="$(context_round_ttl)" UNLEASHED_RB_NOW="$(date +%s 2>/dev/null || echo 0)" \
    python3 -c '
import json, os, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
except (OSError, ValueError):
    sys.exit(0)
if not isinstance(d, dict):
    sys.exit(0)
if d.get("agent") != os.environ.get("UNLEASHED_RB_AGENT"):
    sys.exit(0)
if d.get("slug") != os.environ.get("UNLEASHED_RB_SLUG"):
    sys.exit(0)
sid_want = os.environ.get("UNLEASHED_RB_SID", "")
sid_have = d.get("session_id", "")
if sid_want and sid_have and sid_want != sid_have:   # soft: only reject when both present and differ
    sys.exit(0)
r = d.get("round")
if not isinstance(r, int) or isinstance(r, bool) or r <= 0:
    sys.exit(0)
try:
    ttl = int(os.environ.get("UNLEASHED_RB_TTL", "3600"))
    now = int(os.environ.get("UNLEASHED_RB_NOW", "0"))
except ValueError:
    ttl, now = 3600, 0
t = d.get("time")
if ttl > 0 and now > 0 and isinstance(t, (int, float)) and not isinstance(t, bool):
    if now - t > ttl:
        sys.exit(0)
sys.stdout.write(str(r))
' "$path" 2>/dev/null
}

# Consume-once: delete a subagent's binding after its SubagentStop has read it (so a later duplicate
# stop, or an unrelated reader, never re-reads it). Fail-open. $1 = agent_id.
context_review_round_clear() {
    [ -n "${1:-}" ] || return 0
    rm -f "$(context_round_binding_path "$1")" 2>/dev/null || true
}
