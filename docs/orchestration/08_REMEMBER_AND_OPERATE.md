# Remember and Operate

## Review-first memory

Mission logs are not automatically memory.

After verified completion:

```text
raw events
→ candidate lessons
→ durable/reusable?
→ scope selection
→ conflict check
→ review/promotion
→ memory / Skill / runbook update
```

Reject:
- transient debug state;
- secrets;
- unverified assumptions;
- one-off identifiers unless operationally required;
- client knowledge outside its namespace.

## Operational readiness

Every persistent service/OS exposes:
- health status;
- last Doctor result;
- dependency readiness;
- backup/recovery posture;
- degraded reason;
- next repair action;
- owner.

A degraded service is not described as healthy because the process is running.
