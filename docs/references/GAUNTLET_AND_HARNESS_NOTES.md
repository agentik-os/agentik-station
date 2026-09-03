# Gauntlet / Harness reference notes

The v4 blueprint treats these as engineering patterns, not mandatory third-party runtime dependencies.

## Gauntlet Loop

Useful pattern: bounded implementer → independent critic → targeted revision loops, with evidence and final integration verification.

Reference implementations/inspiration checked during v4 design:
- https://github.com/kamtS/gauntlet-loop
- https://github.com/NicholasSpisak/gauntlet-loop

Agentik implements the pattern with Hermes profiles/delegation/Kanban/worktrees rather than requiring either repository.

## Harness Engineering

Agentik uses "harness" to mean the runtime substrate around a model: context, tools, permissions, task state, isolation, verification, logs, failure recovery and evidence.

Hermes supplies most of the runtime substrate; AGK supplies organizational policy, graph semantics, capabilities, evidence contracts and installable OS composition.
