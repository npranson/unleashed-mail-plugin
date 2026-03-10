---
description: Brainstorm and design an UnleashedMail feature, then research modern approaches before planning
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

## Step 2: Explore the Codebase

Use Read, Grep, and Glob to understand the current state:

- What existing code is related to this feature?
- What patterns are already established?
- Are there similar features we can model this after?
- What's the current state of provider parity in the affected area?

## Step 3: Design Proposal

Present a concise design covering:

1. **Data model changes** — new GRDB records, migrations, or modifications
2. **Service layer** — new protocols/implementations needed (both providers)
3. **ViewModel** — new or modified ViewModels
4. **View** — UI changes (SwiftUI views, WKWebView changes)
5. **Provider parity** — what both Gmail and Graph need, and any known asymmetries

## Step 4: Research Modern Standards

Launch the **`modern-standards-planner`** agent to research current best practices for every technology area this feature touches. The planner will:

- Use Context7 to look up latest GRDB, MSAL, SwiftUI docs
- Web search for latest Gmail API and Graph API recommendations
- Check for deprecated APIs in the proposed approach
- Identify modernization opportunities

Wait for the planner's research summary before finalizing.

## Step 5: Edge Cases & Risks

- What could go wrong?
- What happens offline?
- Are there Gmail API or Graph API quota implications?
- Any security considerations?
- Provider-specific limitations (e.g., Gmail doesn't support X natively)?

## Step 6: Summary for Approval

Present the design as a short spec incorporating the planner's modern standards findings:

- Design decisions with rationale
- Which modern patterns will be adopted
- Provider parity plan
- Estimated task breakdown (S/M/L per task)
- Dual implementation impacts (native + WebKit compose, etc.)

## Step 7: Create Planning Document (Mandatory)

Per project CLAUDE.md, create `docs/planning/FEATURE_NAME_PLAN.md` using the template
from the `modern-standards-planner` agent. This is non-negotiable — no implementation
without a tracked plan.

Update the Jira ticket with a link to the plan document.

Wait for approval before proceeding to `/implement`.
