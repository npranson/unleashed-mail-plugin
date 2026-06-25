"""Deterministic review synthesizer — the coded half of the hybrid.

Input:  validated Finding objects (from the markdown reviewers' JSON, or from
        API tool calls — see reviewers.py).
Output: a consolidated review (clustered, ownership-routed) and a verdict —
        computed in plain Python, not by an LLM parsing a markdown table.

Why "cluster", not "collapse": code CANNOT decide on its own whether two findings
are the *same defect*. Family + line-overlap is necessary but not sufficient
(Gemini's blocker: two `data-race`s on different fields share a family but not a
defect). So this synthesizer NEVER silently drops a fix — it groups merge-
candidates into a cluster and keeps every fix, cross-linked. An optional
`same_defect` adjudicator (an LLM call, or a human) may collapse a cluster
further; the default keeps both. Ownership rules only RE-ROUTE (owner + display
bucket); they never discard.

Run it:  python3 synthesize.py            # uses ./samples/*.json + ./samples/changed_files.txt
         python3 synthesize.py a.json b.json --changed changed_files.txt
"""
from __future__ import annotations

import glob
import itertools
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

from schema import Finding, SEVERITY_EMOJI, SEVERITY_RANK, parse_finding

# --------------------------------------------------------------------------- #
# scope filter
# --------------------------------------------------------------------------- #

def in_gating_scope(f: Finding, changed_files: set[str]) -> bool:
    # structural-pipeline findings gate even outside the diff (the reviewer traced
    # them); everything else must be in the changeset.
    return f.scope == "structural-pipeline" or f.file in changed_files


# --------------------------------------------------------------------------- #
# merge-candidate detection
# --------------------------------------------------------------------------- #

def _overlap(a: Finding, b: Finding) -> bool:
    # file-level (line 0) findings overlap only with other file-level findings —
    # a file-level finding never silently absorbs a line-range one.
    if a.line == 0 or b.line == 0:
        return a.line == 0 and b.line == 0
    return a.line <= b.lineEnd and b.line <= a.lineEnd

# Deliberate CROSS-family merges (the Step-5 ownership rules). These are the only
# places a different-family pair is allowed to cluster.
_OWNERSHIP_MERGE_PAIRS = [
    ({"token-race"}, {"credential", "oauth", "keychain"}),          # security owns
    # a slow WebView render and an HTML-sanitization concern on the same method are
    # one defect (unsanitized/oversized content drives the render cost) — sec owns:
    ({"perceived-perf"}, {"html-sanitization", "webview"}),         # security owns
]

def _ownership_pair(a: Finding, b: Finding) -> bool:
    for left, right in _OWNERSHIP_MERGE_PAIRS:
        if (a.category in left and b.category in right) or \
           (b.category in left and a.category in right):
            return True
    return False

def _candidate(a: Finding, b: Finding) -> bool:
    if a.file != b.file or not _overlap(a, b):
        return False
    return a.family == b.family or _ownership_pair(a, b)


# --------------------------------------------------------------------------- #
# clustering (union-find over merge-candidates)
# --------------------------------------------------------------------------- #

_A11Y_CATEGORIES = {
    "a11y", "curator-tokens", "color-contrast", "dynamic-type", "voiceover",
    "keyboard-nav", "webview-a11y", "dual-impl-parity", "notifications",
    "macos-specific",
}

def _highest(fs: list[Finding]) -> Finding:
    return max(fs, key=lambda f: SEVERITY_RANK[f.severity])

def route_owner(findings: list[Finding]) -> Finding:
    """Pick the authoritative representative of a cluster (Step-5 ownership rules).
    Re-routing only changes which finding leads + its display bucket — no fix is
    discarded (all stay in the cluster)."""
    a11y = [f for f in findings
            if f.category in _A11Y_CATEGORIES or f.sourceAgent == "accessibility-auditor"]
    if a11y:                                   # accessibility-auditor is authoritative
        top = max(SEVERITY_RANK[f.severity] for f in a11y)
        tied = [f for f in a11y if SEVERITY_RANK[f.severity] == top]
        # on a severity tie the auditor wins, regardless of input order (e.g. a
        # ux-perf row with category:"a11y" must not outrank the auditor's row).
        return next((f for f in tied if f.sourceAgent == "accessibility-auditor"), tied[0])
    sec = [f for f in findings if f.family == "security"]
    if sec and (any(f.category == "token-race" for f in findings)
                or any(f.category in ("html-sanitization", "webview") for f in sec)):
        return _highest(sec)                   # security owns credential-race / sanitize-render
    return _highest(findings)


@dataclass
class Cluster:
    findings: list[Finding]

    @property
    def severity(self) -> str:
        return _highest(self.findings).severity

    @property
    def agents(self) -> list[str]:
        return sorted({f.sourceAgent for f in self.findings})

    @property
    def primary(self) -> Finding:
        return route_owner(self.findings)

    @property
    def lead_blocker(self) -> Finding:
        """The highest-severity finding — for a blocker cluster this is an actual
        blocker, unlike `primary` (the ownership-routed representative, which on a
        mixed-severity cluster can be a warning). Use this for the verify gate."""
        return _highest(self.findings)


def cluster_findings(
    findings: list[Finding],
    same_defect: Optional[Callable[[Finding, Finding], bool]] = None,
) -> list[Cluster]:
    """Group merge-candidates. `same_defect(a, b)` (optional) is the semantic
    adjudicator that confirms whether a candidate pair is truly one defect; the
    default treats every candidate as one cluster (conservative cross-link)."""
    decide = same_defect or (lambda a, b: True)
    parent = list(range(len(findings)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in itertools.combinations(range(len(findings)), 2):
        if _candidate(findings[i], findings[j]) and decide(findings[i], findings[j]):
            parent[find(i)] = find(j)

    groups: dict[int, list[Finding]] = {}
    for i, f in enumerate(findings):
        groups.setdefault(find(i), []).append(f)
    return [Cluster(g) for g in groups.values()]


# --------------------------------------------------------------------------- #
# verify gate (pluggable seam)
# --------------------------------------------------------------------------- #

def default_verify(f: Finding) -> bool:
    """Return True if a blocker is CONFIRMED. Default trusts high-confidence
    blockers and quarantines the rest, so the prototype runs with no API/grep.
    Swap in an LLM or `grep file:line` verifier for real use — same signature."""
    return f.confidence == "high"


# --------------------------------------------------------------------------- #
# verdict
# --------------------------------------------------------------------------- #

@dataclass
class Verdict:
    decision: str
    confirmed_blockers: list[Cluster] = field(default_factory=list)
    needs_confirmation: list[Cluster] = field(default_factory=list)


def decide_verdict(clusters: list[Cluster], verify: Callable[[Finding], bool]) -> Verdict:
    confirmed, unconfirmed = [], []
    for c in clusters:
        if c.severity == "blocker":
            # A cluster can hold more than one blocker (cluster-not-collapse), so it
            # gates if ANY of its blockers verifies — not just the lead one. (The MCP
            # path passes verify=lambda f: True; this matters for real verifiers.)
            blockers = [f for f in c.findings if f.severity == "blocker"]
            (confirmed if any(verify(b) for b in blockers) else unconfirmed).append(c)
    if confirmed:
        return Verdict("REQUEST_CHANGES", confirmed, unconfirmed)
    if unconfirmed:
        return Verdict("NEEDS_DISCUSSION", confirmed, unconfirmed)
    if any(c.severity in ("warning", "suggestion") for c in clusters):
        return Verdict("APPROVE_WITH_SUGGESTIONS")
    return Verdict("APPROVE")


# --------------------------------------------------------------------------- #
# top-level synthesize
# --------------------------------------------------------------------------- #

@dataclass
class Review:
    clusters: list[Cluster]
    verdict: Verdict
    pre_existing: list[Finding]
    quarantined: list[tuple[dict, str]]


def synthesize(
    findings: list[Finding],
    changed_files: set[str],
    *,
    same_defect: Optional[Callable[[Finding, Finding], bool]] = None,
    verify: Callable[[Finding], bool] = default_verify,
    quarantined: Optional[list[tuple[dict, str]]] = None,
) -> Review:
    gating = [f for f in findings if in_gating_scope(f, changed_files)]
    pre = [f for f in findings if not in_gating_scope(f, changed_files)]
    clusters = cluster_findings(gating, same_defect=same_defect)
    verdict = decide_verdict(clusters, verify)
    return Review(clusters, verdict, pre, quarantined or [])


# --------------------------------------------------------------------------- #
# rendering (mirrors swift-reviewer.md ## Output Format)
# --------------------------------------------------------------------------- #

def _cell(s: str) -> str:
    """Keep free-text reviewer content from breaking the Markdown table: a literal
    `|` would add a column and a newline would add a row. Escape pipes, flatten
    newlines to `<br>`."""
    return (s.replace("|", "\\|")
            .replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>"))

def _issue_and_fix(c: Cluster) -> tuple[str, str]:
    p = c.primary
    finding, fix = p.finding, p.fix
    extra = [f for f in c.findings if f is not p]
    if extra:  # cross-link the other fixes in the cluster — nothing is dropped
        cats = ", ".join(dict.fromkeys(f.category for f in extra))  # de-dup, keep order
        finding += f"  _(+{len(extra)} related: {cats})_"
        fix += "".join(f"  ·also· {f.fix}" for f in extra)
    return finding, fix

def _consolidated_table(review: Review) -> list[str]:
    """The `### All Issues (Consolidated)` table in swift-reviewer's column format
    (emoji severity, display bucket as Category), one row per cluster."""
    out = ["### All Issues (Consolidated)", "",
           "| # | Severity | Category | File | Issue | Fix |",
           "|---|----------|----------|------|-------|-----|"]
    if not review.clusters:
        out.append("| — | | | | _no in-scope findings_ | |")
    else:
        ordered = sorted(review.clusters, key=lambda c: -SEVERITY_RANK[c.severity])
        for i, c in enumerate(ordered, 1):
            finding, fix = _issue_and_fix(c)
            out.append(f"| {i} | {SEVERITY_EMOJI[c.severity]} | {c.primary.bucket} | "
                       f"`{_cell(c.primary.loc)}` | {_cell(finding)} | {_cell(fix)} |")
    return out + [""]

def _aux_sections(review: Review) -> list[str]:
    out: list[str] = []
    if review.pre_existing:
        out += ["### Pre-existing (non-gating)",
                "_Outside `$CHANGED` and not `structural-pipeline` — surfaced for awareness, never gates._"]
        out += [f"- {SEVERITY_EMOJI[f.severity]} `{f.loc}` — {f.finding}" for f in review.pre_existing]
        out += [""]
    if review.quarantined:
        out += ["### Quarantined (schema-invalid)",
                "_Failed schema validation on ingest — fix the reviewer; never silently dropped._"]
        out += [f"- {err}  ·  `{json.dumps(raw)[:90]}...`" for raw, err in review.quarantined]
        out += [""]
    return out

def render_report(review: Review) -> str:
    """Server-facing report: the consolidated findings table + pre-existing +
    quarantined. **No verdict and no Needs-Confirmation section** — the orchestrator
    owns those (it runs the verify gate against the repo, which this server can't).
    No top-level `#` title, so it nests under the agent's `## Output Format`."""
    return "\n".join(_consolidated_table(review) + _aux_sections(review)).rstrip() + "\n"

def render_markdown(review: Review) -> str:
    """Standalone/CLI report: render_report + the provisional verdict. Not used by
    the MCP server (which omits the verdict)."""
    out = ["# Code Review — synthesized (standalone)", "", render_report(review).rstrip(), ""]
    if review.verdict.needs_confirmation:
        out += ["### Needs Confirmation (non-gating)"]
        out += [f"- 🔴 `{c.lead_blocker.loc}` — {c.lead_blocker.finding}  _(confidence: {c.lead_blocker.confidence})_"
                for c in review.verdict.needs_confirmation]
        out += [""]
    v = review.verdict
    out += ["---", f"## Verdict (provisional): **{v.decision}**"]
    if v.confirmed_blockers:
        out.append(f"- {len(v.confirmed_blockers)} blocker(s) gating")
    if v.needs_confirmation:
        out.append(f"- {len(v.needs_confirmation)} flagged for confirmation")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _load(paths: list[str]) -> tuple[list[Finding], list[tuple[dict, str]]]:
    findings, bad = [], []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:  # quarantine the file, don't crash
            bad.append(({"_file": path}, f"could not read/parse file: {exc}"))
            continue
        items = raw.get("findings") if isinstance(raw, dict) else raw
        if not isinstance(items, list):  # not a findings array nor {findings: [...]}
            bad.append(({"_file": path}, "expected a JSON array or an object with a 'findings' array"))
            continue
        for d in items:
            try:
                findings.append(parse_finding(d))
            except Exception as exc:  # noqa: BLE001 - quarantine, don't crash
                bad.append((d, str(exc)))
    return findings, bad


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    # Parse args without treating `--changed`'s VALUE as a findings file.
    changed_path = None
    paths: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--changed":
            changed_path = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
            continue
        if a.startswith("--"):
            i += 1
            continue
        paths.append(a)
        i += 1
    if changed_path is None:
        changed_path = os.path.join(here, "samples", "changed_files.txt")
    if not paths:  # default demo uses the bundled fixtures
        paths = sorted(glob.glob(os.path.join(here, "samples", "*.json")))

    changed: set[str] = set()
    if os.path.exists(changed_path):
        with open(changed_path, encoding="utf-8") as fh:
            changed = {ln.strip() for ln in fh if ln.strip()}
    findings, bad = _load(paths)
    review = synthesize(findings, changed, quarantined=bad)
    print(render_markdown(review))
    # exit non-zero on a gating verdict, so this can drop into CI
    return 0 if review.verdict.decision.startswith("APPROVE") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
