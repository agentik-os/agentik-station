# Update Detection

Critical self-update detection is host-owned, not dependent on Hermes cron. If Hermes is unhealthy, the watchdog still needs to report drift.

Recommended systemd timer: every 6 hours.

```text
station-hermes-watch.timer
→ station_cli.py hermes-check
→ hermes update --check --branch main
→ hermes update --plan --branch main
→ compare edge checkout HEAD vs origin/main when available
→ write event JSON
→ dispatch Station Maintainer mission
```

Detection is read-only. Mutation happens only in LAB promotion workflow.
