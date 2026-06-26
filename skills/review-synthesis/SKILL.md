---
name: review-synthesis
description: Synthesize the two plan-review transcripts (gemini + codex) into one auditable combined-verdict block. Read-only; run AFTER both /unleashed-mail:gemini-review and /unleashed-mail:codex-review transcripts are captured, before implementation begins.
allowed-tools: Read, Grep
---

# Plan-Review Synthesis

A **read-only** skill that combines the two plan-review transcripts into a single auditable record — the
proof that the `AGENT_CONTRACTS.md §2` "both reviewers must return APPROVE / APPROVE_WITH_NOTES" gate
passed, with any disagreement **surfaced** rather than averaged away. It runs nothing and gates nothing
automatically; it produces a Markdown block for the human running the gate.

Run it **after** both review transcripts are captured (see `/unleashed-mail:gemini-review` and
`/unleashed-mail:codex-review`):

- gemini → `/tmp/agy-out.txt`  (Antigravity `agy`, free-form plaintext)
- codex  → `/tmp/codex-out.txt` (`codex exec`, free-form plaintext)

Those are the default paths the two review skills write. If the caller specifies custom paths in the
prompt (e.g. "synthesize `/tmp/a.txt` and `/tmp/b.txt`"), read those instead.

> **Scope — keep this distinct from the code-review synthesizer.** This is the **plan-review**
> synthesizer: **2 prose transcripts**, before implementation. It is deliberately separate from the
> code-review MCP synthesizer (`mcp/review-synthesizer/`, tool `synthesize_review`), which merges **5
> JSON findings arrays** after implementation and uses a different verdict vocabulary
> (`APPROVE_WITH_SUGGESTIONS` / `NEEDS_DISCUSSION`). **Do not unify the two enums.** This skill's verdict
> set is `APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES | DISAGREEMENT`.

## Inputs

1. Read `/tmp/agy-out.txt` (gemini) and `/tmp/codex-out.txt` (codex). Treat a **missing, empty, or
   0-byte** file as **"reviewer did not return"** — never as silent approval.
2. From each transcript, extract the reviewer's verdict token. Each review skill asks the reviewer to end
   with an explicit `VERDICT:` / `Verdict:` line — prefer that. If it is absent, infer the verdict from
   the prose **conservatively**: when ambiguous, pick the **more conservative** verdict and lower the
   confidence.

## Verdict normalization

Map each reviewer's raw verdict to one canonical token:

| Raw (any reviewer / CLI) | Canonical |
|---|---|
| `APPROVE`, "looks good", "ship it" | `APPROVE` |
| `APPROVE_WITH_NOTES`, `APPROVE_WITH_NITS`, "approve with a couple of nits/notes" | `APPROVE_WITH_NOTES` |
| `REQUEST_CHANGES`, `REQUEST CHANGES`, "needs changes", "blocking" | `REQUEST_CHANGES` |
| missing / empty / unparseable transcript | `MISSING` |

> The `agy`/gemini CLI emits `APPROVE_WITH_NITS`; the project's canonical gate term (CLAUDE.md,
> `AGENT_CONTRACTS.md`) is `APPROVE_WITH_NOTES`. **Normalize `NITS → NOTES`.**

## Combined-verdict rule (apply in priority order — first match wins)

1. **Either or both transcripts `MISSING`** → you **cannot** claim `APPROVE`:
   - **Both** missing → `REQUEST_CHANGES` (the gate did not run at all).
   - One missing, the other `REQUEST_CHANGES` → `REQUEST_CHANGES`.
   - One missing, the other approves (`APPROVE`/`APPROVE_WITH_NOTES`) → `DISAGREEMENT` (a lone approval can't carry the gate).
   Always **low** confidence, with an explicit note naming the reviewer(s) that did not return.
2. **One side approves (`APPROVE`/`APPROVE_WITH_NOTES`) and the other is `REQUEST_CHANGES`** →
   `DISAGREEMENT`. Surface both positions; **do not average** to a middle verdict.
3. **Both `REQUEST_CHANGES`** → `REQUEST_CHANGES`.
4. **Both approve** (`APPROVE`/`APPROVE_WITH_NOTES`) → `APPROVE_WITH_NOTES` **if either reviewer had
   notes**; otherwise `APPROVE`.

## Output (emit exactly this shape; plain Markdown, no emoji)

```markdown
## Plan-Review Synthesis

**Combined verdict:** APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES | DISAGREEMENT

### Agreement
- [points BOTH reviewers raised or endorsed]

### Disagreement
- [points where the reviewers diverge — name which reviewer took which side; leave empty only if they fully agree]

### Minority report
- [a concern raised by ONLY one reviewer that you are NOT folding into the combined verdict but the human should see]

### Risk register

| Risk | Raised by | Likelihood | Mitigation |
|---|---|---|---|
| … | gemini / codex / both | low/med/high | … |

### Conditions that would change the recommendation
- [what evidence or change would flip the verdict — e.g. "codex blocker X addressed", "missing transcript recaptured"]

### Confidence
- **[high | medium | low]** — [one line; low whenever a transcript was MISSING or a verdict was inferred from ambiguous prose]
```

## Guardrails

- **No PII.** Plan transcripts may quote email addresses, subjects, or message bodies. Reference findings
  by **location/topic** (file, area, concern) — never echo an address, subject, or body into the block.
- **Partial capture is the known failure mode.** A short or 0-byte transcript means the reviewer did not
  return; treat it as `MISSING` (rule 1), never as a silent `APPROVE`.
- **Surface, don't average.** `DISAGREEMENT` is a real verdict — keep both reviewers' positions visible
  rather than collapsing a one-approve / one-reject split into either extreme.
- **Passive and read-only.** This skill reads two files and emits one block; it never edits the plan,
  re-runs a reviewer, or gates anything on its own.
