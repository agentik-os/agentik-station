# Agentik Station 11.12 Validation

Release claim: **READY_FOR_SETUP**. This is not a production OPERATIONAL claim.

Locally verified release gates:

- 109 Station tests PASS;
- 7/7 Builder/Librarian deterministic gates PASS;

- repository Doctor;
- unit/security/contract/install test suite;
- full/core and team desired-state plans;
- Bash syntax for `station.sh` and `bootstrap.sh`;
- dedicated `agk-station` account bootstrap contract;
- pinned operator-toolchain and checksum/integrity contract;
- queryable pinned resource catalog and idempotent multi-executor Station rules;
- Hermes release-commit pin, backup/Doctor update wrapper and receipt contract;
- Zone-isolated Hermes gateway argv/alias contract;
- case-insensitive repository path portability;
- `ORGANIZATIONS` category and team member contract;
- no real-person/client/project names in the packaged source;
- six canonical AGK OS source Doctors;
- Librarian v3 canonical source and Hermes compiler path;
- release manifest / file inventory readback;
- ZIP integrity and extracted-repository Doctor.

External gates still required before OPERATIONAL: fresh VPS installation, Hermes setup/provider chat, Hermes gateway/plugin Doctor, Discord test-guild readback, Composio OAuth/MCP readback, Tailscale enrollment, off-Host backup and destructive restore rehearsal.
