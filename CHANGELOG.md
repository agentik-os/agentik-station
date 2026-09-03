# Changelog

## 0.2.0-alpha.11 — Station Kernel hardening

### Security and reconciliation

- replaced permissive identifiers with strict normalized ASCII contracts;
- blocked path traversal, shell syntax, option syntax, ambiguous Unicode, and category/environment mismatches before reconciliation;
- introduced descriptor-based `SafeFS` confinement, symlink refusal, atomic writes, strict tree copy/removal, and best-effort rollback journaling;
- made immutable versioned releases and atomic active-release switching the only software activation path;
- removed dynamic shell command construction from local and remote operations;
- changed remote bootstrap to normalized release archive + separate validated JSON `InstallSpec` with strict host-key checking by default;
- audited existing Unix identities, homes, shells, primary groups, and subordinate ID ranges;
- corrected Project ownership to the owning Zone identity;
- made installed Doctor recalculate every Zone and Project path before traversal and reject tampered desired-state records;
- validated desired OS declarations against the immutable release catalog and blocked false runtime claims;
- corrected Station system-state parent traversal/ownership rules;
- removed privileged unattended external network installers from the safe kernel.

### Truthful state and evidence

- introduced operation receipts and explicit `READY_FOR_SETUP` / `DEGRADED` states;
- separated design maturity from runtime readiness;
- replaced false OS install declarations with `DESIRED.json` entries in `NOT_INSTALLED` state;
- documented and enforced `prepared → observed → reported → verified → read_back → accepted`;
- added exact next repair actions to incomplete modules;
- marked remote bootstrap as transport/reported execution, not verified Fleet reconciliation.

### Architecture and repository

- retained Host + Control Plane + Universal Zones + Fleet as the canonical model;
- made `/etc/station` desired state, `/var/lib/station` observed/runtime state, `/srv/station` human-operational navigation, and `/opt/station/releases` immutable software;
- consolidated systemd into one source;
- removed duplicate Builder/Librarian toolchain copies while preserving canonical source and provenance;
- added the v11 Python package, typed configuration compiler, schema contracts, hardening documentation, professional audit, and adversarial test suites;
- preserved v9 architecture/history as non-canonical provenance.

### Release packaging fix (pre-publish)

- freeze immutable release trees **after** the atomic `os.replace` into `/opt/station/releases/<version>` so staging rename and failure cleanup work on Linux kernels that deny renaming mode-`0555` directories;
- ignore local packaging junk (`*.egg-info/`, `.venv/`) and exclude it from release tree copies.

### Current scope

The release installs and verifies the safe Station Linux foundation only. Hermes compilation, Discord transport, Composio runtime, per-Zone rootless services, complete OS Factory acceptance, Node Agent Fleet reconciliation, and encrypted off-Host recovery remain explicit subsequent releases/gates.
