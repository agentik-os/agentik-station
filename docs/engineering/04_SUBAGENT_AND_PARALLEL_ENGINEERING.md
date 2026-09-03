# Subagent and Parallel Engineering

Hermes provides native `delegate_task`, bounded spawn depth, configurable parallel child count and optional worktree isolation. AGK defines how those primitives are used safely.

## Delegation contract

Every subagent task MUST include:

```yaml
subtask:
  objective: one clear outcome
  scope:
    owns: [explicit files/components/questions]
    must_not_touch: [other ownership areas]
  inputs: [minimum required context]
  outputs:
    - artifact_or_answer
    - evidence
    - assumptions
    - blockers
    - recommended_next_action
  verification: explicit checks
  completion: pass|fail|blocked
```

## When to parallelize

Parallelize when workstreams are:
- independent,
- read-only,
- isolated by worktree,
- or have explicit non-overlapping ownership.

Do NOT parallelize blindly when several agents mutate the same state, schema, migration, deployment target or tightly-coupled core module.

## Fan-out / fan-in

```text
                 Director
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
       Agent A   Agent B   Agent C
       WT-A      WT-B      WT-C
          │         │         │
          └──── evidence ─────┘
                    │
                    ▼
             Integration Agent
                    │
                    ▼
             Integration Critic
```

## Defaults

```yaml
delegation:
  max_concurrent_children: 3
  max_spawn_depth: 2
  orchestrator_enabled: true
  worktree_isolation: true
```

Increase concurrency only after observing collision rate, integration cost, token economics and verification reliability.

## Anti-patterns

- fan-out with overlapping write ownership,
- giving every child the entire parent transcript,
- agents coordinating only through free-form chat,
- unbounded recursive delegation,
- merging child branches without integration tests,
- allowing a child to mark the parent mission DONE.
