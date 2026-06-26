---
description: Brainstorm and design a feature — research modern approaches, then pressure-test with enterprise and SMB stakeholder personas before planning
allowed-tools: Read, Grep, Glob, Agent, WebFetch, WebSearch, AskUserQuestion
disable-model-invocation: true
---

# Feature Brainstorm: $ARGUMENTS

You are starting the design phase for a new feature in UnleashedMail.

**Do NOT write any code yet.** This is design + research only.

## Step 1: Jira Ticket Setup

Launch the **`jira-manager`** agent in parallel with Step 2:
> Check if a Jira ticket exists for this feature. If not, create one (Task type).
> Associate with parent Epic if one exists. Log that brainstorming has begun.

## Step 2: Understand the Request

Restate the feature request in your own words. Ask clarifying questions if ambiguous. Identify:

- **Who** benefits from this feature (end user, developer, both)?
- **What** does it do at a high level?
- **Where** in the app does it live (which views, which layer)?
- **Why** is it needed (user pain point, missing capability)?
- **Which providers** does it affect (Gmail, Graph, both)?

## Step 3: Explore the Codebase

Use Read, Grep, and Glob to understand the current state:

- What existing code is related to this feature?
- What patterns are already established?
- Are there similar features we can model this after?
- What's the current state of provider parity in the affected area?

## Step 4: Design Proposal

Present a concise design covering:

1. **Data model changes** — new GRDB records, migrations, or modifications
2. **Service layer** — new protocols/implementations needed (both providers)
3. **ViewModel** — new or modified ViewModels
4. **View** — UI changes (SwiftUI views, WKWebView changes)
5. **Provider parity** — what both Gmail and Graph need, and any known asymmetries

## Step 4b: Decision-Support Options (for forks)

**Only when the design has a genuine architectural fork** — a point where two or more materially
different approaches are viable and the choice shapes the rest of the plan (sync strategy, storage
shape, provider mechanism, migration timing). Skip this step entirely for a linear design with one
obvious approach; do **not** manufacture a fork.

Present **2–4 options** in a comparison table, then call **`AskUserQuestion`** to record the chosen
fork **before** the Step 9 plan document is written — so the plan commits to a decided approach, not an
open question. No emoji; use the project's vocabulary (`**Pros**` / `**Cons**` / `**(Recommended)**`).

**Comparison table** — one column per option, at least these rows:

| Dimension | Option A | Option B |
|---|---|---|
| **Summary** | one line | one line |
| **Pros** | … | … |
| **Cons** | … | … |
| **Parity-Impact** | what Gmail needs · what Graph needs · any asymmetry | … |
| **Effort** | S / M / L | S / M / L |
| **Reversibility** | easy / moderate / hard to undo later | … |
| **Best for** | when this option wins | … |

Then a recommendation line — **`Option X (Recommended)`** — one sentence on why, honest about the
trade-off being accepted.

**Parity-Impact is mandatory — never drop that row.** Every sync / compose / push / storage fork has a
provider-parity dimension (CLAUDE.md). A "Gmail-only quick win" must still show its Graph cost (e.g. a
tracked `// TODO: PARITY` stub), not omit the column.

**Worked examples (real unleashed forks):**

- **Incremental sync:** Gmail `historyId`-incremental vs full resync. Parity-Impact: Graph's counterpart
  is `deltaLink` delta queries — the choice must land for **both** providers.
- **Push vs poll:** Gmail Pub/Sub push vs Graph webhook subscription / delta-poll — different
  freshness/cost trade-offs per provider.
- **Compose editor:** `NativeRichTextEditor` (macOS 26+) vs `HTMLWebViewEditor` (≤25). **This is
  OS-gated, not a peer choice** — present it as a hard precondition (the native editor only exists on
  macOS 26+; the WebKit editor is the floor on ≤25), never as two interchangeable alternatives on
  macOS 25.
- **Migration timing:** CRITICAL (runs at startup, blocks UI) vs DEFERRABLE (background after UI loads).
  **Default to DEFERRABLE** (CLAUDE.md "defer unless proven critical"); starring CRITICAL requires
  explicit justification that the data is needed before first paint.

**Record the decision:** call `AskUserQuestion` with the option labels — lead with the recommended one,
suffixed `(Recommended)`. Carry the chosen option, **and** the rejected alternatives as "considered and
why not," into the Step 8 summary and the Step 9 plan document.

## Step 5: Research Modern Standards

Launch the **`modern-standards-planner`** agent to research current best practices for every technology area this feature touches. The planner will:

- Use Context7 to look up latest GRDB, MSAL, SwiftUI docs
- Web search for latest Gmail API and Graph API recommendations
- Check for deprecated APIs in the proposed approach
- Identify modernization opportunities

Wait for the planner's research summary before finalizing.

## Step 6: Stakeholder Review

Launch both persona agents **in parallel** to pressure-test the design:

**Agent: `enterprise-stakeholder`**
> Review this feature proposal from an enterprise deployment perspective.
> Evaluate for: compliance (HIPAA, SOC 2, PIPEDA), admin control, scale
> (50k emails, 200 labels, shared mailboxes), SSO/MDM, integration risks,
> and security. Here is the proposed design: [summary from Steps 2-4]

**Agent: `smb-entrepreneur`**
> Review this feature proposal from a small business power-user perspective.
> Evaluate for: daily workflow impact (150 emails/day, 3 accounts), speed,
> keyboard-first UX, client communication edge cases, multi-device sync,
> cost justification, and competitive comparison. Here is the proposed design:
> [summary from Steps 2-4]

Collect both assessments and incorporate their findings:
- Enterprise BLOCK or SHIP WITH CONDITIONS items become hard requirements
- SMB DEAL BREAKER items become hard requirements
- Enterprise NEEDS WORK and SMB NICE TO HAVE items become backlog candidates
- Missing requirements from both personas get added to the spec

## Step 7: Edge Cases & Risks (Consolidated)

Merge technical risks with stakeholder findings:

- What could go wrong technically? (offline, API quotas, provider limitations)
- What could go wrong for enterprise? (compliance gaps, admin blind spots, scale failures)
- What could go wrong for SMB? (workflow disruption, speed regression, missing integrations)
- Security considerations from both perspectives

## Step 8: Summary for Approval

Present the design as a short spec incorporating:

- Design decisions with rationale
- Modern standards findings (from planner)
- Enterprise impact assessment verdict and key conditions
- SMB reality check verdict and key expectations
- Provider parity plan
- Estimated task breakdown (S/M/L per task)
- Dual implementation impacts (native + WebKit compose, etc.)
- Requirements added from stakeholder review

## Step 9: Create Planning Document (Mandatory)

Per project CLAUDE.md, create `docs/planning/FEATURE_NAME_PLAN.md` using the template
from the `modern-standards-planner` agent. This is non-negotiable — no implementation
without a tracked plan.

Update the Jira ticket with a link to the plan document.

Wait for approval before proceeding to `/unleashed-mail:implement`.
