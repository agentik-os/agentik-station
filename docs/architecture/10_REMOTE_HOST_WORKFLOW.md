# Remote Host workflow

Register placement metadata:

```bash
sudo station host register --id moonbase-prod-01 --role client --tailscale-name moonbase-prod-01
```

Bootstrap the same repository on a remote Tailscale/SSH Host:

```bash
station host bootstrap --target operator@moonbase-prod-01 --id moonbase-prod-01 --role client --zone-category CLIENTS --zone-name moonbase --env production --organization moonbase --project platform --plan
station host bootstrap --target operator@moonbase-prod-01 --id moonbase-prod-01 --role client --zone-category CLIENTS --zone-name moonbase --env production --organization moonbase --project platform
```

Create remote desired state from the Gareth Control Plane:

```bash
sudo station zone create --category CLIENTS --name moonbase --env production --host moonbase-prod-01 --organization moonbase
```

A remote Zone is not materialized locally. Control records desired placement; actual application occurs on the target Host.
