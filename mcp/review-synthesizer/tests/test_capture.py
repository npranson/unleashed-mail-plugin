"""Reviewer-verdict capture behaviour (capture.py) — Item 6, COREDEV-2325.

Stdlib unittest only (the repo is pytest-free). Exercises fence extraction, shape
validation, the schema-first + PII-redaction sanitizer, the traversal guard, round
selection, dedup, end-to-end consumability by synthesize.py, and the three PII paths
codex flagged (branch-derived, enum/sourceAgent poisoning, absolute/user paths)."""
import json
import os
import sys
import tempfile
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
    def test_cycle_reviewers_share_a_round(self):
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            for a in C.VALID_AGENTS:
                self.assertEqual(C.capture(root, slug, a, fenced([raw()]), "id-cycle1-%s" % a), "written")
            rd = os.path.join(root, slug, "round-1")
            for a in C.VALID_AGENTS:  # all four reviewers of the cycle landed in round-1
                self.assertTrue(os.path.isfile(os.path.join(rd, a + ".json")))
            self.assertFalse(os.path.isdir(os.path.join(root, slug, "round-2")))

    def test_duplicate_same_agent_id_is_skipped_not_advanced(self):
        # A true duplicate (SAME agent_id) is dedup-skipped, never advanced into a polluting new
        # round — regardless of timing (codex PR review).
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            for a in C.VALID_AGENTS:
                C.capture(root, slug, a, fenced([raw()]), "id1-%s" % a)
            self.assertEqual(
                C.capture(root, slug, "security-reviewer", fenced([raw()]), "id1-security-reviewer"),
                "skipped")
            self.assertFalse(os.path.isdir(os.path.join(root, slug, "round-2")))

    def test_re_review_new_agent_id_starts_new_round(self):
        # A re-review = a NEW subagent (distinct agent_id) for the same reviewer type -> fresh round,
        # deterministically and WITHOUT any timing dependence (the quick-re-review case codex flagged).
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            for a in C.VALID_AGENTS:
                C.capture(root, slug, a, fenced([raw()]), "id1-%s" % a)
            # immediately (no waiting) a re-run with a new id must land in round-2, not be skipped
            self.assertEqual(
                C.capture(root, slug, "security-reviewer", fenced([raw()]), "id2-security-reviewer"),
                "written")
            self.assertTrue(os.path.isfile(os.path.join(root, slug, "round-2", "security-reviewer.json")))

    def test_rerun_reuses_bad_slot_instead_of_advancing(self):
        # If the existing same-round slot is empty/invalid, a rerun (new id) OVERWRITES it in the
        # same round rather than splitting into a new round and leaving the bad slot (codex PR review).
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            self.assertEqual(C.capture(root, slug, "security-reviewer", fenced([]), "id1"), "written")
            dest = os.path.join(root, slug, "round-1", "security-reviewer.json")
            with open(dest, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), [])   # an empty (clean) capture occupies the slot
            self.assertEqual(C.capture(root, slug, "security-reviewer", fenced([raw()]), "id2"), "written")
            self.assertFalse(os.path.isdir(os.path.join(root, slug, "round-2")))  # reused, not advanced
            with open(dest, encoding="utf-8") as fh:
                self.assertEqual(len(json.load(fh)), 1)

    def test_reused_slot_preserves_original_id_for_dedup(self):
        # After a rerun reuses an empty slot, a delayed duplicate of the ORIGINAL subagent must still
        # be recognised (the .agentid sidecar accumulates ids, never forgets one) and skipped — not
        # advanced into round-2 with the stale empty capture (codex PR review).
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            C.capture(root, slug, "security-reviewer", fenced([]), "id1")       # empty slot
            C.capture(root, slug, "security-reviewer", fenced([raw()]), "id2")  # rerun reuses round-1
            self.assertEqual(
                C.capture(root, slug, "security-reviewer", fenced([]), "id1"), "skipped")
            self.assertFalse(os.path.isdir(os.path.join(root, slug, "round-2")))

    def test_delayed_duplicate_skipped_after_round_advanced(self):
        # A duplicate of cycle-1's reviewer arriving AFTER a re-review opened round-2 must still be
        # recognised (its id was seen in round-1) and skipped — not written into a new round-3 with
        # stale findings (codex PR review).
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            for a in C.VALID_AGENTS:
                C.capture(root, slug, a, fenced([raw()]), "id1-%s" % a)            # round-1
            C.capture(root, slug, "security-reviewer", fenced([raw()]), "id2-security-reviewer")  # -> round-2
            self.assertTrue(os.path.isdir(os.path.join(root, slug, "round-2")))
            self.assertEqual(  # delayed duplicate of cycle-1's security (id1) -> skipped
                C.capture(root, slug, "security-reviewer", fenced([raw()]), "id1-security-reviewer"),
                "skipped")
            self.assertFalse(os.path.isdir(os.path.join(root, slug, "round-3")))

    def test_explicit_round_override(self):
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2325"
            C.capture(root, slug, "security-reviewer", fenced([raw()]), "id1")
            os.environ["UNLEASHED_REVIEW_ROUND"] = "2"
            try:  # a re-review (new subagent id) with the orchestrator forcing round 2
                self.assertEqual(
                    C.capture(root, slug, "security-reviewer", fenced([raw()]), "id2"), "written")
            finally:
                del os.environ["UNLEASHED_REVIEW_ROUND"]
            self.assertTrue(os.path.isfile(os.path.join(root, slug, "round-2", "security-reviewer.json")))

    def test_override_with_duplicate_dedup(self):
        # COREDEV-2326 round-trip: the producer-side binding reaches capture.py only as the
        # `UNLEASHED_REVIEW_ROUND` override. This pins the override<->dedup interaction the consumer
        # relies on: a forced round routes a re-review's NEW agent_id into that round, while a TRUE
        # duplicate (same agent_id) is still skipped even with the override set — `_seen_agent_ids`
        # runs in capture() BEFORE select_round()'s override path writes anything.
        with tempfile.TemporaryDirectory() as root:
            slug = "COREDEV-2326"
            self.assertEqual(C.capture(root, slug, "security-reviewer", fenced([raw()]), "id1"), "written")
            os.environ["UNLEASHED_REVIEW_ROUND"] = "2"   # orchestrator pins round 2 for the re-review
            try:
                self.assertEqual(
                    C.capture(root, slug, "security-reviewer", fenced([raw()]), "id2"), "written")
                self.assertTrue(os.path.isfile(os.path.join(root, slug, "round-2", "security-reviewer.json")))
                # a genuine duplicate of the FIRST subagent is still deduped despite the override —
                # it is not re-written into round 2.
                self.assertEqual(
                    C.capture(root, slug, "security-reviewer", fenced([raw()]), "id1"), "skipped")
            finally:
                del os.environ["UNLEASHED_REVIEW_ROUND"]
            # round-1 keeps id1's original capture; round-2 holds only the re-review.
            self.assertTrue(os.path.isfile(os.path.join(root, slug, "round-1", "security-reviewer.json")))


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


# --- Output-Contract status sidecar (COREDEV-2328) ---------------------------------------
def jfence(findings=None):
    return "```json\n" + json.dumps(findings if findings is not None else []) + "\n```\n"


def status_msg(trailer, findings=None):
    """A report whose Output-Contract `trailer` (Status: + detail fields) sits IMMEDIATELY before
    the json findings fence (unlike `fenced`, which injects 'prose before')."""
    return "some findings prose here\n\n" + trailer.rstrip("\n") + "\n" + jfence(findings)


class TestExtractStatus(unittest.TestCase):
    def _s(self, text):
        r = C.extract_status(text)
        return r["status"] if r else None

    def test_complete_blocked_partial(self):
        self.assertEqual(self._s("Status: COMPLETE\n" + jfence()), "COMPLETE")
        self.assertEqual(self._s("Status: BLOCKED\n" + jfence()), "BLOCKED")
        self.assertEqual(self._s("Status: PARTIAL\n" + jfence()), "PARTIAL")

    def test_marker_variants_lowercase_dashes_trailing_period(self):
        for line in ("**Status:** COMPLETE", "**Status**: COMPLETE", "- Status: COMPLETE",
                     "> Status: COMPLETE", "Status: complete", "Status — COMPLETE", "Status: COMPLETE."):
            self.assertEqual(self._s(line + "\n" + jfence()), "COMPLETE", line)

    def test_rejects_concatenation_and_bare_space(self):
        for line in ("StatusCOMPLETE", "statusBlocked", "Status COMPLETE"):
            self.assertIsNone(self._s(line + "\n" + jfence()), line)

    def test_rejects_template_echo(self):
        self.assertIsNone(self._s("Status: COMPLETE | BLOCKED | PARTIAL\n" + jfence()))

    def test_rejects_inline_code_contract_examples(self):
        for line in ("`Status: BLOCKED`", "- `Status: COMPLETE`", "I emit `Status: BLOCKED` when blocked."):
            self.assertIsNone(self._s(line + "\n" + jfence()), line)

    def test_fence_aware_terminated_unterminated_mixed_marker(self):
        self.assertIsNone(self._s("```text\nStatus: BLOCKED\n" + jfence()))                  # unterminated
        self.assertIsNone(self._s("ex\n```text\nStatus: BLOCKED\n```\nprose\n" + jfence()))  # terminated
        self.assertIsNone(self._s("```text\n~~~\nStatus: BLOCKED\n" + jfence()))             # mixed marker
        self.assertIsNone(self._s("~~~text\nStatus: BLOCKED\n~~~\nprose\n" + jfence()))      # tilde fence

    def test_well_formed_code_fence_then_real_trailer(self):
        self.assertEqual(self._s("Bad:\n```swift\nlet x = 1\n```\nStatus: COMPLETE\n" + jfence("[]")), "COMPLETE")
        # a ~~~ inside a ``` block is content; a real top-level status after the close still wins
        self.assertEqual(self._s("```text\n~~~ not a close ~~~\ncode\n```\nStatus: COMPLETE\n" + jfence()), "COMPLETE")

    def test_status_less_and_prose_buried_example(self):
        self.assertIsNone(self._s("...findings...\nAll checks passed.\n" + jfence()))
        self.assertIsNone(self._s("...\n```swift\ncode\n```\n" + jfence()))      # ends in a code block
        self.assertEqual(  # an earlier prose example loses to the real trailer status
            self._s("I emit Status: COMPLETE normally.\n...\nStatus: BLOCKED\nBlocker Description: x\n" + jfence()),
            "BLOCKED")

    def test_no_fence_no_status_returns_none(self):
        self.assertIsNone(C.extract_status("no fence, no status here"))
        self.assertIsNone(C.extract_status(None))

    def test_detail_fields_captured(self):
        self.assertEqual(
            C.extract_status("Status: BLOCKED\nBlocker Description: could not read\nWhat Was Attempted: git diff\n" + jfence()),
            {"status": "BLOCKED", "blockerDescription": "could not read", "whatWasAttempted": "git diff"})
        self.assertEqual(
            C.extract_status("Status: PARTIAL\nCompleted: auth\nRemaining: sync\nConfidence: 70\n" + jfence()),
            {"status": "PARTIAL", "completed": "auth", "remaining": "sync", "confidence": "70"})

    def test_detail_fields_pii_redacted_and_capped(self):
        r = C.extract_status("Status: BLOCKED\nBlocker Description: mail john.doe@corp.com at /Users/john.doe/.ssh\n" + jfence())
        self.assertNotIn("john.doe", r["blockerDescription"])
        # PII in a malformed Confidence value is redacted too (codex r6)
        r2 = C.extract_status("Status: PARTIAL\nConfidence: 80 (contact john.doe@corp.com)\n" + jfence())
        self.assertNotIn("john.doe@corp.com", r2["confidence"])
        long = C.extract_status("Status: BLOCKED\nBlocker Description: " + "A" * 5000 + "\n" + jfence())
        self.assertLessEqual(len(long["blockerDescription"]), C.STATUS_FIELD_CAP)

    def test_redos_safe_linear(self):
        import time
        # ReDoS guard: the marker / separator / keyword classes are single quantifiers separated by a
        # REQUIRED literal, so pathological padding stays linear. (The `:` IS a real separator — these
        # inputs fail the match on a trailing non-keyword char, not on a missing separator.)
        for p in ("Status:" + " " * 70000 + "x",             # post-separator class
                  ">" * 70000 + "status: COMPLETE x",         # leading-marker class + trailing prose
                  "Status: " + "*" * 70000 + "COMPLETEx"):    # pre-keyword class
            t0 = time.time()
            self.assertIsNone(self._s(p), p[:18])
            self.assertLess(time.time() - t0, 0.1, p[:18])

    def test_duplicate_label_first_wins_and_blank_lines_tolerated(self):
        # first-match-per-label de-dup + blank lines interleaved between detail fields are tolerated.
        r = C.extract_status("Status: PARTIAL\nRemaining: first\n\nRemaining: second\nCompleted: done\n" + jfence())
        self.assertEqual(r, {"status": "PARTIAL", "remaining": "first", "completed": "done"})

    def test_multiline_field_wrap_aborts_trailer(self):
        # a label-less wrapped continuation line is "other content" -> trailer aborts -> face value.
        self.assertIsNone(self._s("Status: BLOCKED\nBlocker Description: line one\nline two wrap\n" + jfence()))


class TestStatusSidecar(unittest.TestCase):
    def _cap(self, root, msg, agent="security-reviewer", agent_id="id1"):
        return C.capture(root, "COREDEV-2328", agent, msg, agent_id)

    def _round1(self, root):
        return os.path.join(root, "COREDEV-2328", "round-1")

    def _json(self, path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_blocked_writes_findings_and_status_sidecar(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self._cap(root, status_msg("Status: BLOCKED\nBlocker Description: x", [])), "written")
            rd = self._round1(root)
            with open(os.path.join(rd, "security-reviewer.json")) as fh:
                self.assertEqual(json.load(fh), [])
            with open(os.path.join(rd, "security-reviewer.status")) as fh:
                blob = fh.read()
            self.assertTrue(blob.endswith("\n"))                 # trailing newline (gemini r3)
            self.assertEqual(json.loads(blob),
                             {"agent": "security-reviewer", "status": "BLOCKED", "blockerDescription": "x"})

    def test_complete_with_findings_writes_both(self):
        with tempfile.TemporaryDirectory() as root:
            self._cap(root, status_msg("Status: COMPLETE", [raw()]))
            rd = self._round1(root)
            self.assertEqual(len(self._json(os.path.join(rd, "security-reviewer.json"))), 1)
            self.assertEqual(self._json(os.path.join(rd, "security-reviewer.status"))["status"], "COMPLETE")

    def test_no_status_message_writes_no_sidecar(self):
        with tempfile.TemporaryDirectory() as root:
            self._cap(root, fenced([raw()]))   # no Status line ('prose before' before the fence)
            rd = self._round1(root)
            self.assertTrue(os.path.isfile(os.path.join(rd, "security-reviewer.json")))
            self.assertFalse(os.path.exists(os.path.join(rd, "security-reviewer.status")))

    def test_stale_status_cleared_on_statusless_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            self._cap(root, status_msg("Status: BLOCKED\nBlocker Description: x", []), agent_id="id1")
            st = os.path.join(self._round1(root), "security-reviewer.status")
            self.assertTrue(os.path.isfile(st))
            # a status-less rerun with REAL findings reuses the empty slot -> stale .status removed
            self.assertEqual(self._cap(root, fenced([raw()]), agent_id="id2"), "written")
            self.assertEqual(len(self._json(os.path.join(self._round1(root), "security-reviewer.json"))), 1)
            self.assertFalse(os.path.exists(st))

    def test_skipped_duplicate_preserves_existing_status_sidecar(self):
        # A true duplicate SubagentStop (same agent_id) returns "skipped" via capture()'s early
        # return BEFORE _clear_status/_write_status, so a previously-persisted BLOCKED/PARTIAL
        # sidecar MUST survive the replay untouched (NOT wiped, NOT downgraded). Without that
        # ordering a duplicate replay would silently clear a captured BLOCKED -> it could later
        # read as a clean [], defeating the whole point of COREDEV-2328. (PR #16 review.)
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(
                self._cap(root, status_msg("Status: BLOCKED\nBlocker Description: x", []), agent_id="id1"),
                "written")
            st = os.path.join(self._round1(root), "security-reviewer.status")
            self.assertEqual(self._json(st)["status"], "BLOCKED")
            # Replay the SAME agent_id with a would-be COMPLETE/clean message: it must be skipped,
            # and the existing BLOCKED sidecar must remain exactly as written.
            self.assertEqual(
                self._cap(root, status_msg("Status: COMPLETE", []), agent_id="id1"),
                "skipped")
            self.assertTrue(os.path.isfile(st))
            self.assertEqual(self._json(st)["status"], "BLOCKED")

    def test_sidecar_excluded_by_json_glob_and_quarantined_if_loaded(self):
        import glob
        with tempfile.TemporaryDirectory() as root:
            self._cap(root, status_msg("Status: BLOCKED\nBlocker Description: x", [raw()]))
            rd = self._round1(root)
            # the synthesizer discovers findings via a `*.json` glob (synthesize.py CLI) -> .status excluded
            jsons = sorted(glob.glob(os.path.join(rd, "*.json")))
            self.assertEqual([os.path.basename(p) for p in jsons], ["security-reviewer.json"])
            # even if a caller fed the .status in, it is QUARANTINED (not a finding, not a crash)
            findings, quarantined = S._load(jsons + [os.path.join(rd, "security-reviewer.status")])
            self.assertEqual(len(findings), 1)
            self.assertEqual(len(quarantined), 1)

    def test_sidecar_has_no_pii(self):
        with tempfile.TemporaryDirectory() as root:
            self._cap(root, status_msg(
                "Status: BLOCKED\nBlocker Description: leak /Users/john.doe/.ssh mail john.doe@corp.com", []))
            with open(os.path.join(self._round1(root), "security-reviewer.status")) as fh:
                blob = fh.read()
            for needle in ("john.doe", "corp.com"):
                self.assertNotIn(needle, blob)

    def test_write_status_survives_unencodable_detail_field(self):
        # A lone surrogate in a detail field makes json.dump->utf-8 raise UnicodeEncodeError (a
        # ValueError); _write_status must swallow it so capture() still returns "written", the findings
        # are persisted, the sidecar is simply absent (face value), and no tmp file leaks.
        with tempfile.TemporaryDirectory() as root:
            msg = status_msg("Status: BLOCKED\nBlocker Description: \ud800 lone surrogate", [raw()])
            self.assertEqual(self._cap(root, msg), "written")
            rd = self._round1(root)
            self.assertTrue(os.path.isfile(os.path.join(rd, "security-reviewer.json")))
            self.assertFalse(os.path.exists(os.path.join(rd, "security-reviewer.status")))
            self.assertEqual([f for f in os.listdir(rd) if ".tmp." in f], [])


class TestPromptReviewAgent(unittest.TestCase):
    def test_prompt_review_is_valid_agent(self):
        self.assertIn("prompt-review", C.VALID_AGENTS)  # COREDEV-2329

    def test_captures_ai_safety_finding(self):
        with tempfile.TemporaryDirectory() as root:
            msg = fenced([raw(sourceAgent="prompt-review", category="unsanitized-ingress")])
            self.assertEqual(
                C.capture(root, "COREDEV-2329", "prompt-review", msg, "id1"), "written")
            dest = os.path.join(root, "COREDEV-2329", "round-1", "prompt-review.json")
            self.assertTrue(os.path.isfile(dest))
            with open(dest, encoding="utf-8") as fh:
                rows = json.load(fh)
            self.assertEqual(rows[0]["category"], "unsanitized-ingress")
            self.assertEqual(rows[0]["sourceAgent"], "prompt-review")


if __name__ == "__main__":
    unittest.main()
