# Plan first — coordinated updates and historical installer feedback

## Baseline

Station 11.28 (`e033d10b5bcd2d931c649d8c38d4765c1a70003e`) is published
on main and installed on the existing Host. The software inventory, independent
installer aggregation, blocked Ponytail gate, Zone traversal and legitimate
systemd links are handled separately from service/account readiness. Existing
Host identities, credentials and live workloads must remain intact.

The additional request concerns ALL reviewed upstream dependencies and npm
upgrades, not merely updating a command package. Current source still has a
native Git-only Hermes update watcher and no Workstation release migration.
Never label a package-manager update as an installed-runtime upgrade.

## Intended sequence and boundaries

1. Verify each historical complaint against actual current source and regression
   tests. Fix remaining defects; retain useful safety constraints.
2. Make update discovery exhaustive over the delivered lockfiles, source pins,
   SDKs, server images and vendored components. A new upstream version is a
   proposal, not evidence of compatibility or authorization to deploy it.
3. Add account-free update planning for Git and immutable/tarball Hermes
   installations. Do not run native update commands inside real profile state
   for a read-only check. Preserve unknown provenance as unverified.
4. Distinguish recorded kernel state, current software verification, configuration,
   and live operational acceptance in status output.
5. Implement npm-owned runtime update mechanics only with a validated predecessor,
   explicit scope, preserved projects/accounts, versioned recovery evidence,
   inactive owned services/sessions, and failed-update recovery. Never move a
   completed virtual environment to a different path, silently adopt modified
   software, or overwrite external service/account configuration.
6. Changes to upstream pins require coupled source/adapter/SDK/lockfile updates,
   security review and native compatibility gates before publishing on main.
   No unconditional `git pull`, global latest upgrade, scanner bypass or
   automatic cross-profile enrollment. Project stacks remain Project-owned.
7. Test each new transition (including interruption and refusal), regenerate
   metadata, publish a new immutable Station release, then perform targeted Host
   readback. Never mutate the already published 11.28 release in place.

## Verification ownership and limitations

The root agent owns implementation and final native verification. Earlier
delegated audits were quota-blocked and were not counted as review evidence.
Two later bounded reviews did complete: npm recovery/concurrency/baseline
validation, and account-free upstream discovery/record ancestry. Their concrete
findings were corrected and received regression tests; this is not a claim of
an exhaustive independent security audit.

Installing new application images does not authorize migrations, demo seeding,
public listeners or selection of a client/profile's memory account. Report each
pending activation or migration explicitly. The known Ponytail security block
remains a required incomplete gate.

## Historical feedback disposition

| Reported problem | Current source / observed disposition |
| --- | --- |
| Caller cwd causes `uv.toml` lookup outside operator HOME | Fixed in 11.28 dependency/toolchain operator wrappers; legacy Hermes helper now also changes cwd in a subshell. |
| npm/npx `EEXIST` on self-upgrade | Existing reviewed launcher transaction temporarily handles only owned known launchers, then publishes/restores them; no `--force` over arbitrary files. Retain its adversarial tests. |
| `hermes version` rather than `--version` | Toolchain already uses the isolated exact `--version` probe; retained tests cover native output and private-HOME behavior. |
| Git-only `station hermes check` | Replaced by account-free public metadata and source-identity observations. Non-Git source is explicit, with unknown provenance when not verifiable. No native `update --plan` is invented. |
| `deps install --all` stops at Ponytail | 11.28 independent subprocess batch completed 13/14 installers on the Host; later components ran after the rejected plugin. |
| Static `runtime=NOT_CONFIGURED` obscures installed software | Recorded kernel state is labelled; `status --software` runs the authoritative current native inventory. Configuration and live acceptance are not inferred. |
| Zone parent traversal denied | Live `/var/lib/station` is `0711`; `z-system-discord` read its own `.env` and imported actual Hermes clients after 11.28 deployment. No group broadening. |
| Legitimate systemd enablement link rejected | Existing constrained link rule retained; the post-deployment full Doctor passed with native Zone links intact. |

## Prior release acceptance retained

11.28 is published on main at `e033d10b5bcd2d931c649d8c38d4765c1a70003e`.
All nine GitHub CI jobs passed. The Host is on immutable 11.28; final native
software readback verified 17/18 requirements, with only Ponytail blocked.
The four application bundles have 20 verified image entries (19 unique images),
not activated application accounts. Three known AGK 11.25 controls were updated
after backing up all eight reviewed software targets. All 17 protected file
fingerprints remained unchanged. Evidence is retained under
`/var/backups/station/repair-11.28-20260905/` on the Host.

11.29 adds a software update mechanism; it does not claim a legacy Workstation
was migrated, a newer upstream runtime was accepted, or an npm package was
published. Native installation/update-lifecycle acceptance, CI and immutable
Host deployment must be recorded separately before declaring those gates passed.

## 11.29 local acceptance

- Final complete Station/Factory suite: 1,874 passed, 21 Linux-only cases skipped
  on macOS. Repository Doctor and deterministic release metadata passed.
- Full npm regression suite: 203 passed, including concurrent recovery,
  corrupted/misbound baselines, pending-journal rechecks and nonblocking FIFO
  evidence rejection. The packed consumer smoke test is a separate gate.
- Fresh packed native macOS installation: 21 required software checks passed,
  native service/MCP templates, TUI views and synthetic session lifecycle passed;
  all 14 monitored personal-file fingerprints were unchanged.
- Native macOS software migration passed from label 11.29 to a **synthetic**
  11.30 using the same reviewed upstream pins. Seven software roots were backed
  up/rebuilt at their final paths, native verification and protected in-root
  configuration comparison passed. No service was activated. This is lifecycle
  acceptance, not acceptance of a new upstream version or a legacy installation.
  The subsequent CI harness also fingerprints external personal files across
  updates; that extra check was added after this macOS migration run.
- Live read-only upstream discovery accounted for 186 component rows and all
  87 lock pins: 162 observations, 23 explicit manual-review rows and one missing
  release endpoint. Collection succeeded; complete automatic discovery and
  compatibility acceptance remained false. Client/server versions are separate.
- Native Linux installation/update lifecycle and immutable Host rollout remain
  post-publication gates, not inferred from the macOS run.

## 11.29 Host readback and 11.30 corrective plan

The published 11.29 release (`e7a42c8521025ec729cb6fd3d26b4b9f0552f253`)
was applied as a new immutable Host kernel, not a bootstrap replay. Full Doctor
passed 192 checks; native software verified 17/18 requirements with only the
known Ponytail security block. Root's account-free Hermes check passed, and the
actual weekly coupled-discovery oneshot completed with exit 0.

The separate `station-system` watcher failed its actual systemd test:
`SafeFS._ensure_anchor` opens each ancestor with `O_RDONLY|O_DIRECTORY`.
`/var/lib/station` is intentionally traverse-only (`0711`) to that identity, so
its private receipt could not be written even though ordinary path traversal
worked. Earlier mocked/temp-fixture checks had not reproduced this ownership
combination. This is a repository defect, not a Discord-token error.

Correct it in a **new immutable 11.30**, retaining the published 11.29 evidence:

1. Preserve all Zone permissions and global SafeFS behavior.
2. After strict ancestry checks, let the non-root watcher open its own private
   parent directly, verify directory identity/mode and write only an exclusive
   private receipt through held no-follow directory descriptors.
3. Test execute-only ancestors, wrong owner/modes, symlinks and collisions.
4. Run the candidate as the real watcher UID, then the actual hardened systemd
   oneshot after deployment. Keep its timer disabled if it was disabled.
5. Recheck Doctor/software and all 17 protected fingerprints. No native Hermes
   update, profile enrollment or permission widening is authorized by this fix.
