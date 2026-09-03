# Discord Drift Reconciliation

## Why

Humans will sometimes change roles/channels manually. The system must detect this without treating Discord as immutable infrastructure.

## State model

```text
desired state hash
current managed state hash
binding registry
last successful apply
```

## Drift classes

```text
SAFE
- description/topic changed
- optional resource missing

ROUTING
- bound channel deleted
- channel replaced without binding update

PERMISSION
- required runtime permission removed
- sensitive channel unexpectedly opened

STRUCTURAL
- managed category/channel moved/renamed

DESTRUCTIVE-CONFLICT
- desired change would delete/replace user-managed resource
```

## Reconcile

```text
detect
→ classify
→ plan
→ auto-apply safe class when policy permits
→ request approval for permission/destructive changes
→ verify
→ evidence
```

Never silently recreate a deleted sensitive channel and assume its old permissions are still correct; re-evaluate policy during reconciliation.
