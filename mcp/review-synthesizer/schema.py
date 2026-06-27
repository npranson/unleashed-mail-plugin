"""Canonical finding schema for the hybrid review synthesizer.

Single source of truth shared by:
  - the strict ``report_finding`` tool  -> guarantees ``tool_use.input`` validates
    exactly on the Anthropic API (no beta header; ``strict: true``).
  - the structured-output format         -> ``output_config.format`` / messages.parse.
  - the deterministic synthesizer        -> validates findings on ingest from the
    markdown reviewers' JSON (the prompt-only path, whose JSON is *not* enforced).

Stdlib-only so the synthesizer core runs with zero pip installs. Mirrors the
schema the markdown reviewers already emit (see agents/*-reviewer.md Step 5).
"""
from __future__ import annotations

from dataclasses import dataclass

SEVERITIES = ("blocker", "warning", "suggestion")
CONFIDENCES = ("high", "medium", "low")
SCOPES = ("changeset", "structural-pipeline")

# category -> family. Families gate dedup: two findings can only be "the same
# defect" if they share a family (necessary, NOT sufficient — see synthesize.py).
CATEGORY_FAMILY = {
    # security
    "credential": "security", "keychain": "security", "oauth": "security",
    "webview": "security", "network": "security", "privacy": "security",
    "sqlcipher": "security", "html-sanitization": "security",
    "entitlements": "security", "ci": "security",
    # concurrency
    "actor-isolation": "concurrency", "data-race": "concurrency",
    "async-await": "concurrency", "grdb-threading": "concurrency",
    "webview-threading": "concurrency", "token-race": "concurrency",
    "combine-lifecycle": "concurrency", "sendable": "concurrency",
    # correctness (owned by concurrency-reviewer)
    "logic": "correctness", "error-handling": "correctness",
    # deprecation
    "deprecation": "deprecation", "dependency": "deprecation",
    # perf / ux
    "main-thread": "perf", "rendering": "perf", "db-query": "perf",
    "image-budget": "perf", "network-efficiency": "perf", "memory": "perf",
    "perceived-perf": "perf", "error-ux": "perf", "animation": "perf",
    # accessibility
    "voiceover": "a11y", "keyboard-nav": "a11y", "dynamic-type": "a11y",
    "curator-tokens": "a11y", "color-contrast": "a11y", "webview-a11y": "a11y",
    "dual-impl-parity": "a11y", "notifications": "a11y",
    "macos-specific": "a11y", "a11y": "a11y",
    # ai prompt safety (owned by prompt-review)
    "jailbreak-surface": "ai-safety", "missing-refusal-path": "ai-safety",
    "format-leak": "ai-safety", "context-overflow-risk": "ai-safety",
    "ambiguous-instruction": "ai-safety", "evaluation-gap": "ai-safety",
    "unsanitized-ingress": "ai-safety", "inline-prompt-leak": "ai-safety",
    "unscoped-tool": "ai-safety", "pii-log-leak": "ai-safety",
    # orchestrator-owned singletons
    "parity": "parity", "test-coverage": "test-coverage",
    "verification": "verification",
}

# family -> human display bucket in the consolidated report
DISPLAY_BUCKET = {
    "security": "Security",
    "concurrency": "Concurrency & Correctness",
    "correctness": "Concurrency & Correctness",
    "deprecation": "Concurrency & Correctness",
    "perf": "Performance & UX",
    "a11y": "Accessibility",
    "ai-safety": "AI Prompt Safety",
    "parity": "Provider Parity",
    "test-coverage": "Test Coverage",
    "verification": "Build / Lint / Tests",
}

SEVERITY_EMOJI = {"blocker": "🔴", "warning": "🟡", "suggestion": "🔵"}
SEVERITY_RANK = {"blocker": 3, "warning": 2, "suggestion": 1}

# --- API-layer schema --------------------------------------------------------
# `additionalProperties: false` + `required` + `strict: true` on the tool make the
# API GUARANTEE that tool_use.input validates exactly. This is the determinism
# Gemini wanted — produced at the model boundary, not parsed out of a table.
FINDING_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
        "sourceAgent": {"type": "string"},
        "category": {"type": "string", "enum": sorted(CATEGORY_FAMILY)},
        "file": {"type": "string"},
        "line": {"type": "integer", "minimum": 0},
        "lineEnd": {"type": "integer", "minimum": 0},
        "scope": {"type": "string", "enum": list(SCOPES)},
        "finding": {"type": "string"},
        "evidence": {"type": "string"},
        "fix": {"type": "string"},
    },
    "required": [
        "severity", "confidence", "sourceAgent", "category",
        "file", "line", "lineEnd", "finding", "evidence", "fix",
    ],
}

# A reviewer returns an array of findings (structured-output form).
REPORT_FINDINGS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"findings": {"type": "array", "items": FINDING_JSON_SCHEMA}},
    "required": ["findings"],
}

# Strict-tool form: the model calls report_finding once per finding. Either this
# OR the structured-output form makes the API enforce the schema.
REPORT_FINDING_TOOL = {
    "name": "report_finding",
    "description": "Report exactly one code-review finding. Call once per finding.",
    "strict": True,
    "input_schema": FINDING_JSON_SCHEMA,
}


@dataclass
class Finding:
    severity: str
    confidence: str
    sourceAgent: str
    category: str
    file: str
    line: int
    lineEnd: int
    finding: str
    evidence: str
    fix: str
    scope: str = "changeset"

    @property
    def family(self) -> str:
        return CATEGORY_FAMILY[self.category]

    @property
    def bucket(self) -> str:
        return DISPLAY_BUCKET[self.family]

    @property
    def loc(self) -> str:
        if self.line == 0:
            return f"{self.file} (file-level)"
        if self.lineEnd > self.line:
            return f"{self.file}:{self.line}-{self.lineEnd}"
        return f"{self.file}:{self.line}"


class SchemaError(ValueError):
    """Raised when an ingested finding does not satisfy the schema."""


def canonical_path(p: str) -> str:
    """Canonicalise a repo-relative path so a reviewer's value matches `git diff
    --name-only` output: trim whitespace and strip leading `./` (reviewers copying
    from `find .` / `grep … .` produce `./Unleashed Mail/…`). Used on BOTH the
    finding's `file` and the `changed_files` set, so the scope compare can't miss."""
    p = p.strip().replace("\\", "/")  # normalize Windows separators to forward slashes
    while p.startswith("./"):
        p = p[2:]
    return p


def parse_finding(d: dict) -> Finding:
    """Validate a raw dict (e.g. from a markdown reviewer's JSON) into a Finding.

    On the API path the model output is already schema-valid; this is the
    ingest-side guard for the prompt-only reviewers whose JSON is not enforced.
    Anything that fails here is quarantined, never silently dropped.
    """
    if not isinstance(d, dict):
        raise SchemaError("finding must be a JSON object")
    missing = [k for k in FINDING_JSON_SCHEMA["required"] if k not in d]
    if missing:
        raise SchemaError(f"missing required fields: {missing}")
    for k in ("severity", "confidence", "sourceAgent", "category",
              "file", "finding", "evidence", "fix"):
        if not isinstance(d[k], str):  # else downstream rendering crashes (e.g. .replace on an int)
            raise SchemaError(f"{k} must be a string, got {type(d[k]).__name__}")
    if d["severity"] not in SEVERITIES:
        raise SchemaError(f"bad severity: {d['severity']!r}")
    if d["confidence"] not in CONFIDENCES:
        raise SchemaError(f"bad confidence: {d['confidence']!r}")
    if d["category"] not in CATEGORY_FAMILY:
        raise SchemaError(f"unknown category: {d['category']!r}")
    file = canonical_path(d["file"])  # trim ws + leading ./ so it matches $CHANGED
    if not file:
        raise SchemaError("file must be non-empty")
    scope = d.get("scope", "changeset")
    if not isinstance(scope, str) or scope not in SCOPES:
        raise SchemaError(f"bad scope: {scope!r}")
    def _as_line(v: object) -> int:
        # accept a real int, or an all-digit string ("42"); reject bool (an int
        # subclass), float (1.9 would silently truncate to the wrong line), and
        # any non-digit string — those quarantine rather than mis-locate.
        if isinstance(v, bool):
            raise SchemaError("line/lineEnd must be integers (got bool)")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().isdecimal():
            return int(v.strip())   # isdecimal (0-9 only) — isdigit accepts '²' which int() rejects
        raise SchemaError(f"line/lineEnd must be integers (got {type(v).__name__})")
    line, line_end = _as_line(d["line"]), _as_line(d["lineEnd"])
    if line < 0 or line_end < 0:
        raise SchemaError("line/lineEnd must be >= 0")
    if line_end < line:
        raise SchemaError(f"lineEnd ({line_end}) must be >= line ({line})")
    return Finding(
        severity=d["severity"], confidence=d["confidence"],
        sourceAgent=d["sourceAgent"], category=d["category"],
        file=file, line=line, lineEnd=line_end,
        finding=d["finding"], evidence=d["evidence"], fix=d["fix"], scope=scope,
    )
