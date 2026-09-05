# Update Detection

Critical self-update detection is host-owned, not dependent on Hermes cron. If Hermes is unhealthy, the watchdog still needs to report drift.

Recommended systemd timer: every 6 hours.

```text
station-hermes-watch.timer
→ station hermes check --record
→ read local source identity as data (Git or non-Git)
→ query public upstream release metadata without profile access
→ write a private observation (not an applied update)
→ require Station compatibility/LAB promotion review
```

Detection is read-only. Mutation happens only in LAB promotion workflow.

The weekly compatibility-named `station-hermes-update.timer` additionally runs
`station update check` across the delivered SBOM and version lock. GitHub's
scheduled upstream-inventory workflow publishes the same kind of review artifact
without creating branches. No automated Maintainer mission dispatch or full
ring promotion is claimed by these commands. See
[coordinated updates](../operations/COORDINATED_UPDATES.md).
