# Bootstrap State Machine

```text
NEW
HOST_READY
HERMES_READY
ORG_READY
READY_UNBOUND
DISCORD_BOUND
BOOTSTRAP_PLANNED
BOOTSTRAP_APPLYING
DISCORD_PROVISIONED
BOOTSTRAP_VERIFIED
RUNTIME_SECURED
OPERATIONAL
DEGRADED
RECOVERY_REQUIRED
```

## Invariants

- `OPERATIONAL` requires `RUNTIME_SECURED`.
- `RUNTIME_SECURED` requires bot Administrator=false.
- `DISCORD_PROVISIONED` requires a binding registry for every managed/exposed OS surface.
- failed demotion transitions to `RECOVERY_REQUIRED`, not OPERATIONAL.
- unresolved sensitive routing transitions the mission to blocked/approval, never guessed execution.
