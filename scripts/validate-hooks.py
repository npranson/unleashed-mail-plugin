#!/usr/bin/env python3
"""validate-hooks.py — COREDEV-2338.

Static integrity check for `hooks/hooks.json`: every hook the plugin declares must
actually be able to FIRE. `validate-plugin-assembly.py` only JSON-loads the manifest, and
`scripts/test-hooks.sh` hardcodes the script paths it exercises — so neither catches a
renamed/missing hook script, an invalid event name (a hook that silently NEVER fires), or
a typo'd tool matcher (a PreToolUse/PostToolUse hook that matches nothing). This does.

Checks:
  * top-level `hooks` is an object;
  * every event key is a real, CC-supported event (KNOWN_EVENTS) — else it never fires;
  * every tool matcher (PreToolUse/PostToolUse/PostToolUseFailure) is a known tool name
    or a valid regex — catches `Bsh`, `Write|Edti`, etc.;
  * every hook entry is `type: command` with a non-empty command and (if present) a
    positive numeric timeout;
  * every command references an existing, non-empty `scripts/<file>`;
  * `bash -n` parses every referenced shell script (tied to the manifest, not the broad
    shellcheck glob).

stdlib ONLY (python3 is already a hard dep via the review-synthesizer MCP).

Usage:
  python3 scripts/validate-hooks.py [--root .] [--strict]
    default   warn  — print problems, exit 0  (pre-commit)
    --strict        — print problems, exit 1  (CI)
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Supported Claude Code hook events — the COMPLETE documented set (30). Source:
# https://code.claude.com/docs/en/hooks.md and https://code.claude.com/docs/en/plugins-reference.md
# § "Hooks" (re-verified against the docs 2026-06-27, Claude Code 2.1.x). An event NOT in this
# set will silently never fire. If CI fails here on an event you intend to use, confirm it
# against the docs above and add it in the SAME PR.
KNOWN_EVENTS = {
    "SessionStart", "SessionEnd", "Setup",
    "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "PostToolBatch",
    "PermissionRequest", "PermissionDenied",
    "Notification", "MessageDisplay",
    "SubagentStart", "SubagentStop",
    "TaskCreated", "TaskCompleted", "TeammateIdle",
    "Stop", "StopFailure",
    "InstructionsLoaded", "ConfigChange",
    "CwdChanged", "FileChanged",
    "WorktreeCreate", "WorktreeRemove",
    "PreCompact", "PostCompact",
    "Elicitation", "ElicitationResult",
}

# Events whose `matcher` selects a TOOL by name (per the hooks-reference matcher table) — a
# typo'd tool name = a dead hook. The permission events filter on tool name too.
TOOL_MATCHER_EVENTS = {
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied",
}

# Known Claude Code tool names, used to WARN (never hard-fail) on a likely-typo'd tool matcher.
# Claude Code does not publish a canonical/enumerable built-in tool list, and the set is
# environment- and plugin-dependent (MCP tools, OS-specific tools like PowerShell, plugin-
# contributed tools), so an unrecognized tool token is a non-blocking warning — a real typo and
# a valid-but-unlisted tool are indistinguishable here. The subagent dispatcher is `Agent`, not
# `Task` (AGENT_CONTRACTS.md §9). MCP tools (`mcp__server__tool`) are allowed through implicitly.
KNOWN_TOOLS = {
    "Agent", "AskUserQuestion", "Bash", "Glob", "Grep", "Read", "Edit", "MultiEdit", "Write",
    "NotebookEdit", "WebFetch", "WebSearch", "TodoWrite", "Skill", "Monitor",
    "EnterPlanMode", "ExitPlanMode", "CronCreate", "CronList", "CronDelete",
}

# Per the hooks reference "Matcher value" table: a matcher of ONLY [A-Za-z0-9_ ,|] is an exact
# string or a `|`/`,`-separated list of exact strings (optional surrounding whitespace); a value
# containing ANY other character is a JavaScript regex. This is where tool-name typos are caught.
EXACT_MATCHER = re.compile(r"^[A-Za-z0-9_ ,|]+$")
# Captures the scripts/<path> a hook command runs — allows subdirs (e.g. scripts/lib/x.sh).
SCRIPT_REF = re.compile(r"scripts/([A-Za-z0-9._/-]+)")


def _is_shell_script(path: Path) -> bool:
    """True if `path` is a shell script (by extension or shebang interpreter). `bash -n` runs
    only on real shell scripts so a `python3 scripts/x.py` hook command's target can't
    false-positive. The shebang is PARSED (not substring-scanned), so a path/arg merely
    CONTAINING 'sh'/'bash' (e.g. `#!/usr/bin/shared/python`, a comment mentioning bash) is
    correctly excluded."""
    if path.suffix in (".sh", ".bash"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            first = handle.readline(1024)  # bounded: a shebang lives in the first line
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    parts = first[2:].split()
    if not parts:
        return False
    # Resolve the interpreter: `#!/usr/bin/env [-S] <interp> …` -> <interp>;
    # `#!/bin/bash …` -> basename of the first token.
    if parts[0].rsplit("/", 1)[-1] == "env":
        parts = parts[1:]
        while parts and parts[0].startswith("-"):  # skip env opts like `-S`
            parts = parts[1:]
        interp = parts[0].rsplit("/", 1)[-1] if parts else ""  # basename even an absolute env arg
    else:
        interp = parts[0].rsplit("/", 1)[-1]
    interp = re.sub(r"[0-9.\-]+$", "", interp)  # strip version suffix: bash3.2 -> bash
    return interp in {"sh", "bash", "zsh", "dash", "ksh"}


def validate_matcher(event: str, matcher: str, where: str,
                     problems: list[str], warnings: list[str]) -> None:
    """Validate a hook matcher against the documented grammar (hooks reference "Matcher value"
    table): "" / "*" = match-all; a value of only [A-Za-z0-9_ ,|] is an exact string or a
    `|`/`,`-separated list of exact strings (optional surrounding whitespace); anything else is
    a JavaScript regex."""
    if matcher in ("", "*"):
        return
    if EXACT_MATCHER.match(matcher):
        # Exact string or exact-string list. Tool-name check, ONLY where matchers select a tool
        # (PreToolUse/PostToolUse/PostToolUseFailure/PermissionRequest/Denied). CC tool names
        # aren't canonically enumerable, so we can't simply reject every unknown token. Instead:
        # a token that is a NEAR-MATCH of a known tool is almost certainly a typo (`Bsh`→`Bash`)
        # → hard FAIL; a token FAR from every known tool is probably a valid/new/unlisted tool
        # (`PowerShell`, a plugin tool) → non-blocking WARNING. Split on `|`/`,` (optional
        # whitespace); MCP names (mcp__server__tool) pass implicitly.
        if event not in TOOL_MATCHER_EVENTS:
            return
        for raw in re.split(r"[|,]", matcher):
            token = raw.strip()
            if not token or token in KNOWN_TOOLS:
                continue
            if token.startswith("mcp__"):
                # A full exact MCP tool name is `mcp__server__tool`; a server-only `mcp__server`
                # is an exact string that matches NO tool — to match a whole server you need the
                # regex `mcp__server__.*` (regex-form, handled above), not a bare exact prefix.
                if not re.fullmatch(r"mcp__.+__.+", token):
                    problems.append(
                        f"{where}: matcher token {token!r} is a server-only MCP prefix and matches "
                        f"no tool — use an exact 'mcp__server__tool', or the regex 'mcp__server__.*' "
                        f"to match a whole server")
                continue
            near = difflib.get_close_matches(token, KNOWN_TOOLS, n=1, cutoff=0.7)
            if near:
                problems.append(
                    f"{where}: matcher token {token!r} is not a known tool (did you mean "
                    f"{near[0]!r}?) — it will match nothing; if {token!r} is a real new tool, "
                    f"add it to KNOWN_TOOLS")
            else:
                warnings.append(
                    f"{where}: matcher token {token!r} is not a recognized tool — if a typo the "
                    f"hook will match nothing; if a valid/new tool, add it to KNOWN_TOOLS")
        return
    # Otherwise it is a JavaScript regex (NOT Python `re`). Validate with node when available —
    # Python's engine would both reject valid JS (e.g. `(?<n>…)`) and accept Python-only syntax
    # (`(?P<n>…)`). The matcher is passed via env (no argv-index ambiguity; safe for a leading
    # `-`). Without node we cannot faithfully check a JS regex, so we accept it (documented).
    node = shutil.which("node")
    if not node:
        return
    try:
        res = subprocess.run(
            [node, "-e", "new RegExp(process.env.HOOK_MATCHER)"],
            capture_output=True, text=True, env={**os.environ, "HOOK_MATCHER": matcher},
        )
    except OSError:
        return
    if res.returncode != 0:
        problems.append(f"{where}: matcher {matcher!r} is not a valid JavaScript regex")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate hooks/hooks.json manifest integrity.")
    ap.add_argument("--root", default=None, help="plugin repo root (default: parent of scripts/)")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any problem (CI)")
    ap.add_argument("--require-manifest", action="store_true",
                    help="treat a missing hooks/hooks.json as a problem (CI for a plugin that ships hooks)")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    manifest = root / "hooks" / "hooks.json"
    problems: list[str] = []
    warnings: list[str] = []

    # A plugin need not ship hooks — absence is valid by default. Under --require-manifest
    # (CI for a plugin known to ship hooks) a missing manifest is a problem: deleting it
    # would silently disable every declared hook event while the path-hardcoded harness
    # could still pass.
    if not manifest.is_file():
        if args.require_manifest:
            print("hooks: 1 problem(s):")
            print("  ❌ hooks/hooks.json is MISSING — --require-manifest set; all declared hook "
                  "events would be disabled.")
            if args.strict:
                print("— failing (strict).")
                return 1
            print("— warn mode (not blocking; pass --strict to enforce).")
            return 0
        print("✅ OK — no hooks/hooks.json (plugin ships no hooks)")
        return 0

    try:
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(f"hooks: hooks/hooks.json — invalid JSON ({exc})")
        return 1 if args.strict else 0

    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        problems.append("hooks/hooks.json: top-level `hooks` object missing or not an object")
        hooks = {}

    events = 0
    invocations = 0
    referenced: set[Path] = set()

    for event, entries in hooks.items():
        events += 1
        where_ev = f"hooks.{event}"
        if event not in KNOWN_EVENTS:
            problems.append(
                f"{where_ev}: unknown hook event {event!r} — it will NEVER fire. If this is a "
                f"newly-supported Claude Code event, verify against the docs URL in this script "
                f"and add it to KNOWN_EVENTS.")
        if not isinstance(entries, list):
            problems.append(f"{where_ev}: value must be a list of hook entries")
            continue
        for idx, entry in enumerate(entries):
            where = f"{where_ev}[{idx}]"
            if not isinstance(entry, dict):
                problems.append(f"{where}: entry must be an object")
                continue
            matcher = entry.get("matcher", "")
            if not isinstance(matcher, str):
                problems.append(f"{where}: `matcher` must be a string")
            else:
                validate_matcher(event, matcher, where, problems, warnings)
            hlist = entry.get("hooks")
            if not isinstance(hlist, list) or not hlist:
                problems.append(f"{where}: `hooks` must be a non-empty list")
                continue
            for hidx, hook in enumerate(hlist):
                whereh = f"{where}.hooks[{hidx}]"
                if not isinstance(hook, dict):
                    problems.append(f"{whereh}: must be an object")
                    continue
                invocations += 1
                if hook.get("type") != "command":
                    problems.append(
                        f"{whereh}: unsupported hook type {hook.get('type')!r} (expected 'command')")
                timeout = hook.get("timeout")
                if "timeout" in hook and not (isinstance(timeout, (int, float))
                                              and not isinstance(timeout, bool) and timeout > 0):
                    problems.append(f"{whereh}: `timeout` must be a positive number")
                cmd = hook.get("command", "")
                if not isinstance(cmd, str) or not cmd.strip():
                    problems.append(f"{whereh}: `command` missing/empty")
                    continue
                # Scan the command AND any exec-form `args` (command:"bash",
                # args:["${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"]) — in exec form the script path
                # lives in args, so command alone has no scripts/<file>.
                hook_args = hook.get("args")
                if "args" in hook and not (isinstance(hook_args, list)
                                           and all(isinstance(a, str) for a in hook_args)):
                    problems.append(f"{whereh}: `args`, when present, must be a list of strings")
                scan = cmd
                if isinstance(hook_args, list):
                    scan = cmd + " " + " ".join(a for a in hook_args if isinstance(a, str))
                matches = list(SCRIPT_REF.finditer(scan))
                if not matches:
                    problems.append(f"{whereh}: command/args reference no scripts/<file> ({cmd!r})")
                    continue
                # A command may run more than one script (e.g. `… && …`) — validate each.
                for m in matches:
                    rel = m.group(1)
                    spath = root / "scripts" / rel
                    if not spath.is_file():
                        problems.append(f"{whereh}: references missing script scripts/{rel}")
                    elif spath.stat().st_size == 0:
                        problems.append(f"{whereh}: references empty script scripts/{rel}")
                    else:
                        referenced.add(spath)

    # `bash -n` every referenced SHELL script (parse check tied to the manifest). Non-shell
    # targets (e.g. a `python3 scripts/x.py` hook command) are skipped — bash -n would
    # false-positive on them.
    bash = shutil.which("bash")
    parsed = 0
    if bash:
        for spath in sorted(referenced):
            rel = spath.relative_to(root)
            if not _is_shell_script(spath):
                continue
            try:
                res = subprocess.run([bash, "-n", str(spath)], capture_output=True, text=True)
            except OSError as exc:
                problems.append(f"{rel}: could not run bash -n ({exc})")
                continue
            parsed += 1
            if res.returncode != 0:
                problems.append(f"{rel}: bash -n failed ({res.stderr.strip()})")
    else:
        print("  (note: bash not found — skipped `bash -n` parse checks)")

    summary = (f"{events} events, {invocations} invocations, "
               f"{len(referenced)} scripts, {parsed} parse-checked")

    for warning in warnings:
        print(f"  ⚠️  {warning}")

    if not problems:
        suffix = f" — {len(warnings)} warning(s)" if warnings else ""
        print(f"✅ OK — hooks manifest ({summary}){suffix}")
        return 0

    print(f"hooks: {len(problems)} problem(s) [{summary}]:")
    for problem in problems:
        print(f"  ❌ {problem}")
    if args.strict:
        print("— failing (strict).")
        return 1
    print("— warn mode (not blocking; pass --strict to enforce).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
