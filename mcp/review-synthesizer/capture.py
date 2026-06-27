#!/usr/bin/env python3
"""SubagentStop reviewer-verdict capture core (Item 6, COREDEV-2325).

Importable, stdlib-only module that the `scripts/capture-reviewer-verdict.sh` hook calls to
turn a reviewer subagent's final message into a per-round, per-agent findings file directly
consumable by ``synthesize.py``. It sits beside ``schema.py``/``synthesize.py`` so it can
REUSE the synthesizer's own ``schema.parse_finding`` for enum/type validation, and so the
unit tests can import it.

Security invariants (the capture is persisted telemetry, NOT a gating source of truth — a
dropped/malformed finding is handled by ``swift-reviewer`` Step-5 recovery in-session):
  * The persisted JSON is SANITIZED EVIDENCE. Every transcript-originated free-text field
    (``finding``/``evidence``/``fix``) is PII-redacted and length-capped; ``file`` is
    redacted and any absolute/``/Users/<name>`` path is collapsed to ``[abs]/<basename>``;
    ``sourceAgent`` is normalized to the hook's allowlisted ``agent_type`` (never the
    transcript's value); enum/number fields are validated by ``schema.parse_finding`` so no
    arbitrary string survives. A finding that fails validation is DROPPED, never persisted.
  * The destination path is built only from a PII-safe slug (a ticket token or branch hash)
    plus a numeric round, and is re-checked with a portable real-path traversal guard
    (``os.path.realpath`` — NOT GNU ``realpath -m``) so a write can never escape the
    capture root.
  * A sibling ``<agent>.status`` JSON (COREDEV-2328) records the reviewer's Output-Contract
    ``Status:`` (COMPLETE | BLOCKED | PARTIAL + BLOCKED/PARTIAL detail fields) so a captured
    ``BLOCKED`` can't read as a clean ``[]``. It sits BESIDE the findings array (not inside it),
    leaving ``is_final_capture``/``synthesize._load`` untouched; every persisted detail field is
    PII-redacted + capped; ``agent`` is the allowlisted name; and it is written/cleared best-effort
    AFTER the findings land (never fails the findings capture).
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import schema  # noqa: E402  (sibling module; path inserted above)

# --- PII redaction (mirrors scripts/lib/hook-io.sh `hook_redact_pii` 1:1) ----------------
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_USERS = re.compile(r"/Users/[^/\s\"]+")
_HOME = re.compile(r"/home/[^/\s\"]+")
_TILDE = re.compile(r"~[A-Za-z0-9._-]+")
_BEARER = re.compile(r"bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE)
_JWT = re.compile(r"eyJ[A-Za-z0-9._-]{10,}")
_SECRET = re.compile(r"(?:sk-|pk_)[A-Za-z0-9._-]{8,}")
_APIKEY = re.compile(r"api[\s_-]?key\s*[:=]\s*[A-Za-z0-9._-]+", re.IGNORECASE)

EVIDENCE_CAP = 500
FILE_CAP = 300

VALID_AGENTS = (
    "security-reviewer",
    "concurrency-reviewer",
    "ux-perf-reviewer",
    "accessibility-auditor",
    "prompt-review",
)


def redact_pii(s: object) -> str:
    """Redact emails, home-dir usernames, JWT/Bearer tokens, secrets, and api keys from a
    free-text string, then fold newlines/tabs to spaces. Mirrors the shell redactor."""
    text = s if isinstance(s, str) else str(s)
    text = _EMAIL.sub("[redacted-email]", text)
    text = _USERS.sub("/Users/[redacted]", text)
    text = _HOME.sub("/home/[redacted]", text)
    text = _TILDE.sub("~[redacted]", text)
    text = _BEARER.sub("[redacted-token]", text)
    text = _JWT.sub("[redacted-jwt]", text)
    text = _SECRET.sub("[redacted-secret]", text)
    text = _APIKEY.sub("[redacted-key]", text)
    return re.sub(r"[\r\n\t]+", " ", text)


def cap(s: object, n: int = EVIDENCE_CAP) -> str:
    text = s if isinstance(s, str) else str(s)
    return text[:n]


def normalize_file(f: str) -> str:
    """Redact a `file` path and collapse any remaining absolute/`/Users/...` path to
    `[abs]/<basename>` so a machine path can never persist (an absolute path would not match
    the synthesizer's repo-relative `changed_files` anyway)."""
    text = redact_pii(f)
    if text.startswith("/"):
        text = "[abs]/" + os.path.basename(text.rstrip("/"))
    return cap(text, FILE_CAP)


# --- findings extraction + validation ----------------------------------------------------
# The fence tag must be EXACTLY `json` — the negative lookahead stops `json` matching as a
# prefix of a longer tag (```jsonc / ```json5), which would otherwise let a trailing
# annotated example fence hijack the last-block-wins selection and capture garbage.
_FENCE = re.compile(r"```json(?![A-Za-z0-9_-])(.*?)```", re.DOTALL)


def extract_last_json_block(text: object) -> "str | None":
    """Return the inner text of the LAST ```json fenced block (the reviewer's findings array
    is the report's final fence), or None if there is no fenced json block."""
    if not isinstance(text, str):
        return None
    blocks = _FENCE.findall(text)
    if not blocks:
        return None
    return blocks[-1].strip()


def validate_findings(raw_text: str) -> list:
    """Parse the fenced block and return the raw findings list. Accepts a bare list OR a
    `{"findings": [...]}` object (the synthesizer's input shapes). Raises on anything else."""
    obj = json.loads(raw_text)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and isinstance(obj.get("findings"), list):
        return obj["findings"]
    raise ValueError('not a findings array or {"findings": [...]}')


def sanitize_finding(d: object, agent_type: str) -> "dict | None":
    """Validate one raw finding via the synthesizer's own `schema.parse_finding` (enforces
    enums + int line/lineEnd + path canonicalization), then redact+cap every free-text field
    and normalize `sourceAgent` to the hook's allowlisted `agent_type`. Returns a
    synthesizer-consumable dict, or None to DROP an invalid finding (never persisted)."""
    if not isinstance(d, dict):
        return None
    candidate = dict(d)
    # Normalize sourceAgent BEFORE validation so a missing/spoofed transcript value still
    # validates against the hook-filtered, allowlisted agent (codex BEFORE-gate note 5).
    candidate["sourceAgent"] = agent_type
    try:
        f = schema.parse_finding(candidate)
    except schema.SchemaError:
        return None
    return {
        "severity": f.severity,
        "confidence": f.confidence,
        "sourceAgent": agent_type,
        "category": f.category,
        "file": normalize_file(f.file),
        "line": f.line,
        "lineEnd": f.lineEnd,
        "scope": f.scope,
        "finding": cap(redact_pii(f.finding)),
        "evidence": cap(redact_pii(f.evidence)),
        "fix": cap(redact_pii(f.fix)),
    }


# --- destination + dedup -----------------------------------------------------------------
def safe_join(capture_root: str, slug: str, round_n: int, agent: str) -> str:
    """Build `<root>/<slug>/round-<N>/<agent>.json` and enforce a portable real-path
    traversal guard: the resolved destination must stay strictly under the resolved root.
    `round_n` is coerced to an int (a non-numeric value raises ValueError, so the round
    component can never traverse); the slug is re-checked with realpath as defence-in-depth.
    Raises ValueError on any escape."""
    dest = os.path.join(capture_root, slug, "round-%d" % int(round_n), "%s.json" % agent)
    root_real = os.path.realpath(capture_root)
    dest_real = os.path.realpath(dest)
    if dest_real != root_real and not dest_real.startswith(root_real + os.sep):
        raise ValueError("path traversal: %r escapes %r" % (dest_real, root_real))
    return dest


def _agentid_path(round_dir: str, agent: str) -> str:
    return os.path.join(round_dir, agent + ".agentid")


def _read_agentids(round_dir: str, agent: str) -> "set[str]":
    """The set of subagent ids recorded for this agent's slot in `round_dir`. A slot may be REUSED
    (a rerun overwrites an empty/bad capture), so the sidecar ACCUMULATES every id that has written
    it (one per line) — overwriting it would forget a prior id and miss a later duplicate."""
    try:
        with open(_agentid_path(round_dir, agent), encoding="utf-8") as fh:
            return {ln.strip() for ln in fh if ln.strip()}
    except OSError:
        return set()


def _add_agentid(round_dir: str, agent: str, agent_id: str) -> None:
    """Record `agent_id` for this slot WITHOUT dropping ids already there (codex PR review)."""
    ids = _read_agentids(round_dir, agent)
    ids.add(agent_id)
    try:
        with open(_agentid_path(round_dir, agent), "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(ids)) + "\n")
    except OSError:
        pass


def _seen_agent_ids(base: str, agent: str) -> "set[str]":
    """Every subagent id ever recorded for `agent` across ALL rounds under `base`, so a duplicate
    SubagentStop is recognised no matter how many rounds have opened OR how many times a slot was
    reused since (codex PR review)."""
    seen = set()
    try:
        names = os.listdir(base)
    except OSError:
        return seen
    for name in names:
        if re.match(r"round-(\d+)$", name):
            seen |= _read_agentids(os.path.join(base, name), agent)
    return seen


def select_round(capture_root: str, slug: str, agent: str = "", agent_id: str = "") -> int:
    """The target round. Deterministic override first: `UNLEASHED_REVIEW_ROUND` (a positive int the
    orchestrator may set per cycle). Otherwise: the highest existing `round-N` under `<root>/<slug>`,
    advancing to the NEXT round when this reviewer's slot in the highest round is already filled.

    Duplicates are filtered out earlier by `capture()`'s cross-round `agent_id` check, so a filled
    slot here can only mean a NEW subagent re-ran the reviewer (a re-review) -> a fresh round. With
    `agent_id` this is fully deterministic and timing-independent. When agent_id is unavailable the
    round stays put (highest-or-1) with `UNLEASHED_REVIEW_ROUND` as the explicit fallback. Defaults
    to 1 when there is no prior round."""
    override = os.environ.get("UNLEASHED_REVIEW_ROUND", "")
    if override.isdigit() and int(override) > 0:
        return int(override)
    base = os.path.join(capture_root, slug)
    highest = 0
    try:
        for name in os.listdir(base):
            m = re.match(r"round-(\d+)$", name)
            if m:
                highest = max(highest, int(m.group(1)))
    except OSError:
        pass
    if highest == 0:
        return 1
    # Advance only when the highest round's slot already holds a VALID capture (a real prior
    # review). If the slot is empty/corrupt/schema-dropped junk, stay in the round so the rerun
    # OVERWRITES it instead of splitting the review across rounds (codex PR review).
    if agent and agent_id and is_final_capture(os.path.join(base, "round-%d" % highest, agent + ".json")):
        return highest + 1
    return highest


def is_final_capture(path: str) -> bool:
    """Dedup predicate: True only if `path` already holds a list with at least one finding
    that PARSES as valid (via the synthesizer's schema). A replay of real findings skips; but
    a corrupt/partial file, a list of junk (`[{}]` / `["x"]`), or an empty `[]` (a clean
    review, or a round where every finding was schema-dropped) is treated as "nothing captured
    yet" so a later same-round capture with real findings can replace it."""
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, ValueError):
        return False
    if not isinstance(obj, list) or not obj:
        return False
    for item in obj:
        try:
            schema.parse_finding(item)
            return True  # at least one genuine finding -> a real capture, don't clobber
        except schema.SchemaError:
            continue
    return False


# --- Output-Contract status sidecar (COREDEV-2328) ---------------------------------------
# Persist the reviewer's `Status:` (COMPLETE | BLOCKED | PARTIAL + BLOCKED/PARTIAL detail fields)
# as a sibling `<agent>.status` JSON so `swift-reviewer` can honour a BLOCKED capture instead of
# reading its `[]` as a clean pass — WITHOUT touching the findings array shape (``synthesize._load``,
# ``is_final_capture``, and every existing consumer still see a bare list). Observe-only, fail-open,
# PII-redacted, exactly like the findings capture above.
STATUS_VALUES = ("COMPLETE", "BLOCKED", "PARTIAL")
STATUS_FIELD_CAP = EVIDENCE_CAP

# A status line. REQUIRES a separator (so `StatusCOMPLETE`/`Status COMPLETE` never match); markers
# tolerated on both sides but NOT backtick (so the contract's own inline-code examples
# `` `Status: X` `` are not matched); end-anchored (rejects the `| BLOCKED | PARTIAL` template echo).
# Single-class quantifiers around a REQUIRED separator literal -> linear / ReDoS-safe.
_STATUS_LINE = re.compile(
    r"^[ \t>*_#-]*status[ \t>*_#]*[:=–—-][ \t>*_#-]*(COMPLETE|BLOCKED|PARTIAL)[ \t>*_#.-]*$",
    re.IGNORECASE,
)
# A code-fence marker line: group 1 = the run (>=3 backticks OR tildes), group 2 = info / trailing.
_FENCE_MARK = re.compile(r"^[ \t>]*(`{3,}|~{3,})[ \t]*(.*)$")

# BLOCKED/PARTIAL detail fields: contract label -> persisted key. Require a `:`/`=` separator;
# capture the rest of the (single) line. Backtick excluded, mirroring the status line.
_STATUS_FIELDS = (
    ("blocker description", "blockerDescription"),
    ("what was attempted", "whatWasAttempted"),
    ("completed", "completed"),
    ("remaining", "remaining"),
    ("confidence", "confidence"),
)


def _compile_field(label: str) -> "re.Pattern[str]":
    words = r"[ \t]+".join(re.escape(w) for w in label.split())
    return re.compile(r"^[ \t>*_#-]*" + words + r"[ \t>*_#]*[:=][ \t>*_#-]*(.+)$", re.IGNORECASE)


_FIELD_RES = [(_compile_field(label), key) for label, key in _STATUS_FIELDS]


def _match_field(line: str) -> "tuple[str, str] | None":
    """Return ``(key, raw_value)`` for a single detail-field line, else None."""
    for rx, key in _FIELD_RES:
        m = rx.match(line)
        if m:
            return key, m.group(1)
    return None


def extract_status(text: object) -> "dict | None":
    """Parse the reviewer's Output-Contract status from the report's TRUE pre-fence trailer.

    Walks UP from the final ```` ```json ```` fence over only blank + detail-field lines to a
    top-level ``Status:`` line; ANY other content — prose, or a line inside a code fence
    (CommonMark family/length-aware, terminated OR not) — ends the trailer and yields None. So a
    ``Status:`` buried in an earlier example / code block can never be persisted as the status.
    Returns ``{"status": <UPPER>, ...detail fields}`` (every field PII-redacted + capped) or None.
    """
    if not isinstance(text, str):
        return None
    fences = list(_FENCE.finditer(text))
    region = text[: fences[-1].start()] if fences else text
    lines = region.splitlines()
    # Flag code-fenced lines top-down, family + length aware: a ``` fence closes only on a same-family
    # run >= the opener with no info string, so a `~~~` inside a ``` block (or vice versa) is content.
    in_code = [False] * len(lines)
    open_char, open_len = "", 0
    for i, ln in enumerate(lines):
        m = _FENCE_MARK.match(ln)
        run = m.group(1) if m else ""
        info = m.group(2).strip() if m else ""
        if not open_char:
            if run:
                in_code[i] = True
                open_char, open_len = run[0], len(run)
        else:
            in_code[i] = True
            if run and run[0] == open_char and len(run) >= open_len and not info:
                open_char, open_len = "", 0
    # Walk up the contiguous top-level trailer to the status line.
    status, status_i, i = None, -1, len(lines) - 1
    while i >= 0:
        if in_code[i]:
            break
        ln = lines[i]
        if not ln.strip():
            i -= 1
            continue
        m = _STATUS_LINE.match(ln)
        if m:
            status, status_i = m.group(1).upper(), i
            break
        if _match_field(ln) is not None:
            i -= 1
            continue
        break
    if status is None:
        return None
    out = {"status": status}
    for ln in lines[status_i + 1:]:
        field = _match_field(ln)
        if field is not None and field[0] not in out:
            out[field[0]] = cap(redact_pii(field[1]), STATUS_FIELD_CAP)
    return out


def _status_path(round_dir: str, agent: str) -> str:
    return os.path.join(round_dir, agent + ".status")


def _write_status(round_dir: str, agent: str, status: dict) -> None:
    """Best-effort sibling `<agent>.status` write (tmp+replace, trailing newline). The self-describing
    `agent` is the hook-allowlisted name (never transcript text). Fully fail-open — NEVER raises, so
    it can't flip ``capture()``'s already-successful "written" result. Swallows OSError (fs failures),
    TypeError (a non-serializable value), and ValueError — incl. ``UnicodeEncodeError`` should a
    detail field carry an unencodable lone surrogate (not reachable via the shipped hook input, which
    decodes with ``errors="replace"``, but kept robust for any caller)."""
    dest = _status_path(round_dir, agent)
    tmp = "%s.tmp.%d" % (dest, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            # `agent` LAST so the trusted hook-allowlisted name always wins over any (transcript-
            # derived) `status` key; a dict literal also can't raise on a key collision the way
            # `dict(agent=..., **status)` can. Today `status` never carries an `agent` key (pinned
            # `_STATUS_FIELDS`), so this is behaviourally identical — just collision-proof and keeps
            # the "agent is never transcript text" invariant if the schema ever grows. (PR #16 review.)
            json.dump({**status, "agent": agent}, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, dest)
    except (OSError, TypeError, ValueError):
        try:
            os.remove(tmp)
        except OSError:
            pass


def _clear_status(round_dir: str, agent: str) -> None:
    """Best-effort removal of any existing `<agent>.status` so a status-less overwrite of a reused
    slot never inherits a prior occupant's status. Fully fail-open — NEVER raises."""
    try:
        os.remove(_status_path(round_dir, agent))
    except OSError:
        pass


def capture(capture_root: str, slug: str, agent: str, message: str, agent_id: str = "") -> str:
    """Capture one reviewer message. Returns a status string (for tests/logging):
    rejected | skipped | no-fence | invalid | written."""
    if agent not in VALID_AGENTS:
        return "rejected"
    base = os.path.join(capture_root, slug)
    # A true duplicate: the same agent_id already captured for this reviewer in ANY round (immediate
    # or delayed across round advances) -> skip without writing or advancing (codex PR review).
    if agent_id and agent_id in _seen_agent_ids(base, agent):
        return "skipped"
    round_n = select_round(capture_root, slug, agent, agent_id)
    try:
        dest = safe_join(capture_root, slug, round_n, agent)
    except ValueError:
        return "rejected"
    dest_dir = os.path.dirname(dest)
    # Absent-id fallback dedup: with no agent_id to tell a duplicate from a re-review, skip if a
    # valid capture already occupies this slot.
    if not agent_id and is_final_capture(dest):
        return "skipped"
    block = extract_last_json_block(message)
    if block is None:
        return "no-fence"
    try:
        items = validate_findings(block)
    except ValueError:
        return "invalid"
    sanitized = [s for s in (sanitize_finding(it, agent) for it in items) if s is not None]
    tmp = "%s.tmp.%d" % (dest, os.getpid())
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sanitized, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, dest)
        # Record the subagent id AFTER the findings land (so a stale id never points at no capture),
        # ACCUMULATING with any ids already recorded for this slot so a reuse can't forget a prior id
        # (codex PR review). Best-effort — a missing id just degrades the next selection to "same round".
        if agent_id:
            _add_agentid(dest_dir, agent, agent_id)
    except (OSError, TypeError):
        # Never leave a partial tmp on a write/replace failure (gemini PR review). Fail-open:
        # capture is observe-only, so a failed write just returns "invalid"; the hook exits 0.
        # (OSError = fs failures incl. IsADirectoryError; TypeError = a non-serializable value.)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return "invalid"
    # Status sidecar (COREDEV-2328) — runs only after the findings replace SUCCEEDED, OUTSIDE the
    # try/except above, so a status-side issue can never flip this into "invalid". Clear any prior
    # occupant's status FIRST, then write the freshly-extracted one (if any): a write failure OR a
    # status-less overwrite leaves the sidecar ABSENT (face value), never a stale BLOCKED/PARTIAL.
    # `_clear_status`/`_write_status` never raise.
    _clear_status(dest_dir, agent)
    status = extract_status(message)
    if status:
        _write_status(dest_dir, agent, status)
    return "written"


# --- transcript fallback (subagent transcript, NOT the parent session) -------------------
def _extract_assistant_text(obj: object) -> str:
    if not isinstance(obj, dict):
        return ""
    msg = obj["message"] if isinstance(obj.get("message"), dict) else obj
    if msg.get("role") != "assistant" and obj.get("type") != "assistant":
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                parts.append(b["text"])
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return ""


def read_last_assistant_from_transcript(path: str) -> str:
    """Best-effort: return the LAST assistant text from a JSONL subagent transcript. Read the file
    as BYTES and decode each line STRICTLY, skipping any line with invalid UTF-8 — so a corrupt
    line neither raises an uncaught UnicodeDecodeError (gemini PR review) nor decodes to U+FFFD and
    becomes `last`, shadowing an earlier valid findings message (codex PR review)."""
    last = ""
    try:
        with open(path, "rb") as fh:
            for raw in fh:
                try:
                    line = raw.decode("utf-8").strip()
                except UnicodeDecodeError:
                    continue  # skip a line with invalid UTF-8 entirely — don't let it become `last`
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                text = _extract_assistant_text(obj)
                if text:
                    last = text
    except OSError:
        return ""
    return last


def main(argv: "list[str]") -> int:
    import argparse

    p = argparse.ArgumentParser(description="Capture a reviewer subagent's findings.")
    p.add_argument("--root", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--agent", required=True)
    p.add_argument("--agent-id", dest="agent_id", default="")
    p.add_argument("--transcript", default=None)
    a = p.parse_args(argv)
    if a.transcript:
        message = read_last_assistant_from_transcript(a.transcript)
    else:
        # Read stdin as BYTES + decode UTF-8 explicitly so a non-UTF-8 locale (e.g. LANG=C in CI)
        # can't raise UnicodeDecodeError on a unicode reviewer message (gemini PR review class).
        message = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    if message:
        capture(a.root, a.slug, a.agent, message, a.agent_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
