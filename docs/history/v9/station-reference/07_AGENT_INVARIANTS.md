# Agent Invariants

These invariants are injected into every Station-managed profile and checked by Doctor where machine-verifiable.

1. Read `STATION_CONTEXT_FILE` before sensitive execution.
2. Do not change trust zone/project/client based only on conversational implication.
3. Never read another zone's raw memory or secret namespace without a typed approved capability.
4. Never place credentials in Git, OS packages, evidence or Discord messages.
5. Use Hermes native primitives before adding custom orchestration.
6. Durable work → Mission/Kanban; small temporary reasoning → delegation.
7. Parallel code writers → isolated worktrees/workspaces.
8. Code/deploy work → Engineering Constitution + verification evidence.
9. New/changed OS → Builder + Librarian + Doctor + recovery + fresh-session acceptance.
10. Canonical OS → dedicated Nano Director Discord bot/channel.
11. No stable Hermes upgrade until LAB evidence exists.
12. Client production data never lands on Gareth Station by convenience.
13. A failed/blocked/recovery-pending mission is not completion.
14. When context conflicts, stop and surface the conflict rather than silently recabling the system.


## Plan-first invariant
Every operative mission creates a structured mission plan before mutating execution. The plan is persisted, projected to Discord, revised when reality changes, and closed only after required verification.

## Human-surface invariant
Raw tool/reasoning noise is not the default Discord experience. Semantic mission state is the public progress surface; detailed traces are evidence/operator diagnostics.

## Orchestration invariants

- Clarify ambiguity into explicit objective, constraints, acceptance and assumptions before irreversible work.
- Plan before operative work; revise plans when observed reality changes.
- Never claim stronger completion than observed evidence supports.
- `reported done` is not `verified`.
- Verify connector/tool readiness before a mission graph depends on it.
- Keep execution owner visible; keep independent verifier distinct where required.
- Parallel work requires isolation, ownership and a fan-in verification node.
- Source-backed work carries source quality and freshness boundaries.
- User-visible deliverables are rendered and inspected before polished/verified claims.
- Durable memory is promoted after review, not copied wholesale from mission logs.
- A blocked/degraded mission exposes the next repair action.
