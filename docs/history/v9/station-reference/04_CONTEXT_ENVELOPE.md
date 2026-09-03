# Station Context Envelope v7

Before any sensitive tool or connected-account action, Station resolves an explicit envelope:

```yaml
station_id: gareth-main
organization_id: gareth
trust_zone: agentik-dev
project_id: agentik-platform
os_id: devops-os
profile_id: forge
session_id: sess_...
mission_id: MIS-184
environment: staging
principal_id: principal_opaque_stable_id
capability_set:
  - github.read
  - github.write
credential_namespace:
  - gareth/agentik/staging
memory_namespace:
  - gareth/agentik/platform
allowed_roots:
  - /srv/agentik-dev/agentik-platform
integration_bindings:
  composio:
    subject_ref: principal_id
    session_ref: runtime_only
    connected_account_scope: organization
```

Unresolved security-critical context = deny, ask or re-route. Never guess the client, project, connected account, environment or credential namespace.
