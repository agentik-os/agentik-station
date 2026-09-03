# Builder OS

Builder OS is installed by default on Agentik development/candidate Nodes and is the canonical factory/upgrader for all OS packages.

See `15_BUILDER/` for the complete contract.

## Hermes implementation

```text
Dedicated Discord Bot
        -> master-os-builder Hermes Profile (Nano Director)
        -> Builder Bot Group / NanoTeam
        -> Kanban board: builder
        -> Librarian dependency
        -> DevOps Engineering Harness
        -> OS registry + evidence
```

Builder itself must pass its own OS Contract, Doctor, rollback, recovery and fresh-session acceptance.
