# Oh My Hermes (OMH) Interop

OMH is useful to Station as an **optional observed-executor/handoff adapter**, especially for engineering workflows. It is not the Station source of truth and it does not replace Hermes, AGK mission state, Builder, Librarian or Station policy.

## What Station adopts conceptually

- explicit capability/workflow selection;
- prepared intent vs observed execution;
- executor-neutral coding handoffs;
- status narration without pretending a handoff executed;
- evidence boundaries between reported completion and verified completion.

## Integration boundary

```text
Station Mission Contract
        ↓
Station owner/executor resolver
        ↓
optional OMH prepared handoff / observation adapter
        ↓
selected executor
        ↓
observations returned
        ↓
Station Evidence Claim Model
```

OMH records may be imported as observations, but Station independently maps them to its evidence classes.

## Hard rules

- OMH is optional; Station must still operate without it.
- no OMH metadata record is stronger than the evidence it actually contains.
- OMH cannot grant capabilities or cross trust zones.
- Station does not patch Hermes core to integrate OMH.
- stable Station releases pin/verify optional adapter compatibility before client rollout.
