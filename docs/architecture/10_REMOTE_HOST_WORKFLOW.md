# Remote Host workflow

Register placement metadata:

```bash
sudo station host register --id organization-alpha-prod-01 --role team --tailscale-name organization-alpha-prod-01
```

Bootstrap the same repository on a remote Tailscale/SSH Host:

```bash
station host bootstrap --target operator@organization-alpha-prod-01 --id organization-alpha-prod-01 --role team --zone-category ORGANIZATIONS --zone-name organization-alpha --env production --organization organization-alpha --project platform --plan
station host bootstrap --target operator@organization-alpha-prod-01 --id organization-alpha-prod-01 --role team --zone-category ORGANIZATIONS --zone-name organization-alpha --env production --organization organization-alpha --project platform
```

Create remote desired state from the Operator Control Plane:

```bash
sudo station zone create --category ORGANIZATIONS --name organization-alpha --env production --host organization-alpha-prod-01 --organization organization-alpha
```

A remote Zone is not materialized locally. Control records desired placement; actual application occurs on the target Host.
