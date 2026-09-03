# Discord Provisioner Contract

## Interface

Conceptual operations:

```text
inspect(guild_id) -> CurrentGuildState
compile(org, os_registry, policies) -> DesiredGuildState
plan(current, desired) -> ProvisionPlan
apply(plan, policy) -> ApplyResult
verify(desired, bindings) -> VerificationReport
demote() -> RuntimePermissionReport
reconcile() -> ReconcileReport
```

## Plan operation types

```text
CREATE_ROLE
ADOPT_ROLE
UPDATE_ROLE
MOVE_ROLE
CREATE_CATEGORY
ADOPT_CATEGORY
UPDATE_CATEGORY
CREATE_CHANNEL
ADOPT_CHANNEL
UPDATE_CHANNEL
SET_PERMISSION_OVERWRITE
WRITE_BINDING
WARN_CONFLICT
BLOCK_DESTRUCTIVE
```

## Managed identity

Resources created by Agentik should be traceable through stored IDs and state metadata. Do not depend on naming prefixes alone.

## Idempotency

Given the same desired state and unchanged guild, a second plan after successful apply must converge to no-op.

## Partial failure

- record completed operations
- stop on unsafe dependency failure
- rerun from observed state, not from assumptions
- never fake transactionality across Discord API calls
- emit recoverable plan/evidence
