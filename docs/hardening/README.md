# v11 Hardening Program

v11 is the audit-response release that turns the previous architecture prototype into a typed, security-reviewed Station Kernel alpha.

## Fixed blockers

- root path traversal through Zone/Project identifiers;
- remote shell/SSH option injection;
- privileged symlink following and unsafe overwrite;
- root-owned Projects inside non-root Zones;
- inaccessible `station-system` runtime home;
- mutable release overwrite;
- duplicated desired-state sources;
- false OS/module installation claims;
- shallow module readiness based on file/binary presence;
- silent Hermes update checks;
- duplicate systemd sources and generated cache artifacts.

## Current acceptance boundary

The v11 release may claim `READY_FOR_SETUP` only after:

- typed desired state compiled;
- Station Kernel and FHS foundation reconciled;
- immutable release activated;
- Zone/Project layout and ownership reconciled;
- receipts and observed state written;
- full installed-Host Doctor passed.

It may not claim `OPERATIONAL` until external module setup, readback, fresh-session acceptance, and recovery rehearsal pass.

See the companion documents in this directory for implementation details and the release roadmap.
