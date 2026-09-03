# Engineering Episode Model

A mission episode is the auditable trace of one engineering outcome.

Minimum indexed fields:

```text
organization
OS
mission
root Kanban task
mission graph version
profiles/Bots
model route aliases + resolved provider:model
sessions
subagents
worktrees
commits/PR
verification runs
Gauntlet critic runs
approvals
CI/deployments
Hermes log references
cost/latency
final outcome
failure attribution
learning candidates
```

Use episode data for:
- incident review,
- evaluator datasets,
- cost/performance analysis,
- model-route comparison,
- regression detection,
- skill self-improvement,
- proving delivery to clients.
