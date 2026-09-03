# Control / Bootstrap OS

This is a **system OS**, not a normal marketplace business OS.

## Purpose

Own installation finalization and organization cockpit reconciliation.

## Director

```text
discord-bootstrap-director
```

## Responsibilities

```text
read organization desired state
read installed OS surface manifests
inspect Discord guild
plan safe reconciliation
apply allowed changes
bind Discord IDs to teams/profiles/projects/boards
verify routing
remove bootstrap Administrator privilege
emit evidence
```

## Runtime mode

After bootstrap, this OS remains installed for:
- drift detection
- explicit reconciliation
- adding new OS surfaces
- organization migrations

But its privileged apply capability stays disabled/approval-gated outside an authorized maintenance window.

## Not allowed

It is not allowed to:
- become a generic root shell agent
- inspect unrelated client Nodes
- access arbitrary business data
- retain permanent Discord Administrator simply for convenience
