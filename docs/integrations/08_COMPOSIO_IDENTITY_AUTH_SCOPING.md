# Composio Identity, Auth and Connected-Account Scoping

## Stable subject mapping

Composio sessions are user-scoped. Station therefore maintains a stable opaque `principal_id` and maps it to the Composio user identifier.

```text
Station principal registry
  organization_id
  principal_id        # stable opaque ID; never an email
  principal_type      # human | service | OS
        ↓
Composio user ID
        ↓
connected accounts
```

Never use `default` in production.

## Personal vs company

```text
personal/private OS
  -> personal principal
  -> personal connected-account references only

company/client OS
  -> company/client principal or service principal
  -> company connected-account references only
```

No agent may infer that a personal connection can be used for a company mission or vice versa.

## Client isolation

Client Zones keep separate Composio principals and connected-account bindings regardless of whether the Zone is placed locally or on a remote Host. Production may run on a dedicated Node; development may run locally. Never reuse principal IDs or connected-account bindings across client Zones.

## Package rule

The immutable OS package may contain:
- required toolkit names;
- allowed tool names/tags;
- auth configuration references;
- account-selection policy;
- scopes/approval requirements.

It must never contain OAuth tokens, live account credentials, user emails as identity keys, or a hard-coded cross-client connected-account ID.
