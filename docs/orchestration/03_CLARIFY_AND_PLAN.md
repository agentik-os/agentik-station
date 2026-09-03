# Clarify and Plan

## Ambiguity resolution

Every mission begins with a Mission Contract:

```yaml
objective: explicit outcome
scope:
  in: []
  out: []
constraints: []
assumptions: []
acceptance_criteria: []
risk_class: low|medium|high|critical
reversibility: reversible|costly|irreversible
required_capabilities: []
```

### When not to stop for a human

Proceed with explicit assumptions when all are true:
- action is reversible;
- no trust-zone/client/security boundary is crossed;
- no meaningful financial/legal/external-communication risk;
- acceptance can be verified objectively.

### When to gate

Require human/owner input when ambiguity affects:
- identity/account/recipient;
- irreversible deletion;
- production release with policy requirement;
- client boundary;
- secrets/permissions;
- high-impact public communication;
- a required success criterion that cannot be inferred.

## Plan object

A Plan is a versioned Loop-Graph, not prose alone. Every node declares:

```text
node_id
objective
type
owner
workspace / boundary
inputs
outputs
dependencies
verification
expected evidence
retry policy
```

The plan card is projected to Discord, but durable mission state belongs to Station/Hermes state.
