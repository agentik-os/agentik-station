# Credential Architecture

## Never

```text
.env
├── client A secrets
├── client B secrets
├── Gareth secrets
└── production everything
```

## Scope model

Credential resolution should consider:

```text
organization_id
profile_id
project_id
environment
capability
```

## Example

```text
organization = moonbase
profile = moonbase-devops
project = platform
environment = staging
capability = deployment.staging
```

returns only the staging deployment secret.

## Production

Production credentials should ideally be:
- separate
- short-lived where possible
- unavailable to normal research/QA agents
- auditable

## Client Node

On a dedicated client Node:
- credentials belong to client
- Agentik distribution contains references only
- offboarding does not require extracting Gareth's mixed secret store
