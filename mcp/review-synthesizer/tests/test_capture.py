"""Reviewer-verdict capture behaviour (capture.py) — Item 6, COREDEV-2325.

Stdlib unittest only (the repo is pytest-free). Exercises fence extraction, shape
validation, the schema-first + PII-redaction sanitizer, the traversal guard, round
selection, dedup, end-to-end consumability by synthesize.py, and the three PII paths
codex flagged (branch-derived, enum/sourceAgent poisoning, absolute/user paths)."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capture as C  # noqa: E402
import synthesize as S  # noqa: E402


def raw(**over):
    d = dict(severity="blocker", confidence="high", sourceAgent="security-reviewer",
             category="keychain", file="Unleashed Mail/Sources/Auth/TokenManager.swift",
             line=40, lineEnd=52, finding="f", evidence="e", fix="x")
    d.update(over)
    return d


def fenced(findings):
    return "prose before\n\n```json\n" + json.dumps(findings) + "\n```\n"


class TestFenceExtraction(unittest.TestCase):
    def test_last_block_wins(self):
        text = "```json\n[1]\n```\nmiddle\n```json\n[2,3]\n```\n"
        self.assertEqual(json.loads(C.extract_last_json_block(text)), [2, 3])

    def test_no_fence_returns_none(self):
        self.assertIsNone(C.extract_last_json_block("no fence here"))
        self.assertIsNone(C.extract_last_json_block(None))

    def test_jsonc_suffix_does_not_hijack(self):
        # a trailing ```jsonc / ```json5 example must NOT win over the real ```json findings.
        text = "```json\n[{\"real\":1}]\n```\nexample:\n```jsonc\n{\"note\":2}\n```\n"
        self.assertEqual(json.loads(C.extract_last_json_block(text)), [{"real": 1}])
        text5 = "```json\n[1]\n```\n```json5\n{x:2}\n```\n"
        self.assertEqual(json.loads(C.extract_last_json_block(text5)), [1])


class TestValidateFindings(unittest.TestCase):
    def test_bare_list(self):
        self.assertEqual(C.validate_findings("[{\"a\":1}]"), [{"a": 1}])

    def test_findings_object(self):
        self.assertEqual(C.validate_findings('{"findings":[{"a":1}]}'), [{"a": 1}])

    def test_wrong_shape_raises(self):
        with self.assertRaises(ValueError):
            C.validate_findings('{"notFindings":1}')
        with self.assertRaises(ValueError):
            C.validate_findings('"a string"')


class TestRedaction(unittest.TestCase):
    def test_email(self):
        self.assertNotIn("john.doe@corp.com", C.redact_pii("mail john.doe@corp.com x"))

    def test_user_paths(self):
        out = C.redact_pii("see /Users/john.doe/secret and /home/jane/x and ~jane/y")
        self.assertNotIn("john.doe", out)
        self.assertNotIn("/home/jane", out)
        self.assertNotIn("~jane", out)

    def test_jwt_full_token(self):
        tok = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payloadSEGMENThere.signatureSEGMENThere"
        out = C.redact_pii(tok)
        self.assertNotIn("payloadSEGMENThere", out)
        self.assertNotIn("signatureSEGMENThere", out)

    def test_bearer_case_insensitive(self):
        for kw in ("Bearer", "bearer", "BEARER", "BeArEr"):
            self.assertNotIn("opaqueTOKEN", C.redact_pii(kw + " opaqueTOKEN1234567890abcdef"), kw)

    def test_newlines_folded(self):
        self.assertNotIn("\n", C.redact_pii("a\nb\tc"))

    def test_api_key_spellings(self):
        for s in ("API key: ABCDEFGHIJKLMNOP", "api_key=ABCDEFGHIJKLMNOP",
                  "api-key : ABCDEFGHIJKLMNOP", "apikey=ABCDEFGHIJKLMNOP"):
            self.assertNotIn("ABCDEFGHIJKLMNOP", C.redact_pii(s), s)


class TestSanitizeFinding(unittest.TestCase):
    def test_valid_passes_and_normalizes_sourceagent(self):
        out = C.sanitize_finding(raw(sourceAgent="SPOOFED"), "security-reviewer")
        self.assertIsNotNone(out)
        self.assertEqual(out["sourceAgent"], "security-reviewer")  # normalized, not spoofed

    def test_enum_poisoning_dropped(self):
        # severity is a transcript-controlled enum; a poisoned value must NOT be persisted.
        self.assertIsNone(C.sanitize_finding(raw(severity="/Users/x/leak"), "security-reviewer"))
        self.assertIsNone(C.sanitize_finding(raw(category="totally-bogus"), "security-reviewer"))

    def test_missing_required_field_dropped(self):
        d = raw()
        del d["fix"]
        self.assertIsNone(C.sanitize_finding(d, "security-reviewer"))

    def test_absolute_file_collapsed(self):
        out = C.sanitize_finding(raw(file="/Users/john.doe/App/Secret.swift"), "security-reviewer")
        self.assertNotIn("john.doe", out["file"])
        self.assertTrue(out["file"].startswith("[abs]/"))
        self.assertEqual(os.path.basename(out["file"]), "Secret.swift")

    def test_free_text_fields_redacted(self):
        out = C.sanitize_finding(
            raw(evidence="leak /Users/john.doe/.ssh/id_rsa",
                fix="email john.doe@corp.com and Bearer eyJabcdefghij.klmnopqrst.uvwxyz012345"),
            "security-reviewer")
        self.assertNotIn("john.doe", out["evidence"])
        self.assertNotIn("john.doe@corp.com", out["fix"])
        self.assertNotIn("klmnopqrst", out["fix"])

    def test_evidence_capped(self):
        out = C.sanitize_finding(raw(evidence="A" * 5000), "security-reviewer")
        self.assertLessEqual(len(out["evidence"]), C.EVIDENCE_CAP)


class TestSafeJoin(unittest.TestCase):
    def test_normal_within_root(self):
        with tempfile.TemporaryDirectory() as d:
            dest = C.safe_join(d, "COREDEV-2325", 1, "security-reviewer")
            self.assertTrue(os.path.realpath(dest).startswith(os.path.realpath(d) + os.sep))

    def test_traversal_slug_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                C.safe_join(d, "../../etc", 1, "security-reviewer")

    def test_traversal_round_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                C.safe_join(d, "slug", "../../../etc", "x")


class TestSelectRound(unittest.TestCase):
    def test_default_one(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(C.select_round(d, "slug"), 1)

    def test_highest_existing(self):
        with tempfile.TemporaryDirectory() as d:
            for r in ("round-1", "round-3", "round-2", "not-a-round"):
                os.makedirs(os.path.join(d, "slug", r))
            self.assertEqual(C.select_round(d, "slug"), 3)

    def test_env_override(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["UNLEASHED_REVIEW_ROUND"] = "7"
            try:
                self.assertEqual(C.select_round(d, "slug"), 7)
            finally:
                del os.environ["UNLEASHED_REVIEW_ROUND"]


class TestRoundSelection(unittest.TestCase):
    def test_within_cycle_window_stays_same_round(self):
        # A cycle's four reviewers (and an immediate duplicate) land within the window -> same round.
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            for a in C.VALID_AGENTS:
                self.assertEqual(C.capture(root, slug, a, fenced([raw()])), "written")
            self.assertEqual(C.select_round(root, slug), 1)

    def test_duplicate_within_window_is_skipped_not_advanced(self):
        # A duplicate SubagentStop (arrives within seconds) must be dedup-skipped, NOT advanced into
        # a new round where it would pollute a real re-review (codex PR review).
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            for a in C.VALID_AGENTS:
                C.capture(root, slug, a, fenced([raw()]))
            self.assertEqual(C.capture(root, slug, "security-reviewer", fenced([raw()])), "skipped")
            self.assertFalse(os.path.isdir(os.path.join(root, slug, "round-2")))

    def test_capture_after_cycle_window_starts_new_round(self):
        # A re-review cycle arrives long after the prior round -> a fresh round (persisted mtime
        # signal), so its findings aren't dedup-skipped into the stale round (codex PR review).
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            for a in C.VALID_AGENTS:
                C.capture(root, slug, a, fenced([raw()]))
            rd = os.path.join(root, slug, "round-1")
            old = time.time() - (C.CYCLE_WINDOW_SEC + 60)
            for f in os.listdir(rd):
                os.utime(os.path.join(rd, f), (old, old))
            self.assertEqual(C.select_round(root, slug), 2)
            self.assertEqual(C.capture(root, slug, "security-reviewer", fenced([raw()])), "written")
            self.assertTrue(os.path.isfile(os.path.join(root, slug, "round-2", "security-reviewer.json")))

    def test_explicit_round_override_starts_fresh_round(self):
        # The orchestrator can still force a round deterministically via UNLEASHED_REVIEW_ROUND.
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            C.capture(root, slug, "security-reviewer", fenced([raw()]))
            os.environ["UNLEASHED_REVIEW_ROUND"] = "2"
            try:
                self.assertEqual(C.capture(root, slug, "security-reviewer", fenced([raw()])), "written")
            finally:
                del os.environ["UNLEASHED_REVIEW_ROUND"]
            self.assertTrue(os.path.isfile(os.path.join(root, slug, "round-2", "security-reviewer.json")))


class TestWriteFailureCleanup(unittest.TestCase):
    def test_tmp_cleaned_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            dest_dir = os.path.join(root, slug, "round-1")
            os.makedirs(dest_dir)
            # dest is a DIRECTORY -> os.replace(tmp, dest) raises -> tmp must be cleaned up.
            os.mkdir(os.path.join(dest_dir, "security-reviewer.json"))
            self.assertEqual(C.capture(root, slug, "security-reviewer", fenced([raw()])), "invalid")
            leftovers = [f for f in os.listdir(dest_dir) if ".tmp." in f]
            self.assertEqual(leftovers, [], "tmp file left on disk after write failure")


class TestLocaleRobustness(unittest.TestCase):
    def test_capture_handles_unicode_under_c_locale(self):
        # Under LANG=C + PYTHONUTF8=0 the old `sys.stdin.read()` would UnicodeDecodeError on a
        # unicode message; the bytes read (`sys.stdin.buffer`) is locale-independent (gemini PR).
        import subprocess
        with tempfile.TemporaryDirectory() as root:
            msg = fenced([raw(finding="café résumé keychain leak")])
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env = dict(os.environ, LC_ALL="C", LANG="C", PYTHONUTF8="0", PYTHONIOENCODING="")
            r = subprocess.run(
                [sys.executable, os.path.join(here, "capture.py"),
                 "--root", root, "--slug", "COREDEV-2325", "--agent", "security-reviewer"],
                input=msg.encode("utf-8"), env=env, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            dest = os.path.join(root, "COREDEV-2325", "round-1", "security-reviewer.json")
            self.assertTrue(os.path.isfile(dest), r.stderr.decode("utf-8", "replace"))
            with open(dest, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(len(data), 1)
            self.assertIn("café", data[0]["finding"])


class TestCaptureEndToEnd(unittest.TestCase):
    def test_writes_and_is_consumable_and_dedups(self):
        with tempfile.TemporaryDirectory() as root:
            msg = fenced([raw(), raw(category="webview", line=55, lineEnd=60)])
            self.assertEqual(C.capture(root, "COREDEV-2325", "security-reviewer", msg), "written")
            dest = os.path.join(root, "COREDEV-2325", "round-1", "security-reviewer.json")
            self.assertTrue(os.path.isfile(dest))
            with open(dest, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(len(data), 2)
            # directly consumable by the synthesizer's loader (no quarantine)
            findings, quarantined = S._load([dest])
            self.assertEqual((len(findings), len(quarantined)), (2, 0))
            # replay -> dedup, no second write (mtime unchanged)
            before = os.path.getmtime(dest)
            self.assertEqual(C.capture(root, "COREDEV-2325", "security-reviewer", msg), "skipped")
            self.assertEqual(os.path.getmtime(dest), before)

    def test_bad_file_is_overwritten(self):
        # corrupt JSON, AND a non-empty list of junk that does NOT parse as findings
        # (`[{}]` / `["x"]`) — both must be overwritable, not treated as a final capture.
        for bad in ("{ not valid json", "[{}]", '["junk", 1]'):
            with tempfile.TemporaryDirectory() as root:
                dest = os.path.join(root, "COREDEV-2325", "round-1", "security-reviewer.json")
                os.makedirs(os.path.dirname(dest))
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(bad)
                self.assertEqual(
                    C.capture(root, "COREDEV-2325", "security-reviewer", fenced([raw()])),
                    "written", "should overwrite bad file %r" % bad)
                with open(dest, encoding="utf-8") as fh:
                    data = json.load(fh)
                self.assertEqual(len(data), 1)

    def test_empty_capture_overwritten_by_real_findings(self):
        with tempfile.TemporaryDirectory() as root:
            # a clean review writes [] ...
            self.assertEqual(C.capture(root, "COREDEV-2325", "security-reviewer", fenced([])), "written")
            dest = os.path.join(root, "COREDEV-2325", "round-1", "security-reviewer.json")
            with open(dest, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), [])
            # ... a later same-round capture with real findings must REPLACE it, not skip.
            self.assertEqual(
                C.capture(root, "COREDEV-2325", "security-reviewer", fenced([raw()])), "written")
            with open(dest, encoding="utf-8") as fh:
                self.assertEqual(len(json.load(fh)), 1)

    def test_excluded_agent_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(
                C.capture(root, "slug", "swift-reviewer", fenced([raw()])), "rejected")

    def test_no_fence_not_written(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(C.capture(root, "slug", "security-reviewer", "no json here"), "no-fence")
            self.assertFalse(os.path.exists(os.path.join(root, "slug")))

    def test_persisted_file_has_no_pii(self):
        with tempfile.TemporaryDirectory() as root:
            msg = fenced([raw(
                file="/Users/john.doe/App/SimpleEmailWebView.swift",
                evidence="token Bearer eyJaaaaaaaaaa.bbbbbbbbbb.cccccccccc at /Users/john.doe/x",
                fix="contact john.doe@corp.com")])
            C.capture(root, "COREDEV-2325", "security-reviewer", msg)
            dest = os.path.join(root, "COREDEV-2325", "round-1", "security-reviewer.json")
            with open(dest, encoding="utf-8") as fh:
                blob = fh.read()
            for needle in ("john.doe", "corp.com", "bbbbbbbbbb", "cccccccccc"):
                self.assertNotIn(needle, blob)


class TestTranscriptFallback(unittest.TestCase):
    def test_reads_last_assistant_text(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.jsonl")
            lines = [
                {"type": "user", "message": {"role": "user", "content": "go"}},
                {"type": "assistant", "message": {"role": "assistant",
                 "content": [{"type": "text", "text": "first"}]}},
                {"type": "assistant", "message": {"role": "assistant",
                 "content": [{"type": "text", "text": "FINAL findings"}]}},
            ]
            with open(path, "w", encoding="utf-8") as fh:
                for ln in lines:
                    fh.write(json.dumps(ln) + "\n")
            self.assertEqual(C.read_last_assistant_from_transcript(path), "FINAL findings")

    def test_missing_file_empty(self):
        self.assertEqual(C.read_last_assistant_from_transcript("/no/such/transcript"), "")

    def _asst(self, text):
        return {"type": "assistant", "message": {"role": "assistant",
                "content": [{"type": "text", "text": text}]}}

    def test_invalid_utf8_does_not_raise(self):
        # A transcript with invalid UTF-8 bytes must not raise UnicodeDecodeError (gemini PR).
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.jsonl")
            with open(path, "wb") as fh:
                fh.write(b"\xff\xfe invalid bytes not json\n")                    # garbage first
                fh.write((json.dumps(self._asst("valid line")) + "\n").encode())  # good after
            self.assertEqual(C.read_last_assistant_from_transcript(path), "valid line")

    def test_corrupt_line_does_not_shadow_earlier_good(self):
        # A corrupt line AFTER a good one must be SKIPPED (not decoded to U+FFFD and kept as
        # `last`), so the earlier valid findings message still wins (codex PR review).
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.jsonl")
            with open(path, "wb") as fh:
                fh.write((json.dumps(self._asst("GOOD findings")) + "\n").encode())
                fh.write(b'{"type":"assistant","message":{"role":"assistant","content":'
                         b'[{"type":"text","text":"\xff\xfe corrupt"}]}}\n')
            self.assertEqual(C.read_last_assistant_from_transcript(path), "GOOD findings")


if __name__ == "__main__":
    unittest.main()
