#!/usr/bin/env python3
"""validate-plugin-assembly.py — Phase 0, Item 2 (COREDEV-2322).

Treats the unleashed-mail plugin's own assets as software: every agent/skill/command
must have well-formed YAML frontmatter, and every JSON manifest must parse. Catches the
silent-load-failure class (a dropped `description` => a skill that never auto-triggers; a
non-kebab name; an unparseable manifest) at commit/PR time instead of at runtime.

Design constraints (from the plan):
  * stdlib ONLY — no PyYAML (python3 is already a hard dep via the review-synthesizer MCP).
    Frontmatter is hand-parsed (top-level keys + block scalars), which is all we need here.
  * unleashed uses Claude Code AUTO-DISCOVERY, so there is NO "registered in plugin.json"
    cross-check (plugin.json does not list agents/skills/commands) — that octo check would
    false-positive here and is deliberately omitted.

Required frontmatter (verified against the repo):
  * agents/*.md         -> name (kebab-case) + description
  * skills/*/SKILL.md   -> name (kebab-case) + description
  * commands/*.md       -> description   (name is derived from the FILENAME; the stem must be kebab-case)

Usage:
  python3 scripts/validate-plugin-assembly.py [--root .] [--strict]
    default     warn  — print problems, exit 0  (pre-commit)
    --strict          — print problems, exit 1  (CI)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOP_KEY = re.compile(r"^([A-Za-z0-9_-]+):(.*)$")  # column-0 key: value


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return {key: value} for the leading `---`…`---` block, or None if absent.

    Handles inline values and block scalars (`key: >` / `key: |` followed by indented
    lines): such a key is recorded with a non-empty sentinel if it has indented content.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm: dict[str, str] = {}
    i, n = 1, len(lines)
    current: str | None = None
    while i < n:
        line = lines[i]
        if line.strip() == "---":
            return fm
        m = TOP_KEY.match(line)
        if m and not line[:1].isspace():
            key, val = m.group(1), m.group(2).strip()
            # Quoted value: extract up to the matching closing quote, dropping any
            # trailing ` # comment` (a `#` inside the quotes is literal). This must
            # handle `name: "x" # note`, where the value no longer *ends* with a quote
            # (codex/gemini PR #11). Unquoted: strip a YAML comment so `description: #
            # TODO` reads as empty and `name: good-agent # note` validates.
            if val[:1] in ('"', "'"):
                end = val.find(val[0], 1)
                if end != -1:
                    val = val[1:end].strip()
            elif val.startswith("#"):
                val = ""
            else:
                hashpos = val.find(" #")
                if hashpos != -1:
                    val = val[:hashpos].strip()
            fm[key] = val  # may be "", ">", "|", or an inline value
            current = key
        elif current is not None and line.strip() and line[:1].isspace():
            # continuation / block-scalar body -> the key has content
            if fm.get(current, "") in ("", ">", "|", ">-", "|-"):
                fm[current] = line.strip()
        i += 1
    return None  # no closing '---'


def has(fm: dict[str, str], key: str) -> bool:
    v = fm.get(key, "")
    return v not in ("", ">", "|", ">-", "|-")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate unleashed-mail plugin assets.")
    ap.add_argument("--root", default=None, help="plugin repo root (default: parent of scripts/)")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any problem (CI)")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    problems: list[str] = []

    def check_frontmatter(path: Path, require_name: bool) -> None:
        rel = path.relative_to(root)
        try:
            text = path.read_text(encoding="utf-8-sig")  # utf-8-sig strips a BOM (PR #11)
        except OSError as e:
            problems.append(f"{rel}: cannot read ({e})")
            return
        fm = parse_frontmatter(text)
        if fm is None:
            problems.append(f"{rel}: missing or unterminated YAML frontmatter (`---` block)")
            return
        if not has(fm, "description"):
            problems.append(f"{rel}: frontmatter missing non-empty `description`")
        if require_name:
            if not has(fm, "name"):
                problems.append(f"{rel}: frontmatter missing non-empty `name`")
            elif not KEBAB.match(fm["name"]):
                problems.append(f"{rel}: `name: {fm['name']}` is not kebab-case")

    # agents/*.md and skills/*/SKILL.md require name+description.
    agents = sorted((root / "agents").glob("*.md"))
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    commands = sorted((root / "commands").glob("*.md"))

    for p in agents:
        check_frontmatter(p, require_name=True)
    for p in skills:
        check_frontmatter(p, require_name=True)
    # commands: name is the filename — require description + a kebab-case stem.
    for p in commands:
        check_frontmatter(p, require_name=False)
        if not KEBAB.match(p.stem):
            problems.append(f"{p.relative_to(root)}: command filename stem `{p.stem}` is not kebab-case")

    # JSON manifests must parse. plugin.json + marketplace.json are required;
    # .mcp.json + hooks/hooks.json are optional — validated only when present (the
    # plan lists hooks.json as JSON-loaded; PR #11). `ValueError` also catches a
    # UTF-8 BOM/decode error, not just `JSONDecodeError` (which subclasses it).
    required_manifests = [
        root / ".claude-plugin" / "plugin.json",
        root / ".claude-plugin" / "marketplace.json",
    ]
    optional_manifests = [
        root / ".mcp.json",
        root / "hooks" / "hooks.json",
    ]
    parsed = 0
    total_manifests = len(required_manifests)
    for m in required_manifests:
        if not m.exists():
            problems.append(f"{m.relative_to(root)}: missing")
            continue
        try:
            json.loads(m.read_text(encoding="utf-8-sig"))
            parsed += 1
        except (OSError, ValueError) as e:
            problems.append(f"{m.relative_to(root)}: invalid JSON ({e})")
    for m in optional_manifests:
        if not m.is_file():
            continue
        total_manifests += 1
        try:
            json.loads(m.read_text(encoding="utf-8-sig"))
            parsed += 1
        except (OSError, ValueError) as e:
            problems.append(f"{m.relative_to(root)}: invalid JSON ({e})")

    summary = (f"{len(agents)} agents, {len(skills)} skills, {len(commands)} commands, "
               f"{parsed}/{total_manifests} manifests")
    if not problems:
        print(f"✅ OK — plugin assembly ({summary})")
        return 0

    print(f"plugin-assembly: {len(problems)} problem(s) [{summary}]:")
    for p in problems:
        print(f"  ❌ {p}")
    if args.strict:
        print("— failing (strict).")
        return 1
    print("— warn mode (not blocking; pass --strict to enforce).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
