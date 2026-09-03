# Connect with Clear Boundaries

## Availability-before-dependency

A plan cannot depend on a connector merely because its name exists in configuration.

Station first resolves and probes:

```text
capability requested
→ adapter selected
→ tool/plugin/MCP/Composio/API present?
→ reachable?
→ authentication valid?
→ principal/account correct?
→ scope/capability allowed?
→ environment correct?
→ safe probe/readback succeeds?
→ READY
```

Possible readiness states:

```text
unknown
configured
available
authenticated
scoped
verified_ready
degraded
unavailable
```

Only `verified_ready` supports high-confidence execution planning. `available/authenticated/scoped` may be enough for low-risk read operations when policy permits.

## Boundary rule

Connector discovery never expands authority. A tool being discoverable through Composio, MCP or Hermes does not grant the current OS permission to use it.
