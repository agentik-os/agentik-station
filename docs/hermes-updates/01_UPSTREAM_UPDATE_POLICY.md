# Hermes Upstream Update Policy

Station watches upstream when its discovery timers are enabled and uses
reviewed release rings. Discovery is not automatic promotion.

The supported Station discovery interface is `station hermes check` and
`station update plan/check`. It reads source identity and public upstream
metadata without invoking the native updater or importing a real profile.
Git and immutable/non-Git distributions are both recognized; unavailable
provenance stays explicit. Native Hermes updater options and backup formats
depend on its version and are not Station's automated deployment contract.
See [coordinated updates](../operations/COORDINATED_UPDATES.md) for npm software
migration, immutable Host releases, persistence review and recovery boundaries.

## Rings

```text
UPSTREAM main
    ↓ read-only discovery (enabled watcher/timer)
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

The rings above define acceptance policy, not an implemented unattended fleet
promotion service. A successful metadata check cannot accept a new runtime,
database schema, OS profile, account or gateway.
