# Tenancy and Boundaries — v6

## Operator-owned workloads

May share one physical VPS only when separated into explicit trust zones with separate Unix users/HERMES_HOME/storage/secret namespaces. Prompt/profile separation alone is insufficient for hard boundaries.

## Production clients

```text
1 client environment = 1 explicit Zone. Development may be local; production normally uses a dedicated Host/Node according to policy.
```

## Cross-zone/node communication

Allowed: typed capabilities, sanitized summaries, signed events, APIs, explicit file handoffs.  
Forbidden by default: shared `.env`, raw memory, shared writable home, unrestricted mounts, accidental credential inheritance.
