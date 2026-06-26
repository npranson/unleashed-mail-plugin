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
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

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
_APIKEY = re.compile(r"[Aa][Pp][Ii][\s_-]?[Kk][Ee][Yy]\s*[:=]\s*[A-Za-z0-9._-]+")

EVIDENCE_CAP = 500
FILE_CAP = 300

VALID_AGENTS = (
    "security-reviewer",
    "concurrency-reviewer",
    "ux-perf-reviewer",
    "accessibility-auditor",
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


CYCLE_WINDOW_SEC = 600  # captures within this of the latest round's newest file belong to the same
                        # review cycle; a later capture starts a new round. Override via env.


def _cycle_window_sec() -> int:
    raw = os.environ.get("UNLEASHED_REVIEW_CYCLE_SEC", "")
    return int(raw) if raw.isdigit() and int(raw) > 0 else CYCLE_WINDOW_SEC


def select_round(capture_root: str, slug: str) -> int:
    """The target round. Deterministic override first: `UNLEASHED_REVIEW_ROUND` (a positive int the
    orchestrator may set per cycle). Otherwise derive it from a PERSISTED SIGNAL — the mtime of the
    newest capture in the highest existing round (codex PR review):

      * within the cycle window of that newest capture -> the SAME round. A review cycle's four
        reviewers run in parallel (seconds–minutes apart) and a duplicate SubagentStop arrives
        within seconds, so both stay in the round (the duplicate is then dedup-skipped);
      * past the window -> a NEW round, because a later capture is a fresh re-review cycle whose
        findings must not be dedup-skipped into the stale round.

    Defaults to 1 when there is no prior round. This avoids both relying on an unset env var and the
    stray-duplicate pollution that an unconditional 'completed round' auto-advance caused."""
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
    newest = 0.0
    round_dir = os.path.join(base, "round-%d" % highest)
    try:
        for f in os.listdir(round_dir):
            try:
                newest = max(newest, os.path.getmtime(os.path.join(round_dir, f)))
            except OSError:
                pass
    except OSError:
        pass
    if newest > 0.0 and (time.time() - newest) > _cycle_window_sec():
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


def capture(capture_root: str, slug: str, agent: str, message: str) -> str:
    """Capture one reviewer message. Returns a status string (for tests/logging):
    rejected | skipped | no-fence | invalid | written."""
    if agent not in VALID_AGENTS:
        return "rejected"
    round_n = select_round(capture_root, slug)
    try:
        dest = safe_join(capture_root, slug, round_n, agent)
    except ValueError:
        return "rejected"
    if is_final_capture(dest):
        return "skipped"  # dedup — a non-empty capture already exists for this round/agent
    block = extract_last_json_block(message)
    if block is None:
        return "no-fence"
    try:
        items = validate_findings(block)
    except ValueError:
        return "invalid"
    sanitized = [s for s in (sanitize_finding(it, agent) for it in items) if s is not None]
    dest_dir = os.path.dirname(dest)
    tmp = "%s.tmp.%d" % (dest, os.getpid())
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sanitized, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, dest)
    except (OSError, TypeError):
        # Never leave a partial tmp on a write/replace failure (gemini PR review). Fail-open:
        # capture is observe-only, so a failed write just returns "invalid"; the hook exits 0.
        # (OSError = fs failures incl. IsADirectoryError; TypeError = a non-serializable value.)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return "invalid"
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
    p.add_argument("--transcript", default=None)
    a = p.parse_args(argv)
    if a.transcript:
        message = read_last_assistant_from_transcript(a.transcript)
    else:
        # Read stdin as BYTES + decode UTF-8 explicitly so a non-UTF-8 locale (e.g. LANG=C in CI)
        # can't raise UnicodeDecodeError on a unicode reviewer message (gemini PR review class).
        message = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    if message:
        capture(a.root, a.slug, a.agent, message)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
