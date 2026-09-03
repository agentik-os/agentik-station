# Delegation and Worktrees

## Delegation model

```text
Nano Director
├── Team Director A
│   ├── Specialist
│   └── Specialist
└── Team Director B
    ├── Specialist
    └── Specialist
```

Keep concurrency and spawn depth bounded.

Recommended initial design:

```yaml
delegation:
  max_concurrent_children: 3
  max_spawn_depth: 2
  orchestrator_enabled: true
  worktree_isolation: true
```

## Worktree rule

For meaningful code implementation:

```text
1 implementation task
≈
1 worktree
≈
1 branch
```

Example:

```text
repo/
├── main
└── .worktrees/
    ├── mb142-backend/
    ├── mb142-ui/
    └── mb142-tests/
```

This prevents multiple workers from modifying the same checkout.

## Fresh context

Delegated agents should begin with:
- focused mission
- relevant project context
- relevant tools
- no unnecessary parent conversation history

## Team communication

Subagents should return:
- result
- evidence
- assumptions
- blockers
- recommended next action

Do not rely on uncontrolled agent-to-agent chat as the primary coordination mechanism.


## Agentik engineering rule

Hermes delegation is the runtime primitive. AGK adds delegation contracts, typed graph ownership, bounded loops and integration gates.

Do not equate a Discord thread with a worktree. Threads are sessions; mutable coding workstreams receive worktrees. A single mission may fan out into several child worktrees and then fan in through an integration verification node.

See `14_ENGINEERING/04_SUBAGENT_AND_PARALLEL_ENGINEERING.md` and `14_ENGINEERING/05_WORKTREE_ISOLATION.md`.
