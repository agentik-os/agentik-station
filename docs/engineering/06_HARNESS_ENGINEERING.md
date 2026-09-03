# Harness Engineering

The model is replaceable. The harness is the reliable operating environment around it.

In Agentik, Hermes supplies much of the runtime harness. AGK and the installed OS define policy, topology, gates and desired state.

## Harness responsibilities

```text
Task specification
Context selection
Model/provider routing
Tool surface
Permissions
Project/workspace selection
Memory and skills
Task state / Kanban
Subagent topology
Worktree isolation
Verification
Approvals
Logging / observability
Failure attribution
Rollback / checkpoints
Evidence retention
Human intervention
Learning promotion
```

## Ownership

| Responsibility | Primary owner |
|---|---|
| agent loop, sessions, tools | Hermes |
| providers/models/fallback | Hermes |
| subagent delegation | Hermes |
| worktrees/checkpoints | Hermes |
| native logs | Hermes |
| self-improvement loop | Hermes |
| OS topology | AGK + OS package |
| capability policy | AGK |
| verification contract | AGK Engineering Standard |
| mission graph | OS Director + Hermes Kanban |
| evidence normalization | AGK Evidence |
| client boundary | Station Zone; dedicated Host/Node when policy requires |
| Discord cockpit | Agentik compiler + Hermes gateway |

## Principle

Never add an Agentik service merely because the concept sounds important. First ask whether Hermes already provides the primitive. Agentik should add policy, portability, governance, composition or evidence — not duplicate the kernel.
