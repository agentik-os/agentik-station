# Agentik Station 11.12 — Final Release Validation

**Release:** `11.12`  
**Posture:** final repository candidate / private alpha  
**Maximum verified local claim:** `READY_FOR_SETUP`  
**External production acceptance:** pending on real infrastructure

## What 11.12 proves in the release workspace

- canonical Host / Control Plane / Zone / Project / OS / Workspace / Fleet architecture;
- generic repository: no real client, personal project, or operator-specific names in active or archived text;
- no embedded historical ZIP containing real client identities;
- one canonical editable OS source tree under `os/`;
- Librarian OS v3.0.0 Universal Knowledge integrated as the canonical Librarian source;
- Builder ↔ Librarian mandatory handoff, including `/book`, `/bestseller`, web/current/expert/canonical/contrarian/triangulation lanes;
- typed `InstallSpec` used by plan and apply;
- `station spec` for deterministic InstallSpec generation;
- `station.sh` thin Bash orchestration wrapper using the same typed kernel;
- root-path confinement, traversal rejection, symlink refusal, atomic managed-file writes, and safe remote argument transport;
- correct Zone and Project ownership contracts;
- immutable Station release layout and operation receipts;
- AGK OS v2 Doctors for canonical OS sources;
- OS → Hermes Profile Distribution compiler present and contract-tested;
- Discord, Composio, rootless runtime, backup/recovery, Hermes update, and Fleet adapters remain evidence-gated rather than overclaimed.

## Automated validation

- Main pytest suite: **87 passed**.
- Factory deterministic gates: **7/7 passed**.
- Repository Doctor: **PASS** after final manifest regeneration.
- Python source compilation/parsing: **PASS**.
- JSON/YAML parsing: **PASS**.
- Generic-name scan: **PASS** for real organization/project/operator names.
- Repository symlink scan: **PASS**.
- Generated cache scan: **PASS**.
- Release ZIP integrity: required before publication.

## Evidence ladder

Station never collapses these states:

```text
PREPARED
→ OBSERVED
→ REPORTED
→ VERIFIED
→ READ_BACK
→ ACCEPTED
```

`READY_FOR_SETUP` therefore means the Station kernel and repository contracts are verified locally. It does not mean that external providers or production operations have passed live acceptance.

## External gates still required

Before claiming a production Station `OPERATIONAL`, perform and retain evidence for:

1. fresh supported Ubuntu/Debian VPS install with actual root identities and permissions;
2. reboot and post-reboot full Doctor;
3. Tailscale enrollment and remote identity/readback;
4. Hermes installation, Zone-local HERMES_HOME, profile distributions, gateways, boards and plugin Doctor;
5. Ponytail registration in Builder/DevOps profiles;
6. dedicated Discord bot enrollment, Components V2 progress card, interactions and test-guild readback;
7. Composio scoped principal, connected-account, session/MCP and revocation tests;
8. rootless cross-Zone negative tests;
9. encrypted off-Host backup plus clean restore rehearsal;
10. fresh-session OS mission, rollback and recovery acceptance.

No document in 11.12 may claim those gates passed until they are actually observed.
