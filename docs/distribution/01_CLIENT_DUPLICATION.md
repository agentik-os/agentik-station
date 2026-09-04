# Client Duplication

## Goal

Installing a new client means applying a reproducible organization package, not cloning Operator's mutable VPS.

## Flow

```text
Fresh VPS
→ install Agentik Node
→ organization init
→ apply organization.yaml
→ connect external secret source
→ install OSs
→ install Directors/profiles
→ create Projects/Boards
→ Node READY_UNBOUND
→ connect client's Discord
→ Bootstrap Director inventories server
→ compile client-specific Discord desired state
→ plan/apply/adopt
→ bind teams to channels
→ remove Administrator
→ connect GitHub/Linear/Notion as configured
→ doctor
→ E2E
→ OPERATIONAL
```

## Client config repository

Each client gets a secret-free config repo containing:
- organization model
- installed OS list/versions
- desired Discord surfaces
- team bindings
- capability policies
- project/board declarations

Actual Discord IDs may live in backed-up runtime state rather than the distributable template.

## Existing client Discord

Use `adopt-and-extend` by default. Do not reset the client's server.

## Offboarding

Client can receive:
- config repo
- OS/version manifest
- state backup
- Discord binding export
- recovery instructions

without receiving Operator credentials, other client data or Operator memory.
