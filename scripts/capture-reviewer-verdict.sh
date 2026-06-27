#!/usr/bin/env bash
# SubagentStop reviewer-verdict capture (Item 6, COREDEV-2325).
#
# When one of the four SPECIALIST reviewers finishes, persist its findings array to a
# per-round, per-agent file directly consumable by mcp/review-synthesizer/synthesize.py —
# closing the synthesizer's producer gap. EXCLUDES `swift-reviewer` (it is the synthesizer's
# CONSUMER/orchestrator; capturing it would feed the synthesizer its own output).
#
# The reviewer's final message comes from `last_assistant_message`, else the SUBAGENT
# transcript `agent_transcript_path` (NOT `transcript_path`, which is the parent session).
# All validation, PII-redaction, and the path-traversal guard live in capture.py.
# Observe-only: a missed capture never blocks (the orchestrator still collects findings).
#
# Kill switch:  UNLEASHED_CAPTURE_REVIEWERS=off  -> exit 0
set -uo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=scripts/lib/hook-io.sh
. "$_DIR/lib/hook-io.sh"
# shellcheck source=scripts/lib/context.sh
. "$_DIR/lib/context.sh"

CAPTURE_PY="$_DIR/../mcp/review-synthesizer/capture.py"

[ "${UNLEASHED_CAPTURE_REVIEWERS:-on}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
[ -f "$CAPTURE_PY" ] || exit 0

hook_io_read

AGENT="$(hook_str agent_type)"
case "$AGENT" in
    security-reviewer|concurrency-reviewer|ux-perf-reviewer|accessibility-auditor|prompt-review) ;;
    *) exit 0 ;;   # EXCLUDE swift-reviewer + everything else
esac

SLUG="$(context_branch_slug "$(context_branch)")"
ROOT="$(context_reviews_dir)"
# agent_id (distinct per subagent, identical on a true duplicate) lets capture.py tell a duplicate
# SubagentStop from a genuine re-review deterministically — see select_round.
AGENT_ID="$(hook_str agent_id)"

# COREDEV-2326: bind this capture to the round FROZEN at this subagent's SubagentStart
# (scripts/capture-reviewer-round-start.sh), looked up by the SAME agent_id — so a late reviewer from
# an earlier cycle lands in its ORIGINATING round regardless of completion order. Never clobber an
# explicitly-set value; honor the kill switch; an absent/stale/foreign binding -> leave it unset ->
# capture.py falls back to round inference (the shipped default). capture.py re-validates the value.
if [ "${UNLEASHED_REVIEW_ROUND_SIGNAL:-on}" != "off" ] && [ -z "${UNLEASHED_REVIEW_ROUND:-}" ] && [ -n "$AGENT_ID" ]; then
    _RS_ROUND="$(context_review_round_lookup "$AGENT" "$AGENT_ID" "$(hook_str session_id)" 2>/dev/null || true)"
    case "$_RS_ROUND" in ''|*[!0-9]*) ;; *) export UNLEASHED_REVIEW_ROUND="$_RS_ROUND" ;; esac
fi

MSG="$(hook_str last_assistant_message)"
if [ -n "$MSG" ]; then
    printf '%s' "$MSG" | python3 "$CAPTURE_PY" --root "$ROOT" --slug "$SLUG" --agent "$AGENT" --agent-id "$AGENT_ID" >/dev/null 2>&1 || true
else
    TP="$(hook_str agent_transcript_path)"
    if [ -n "$TP" ] && [ -f "$TP" ]; then
        python3 "$CAPTURE_PY" --root "$ROOT" --slug "$SLUG" --agent "$AGENT" --agent-id "$AGENT_ID" --transcript "$TP" >/dev/null 2>&1 || true
    fi
fi

# Consume-once: drop this subagent's binding now that its stop has read it, so a duplicate SubagentStop
# (or any later reader) can't re-use it. Best-effort; capture.py's cross-round agent_id dedup already
# guards a true duplicate independently.
[ -n "$AGENT_ID" ] && context_review_round_clear "$AGENT_ID" 2>/dev/null || true
exit 0
