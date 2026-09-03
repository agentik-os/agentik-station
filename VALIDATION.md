# Agentik Station v11 Validation

**Release:** `0.2.0-alpha.11`  
**Posture:** safe-kernel alpha  
**Maximum verified base-install state:** `READY_FOR_SETUP`  
**Validation date:** 2026-09-03

## Verified in this release workspace

### Repository and contracts

- Repository Doctor: **PASS**.
- Canonical Station configuration and all referenced OS IDs: **PASS**.
- Module maturity catalog: **PASS**.
- AGK OS v2 package catalog and truthful `NOT_INSTALLED` runtime claims: **PASS**.
- Exact release manifest inventory: **PASS**.
- Canonical Zone terminology and simple `1…7` category numbering: **PASS**.
- No generated Python/test caches in the release tree: **PASS**.
- No repository symlinks: **PASS**.
- One canonical systemd source: **PASS**.

### Automated tests

- Station unit, contract, security, orchestration, and temp-root install tests: **71 passed**.
- OS Factory pytest tests: **4 passed**.
- Total pytest collection: **75 passed**.
- Deterministic Builder/Librarian release gates: **7/7 passed**.
- Preserved Builder/Librarian source-pack tests: **4 passed** and deterministic gates **7/7 passed**.

### Security regressions

The suite verifies rejection of:

- path traversal and separator injection;
- shell/option syntax and ambiguous Unicode identifiers;
- unknown JSON fields and string booleans;
- symlink ancestors, symlink destinations, and filesystem escape attempts;
- unsafe remote target/argument construction;
- tampered Zone roots before filesystem traversal;
- Project runtime-root drift;
- false OS runtime claims;
- malformed remote desired-state records;
- release-manifest inventory drift.

### Installation and state

Verified with isolated temp-root installations:

- Core Host layout with all seven Zone categories;
- Client Host layout with only System Zones plus the requested client Zone;
- Project ownership by the parent Zone identity;
- Zone and Project credential directory modes;
- separate human/runtime/Hermes state roots;
- immutable versioned release creation;
- atomic active-release and command pointers;
- idempotent reconciliation of identical release content;
- operation receipts and truthful `READY_FOR_SETUP` observed state;
- installed Doctor, including exact Zone/Project contract and path validation.

### Parsing and build hygiene

- Active Python source AST parsing: **PASS**.
- Active JSON parsing: **PASS**.
- Active YAML parsing: **PASS**.
- InstallSpec and release-manifest schemas: **PASS**.
- Core, Client, Project, Lab, and Worker plan compilation: **PASS**.
- Preserved v9 history archive integrity: **PASS**.
- Builder/Librarian source-pack archive integrity: **PASS**.

## Deliberately not claimed

This environment did not perform a privileged installation on an external fresh VPS. The following external acceptance evidence therefore remains pending:

- real supported Ubuntu/Debian Host install, reboot, and post-reboot Doctor;
- real Unix identities, subordinate IDs, systemd services, firewall, fail2ban, and rootless runtime negative tests;
- Hermes installation, Zone profile/distribution compilation, gateway/board/plugin Doctor, and mission execution;
- Ponytail registration inside Builder/DevOps profiles;
- Discord dedicated-bot enrollment, Components V2 transport, authorization, progress-message editing, and test-guild readback;
- Composio principal, connected-account, restricted-session, hosted-MCP, trigger, and revocation tests;
- Station Node Agent, remote reconciliation receipts, drift detection, and remote rollback;
- encrypted off-Host backup and destructive restore rehearsal;
- complete AGK OS v2 build → install → fresh-session → rollback → recovery acceptance.

Until those gates pass, v11 is suitable for private repository publication, code review, and disposable-VPS alpha testing. It is not a production client release.
