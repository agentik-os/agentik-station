# Repository Bootstrap Contract

The Git repository is the executable source of truth for a Station installation.

## Fresh-host contract

```text
Fresh supported Linux host
→ install a trusted coding agent (optional but intended)
→ clone repository
→ agent reads AGENTS.md + ARCHITECTURE.md + INSTALL.md
→ ./station plan
→ sudo ./install
→ station doctor --full
→ READY_FOR_SETUP
→ SETUP.md
→ fresh-session acceptance
→ OPERATIONAL
```

## Separation of concerns

- repository: desired state, installer, runtime code, OS packages, contracts and documentation;
- `/etc/station`: installed configuration/policy;
- `/opt/station`: installed software/repository copy;
- `/srv/station`: human-operational Control/Zones/Shared/Archive;
- `/var/lib/station`: machine-owned state;
- credentials: enrolled after installation and never committed.

The installer must be idempotent and role-aware (`core`, `client`, `project`, `lab`, `worker`). A remote Host receives only the system foundation and the Zones appropriate to its role/desired state.
