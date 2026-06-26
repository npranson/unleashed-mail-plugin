#!/usr/bin/env bash
# PreCompact work-context snapshot (Item 5, COREDEV-2325).
#
# Before context compaction wipes the conversation, snapshot a tiny, PII-SAFE work
# context to a state file so SessionStart(source=compact) can re-inject a one-line resume
# hint. The raw branch name is NEVER persisted — only safe derived tokens (ticket key /
# version / branch hash; see scripts/lib/context.sh). PreCompact output is side-effect
# only; this hook never blocks compaction.
#
# Kill switch:  UNLEASHED_COMPACT_SNAPSHOT=off  -> exit 0
set -uo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=scripts/lib/hook-io.sh
. "$_DIR/lib/hook-io.sh"
# shellcheck source=scripts/lib/context.sh
. "$_DIR/lib/context.sh"

[ "${UNLEASHED_COMPACT_SNAPSHOT:-on}" = "off" ] && exit 0

BRANCH="$(context_branch)"
TICKET="$(context_ticket "$BRANCH")"      # COREDEV-NNNN / vX.Y.Z / 1.0X / unknown
SLUG="$(context_branch_slug "$BRANCH")"   # safe token or 12-hex hash — never raw branch

# Newest plan doc, resolved from the REPO ROOT (not the session cwd, which may be a subdirectory)
# so it's found wherever the hook fires (codex PR review), stored repo-relative. stderr-clean even
# when docs/planning exists but holds no *_PLAN.md (the literal glob would otherwise make `ls`
# error). Redact + cap defensively.
PLAN="unknown"
_root="$(context_repo_root)"
if [ -d "$_root/docs/planning" ]; then
    _plan="$(ls -t "$_root"/docs/planning/*_PLAN.md 2>/dev/null | head -1)"
    [ -n "$_plan" ] && PLAN="${_plan#"$_root"/}"
fi
PLAN="$(hook_redact_pii "$PLAN")"
PLAN="${PLAN:0:200}"   # bash substring (char-aware, no cut subprocess / BSD `cut -c` quirk)
[ -n "$PLAN" ] || PLAN="unknown"

# Round = newest reviews/<slug>/round-N bucket, else "unknown" (enriched once Item 6 captures).
# Glob + arithmetic compare (no `ls | grep`) so a non-numeric/odd name can't trip it.
ROUND="unknown"
_rev="$(context_reviews_dir)/$SLUG"
if [ -d "$_rev" ]; then
    _max=0
    for _d in "$_rev"/round-*; do
        [ -d "$_d" ] || continue
        _n="${_d##*/round-}"
        case "$_n" in ''|*[!0-9]*) continue ;; esac
        [ "$_n" -gt "$_max" ] && _max="$_n"
    done
    [ "$_max" -gt 0 ] && ROUND="$_max"
fi

SNAPTIME="$(date +%s 2>/dev/null)" || SNAPTIME=0
case "$SNAPTIME" in ''|*[!0-9]*) SNAPTIME=0 ;; esac

mkdir -p "$(context_state_dir)" 2>/dev/null || exit 0
SNAP="$(context_snapshot_path)"   # per-checkout: .state/work-context-snapshot-<repohash>.json
TMP="${SNAP}.tmp.$$"
# Self-disarming EXIT trap: any early exit removes the partial tmp; disarmed after the mv.
trap 'rm -f "$TMP" 2>/dev/null' EXIT

PLAN_JSON="$(json_escape "$PLAN")"
# `2>/dev/null` BEFORE `> "$TMP"` so an open failure (state dir unwritable) is suppressed too
# (bash applies redirects left-to-right; a trailing `2>/dev/null` would let the open error —
# which echoes the full PII-bearing tmp path — reach stderr). EXIT trap removes the tmp.
printf '{"ticket":"%s","branch_slug":"%s","plan":%s,"round":"%s","snapshot_time":%s}\n' \
    "$TICKET" "$SLUG" "$PLAN_JSON" "$ROUND" "$SNAPTIME" 2>/dev/null > "$TMP" || exit 0
mv "$TMP" "$SNAP" 2>/dev/null || exit 0
trap - EXIT
exit 0
