# Memory Provider Architecture

## Goal

Build:

```text
agentik-memory
```

as an external Hermes Memory Provider.

## Namespaces

At minimum:

```text
organization
project
os
mission
person
```

## Metadata

```yaml
organization_id:
project_id:
os_id:
mission_id:
actor_id:
role:
memory_type:
source:
confidence:
sensitivity:
created_at:
expires_at:
```

## Write flow

Do not give all subagents unrestricted permanent write access.

Preferred:

```text
Subagent finding
→ memory candidate
→ Nano Director / curator
→ deduplicate
→ validate source
→ classify
→ persist
```

## Memory vs Notion

Memory:
- compact recall
- semantic context
- entities
- decisions
- lessons
- preferences
- machine-oriented

Notion:
- docs
- architecture
- SOP
- research
- meeting notes
- human-readable decisions
- runbooks

## Isolation

Operator private Life memory should not automatically be visible to Business or clients.

Client memory never crosses organizations except through explicit contracts / sanitized summaries.

## Self-improvement governance

Hermes' native learning loop is the default implementation for agent self-improvement. Agentik wraps it with promotion policy: local low-risk memories may be accepted automatically, but shared skills require eval/review and security/policy/capability changes must never self-promote.

See `14_ENGINEERING/09_SELF_IMPROVING_AGENTS.md`.
