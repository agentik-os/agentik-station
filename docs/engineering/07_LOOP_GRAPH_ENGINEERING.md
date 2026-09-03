# Loop-Graph Engineering

Complex autonomous engineering must be represented as a bounded execution graph rather than a long linear prompt.

## Graph model

```text
G = (V, E)
```

Node types:

```text
SPEC
RESEARCH
DECISION
IMPLEMENT
VERIFY
CRITIC
INTEGRATE
APPROVAL
DEPLOY
OBSERVE
LEARN
```

Edge types:

```text
depends_on
fan_out
fan_in
pass
fail
retry
escalate
rollback
```

Hermes Kanban provides durable task/dependency state. AGK adds typed graph semantics and completion rules.

## Example

```text
SPEC
 ↓
ARCHITECTURE
 ↓
 ┌──────────── fan-out ────────────┐
 ▼                                 ▼
API IMPLEMENT                  UI IMPLEMENT
 ↓                                 ↓
VERIFY API                     VERIFY UI
 └──────────── fan-in ─────────────┘
                ↓
            INTEGRATE
                ↓
        INTEGRATION VERIFY
                ↓
          GAUNTLET CRITIC
           │           │
         pass         fail
           │           └──→ targeted retry node
           ▼
          STAGING
            ↓
          LIVE E2E
            ↓
            DONE
```

## Loop rules

- Every loop has a max iteration count or explicit budget.
- Every fail edge points to the smallest responsible node.
- Every graph has escalation edges.
- Parallel branches must converge through a fan-in verification node.
- No cyclic loop can bypass a human approval boundary.
- Graph state must survive process restarts.
