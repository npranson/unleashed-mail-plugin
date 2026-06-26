#!/usr/bin/env bash
# shellcheck shell=bash
# Shared quality-marker reader/writer for the Stop-gate (Item 4, COREDEV-2324).
#
# This file is SOURCED, never executed.
#
# Markers live OUTSIDE the repo, under the plugin data dir — never /tmp, never the
# repo. The body is PII-free: status/kind/ts/short-sha + a repo HASH only; the
# absolute repo path is consumed solely to compute the hash and is never written,
# emitted, or echoed to stderr. Every probe and state write is `2>/dev/null` and
# fail-open so a failed mkdir/redirect/mv can never leak a path or abort a hook.
#
# Marker body: {"status":"pass|fail","kind":"lint|build","ts":"…Z","commit":"<short>","repo_hash":"<12hex>"}
# Freshness source of truth is the marker FILE's mtime, not the `ts` field.

marker_base() {
    # ${HOME:-} so a missing HOME under `set -u` never aborts a hook; if both are
    # unset the path becomes "/.claude/..." and the later mkdir simply fails open.
    printf '%s' "${CLAUDE_PLUGIN_DATA:-${HOME:-}/.claude/unleashed-mail}"
}

marker_dir() {
    printf '%s/.state' "$(marker_base)"
}

# Pure-bash 32-bit djb2 hash (hex) of a string. Used ONLY when no hashing binary
# exists. It emits a hash, never any path-derived characters, so the absolute path
# is never exposed (a `tr`-slug fallback would leak e.g. the username).
_marker_bash_hash() {
    local s="$1" i=0 len="${#1}" h=5381 c=0 ch=""
    while [ "$i" -lt "$len" ]; do
        ch="${s:$i:1}"
        # A single-quote char makes `printf '%d' "'${ch}"` the invalid constant "''"
        # which fails to 0; handle it explicitly so paths with quotes still hash (PR #12).
        if [ "$ch" = "'" ]; then
            c=39
        else
            c="$(printf '%d' "'$ch" 2>/dev/null)"
        fi
        h=$(( (h * 33 + ${c:-0}) & 0xffffffff ))
        i=$(( i + 1 ))
    done
    printf '%x' "$h"
}

# 12-hex sha1 of the repo's absolute path. The path is hashed, never surfaced.
# Cached per-process: the Stop hook calls this several times per invocation (gemini PR #12).
_MARKER_REPO_HASH_CACHE=""
marker_repo_hash() {
    [ -n "$_MARKER_REPO_HASH_CACHE" ] && { printf '%s' "$_MARKER_REPO_HASH_CACHE"; return 0; }
    local root="" h=""
    root="$(git rev-parse --show-toplevel 2>/dev/null)" || root=""
    [ -n "$root" ] || root="$PWD"
    if command -v shasum >/dev/null 2>&1; then
        h="$(printf '%s' "$root" | shasum 2>/dev/null | cut -d' ' -f1)"
    elif command -v sha1sum >/dev/null 2>&1; then
        h="$(printf '%s' "$root" | sha1sum 2>/dev/null | cut -d' ' -f1)"
    elif command -v openssl >/dev/null 2>&1; then
        h="$(printf '%s' "$root" | openssl dgst -sha1 2>/dev/null | awk '{print $NF}')"
    elif command -v python3 >/dev/null 2>&1; then
        h="$(printf '%s' "$root" | python3 -c 'import hashlib,sys; sys.stdout.write(hashlib.sha1(sys.stdin.buffer.read()).hexdigest())' 2>/dev/null)"
    fi
    # Fail-open but NEVER empty: an empty hash would drop the per-repo discriminator
    # from the marker path/body. Fall back to cksum, then a path-derived slug.
    if [ -z "$h" ] && command -v cksum >/dev/null 2>&1; then
        h="$(printf '%s' "$root" | cksum 2>/dev/null | tr -cd '0-9')"
    fi
    # Final resort: a pure-bash hash of the path — PII-free (never path characters),
    # always available. Guarantees a non-empty, per-repo discriminator.
    [ -n "$h" ] || h="$(_marker_bash_hash "$root")"
    _MARKER_REPO_HASH_CACHE="${h:0:12}"
    printf '%s' "$_MARKER_REPO_HASH_CACHE"
}

# Absolute path of a marker file. $1 = kind (lint|build).
marker_path() {
    printf '%s/quality-marker-%s-%s.json' "$(marker_dir)" "$1" "$(marker_repo_hash)"
}

# Write a marker atomically. $1 = kind (lint|build), $2 = status (pass|fail).
# status/kind are controlled tokens (no escaping needed). Fail-open on any error.
marker_write() {
    local kind="$1" status="$2" dir="" path="" tmp="" commit="" ts="" hash=""
    dir="$(marker_dir)"
    mkdir -p "$dir" 2>/dev/null || return 0
    path="$(marker_path "$kind")"
    tmp="${path}.tmp.$$"
    commit="$(git rev-parse --short HEAD 2>/dev/null)" || commit=""
    [ -n "$commit" ] || commit="unknown"
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
    hash="$(marker_repo_hash)"
    printf '{"status":"%s","kind":"%s","ts":"%s","commit":"%s","repo_hash":"%s"}\n' \
        "$status" "$kind" "$ts" "$commit" "$hash" > "$tmp" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 0; }
    mv "$tmp" "$path" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 0; }
    # On a pass, clear the Stop-gate's last-blocked sentinel for this repo so a later
    # regression on the same commit can block again (gemini PR #12).
    if [ "$status" = "pass" ]; then
        rm -f "$dir/stop-last-blocked-${hash}" 2>/dev/null || true
    fi
}

# Read one string field from a marker file. $1 = kind, $2 = field. Empty if absent.
marker_field() {
    local kind="$1" field="$2" path="" line=""
    path="$(marker_path "$kind")"
    [ -f "$path" ] || return 0
    # Fast path: the marker is a known single-line JSON — parse with bash's built-in
    # regex to avoid spawning jq/python3 on every call (gemini PR #12, perf).
    if read -r line < "$path" 2>/dev/null && [[ "$line" =~ \"$field\":\"([^\"]+)\" ]]; then
        printf '%s' "${BASH_REMATCH[1]}"
        return 0
    fi
    if command -v jq >/dev/null 2>&1; then
        jq -r --arg f "$field" '.[$f] // empty' "$path" 2>/dev/null
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1]))
    v=d.get(sys.argv[2],"")
    sys.stdout.write("" if v is None else str(v))
except Exception:
    pass' "$path" "$field" 2>/dev/null
    else
        grep -o "\"$field\":\"[^\"]*\"" "$path" 2>/dev/null | head -1 | sed 's/.*:"//; s/"$//'
    fi
}

marker_status() { marker_field "$1" status; }
marker_commit() { marker_field "$1" commit; }

# Marker file mtime in epoch seconds — the freshness source of truth. 0 on error.
marker_mtime() {
    local path="" m=""
    path="$(marker_path "$1")"
    [ -f "$path" ] || { printf '0'; return 0; }
    if [ "$(uname 2>/dev/null)" = "Darwin" ]; then
        m="$(stat -f %m "$path" 2>/dev/null)"
    else
        m="$(stat -c %Y "$path" 2>/dev/null)"
    fi
    printf '%s' "${m:-0}"
}
