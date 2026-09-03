# Agentik Engineering Constitution

This document is mandatory for DevOps OS, Builder OS, Engineering OS, QA OS and any OS allowed to modify production software.

## Prime directive

**Hermes is the runtime harness. AGK defines the engineering constitution. OS packages define teams and capabilities. Models remain replaceable. Evidence decides completion.**

The engineering system MUST optimize for correctness, simplicity, recoverability, observability and bounded autonomy rather than raw code generation volume.

## Canonical stack

```text
Intent / Issue / Mission
        ↓
Specification + acceptance criteria
        ↓
Repository comprehension
        ↓
Ponytail simplification ladder
        ↓
Loop-Graph plan G=(V,E)
        ↓
Parallel isolated execution where safe
        ↓
Subagent engineering contracts
        ↓
Implementation in worktrees
        ↓
Deterministic verification
        ↓
Independent Gauntlet critics
        ↓
Revision loop (bounded)
        ↓
Integration verification
        ↓
PR / CI / staging / live verification
        ↓
Evidence package + logs
        ↓
Learning review
        ↓
Skill/memory candidate promotion
```

## Mandatory disciplines

1. **Plan First** — no substantial implementation without a mission graph and acceptance criteria.
2. **Repository Comprehension** — inspect the real path, dependencies, conventions and existing code before proposing additions.
3. **Ponytail** — prefer deletion, reuse, stdlib, platform primitives and installed dependencies before new abstraction.
4. **Verification Engineering** — completion is based on evidence, not agent confidence.
5. **Gauntlet Loop** — important artifacts are independently criticized and revised with bounded retries.
6. **Subagent Engineering** — every delegated task has explicit input, ownership, output contract and verification contract.
7. **Parallel Agents** — parallelize only non-overlapping or isolated work; use fan-in integration gates.
8. **Worktree Isolation** — concurrent code-writing agents must not share a mutable checkout.
9. **Harness Engineering** — reliability lives in context, tools, permissions, state, tests, logs, recovery and gates around the model.
10. **Loop-Graph Engineering** — complex work is modeled as a graph with typed nodes, dependencies, gates, bounded loops and escalation edges.
11. **Model-Agnostic Coding** — workflows target capabilities and contracts, never one proprietary model behavior.
12. **Self-Improvement with Governance** — Hermes may learn; production policy, permissions and security rules never self-modify without promotion gates.
13. **Evidence + Logs** — every material mission produces an auditable episode package.

## Definition of done

A code mission is not DONE because an agent says it is done. It is DONE only when all required gates are green and evidence is attached.

## Build with leverage before implementation

Engineering begins with a leverage scan across existing Station/OS capabilities, repository implementation, Hermes-native primitives, platform/stdlib, installed dependencies, Skills/programs and already-bound MCP/Composio/API adapters. Ponytail remains the coding-level simplification discipline, but the leverage decision happens before architecture expands.

## Evidence Before Claims

Engineering status uses the Station evidence ladder. Implementation owner reports can advance work to `reported`, never to `verified`. Verification, CI, security and post-deploy readback have their own owners and evidence.
