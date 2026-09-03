# Builder OS — Canonical System OS

Builder OS is a mandatory **system OS** in every Agentik development Node. It is the factory, upgrader and contract enforcer for all other Operative Systems.

Builder OS itself MUST satisfy the AGK OS Contract. It is not a privileged exception.

## Canonical purpose

Builder converts a domain mission into a versioned, installable, testable, recoverable Agentik OS that compiles onto Hermes primitives without rebuilding Hermes.

```text
Intent / OS Theme
  -> Librarian deep research
  -> 15-input Builder handoff
  -> Owner gates
  -> Contract/spec
  -> RED acceptance tests
  -> Build
  -> Hermes compilation
  -> Gauntlet + Verification Engineering
  -> Package + Doctor + Rollback + Recovery
  -> Dedicated Discord Nano Director Bot
  -> Fresh-session acceptance
  -> Registry release
  -> Evidence bundle
  -> Learning candidate
```

## Default NanoTeam

- `master-os-builder` — Nano Director / dedicated Hermes Bot profile
- `domain-scout` — domain research and source quality
- `specification-reviewer` — contract and acceptance review
- `test-engineer` — tests, evals, fresh-session acceptance
- `recovery-auditor` — doctor, rollback and recovery rehearsal
- `security-reviewer` — capabilities, secrets and trust-boundary review
- `discord-provisioner` — dedicated bot/channel/command provisioning and readback

Short-lived research or code exploration stays `delegate_task`; durable cross-role work is Kanban.

## Mandatory dependencies

- Hermes pinned in `agentik.lock`
- Librarian OS/capability
- DevOps OS / Engineering Harness
- Ponytail plugin for Builder coding paths
- Git + registry access
- Discord provisioning capability
- Evidence store

Builder never owns client secrets in its package. Secrets are bound after install through the Node credential layer.
