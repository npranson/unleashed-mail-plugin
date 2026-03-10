---
name: agent-orchestration
description: >
  Orchestration patterns for running UnleashedMail agents in parallel. Activates
  when coordinating multi-agent workflows, determining which agents to run, or
  deciding execution order. Defines dependency rules and parallelization strategies
  for all agent combinations.
allowed-tools: Task, Read, Grep, Glob, Bash
---

# Agent Orchestration — Flexible Parallel Execution

## Agent Registry

### Coding Agents (produce code)

| Agent | Layer | Depends On | Can Parallel With |
|---|---|---|---|
| `db-engineer` | Database | Nothing (runs first) | `jira-manager` |
| `logic-engineer` | Services/ViewModels | `db-engineer` output | `jira-manager`, `ui-engineer` (if protocol is defined first) |
| `ui-engineer` | Views | `logic-engineer` ViewModel interface | `jira-manager`, `db-engineer` (next feature) |

### Review Agents (evaluate code)

| Agent | Focus | Depends On | Can Parallel With |
|---|---|---|---|
| `security-reviewer` | Credentials, OAuth, injection, CI | Changeset | All other reviewers |
| `concurrency-reviewer` | Races, actors, deprecated APIs | Changeset | All other reviewers |
| `ux-perf-reviewer` | Responsiveness, rendering, query perf | Changeset | All other reviewers |
| `accessibility-auditor` | VoiceOver, keyboard nav, a11y labels | Changeset | All other reviewers |
| `swift-reviewer` | Orchestrator + parity audit | Reviewer outputs | Runs after reviewers complete |

### Planning & Support Agents

| Agent | Role | Depends On | Can Parallel With |
|---|---|---|---|
| `modern-standards-planner` | Research current best practices | Feature description | `jira-manager` |
| `jira-manager` | Ticket lifecycle | Nothing | Everything — always parallel |
| `xcode-build-fixer` | Build failure diagnosis | Build error output | Nothing (reactive) |
| `graph-api-debugger` | Graph/MSAL debugging | Error context | Nothing (reactive) |

## Parallel Execution Rules

### Rule 1: Independent agents ALWAYS run in parallel

When spawning agents via `Task`, launch all independent agents in a single message.
Do NOT wait for one to finish before starting another if they don't depend on each other.

```
✅ Good: Launch security-reviewer + concurrency-reviewer + ux-perf-reviewer + accessibility-auditor simultaneously
❌ Bad: Run security-reviewer, wait, then run concurrency-reviewer, wait, then...
```

### Rule 2: Dependent agents chain, but parallelize within each stage

```
Stage 1 (parallel):  db-engineer + jira-manager + modern-standards-planner
Stage 2 (parallel):  logic-engineer (Gmail) + logic-engineer (Graph) + jira-manager update
Stage 3 (parallel):  ui-engineer + jira-manager update
Stage 4 (parallel):  security-reviewer + concurrency-reviewer + ux-perf-reviewer + accessibility-auditor
Stage 5 (serial):    swift-reviewer orchestrator synthesizes
```

### Rule 3: Jira manager is always parallel

The `jira-manager` agent runs alongside everything. It never blocks and never waits.
Invoke it at natural breakpoints (stage transitions) to log progress.

### Rule 4: Any subset of agents can be invoked

The user can request any combination:

```
"Run the security and accessibility reviewers on this PR"
→ Launch security-reviewer + accessibility-auditor in parallel

"Just have the db-engineer and logic-engineer implement this migration"
→ Launch db-engineer, then chain logic-engineer

"Do a full review"
→ Launch all 4 reviewers in parallel → swift-reviewer synthesizes

"Implement and review, but skip the planner"
→ db → logic → ui → all reviewers in parallel
```

## Execution Patterns

### Pattern A: Full Feature Lifecycle

```
1. modern-standards-planner + jira-manager (parallel)
   ↓
2. db-engineer + jira-manager milestone (parallel)
   ↓
3. logic-engineer + jira-manager milestone (parallel)
   ↓
4. ui-engineer + jira-manager milestone (parallel)
   ↓
5. security-reviewer + concurrency-reviewer + ux-perf-reviewer + accessibility-auditor (parallel)
   ↓
6. swift-reviewer (synthesizes) + jira-manager final update (parallel)
```

### Pattern B: Review Only

```
1. security-reviewer + concurrency-reviewer + ux-perf-reviewer + accessibility-auditor (all parallel)
   ↓
2. swift-reviewer synthesizes + jira-manager logs review results
```

### Pattern C: Targeted Implementation

```
User: "Just fix the database layer for this feature"
→ db-engineer only + jira-manager
   ↓
→ Optional: concurrency-reviewer + security-reviewer (targeted to db changes)
```

### Pattern D: Debug & Fix

```
1. xcode-build-fixer OR graph-api-debugger (diagnostic)
   ↓
2. Appropriate coding agent for the fix
   ↓
3. Targeted review (security if auth-related, concurrency if threading-related)
   ↓
4. jira-manager logs the fix
```

## Handoff Protocol

When one agent's output feeds into the next, the handoff must include:

### db-engineer → logic-engineer

```
Handoff: Database layer complete
- Migration: v{N}_{description} 
- Record types: [list of structs]
- Query extensions: [list of static methods]
- Available observations: [ValueObservation setups]
```

### logic-engineer → ui-engineer

```
Handoff: Logic layer complete
- ViewModel: [class name]
  - Published state: [list of properties with types]
  - Actions: [list of async methods]
  - Error type: [MailProviderError cases relevant]
  - Observation: [how the VM starts/stops observation]
- Service protocol: [protocol name and key methods]
```

### All reviewers → swift-reviewer

```
Handoff: Review complete
- Severity: [highest severity found]
- Findings: [count by severity]
- Report: [structured review output]
```

## Context Sharing

Agents operating in parallel on the same feature should reference:

1. The **planning document** (`docs/planning/FEATURE_NAME_PLAN.md`) for shared context
2. The **Jira ticket** (managed by `jira-manager`) for status and decisions
3. The **CLAUDE.md** (this plugin's global context) for conventions and constraints

When spawning agents, always include:
- Which feature/ticket they're working on
- Which stage of the pipeline they're in
- What other agents have already produced (if any)
