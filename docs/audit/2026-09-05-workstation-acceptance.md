# Workstation 11.26 — installation acceptance

Scope: the [portable mission](2026-09-05-portable-install-plan.md), repository
implementation, npm consumer package, personal macOS runtime and Linux CI gates.
No production VPS update, npm publication, account enrollment, real Discord bot
activation, paid model request or client/OS-instance deployment is claimed here.

## Reproduced defects and repairs

| Observed failure | Repair and regression gate |
| :-- | :-- |
| Legacy Mac staging omits rule/theme support; paths assume Linux users/homes | New complete private source staging; validated Workstation context; Host identity guard preserved |
| Exact pinned Hermes checkout is dirty immediately on a case-insensitive Mac | Exclude only case-colliding `contributors/emails/` with an exact checked sparse specification; verify pin and remaining tracked source |
| RMUX archive contains multiple executables named rmux | Extract the reviewed three-executable layout, not a guessed basename; archive/path/type/digest regressions |
| Cold Rust TUI cannot start the SDK daemon through a `-S` wrapper | Explicit raw `RMUX_SDK_DAEMON_BINARY`, private socket, mandatory launcher-context check; real cold TUI acceptance |
| npm's installed executable symlink silently imports rather than starts the CLI | Resolve the real entrypoint path; offline tarball-consumer and symlink regression |
| Composio's exact upstream Mac arm64 executable is killed with invalid signature | Disclosed, exact-version/source-digest-only derived ad-hoc-signed bundle; original preserved, strict signature and native-version checks |
| Process leader exit leaves descendants, or escaped pipe owners prevent settlement | Held supervisor, same-group cleanup, bounded capture drain; real success/timeout/signal/parent-death process-tree regressions |
| Personal AGK paths and legacy actions can escape the intended installation workflow | Validated Project/runtime paths and guards around legacy install/sync/gateway/client/topology routes; no same-UID sandbox claim |
| Default Host web-path contract loads the module outside package import context | Preserve standalone Host resolution without importing personal helpers; existing contract regression retained |
| Native CI reports only a generic install failure and a disposable receipt path | Fixed phase in CLI errors/receipts; bounded allowlisted check IDs/statuses in CI; synthetic failure and secret-redaction regressions |

## Local verification

- Station and Factory: **1,513 passed**, 21 Linux-only cases skipped on macOS.
- AGK component pipeline: **112 Rust + 425 Python + 24 JavaScript passed**;
  two optional local Python web-library tests skipped. Format, Clippy, typechecks
  and client/server builds also passed in the isolated component test copy.
- npm Workstation: **160 tests passed**, covering CLI, filesystem, package hooks,
  process supervision, terminal presentation, onboarding, gateway, runtime,
  connectors and web health contracts.
- Repository Doctor: **85 checks passed**; deterministic metadata checked.
- Packed consumer smoke: package assets, Cargo lock, both dashboard dist files,
  themes, CLI modules, offline install, executable symlink and read-only plan.

The first full Station run exposed the standalone Host web-module regression
(1 failure, 1,512 passes). The existing nine dependency contracts then passed
after repair, followed by the full **1,513-pass** rerun. It was not waived.

## Real macOS consumer installation

`node installer/npm/test/native-install.mjs` packed the repository, installed the
tarball into a new consumer prefix, and ran the **installed npm executable** into
a fresh private test directory. It did not reuse the earlier repaired runtime.

Final recorded root: `/private/tmp/stnf.KdUcQq/station`.
Machine evidence: `/private/tmp/stnf.KdUcQq/native-acceptance.json`.
That receipt records the exact tested package integrity and the returned checks;
it is not a claim that later documentation edits have the same tarball hash.

Results:

- **20 required native checks verified**, including pinned Hermes source/imports,
  actual enabled plugin discovery, AGK/controller/RMUX context, Vercel, Codex,
  shadcn, discord.js, GitHub, Composio and both web workers.
- Crawl4AI and ScrapeGraphAI imported their real libraries and launched private
  Chromium instances. No website extraction or paid model request was made.
- Native macOS service definition generated and checked; the corresponding
  account LaunchAgents plist was absent before and after. No service started.
- Real Rust TUI: **10 views**, **64×16 / 100×24 / 140×40**, clean exit.
- Synthetic Project and `/bin/cat` session: private context/socket, literal
  readback, rename, respawn, archived restart visibility and scoped cleanup.
- **12 protected personal files fingerprinted; zero changes observed** across
  the consumer installation and acceptance. Credential bytes were not logged.
- Software result: `ready-for-setup`. Capability result: `incomplete` — external
  accounts, voice hardware/APIs, optional services and live Discord remain gates.

Earlier development evidence is retained at
`/private/tmp/stw.UWEUu4/station/evidence/`, including the eight-wrapper SDK fix
hash readback, native acceptance, and Composio source/derived/signing-tool hashes.
The first case-collision failure remains under `/private/tmp/stw.Fa90sC/`.
These are disposable acceptance locations, not user Project or production paths.

## Continuous verification and limits

The main CI workflow now runs npm regression and packed-consumer checks on both
Ubuntu and macOS, plus a complete native Linux Workstation installation from its
packed CLI, real TUI navigation and a synthetic session. The Linux runner's OS
libraries are prepared explicitly by CI, not silently installed by Workstation.

Commit `023c03680b34744c09aea401afc9f7c41e520d5f` passed
[all nine CI jobs](https://github.com/agentik-os/agentik-station/actions/runs/33967030631).
The native Ubuntu 24.04 installation completed in 4m05s: **19 required checks**,
native service-template verification, real TUI navigation, synthetic session
lifecycle and no changes to the protected-file set. The extra macOS check covers
the exact contributor-attribution sparse checkout. The runner's disposable receipt
path is not a persisted artifact; the linked job log records the acceptance summary.
For subsequent commits, check their own
[Actions run](https://github.com/agentik-os/agentik-station/actions/workflows/ci.yml);
this observed result does not certify later changes automatically.

Native persistent service **templates** were verified on the exact Hermes pin;
service activation, restart after login/reboot, Discord authorization rejection
and a real reply require their own live acceptance. Ad-hoc signing proves the
recorded local transformation, not publisher identity or notarization. Windows
native, macOS Host Zones, Linux services ported to macOS, unattended Workstation
upgrades and automatic client/OS provisioning are not implemented by this route.
