# Control Plane and Fleet

Control contains desired state and metadata:

```text
registry/hosts
registry/zones
registry/projects
registry/os
bindings
fleet/deployments
fleet/health
fleet/releases
policies
evidence index
```

Control does not mirror all client memory, raw documents or production credentials.

Remote Host operations must be explicit and auditable. Tailscale/private networking is the preferred transport boundary.
