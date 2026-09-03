# Executor-Neutral and Parallel Orchestration

## Neutral owners

Graph nodes declare an execution requirement, then Station resolves an owner:

```text
Hermes profile
external coding executor
human
program/script
CI system
artifact renderer
connector adapter
```

Product language and evidence do not assume Codex, Claude Code or a specific model unless the mission explicitly requires it.

## Durable parallelism

Parallel execution is allowed only if:
- branches are dependency-independent or dependency boundaries are explicit;
- ownership is visible;
- mutable code work has isolated worktrees/workspaces;
- data/account side effects do not conflict;
- fan-in/integration owner is declared;
- each branch emits its own evidence.

## Fan-in

Parallel branch completion does not complete the mission. The fan-in node integrates outputs, resolves conflicts, re-runs system-level verification and advances evidence status only after integration passes.
