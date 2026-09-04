# Changelog

## Unreleased — governed Strix and deep Station audit (2026-09-05)

- integrate pinned Strix 1.6.1 as a subordinate tool of the existing Hermes DevOps
  team, with reviewed local snapshots, separate human approval, disposable LAB
  execution, dedicated protected-key setup, bounded evidence and cleanup;
- fix profile YAML/identity/cwd, distribution-owned assets, privileged publication,
  Zone ancestor traversal and inherited cross-identity environments;
- fix false-success Hermes update receipts and Tailscale readiness;
- prepare verified ScrapeGraphAI tokenizer assets; put DNS under the worker
  deadline and validate actual offline graph execution;
- document nine repaired defects, eleven remaining decisions and explicit external
  acceptance gates. A new immutable release ID/profile migration is still required
  before upgrading an already installed 11.12 Host.

## 11.12 — DevOps delivery and supply-chain completion

- made the DevOps OS machine-semantic with six canonical identities, typed
  tools/provider routes, a closed workflow, deterministic validators, 15
  source-mapped Librarian inputs, 12 adversarial evals and checksum-bound recovery;
- added tracker-neutral delivery semantics, soft autonomy, five-field Blocked
  records, idempotent material comments, exact PR/head approvals and separate
  signed engineering/production authorization receipts;
- added authenticated Discord batch-start handling with one issue thread per
  authorized ready item and preserved correction context;
- added the client `operations.yaml` contract for services, reliability,
  incidents, backups, dependencies, costs, access, offboarding, ADRs and runbooks;
- exposed the AGK client controller through `station client`;
- integrated Zone-scoped Composio Discord plan/link/readback with default-deny
  tool execution while keeping Hermes as the only messaging Gateway;
- pinned and installed discord.js 14.27.0 as an isolated SDK resource;
- added CODEOWNERS, Dependabot, Python compatibility, Node build tests,
  disposable Ubuntu acceptance, deterministic CycloneDX SBOM, SHA-256 source
  provenance and GitHub build attestation;
- fixed the release-manifest schema/CI omission for the shipped AGK-TUI suite.
- added default Zone-local ScrapeGraphAI 2.2.2 with Playwright Chromium 1.62.0 and the bounded Hermes `station_scrapegraph` tool; URLs, credentials, timeout and output policy are enforced before execution.

## 11.12 — Station Kernel hardening

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

### Current scope

The release installs and verifies the safe Station Linux foundation only. Hermes compilation, Discord transport, Composio runtime, per-Zone rootless services, complete OS Factory acceptance, Node Agent Fleet reconciliation, and encrypted off-Host recovery remain explicit subsequent releases/gates.

## 11.12

- made the canonical repository fully generic: real organization/project/operator names removed from active docs, tests, examples and historical text;
- removed the opaque v9 snapshot archive that still contained organization-specific historical identities;
- integrated Librarian OS v3.0.0 Universal Knowledge as the canonical Librarian source;
- expanded deterministic Librarian factory helpers to expose the v3 research surface while keeping actual research inside the Librarian OS/Hermes runtime;
- added `station spec` for validated InstallSpec generation;
- added `station.sh`, a thin one-command Bash orchestration wrapper for repo Doctor → InstallSpec → plan → apply → full Doctor → status → setup gates;
- preserved Evidence Before Claims: external Hermes/Discord/Composio/Fleet/restore acceptance remains explicitly pending until observed.
