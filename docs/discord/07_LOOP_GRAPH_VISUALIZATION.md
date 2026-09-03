# Loop-Graph Visualization in Discord

The visible plan is a projection of the durable mission graph.

## Node states

```text
pending | ready | running | blocked | verifying | done | failed | skipped
```

## Loop state

Every bounded loop records:
- loop id;
- purpose;
- current round;
- max rounds;
- exit condition;
- last failure reason;
- escalation rule.

## Discord projection

The card shows only the most useful 5–10 plan nodes. Larger graphs use:

1. a compact current-path summary in Discord;
2. `/graph` for an attached Mermaid/structured graph artifact;
3. `Open Graph` for Agentik React Flow when the UI is available.

Do not turn a 40-node DAG into an unreadable Discord message.
