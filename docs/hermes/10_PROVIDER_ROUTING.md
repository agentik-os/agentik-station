# Provider Pools and Model Routing

## Goal

Do not use the most expensive / strongest model for every action.

Use the right model for the role.

## Suggested routing

```text
Oracle / Executive
→ strongest reasoning model

Nano Director
→ strong reasoning model

Architecture / Security / Reviewer
→ strong independent reasoning model

Engineer
→ strong coding model

QA
→ independent cost-efficient model

Knowledge / summaries / classification
→ cheaper model
```

## Credential pools

Credential pool:
- multiple credentials for the same provider
- useful for quota / rate-limit continuity

## Fallback providers

Fallback provider:
- switch provider when primary becomes unavailable

These are different mechanisms.

## Mission override

A specific difficult Kanban task may override the model without changing the entire Director profile.

## Policy

Model routing should consider:

```text
role
task criticality
privacy
cost
latency
required tool compatibility
```

Do not hardcode one provider as the architecture.

## Model-Agnostic Coding rule

AGK OS manifests should reference route aliases/capability classes rather than hard-code one model. Hermes resolves those aliases to provider:model selections and fallback chains. Critical critic routes should preferably differ from implementer routes when practical, while deterministic tests remain the primary truth source.

See `14_ENGINEERING/08_MODEL_AGNOSTIC_CODING.md`.
