"""MCP stdio JSON-RPC protocol behaviour — drives the server as a subprocess,
exactly as Claude Code does."""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(os.path.dirname(HERE), "mcp_server.py")


def rpc(messages, timeout=30):
    """Send newline-delimited JSON-RPC messages; return (parsed_replies, proc)."""
    stdin = "\n".join(m if isinstance(m, str) else json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run([sys.executable, SERVER], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", timeout=timeout)  # report has emoji
    replies = [json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip()]
    return replies, proc


def good(**over):
    d = dict(severity="blocker", confidence="high", sourceAgent="security-reviewer",
             category="html-sanitization", file="A.swift", line=10, lineEnd=10,
             finding="f", evidence="e", fix="x")
    d.update(over)
    return d


class TestProtocol(unittest.TestCase):
    def test_initialize(self):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}])
        result = out[0]["result"]
        self.assertEqual(result["serverInfo"]["name"], "review-synthesizer")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["protocolVersion"], "2025-06-18")  # echoes the client's (supported)

    def test_initialize_unsupported_version_falls_back(self):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2024-01-01", "capabilities": {}}}])
        # must NOT echo an unsupported version — reply with the one we actually speak
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")

    def test_tools_list(self):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        tools = out[0]["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["synthesize_review"])
        self.assertEqual(set(tools[0]["inputSchema"]["properties"]), {"findings", "changed_files"})
        # findings items must stay PERMISSIVE so malformed rows reach the server and
        # are quarantined — a strict item schema would let a client reject them first.
        self.assertEqual(tools[0]["inputSchema"]["properties"]["findings"]["items"], {"type": "object"})

    def test_ping(self):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        self.assertEqual(out[0]["result"], {})

    def test_notification_gets_no_reply(self):
        out, _ = rpc([{"jsonrpc": "2.0", "method": "notifications/initialized"},
                      {"jsonrpc": "2.0", "id": 9, "method": "ping"}])
        self.assertEqual([m.get("id") for m in out], [9])

    def test_unknown_method_error(self):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "frobnicate"}])
        self.assertEqual(out[0]["error"]["code"], -32601)

    def test_unknown_tool_error(self):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "nope", "arguments": {}}}])
        self.assertEqual(out[0]["error"]["code"], -32602)

    def test_array_params_rejected_as_invalid_params(self):
        # JSON-RPC allows array params; this by-name server must reject them with
        # -32602, not crash on params.get() into a -32603 internal error.
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": [1, 2, 3]}])
        self.assertEqual(out[0]["error"]["code"], -32602)

    def test_empty_array_params_rejected(self):
        # `[]` is falsy — must not be coerced to `{}` and silently accepted
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": []}])
        self.assertEqual(out[0]["error"]["code"], -32602)

    def test_non_object_message_does_not_crash(self):
        out, proc = rpc(["[]", {"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        self.assertEqual(out[0]["result"], {})            # server still alive after bare []
        self.assertIn("non-object", proc.stderr)

    def test_non_json_line_does_not_crash(self):
        out, _ = rpc(["this is not json", {"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        self.assertEqual(out[0]["result"], {})

    def test_explicit_null_id_is_a_request_and_gets_a_reply(self):
        # a notification has NO id member; `id: null` is still a request -> reply
        out, _ = rpc([{"jsonrpc": "2.0", "id": None, "method": "ping"}])
        self.assertEqual(len(out), 1)
        self.assertIn("id", out[0])
        self.assertIsNone(out[0]["id"])
        self.assertEqual(out[0]["result"], {})


class TestSynthesizeTool(unittest.TestCase):
    def _call(self, findings, changed):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "synthesize_review",
                                  "arguments": {"findings": findings, "changed_files": changed}}}])
        return out[0]["result"]

    def test_provisional_verdict_and_findings_only_text(self):
        res = self._call([good()], ["A.swift"])
        self.assertFalse(res["isError"])
        self.assertEqual(res["structuredContent"]["provisionalVerdict"], "REQUEST_CHANGES")
        text = res["content"][0]["text"]
        self.assertNotIn("## Verdict", text)              # agent owns the verdict
        self.assertNotIn("## Needs Confirmation", text)
        self.assertIn("### All Issues (Consolidated)", text)

    def test_verify_data_mirrored_into_text_content(self):
        # not every client reads structuredContent — content[1] carries the verify data
        res = self._call([good()], ["A.swift"])
        self.assertEqual(len(res["content"]), 2)
        self.assertIn("provisionalVerdict", res["content"][1]["text"])
        self.assertIn("blockersToVerify", res["content"][1]["text"])
        self.assertNotIn("## Verdict", res["content"][0]["text"])   # table block stays clean

    def test_blockers_to_verify_shape(self):
        res = self._call([good()], ["A.swift"])
        b = res["structuredContent"]["blockersToVerify"][0]
        for key in ("file", "line", "lineEnd", "category", "sourceAgent",
                    "confidence", "finding", "clusterSeverity", "clusterSize"):
            self.assertIn(key, b)
        self.assertEqual(b["clusterSeverity"], "blocker")

    def test_malformed_finding_quarantines_not_crashes(self):
        res = self._call([good(sourceAgent=123)], ["A.swift"])
        self.assertFalse(res["isError"])                  # NOT a -32603 protocol error
        self.assertEqual(res["structuredContent"]["quarantined"], 1)
        # fail closed: a quarantined row could hide a blocker -> never a clean APPROVE
        self.assertEqual(res["structuredContent"]["provisionalVerdict"], "NEEDS_DISCUSSION")

    def test_out_of_scope_finding_is_pre_existing(self):
        res = self._call([good(file="Z.swift")], ["A.swift"])
        sc = res["structuredContent"]
        self.assertEqual(sc["preExisting"], 1)
        self.assertEqual(sc["provisionalVerdict"], "APPROVE")  # nothing gating in scope

    def test_empty_findings_approve(self):
        res = self._call([], ["A.swift"])
        self.assertEqual(res["structuredContent"]["provisionalVerdict"], "APPROVE")

    def test_changed_files_as_string_is_rejected(self):
        # a newline-joined string would set()-coerce to characters -> every finding
        # mis-scoped to pre-existing -> a real blocker could get a provisional APPROVE
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "synthesize_review",
                                  "arguments": {"findings": [good()],
                                                "changed_files": "A.swift\nB.swift"}}}])
        self.assertEqual(out[0]["error"]["code"], -32602)   # fail CLOSED, not silent APPROVE

    def test_changed_files_with_non_string_element_is_rejected(self):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "synthesize_review",
                                  "arguments": {"findings": [good()],
                                                "changed_files": ["A.swift", 7]}}}])
        self.assertEqual(out[0]["error"]["code"], -32602)

    def test_findings_as_non_list_is_rejected(self):
        # a lone finding object would iterate as dict KEYS and quarantine silently
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "synthesize_review",
                                  "arguments": {"findings": good(),
                                                "changed_files": ["A.swift"]}}}])
        self.assertEqual(out[0]["error"]["code"], -32602)

    def test_missing_changed_files_is_rejected(self):
        # required by schema; defaulting to [] would mis-scope a real blocker to APPROVE
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "synthesize_review",
                                  "arguments": {"findings": [good()]}}}])
        self.assertEqual(out[0]["error"]["code"], -32602)

    def test_missing_findings_is_rejected(self):
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "synthesize_review",
                                  "arguments": {"changed_files": ["A.swift"]}}}])
        self.assertEqual(out[0]["error"]["code"], -32602)

    def test_non_object_arguments_rejected(self):
        # a non-dict arguments (e.g. a number) would TypeError -> -32603; reject -32602
        out, _ = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "synthesize_review", "arguments": 5}}])
        self.assertEqual(out[0]["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
