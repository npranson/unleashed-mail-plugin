---
description: Implement a feature using specialized coding agents (db, logic, UI) with TDD and modern standards
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
disable-model-invocation: true
---

# Implement: $ARGUMENTS

This command orchestrates implementation across specialized coding agents.

## Phase 1: Design Check

Check if a planning document exists for this feature:

```bash
ls docs/planning/*PLAN*.md 2>/dev/null
```

If no plan exists, run `/brainstorm` first — implementation without a tracked plan
violates project CLAUDE.md.

If a plan exists, read it and confirm the modern standards planner's recommendations
are still current.

## Phase 2: Implementation Plan

Break the feature into tasks, organized by the agent that will own each task.
Order by dependency — database first, then logic, then UI.

```
=== Database Layer (db-engineer) ===
Task 1: [Schema design + migration]
Task 2: [Record types + query extensions]
Task 3: [Database tests]

=== Logic Layer (logic-engineer) ===
Task 4: [Service protocol definition]
Task 5: [Gmail provider implementation]
Task 6: [Graph provider implementation]
Task 7: [ViewModel with state management]
Task 8: [Mock implementations + logic tests]

=== UI Layer (ui-engineer) ===
Task 9: [View hierarchy + layout]
Task 10: [Loading/error/empty states]
Task 11: [Accessibility + animations]
Task 12: [UI integration tests]
```

Present the plan and wait for approval. Note which tasks can run in parallel
(e.g., Gmail and Graph implementations can be parallel after the protocol is defined).

## Phase 3: Execute with Specialized Agents

### Database tasks → `db-engineer` agent

Launch the `db-engineer` agent for Tasks 1-3:
> Implement the following database changes for [feature]. Follow the `grdb-patterns`
> skill and `swift-tdd` skill (write failing tests first). [task details]

Wait for completion. The db-engineer will produce: migration, Record types, query
extensions, and database tests.

### Logic tasks → `logic-engineer` agent

Launch the `logic-engineer` agent for Tasks 4-8:
> Implement the service layer and ViewModel for [feature]. The database layer is
> already done — here are the Record types and query extensions available: [summary].
> Follow `provider-parity` skill for dual-provider implementation. Use `swift-tdd`
> skill for testing. [task details]

The logic-engineer will produce: protocol, both provider implementations, ViewModel,
mocks, and logic tests.

### UI tasks → `ui-engineer` agent

Launch the `ui-engineer` agent for Tasks 9-12:
> Build the UI for [feature]. The ViewModel is already done — here is its public
> interface: [summary of properties and methods]. Follow `swiftui-mvvm` skill.
> Include accessibility and all view states. [task details]

The ui-engineer will produce: SwiftUI views, subcomponents, accessibility config,
and state views.

## Phase 4: Integration

After all three agents complete:

1. **Wire it together** — Ensure the View instantiates the ViewModel with the correct
   service and database dependencies.

2. **Run the full test suite**:
   ```bash
   swift test 2>&1 | tail -30
   ```

3. **Verify provider parity**:
   ```bash
   grep -rn "TODO: PARITY" --include='*.swift' Sources/
   grep -rn "GmailMailProvider\|GraphMailProvider" --include='*.swift' Sources/ViewModels/ Sources/Views/
   ```

4. **Commit with conventional format**:
   ```bash
   git add <specific-changed-files>
   git commit -m "feat: [description]"
   ```

## Phase 5: Multi-Agent Review

Launch the `swift-reviewer` orchestrator agent, which will spawn four
specialized reviewers in parallel:
- `security-reviewer` — credentials, OAuth, pipeline, injection
- `concurrency-reviewer` — races, actors, deprecated APIs
- `ux-perf-reviewer` — responsiveness, rendering, query perf
- `accessibility-auditor` — VoiceOver, keyboard nav, a11y labels, dual-impl parity

Plus the `jira-manager` to log the review results on the ticket.

The orchestrator also runs the provider parity audit and produces a unified verdict.

Address any blockers or warnings before proceeding.

## Phase 6: Wrap Up

- Update `docs/planning/FEATURE_NAME_PLAN.md` status to "Complete" (or "In Review")
- Summarize what was implemented across all three layers
- List all commits made
- Note any follow-up items, tech debt, or deferred parity stubs
- Update Jira ticket via `jira-manager` with final status and follow-up tickets
- Offer to create a PR via `gh pr create`
