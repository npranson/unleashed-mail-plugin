---
description: Brainstorm and design a feature — research modern approaches, then pressure-test with enterprise and SMB stakeholder personas before planning
allowed-tools: Read, Grep, Glob, Task, WebFetch, WebSearch
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

Wait for approval before proceeding to `/implement`.
