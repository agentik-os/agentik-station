# AGK TUI and Station installation acceptance

## Plan First — scope and ownership

Requested outcome: exercise AGK's shipped feature surfaces, repair reproduced
defects in the source and Station installation, and simplify first Discord AI
Admin onboarding without weakening identity, credential or activation boundaries.
Baseline: Station 11.23, commit `8d6994ea329c348abea628311e9e20b1ec6863a1`.
The existing `/Users/hacker/agentik-station` checkout is the explicitly selected
local Project workspace for this mission; parallel owners use disjoint files.
The existing `moonbase@76.13.36.148` Host is in scope for bounded verification and
a reviewed immutable release update, not unrelated changes or credential copying.

```text
Inventory + source contracts + tool/Host availability
  |-- Terminal/session/provider controls (ponytail_guard_review)
  |-- Installer/legacy client/Fleet dashboard (voice_provider)
  |-- Discord onboarding and permission gates (voice_path_map)
  `-- Station integration + safe VPS readback (root)
           |
Reproduce defects -> focused fixes + negative regression tests
           |
Independent cross-review -> full tests + repo Doctor + release integrity
           |
New immutable release -> targeted AGK refresh -> VPS acceptance + readback
           |
Evidence matrix + explicit untested external gates + operator handoff
```

Root owns integration, public launcher, Station CLI wiring, release metadata,
this evidence record and deployment. Terminal owner owns `bin/`, `hermes/`,
`rmux/`, `scripts/agk_control.py`, provider/watchdog scripts and related tests.
Installer owner owns installer scripts, client controllers and Fleet dashboard
with their tests, excluding terminal-owned scripts. Discord owner proposes an
explicit file set before mutation; shared-file edits require coordination.
Root is verification owner for every branch; a separate branch reviews security
and integration-sensitive changes before release.

## Constraints and acceptance gates

- Preserve existing sessions, user edits, Zone/instance credentials and OS ledgers.
- Use synthetic private fixtures for lifecycle, delete, failure and attack tests;
  on the VPS only create and clean up explicitly named test sessions/artifacts.
- No real model requests, chat messages, OAuth enrollment, token rotation, gateway
  activation, port exposure or destructive operations on real user assets merely
  to fill a test matrix. Such gates remain unaccepted until explicitly exercised.
- Read-only Host discovery precedes any deployed change. Do not rerun full Host
  bootstrap to repair an AGK component or overwrite an immutable release.
- Reuse native Hermes setup and existing protected broker paths; Discord remains
  a control surface, not Linux sudo authority. Runtime Administrator is not a
  default, bots cannot mint other application tokens, and setup does not equal
  live bidirectional acceptance.
- Run component, Station, security, factory and dashboard tests appropriate to
  changes; verify a clean build and repo Doctor. Exercise installed PTY rendering,
  safe session lifecycle and Station acceptance after a deployment.
- Record observed results separately from mocks/fixtures and from external
  acceptance. Every failure must retain its evidence and next repair action.

## Execution evidence

Source branches are frozen for release 11.24. Confirmed defects were reproduced
before fixes, including lost Hermes profile on fork, archived restart visibility,
rename collisions, mixed logical-environment registry reads, login despite
`--no-login`, malformed inventories/watchdog/picker data, malformed Fleet URLs,
and model setup opening the full Hermes service-bearing wizard. The release also
adds an explicit static offline Doctor and fixes the shipped test runner so its
builds do not pollute a release tree. Default/full Doctor remains unchanged.

The installed 11.23 controller was tested on `capital` under UID `agk-station`
with a fresh fixture HOME/registry and a separate explicit RMUX socket. Creating
an explicit `/bin/cat` session, sending/reading a synthetic marker, renaming,
respawning and terminating/archiving passed. Restart then reproduced the hidden
archive defect. Only the synthetic session was purged and its private RMUX server
stopped; no existing session or provider was used. Fixture:
`/tmp/agk-1124-ajiz59xz` (synthetic metadata only).

The live Fleet dashboard is not installed on this Host; its tests/builds are
source verification, not a claim that a web service was deployed.

### Final source verification

| Surface | Observed result | Boundary |
| --- | --- | --- |
| Station + Factory | 1,503 passed, 15 skipped | Skips require real Linux process groups, not macOS |
| AGK Rust | 112 passed | Fresh locked/offline build; format and Clippy pass |
| AGK Python | 384 passed, 2 skipped | Optional real Crawl4AI/ScrapeGraphAI libraries absent locally |
| Fleet JavaScript | 24 passed | Includes malformed HTTP/WebSocket target regressions |
| Fleet TypeScript/build | Three typechecks, client/server builds, Node syntax pass | Not a deployed web service |
| Repository integrity | 85 Doctor checks, deterministic release metadata, diff hygiene pass | Source verification, not account acceptance |

The complete shipped component runner ran with `--offline` in a private copy;
no build output, cache, `node_modules` or `target` was added to the release tree.
An initial macOS Station test run used a new `/private/tmp` directory that
inherited group `wheel`; ownership fixtures correctly rejected it for the
`staff` test identity. Only the two newly created temporary parent directories
were assigned to the test identity's group. The complete rerun above passed;
production ownership checks were not weakened.

### Deployment and external acceptance boundary

The 11.24 source is verified for publication. Deployment must preserve the
immutable 11.23 rollback release and use the reviewed eight-file controls-only
refresh from the new immutable release, not repeat full bootstrap. Root-only
Host evidence and software backups are held in
`/var/backups/station/repair-11.24-20260905`; 17 existing protected files were
fingerprinted without printing or copying their contents. Two exact installed
Discord plugin directories and their two known-hash panel files were hardened
from `0775`/`0664` to `0755`/`0644`; no user credential or HOME mode was changed.

Post-publication gates are native isolated session restart/readback, ten TUI
views, three terminal sizes, public launcher/offline Doctor, full Host acceptance
and unchanged protected-file fingerprints. Their actual results belong to the
Host repair evidence; source test counts above do not predeclare their success.
The test-only RMUX socket/registry must never be replaced with the operator's
existing sessions. Live provider billing/authentication, Discord exchange,
gateway activation, guild provisioning and other external account enrollment
remain explicitly unaccepted by this mission's offline tests.
