# Station Orchestration Contract v1

Station orchestration is the governed path from ambiguous human intent to verified operational outcome.

It is **not** a second agent runtime. Hermes remains the runtime. Station supplies mission semantics, capability routing, evidence boundaries, ownership, quality gates and the projection humans see in Discord/Agentik.

## Canonical mission path

```text
INTENT
  ↓
CLARIFY
  ↓
GOAL + CONSTRAINTS + ACCEPTANCE
  ↓
CAPABILITY / CONNECTOR READINESS
  ↓
PLAN + LOOP-GRAPH + OWNERS
  ↓
PREPARED
  ↓
EXECUTE / OBSERVE
  ↓
REPORTED RESULT
  ↓
VERIFY
  ↓
QUALITY / SAFETY / READBACK GATES
  ↓
ACCEPT
  ↓
REMEMBER / OPERATE
```

## Seven capability lanes

Every mission activates one or more lanes:

1. **Clarify and Plan**
2. **Build with Leverage**
3. **Research and Learn**
4. **Code and Ship Safely**
5. **Create Polished Deliverables**
6. **Remember and Operate**
7. **Connect with Clear Boundaries**

The lanes are composable. A website launch can activate all seven; a simple research request may activate only Clarify/Plan + Research/Learn.

## Non-negotiable invariants

- a plan is intent, not execution evidence;
- an executor saying “done” is not verification;
- “running” requires a runtime observation;
- “verified” requires a test/review/CI/render/readback gate appropriate to the claim;
- ownership is explicit on every durable graph node;
- tool/connector availability is probed before the plan depends on it;
- source freshness and quality are explicit for research claims;
- external writes and trust-zone crossings stay behind capability/approval policy;
- parallelism is used only when ownership, isolation and fan-in are explicit;
- blocked/degraded work always exposes the next repair action.
