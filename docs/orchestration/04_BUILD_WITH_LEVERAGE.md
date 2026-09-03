# Build with Leverage

The Station default is **reuse, compose, delete, then build**.

## Leverage scan

Before creating new architecture or code, the owner records which levels were checked:

1. Can the requested outcome be removed/simplified?
2. Does an installed OS already own it?
3. Does the repository already implement it?
4. Does Hermes now provide it natively?
5. Does the platform/stdlib provide it?
6. Is an installed dependency sufficient?
7. Is an existing Skill/program/workflow reusable?
8. Is MCP/Composio/direct API already bound safely?
9. Can a small adapter solve it?
10. Only then create a new subsystem.

## Leverage evidence

For medium/high engineering changes, the final report includes:

```text
Reused:
Removed/avoided:
New code introduced:
Why new code was necessary:
```

This keeps Station from accumulating duplicate infrastructure as Hermes and external tools improve.
