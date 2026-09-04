# Hermes Upstream Update Policy

Station **always watches** Hermes upstream but uses release rings.

Hermes currently provides supported update primitives including:
- `hermes update --check`;
- `hermes update --plan`;
- `hermes update --branch <name>`;
- quick/full pre-update snapshots/backups;
- `~/.hermes/logs/update.log`;
- machine-readable update receipts under `~/.hermes/logs/update_receipts/`;
- `hermes config check` / `hermes config migrate`;
- gateway restart and post-update fleet-version verification;
- `hermes doctor`.

## Rings

```text
UPSTREAM main
    ↓ check every 6h
LAB / edge
    ↓ full regression
OPERATOR candidate
    ↓ burn-in + acceptance
STABLE Station release
    ↓ explicit policy/maintenance window
CLIENT stable Nodes
```

## Rule

**Never run blind `/update` on a organization production bot as the normal fleet strategy.** `/update` is useful operationally, but Station promotion must preserve reproducibility and evidence.
