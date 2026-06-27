"""Deterministic synthesis: dedup, ownership routing, scope, verdict, render."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import synthesize as S  # noqa: E402
from schema import parse_finding  # noqa: E402


def f(**over):
    d = dict(severity="warning", confidence="high", sourceAgent="x", category="logic",
             file="A.swift", line=10, lineEnd=12, finding="f", evidence="e", fix="x")
    d.update(over)
    return parse_finding(d)


class TestDedup(unittest.TestCase):
    def test_same_family_overlap_clusters(self):
        cs = S.cluster_findings([f(category="logic", line=10, lineEnd=20),
                                 f(category="error-handling", line=15, lineEnd=18)])
        self.assertEqual(len(cs), 1)
        self.assertEqual(len(cs[0].findings), 2)

    def test_non_overlapping_lines_separate(self):
        cs = S.cluster_findings([f(line=10, lineEnd=12), f(line=30, lineEnd=32)])
        self.assertEqual(len(cs), 2)

    def test_different_family_separate(self):
        cs = S.cluster_findings([f(category="logic"),
                                 f(category="rendering", sourceAgent="ux-perf-reviewer")])
        self.assertEqual(len(cs), 2)

    def test_line0_only_clusters_with_line0(self):
        cs = S.cluster_findings([f(category="logic", line=0, lineEnd=0),
                                 f(category="error-handling", line=5, lineEnd=6)])
        self.assertEqual(len(cs), 2)

    def test_cross_family_ownership_pair_clusters(self):
        cs = S.cluster_findings([
            f(category="keychain", sourceAgent="security-reviewer", line=40, lineEnd=52),
            f(category="token-race", sourceAgent="concurrency-reviewer", line=44, lineEnd=48)])
        self.assertEqual(len(cs), 1)

    def test_cluster_keeps_all_fixes_cross_linked(self):
        cs = S.cluster_findings([f(category="logic", fix="FIX_A"),
                                 f(category="error-handling", fix="FIX_B")])
        review = S.Review(cs, S.decide_verdict(cs, lambda x: True), [], [])
        report = S.render_report(review)
        self.assertIn("FIX_A", report)
        self.assertIn("FIX_B", report)   # second fix is never silently dropped

    def test_related_categories_are_deduped(self):
        cs = S.cluster_findings([f(category="logic", line=10, lineEnd=20, fix="A"),
                                 f(category="error-handling", line=11, lineEnd=19, fix="B"),
                                 f(category="error-handling", line=12, lineEnd=18, fix="C")])
        self.assertEqual(len(cs), 1)
        finding, _ = S._issue_and_fix(cs[0])
        self.assertIn("related:", finding)
        self.assertEqual(finding.count("error-handling"), 1)   # not "error-handling, error-handling"

    def test_extra_fix_identical_to_primary_is_not_repeated(self):
        cs = S.cluster_findings([f(category="logic", line=10, lineEnd=20, fix="SAME"),
                                 f(category="error-handling", line=11, lineEnd=19, fix="SAME")])
        self.assertEqual(len(cs), 1)
        _, fix = S._issue_and_fix(cs[0])
        self.assertEqual(fix.count("SAME"), 1)        # primary's fix once; identical extra skipped
        self.assertNotIn("·also· SAME", fix)


class TestOwnershipRouting(unittest.TestCase):
    def test_a11y_authoritative(self):
        fs = [f(category="curator-tokens", sourceAgent="accessibility-auditor", severity="warning"),
              f(category="curator-tokens", sourceAgent="accessibility-auditor", severity="blocker")]
        self.assertEqual(S.route_owner(fs).severity, "blocker")

    def test_security_owns_credential_race(self):
        fs = [f(category="keychain", sourceAgent="security-reviewer", line=40, lineEnd=52),
              f(category="token-race", sourceAgent="concurrency-reviewer", line=44, lineEnd=48)]
        self.assertEqual(S.route_owner(fs).family, "security")

    def test_a11y_tie_prefers_accessibility_auditor_over_input_order(self):
        # ux-perf row tagged a11y listed BEFORE the auditor row, same severity:
        # the auditor must still own it (documented authority), not input order.
        fs = [f(category="color-contrast", sourceAgent="ux-perf-reviewer", severity="warning", finding="ux"),
              f(category="color-contrast", sourceAgent="accessibility-auditor", severity="warning", finding="audit")]
        self.assertEqual(S.route_owner(fs).sourceAgent, "accessibility-auditor")

    def test_ai_safety_owned_by_prompt_review(self):
        # an ai-safety row clustered with a security row -> prompt-review owns (COREDEV-2329).
        fs = [f(category="privacy", sourceAgent="security-reviewer", severity="warning", finding="sec"),
              f(category="pii-log-leak", sourceAgent="prompt-review", severity="warning", finding="ai")]
        self.assertEqual(S.route_owner(fs).sourceAgent, "prompt-review")

    def test_ai_safety_tie_prefers_prompt_review_over_input_order(self):
        fs = [f(category="unsanitized-ingress", sourceAgent="security-reviewer", severity="blocker", finding="sec"),
              f(category="unsanitized-ingress", sourceAgent="prompt-review", severity="blocker", finding="ai")]
        self.assertEqual(S.route_owner(fs).sourceAgent, "prompt-review")


class TestAISafetyFamily(unittest.TestCase):
    # The 10 prompt-review taxonomy kinds, canonical. The agent emits these verbatim as `category`.
    EXPECTED = {
        "jailbreak-surface", "missing-refusal-path", "format-leak", "context-overflow-risk",
        "ambiguous-instruction", "evaluation-gap", "unsanitized-ingress", "inline-prompt-leak",
        "unscoped-tool", "pii-log-leak",
    }

    def test_category_set_equality_invariant(self):
        # The silent-drop trap (COREDEV-2329): the agent-emitted set MUST equal the schema family
        # set MUST equal synthesize's ownership set — exact, all kebab-case. Any drift quarantines.
        import schema
        schema_set = {c for c, fam in schema.CATEGORY_FAMILY.items() if fam == "ai-safety"}
        self.assertEqual(schema_set, self.EXPECTED)
        self.assertEqual(S._AI_SAFETY_CATEGORIES, self.EXPECTED)
        for c in self.EXPECTED:
            self.assertRegex(c, r"^[a-z]+(?:-[a-z]+)*$")

    def test_agent_md_documents_every_category(self):
        # the shipped agents/prompt-review.md must name each category (so its output can't drift
        # from the schema undetected).
        here = os.path.dirname(os.path.abspath(__file__))
        agent_md = os.path.join(here, "..", "..", "..", "agents", "prompt-review.md")
        with open(agent_md, encoding="utf-8") as fh:
            text = fh.read()
        for c in self.EXPECTED:
            self.assertIn(c, text, f"prompt-review.md does not document category {c!r}")

    def test_ai_safety_finding_validates_and_buckets(self):
        fnd = f(category="jailbreak-surface", sourceAgent="prompt-review")
        self.assertEqual(fnd.family, "ai-safety")
        self.assertEqual(fnd.bucket, "AI Prompt Safety")


class TestScope(unittest.TestCase):
    CHANGED = {"A.swift"}

    def test_changeset_finding_gates(self):
        r = S.synthesize([f(file="A.swift")], self.CHANGED)
        self.assertEqual((len(r.clusters), len(r.pre_existing)), (1, 0))

    def test_structural_pipeline_gates_outside_diff(self):
        r = S.synthesize([f(file="Z.swift", scope="structural-pipeline")], self.CHANGED)
        self.assertEqual(len(r.clusters), 1)

    def test_out_of_scope_is_pre_existing(self):
        r = S.synthesize([f(file="Z.swift")], self.CHANGED)
        self.assertEqual((len(r.clusters), len(r.pre_existing)), (0, 1))

    def test_path_normalization_matches_scope_on_both_sides(self):
        # finding uses a ./ prefix, $CHANGED is clean -> still gates
        r = S.synthesize([f(category="logic", severity="blocker", file="./A.swift")],
                         self.CHANGED, verify=lambda x: True)
        self.assertEqual((len(r.clusters), len(r.pre_existing)), (1, 0))
        # clean finding, $CHANGED carries the ./ -> still gates
        r2 = S.synthesize([f(category="logic", severity="blocker", file="A.swift")],
                          {"./A.swift"}, verify=lambda x: True)
        self.assertEqual((len(r2.clusters), len(r2.pre_existing)), (1, 0))

    def test_verification_blocker_gates_even_outside_diff(self):
        # a red build is emitted with file = scheme/target, not a changed path —
        # it must gate, not be scoped out to pre-existing.
        r = S.synthesize([f(category="verification", sourceAgent="swift-reviewer",
                            severity="blocker", file="Unleashed Mail (scheme)",
                            finding="xcodebuild build FAILED")],
                         self.CHANGED, verify=lambda x: True)
        self.assertEqual((len(r.clusters), len(r.pre_existing)), (1, 0))
        self.assertEqual(r.verdict.decision, "REQUEST_CHANGES")

    def test_parity_and_coverage_gate_outside_diff(self):
        for cat in ("parity", "test-coverage"):
            r = S.synthesize([f(category=cat, severity="blocker", file="(global)",
                               finding="gate")], self.CHANGED, verify=lambda x: True)
            self.assertEqual(len(r.pre_existing), 0, cat)
            self.assertEqual(r.verdict.decision, "REQUEST_CHANGES", cat)


class TestVerdict(unittest.TestCase):
    def _mixed(self):
        # keychain WARNING (routes as display primary) + token-race BLOCKER
        return S.cluster_findings([
            f(category="keychain", sourceAgent="security-reviewer", severity="warning",
              line=40, lineEnd=52, finding="kc"),
            f(category="token-race", sourceAgent="concurrency-reviewer", severity="blocker",
              line=44, lineEnd=48, finding="tr")])

    def test_lead_blocker_is_the_blocker_not_the_routed_primary(self):
        c = self._mixed()[0]
        self.assertEqual(c.severity, "blocker")
        self.assertEqual(c.primary.finding, "kc")        # ownership-routed display owner (warning)
        self.assertEqual(c.lead_blocker.finding, "tr")    # actual blocker — what the verify gate uses

    def test_verify_gate_targets_the_blocker(self):
        seen = {}
        S.decide_verdict(self._mixed(), lambda x: seen.setdefault("v", x.finding) or True)
        self.assertEqual(seen["v"], "tr")

    def test_verify_all_true_gates(self):
        r = S.synthesize([f(severity="blocker", confidence="low")], {"A.swift"}, verify=lambda x: True)
        self.assertEqual(r.verdict.decision, "REQUEST_CHANGES")

    def test_unconfirmable_blocker_needs_discussion(self):
        r = S.synthesize([f(severity="blocker", confidence="low")], {"A.swift"}, verify=lambda x: False)
        self.assertEqual(r.verdict.decision, "NEEDS_DISCUSSION")

    def test_warnings_only_approve_with_suggestions(self):
        r = S.synthesize([f(severity="warning")], {"A.swift"})
        self.assertEqual(r.verdict.decision, "APPROVE_WITH_SUGGESTIONS")

    def test_clean_approve(self):
        self.assertEqual(S.synthesize([], set()).verdict.decision, "APPROVE")

    def test_quarantined_findings_force_needs_discussion(self):
        # a malformed row could have hidden a blocker -> never a clean APPROVE
        bad = [({"bad": 1}, "schema error")]
        self.assertEqual(S.synthesize([f(severity="warning")], {"A.swift"},
                                      quarantined=bad).verdict.decision, "NEEDS_DISCUSSION")
        self.assertEqual(S.synthesize([], {"A.swift"},
                                      quarantined=bad).verdict.decision, "NEEDS_DISCUSSION")

    def test_cluster_gates_if_any_blocker_verifies_not_just_lead(self):
        # two blockers cluster (same family, overlapping lines); the lead fails
        # verification but the other passes -> the cluster must still gate.
        cs = S.cluster_findings([
            f(category="data-race", sourceAgent="concurrency-reviewer", severity="blocker",
              line=10, lineEnd=20, finding="race A"),
            f(category="data-race", sourceAgent="concurrency-reviewer", severity="blocker",
              line=12, lineEnd=18, finding="race B")])
        self.assertEqual(len(cs), 1)
        self.assertEqual(sum(1 for x in cs[0].findings if x.severity == "blocker"), 2)
        v = S.decide_verdict(cs, lambda b: b.finding == "race B")  # only the non-lead one
        self.assertEqual(v.decision, "REQUEST_CHANGES")


class TestRender(unittest.TestCase):
    def test_render_report_omits_verdict_sections(self):
        r = S.synthesize([f(severity="blocker")], {"A.swift"}, verify=lambda x: True)
        report = S.render_report(r)
        self.assertTrue(report.lstrip().startswith("### All Issues (Consolidated)"))
        self.assertNotIn("## Verdict", report)
        self.assertNotIn("## Needs Confirmation", report)

    def test_render_report_pre_existing_and_quarantine(self):
        r = S.Review([], S.Verdict("APPROVE"), [f(file="Z.swift")], [({"x": 1}, "bad row")])
        report = S.render_report(r)
        self.assertIn("Pre-existing", report)
        self.assertIn("Quarantined", report)

    def test_blocker_text_surfaces_in_ownership_routed_row(self):
        # a security keychain WARNING owns a token-race BLOCKER (ownership pair) — the
        # 🔴 row must lead with the blocker's text, not the routed warning's.
        r = S.synthesize([
            f(category="keychain", sourceAgent="security-reviewer", severity="warning",
              line=40, lineEnd=52, finding="keychain warning here", fix="rotate"),
            f(category="token-race", sourceAgent="concurrency-reviewer", severity="blocker",
              line=44, lineEnd=48, finding="TOKEN RACE blocker here", fix="add actor")],
            {"A.swift"}, verify=lambda x: True)
        report = S.render_report(r)
        self.assertIn("TOKEN RACE blocker here", report)
        self.assertIn("keychain", report)   # the routed warning is still cross-linked

    def test_table_cells_escape_pipes_and_newlines(self):
        # a literal `|` would add a table column; a newline would add a row
        r = S.synthesize([f(severity="warning", finding="has | pipe", fix="line1\nline2")], {"A.swift"})
        report = S.render_report(r)
        self.assertIn("has \\| pipe", report)
        self.assertIn("line1<br>line2", report)
        self.assertNotIn("line1\nline2", report)   # raw newline must not survive into the row


_VALID_RAW = dict(severity="warning", confidence="high", sourceAgent="x", category="logic",
                  file="A.swift", line=10, lineEnd=12, finding="f", evidence="e", fix="x")


class TestCliLoad(unittest.TestCase):
    """`_load` (standalone CLI path) must quarantine bad files, never crash."""

    def _write(self, d, name, content):
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_malformed_json_file_is_quarantined_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            bad = self._write(d, "bad.json", "{ not valid json ")
            good = self._write(d, "good.json", json.dumps([_VALID_RAW]))
            findings, quarantined = S._load([bad, good])   # must not raise
            self.assertEqual(len(findings), 1)
            self.assertEqual(len(quarantined), 1)

    def test_wrong_top_level_shape_is_quarantined(self):
        with tempfile.TemporaryDirectory() as d:
            wrong = self._write(d, "w.json", json.dumps({"notFindings": 1}))
            findings, quarantined = S._load([wrong])
            self.assertEqual((len(findings), len(quarantined)), (0, 1))

    def test_object_with_findings_array_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            obj = self._write(d, "o.json", json.dumps({"findings": [_VALID_RAW]}))
            findings, quarantined = S._load([obj])
            self.assertEqual((len(findings), len(quarantined)), (1, 0))

    def test_help_flag_prints_usage_and_exits_zero(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = S.main(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("usage:", buf.getvalue())

    def test_explicit_missing_changed_file_fails_closed(self):
        # a typo'd --changed must NOT silently scope everything out and exit 0 APPROVE
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            rc = S.main(["--changed", "/no/such/changed_file_xyz.txt"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
