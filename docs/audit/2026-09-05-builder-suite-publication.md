# Canonical Builder suite publication and runtime selection

## Objective and scope

Publish `agentik-os/agk-builder-os` as a complete generated snapshot of Station's
canonical Builder, Librarian and Stepper packages. Station remains the only
editable canonical OS source. Included packages retain separate Directors,
profiles, credentials and runtime identities. Correct stale/legacy Builder
selection and verify the actual selected Moonbase instance against Station.

Baseline: Station `fca214f` / 11.34; external Builder repository `1a1ee047`.
Current canonical packages: Builder 11.14, Librarian 3.0.1, Stepper 0.2.0.
The external repository advertises older Builder 0.5.0 and Librarian 2.2.2.

## Plan First

```text
read canonical contracts + external repository + native metadata
├── generated suite/export/provenance → verify exact three-package snapshot
├── Station resolver/execution → distinguish current and installed versions
└── AGK routing → canonical scoped instance, never implicit legacy fallback
    ↓
independent review + regression + full tests + deterministic metadata
    ↓
publish Station main → generate pinned external snapshot → verify/publish main
    ↓
immutable Moonbase kernel update + existing-team/version/route readback
    ↓
protected configuration/service comparison + CI + honest acceptance report
```

Main owns distribution/publication, global docs/version metadata and native VPS
acceptance. A dedicated worker owns discovery/CLI guards and another owns AGK
canonical routing; main independently reviews their changes. The external
repository workspace is explicitly designated as
`/Users/hacker/workspace/agentik/projects/agk-builder-os/repos/agk-builder-os`.
Preserve its existing history and unrelated assets; do not rewrite Git history.

## Constraints and acceptance

- Source snapshot records immutable Station commit, package versions and exact
  file hashes; it is not another hand-editable canonical tree or a live runtime.
- Compilation/install uses the pinned Station release and its complete support
  dependency closure. Do not mislabel raw OS sources as native Hermes profiles.
- Read-only resolution exposes drift; chat/service activation must not silently
  launch a different version or a legacy generic operator agent.
- Retain diagnostic/configuration/repair access and existing profile configuration.
- No silent credential copying, forced profile replacement, account enrollment,
  live model calls, bot activation or scanner bypass.
- If Moonbase already has the current OS versions and exact bundles, preserve
  them. Any genuine runtime migration requires inspected, recoverable evidence.
- Verify local suites, both repository publications, installed source/role/profile
  selection, native filesystem readback, Doctor and protected state independently.

## Reproduced findings

- `bind_instance` can present catalog Builder 11.14 beside installed 0.5.0 with
  the instruction to use that old profile when role sets match.
- Actual instance chat bypasses that discovery path; fixing display alone cannot
  guarantee current-source execution.
- AGK's general agent router and OS-view fallback still expose legacy
  `master-os-builder` paths. Those are not evidence of canonical Station instance
  selection and need scoped routing or an explicit non-executing repair response.

## Implementation and local acceptance

- Added a non-root, exact-commit exporter and standalone readback verifier. All
  three complete OS trees, package roles and provenance are included. Source
  validation, manifest consistency and runtime operation are separate claims.
- Exporter review found intermediate-directory races under permissive umask and
  malformed metadata shapes. Descriptor-relative creation, explicit type checks
  and negative tests address both findings.
- Discovery now distinguishes installed/current versions and roles. Stale chat
  and activation selection cannot silently launch the old instance; diagnostics
  and repair remain accessible. Source bytes are not claimed recompiled/compared
  during runtime selection: immutable bundle and native profile readback remain
  separate evidence.
- AGK aliases hand off to explicitly scoped Station resolution without executing
  a generic operator agent. Legacy Builder requires its explicit legacy alias.
  This is not a new privileged cross-UID launcher or a live model acceptance test.
- The dedicated-operator controls refresh checks all 12 software destinations
  before mutation and installs the two new helper dependencies first. Existing
  accounts and configuration are outside this update. Rust TUI rebuild/publication
  is a separate Host step, not implied by controls-only refresh.
- Local validation: 2,383 Station/Factory tests passed (23 Linux-only skips),
  529 AGK Python tests passed (two absent native-web-library skips), 115 Rust tests
  passed, Rust formatting passed, and all 263 npm tests passed. The 46 exporter
  tests include a complete real-source three-OS/29-role export and readback.

Published-commit CI, generated external repository verification and native Host
readback must be recorded separately after publication; no new OS package version
or forced profile migration is needed for unchanged canonical OS source trees.
