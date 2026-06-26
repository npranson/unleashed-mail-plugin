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
