# Agentik Station 11.19 Validation

## Live VPS repair campaign — 2026-09-05

- Baseline 11.14 Station/Factory suite rerun: **692 passed**.
- On a fresh Ubuntu 26.04.1 x86_64 VPS, repository Doctor and the full bootstrap
  plan passed. The first real installation completed base packages, Tailscale and
  operator creation, then failed because root-owned `.local` prevented the
  operator's Hermes installer from creating its managed Python directory.
- The failed attempt is retained; no kernel release had been published. Its
  service exited and no apt/dpkg/uv child remained before repair preparation.
- 11.15 adds targeted ownership/shared-interpreter, npm launcher, redacted AGK
  synchronization and safe observed-host evidence regressions.
- Corrective Station/Factory suite: **795 passed**. Shipped AGK-TUI component
  suite: **225 passed, 2 skipped** (the two unavailable local web libraries).
- Repository Doctor, shell syntax, diff hygiene and regenerated release metadata
  checks passed before publication of this corrective candidate.

All six 11.15 GitHub Actions jobs passed, including real web-library/Chromium
checks. A second VPS attempt successfully installed the pinned Hermes source and
its shared Python 3.11.16 environment, then exposed a native npm Arborist conflict
with Hermes' existing `npm`/`npx` launchers. That failed receipt is preserved.
The shared interpreter, SSL and Hermes imports were independently exercised as
the unprivileged `nobody` identity from `/`, while the operator home remains 0750.

11.16 repairs npm self-upgrade's lifecycle handling and pins repeated Hermes
installation to the reviewed commit. Its complete Station/Factory suite passed
**825 tests**, including native npm Arborist and real-Git retry regressions.
The three GitHub Actions dependencies now use verified immutable Node 24-based
release pins; jobs, permissions, gates and the Python matrix are unchanged.
All six 11.16 CI jobs passed. A third live attempt preserved the exact Hermes
commit and all three pre-existing private configuration files byte-for-byte,
but the complete npm install still hit `EEXIST` in Arborist's earlier extraction
phase. The rebuild-only regression did not cover that path.

A separate, disposable VPS prefix reproduced this with actual Node 24.20.0 and
bundled npm 11.19.0. Reserving only its two synthetic predecessor symlinks allowed
the complete npm 12.0.2 installation and version readback to succeed. This is
evidence for the handoff strategy. The revised, exact production helper was then
executed in a second disposable VPS prefix with a copy of that same native Node
bundle: installation, repeat installation, version readback, both launcher
targets and absence of leftover reservations passed. The real operator prefix
was not modified by these fixtures. The failed attempt and private configuration
backup remain.

The 11.17 full Station/Factory suite passed **830 tests**. Its focused launcher
suite passed **29 tests**, including complete offline
native npm installation and rollback on native failure, invalid package and
SIGTERM. Recovery restores launcher links, not arbitrary npm package contents.

All six 11.17 CI jobs passed. The fourth bootstrap installed the complete operator
toolchain but exposed the obsolete `hermes version` check. The corrected exact
check subsequently passed on the VPS: Python 3.14.7/3.13.15, Node 24.20.0,
npm 12.0.2, uv 0.12.9, GitHub CLI 2.100.0, Vercel 59.11.2, Codex 0.153.2,
Composio 0.4.0, shadcn 4.21.0, discord.js 14.27.0 and native Hermes.

ScrapeGraphAI 2.2.2 and Crawl4AI 0.9.3 were independently installed in their shared
immutable runtimes and passed actual Chromium launch on Ubuntu 26.04. Native
`--help` readback also
proved that the updater's proposed restore command was unsupported; 11.18
removes that invocation and records manual recovery instead. No Hermes update,
restore or provider login was performed during these read-only CLI probes.

Strix 1.6.1 was installed and its native version command passed; no Docker access,
image pull, cloud connection or security scan was granted/performed. The 11.18
Station/Factory suite passed **856 tests**, including 31 toolchain and 24 updater
cases; independent review, repository Doctor and release metadata checks passed.
An initial custom macOS fixture root inherited group `wheel` and correctly
triggered 42 ownership refusals. Recreating that test-only base with the test
account's group produced the passing run; no production guard was weakened.

All six 11.18 CI jobs passed. The fifth full bootstrap installed the voice and
messaging extras but its unconditional `sounddevice` import tried to initialize
PulseAudio on the headless VPS and failed before AGK/kernel publication. That
failed receipt is retained; its process group was empty before the next repair.
The pinned Hermes Discord adapter uses file/stream codecs, not a local microphone.

The replacement headless checker passed on the actual VPS: installed Python
modules, PyNaCl authenticated encryption, PortAudio library binding without
device initialization, Discord Opus and ffmpeg synthetic audio round-trips.
Its 24 focused tests include a private-source/operator-checkout handoff regression.
Local audio hardware, paid transcription/TTS and live Discord audio remain untested.

An independent AGK installation attempt then exposed a fresh-account RMUX check
that incorrectly required a running daemon. The revised native capabilities and
endpoint check passed against actual RMUX 0.10.0, reporting `IDLE` without starting
or accepting a daemon. The AGK Rust release build completed successfully using
the locked dependencies and operator-owned external build cache. The complete
AGK installation still requires readback after this fix.

Parakeet transcript publication now refuses a competing output atomically.
Eleven new regression cases exercised actual GNU filesystem tools, including
concurrent files, directories, links and FIFO; all passed without overwrites.
The complete shipped AGK-TUI suite passed **248 tests**, with two unavailable
local web-library skips; those libraries have separate CI and actual VPS checks.
The frozen 11.19 Station/Factory suite passed **891 tests**. An earlier concurrent
test run correctly caught stale release provenance after the final test-file edit;
metadata was regenerated before the complete passing rerun. Repository Doctor,
shell syntax, metadata/diff checks and independent voice/RMUX review passed.

Eight deferred Dependabot proposals were preserved under exact-SHA archive tags
before closure; remote readback confirmed `main` as the only remaining branch.
No proposed dependency upgrade was silently merged. See the
[manual update policy](docs/operations/DEPENDENCY_UPDATE_POLICY.md).

Corrected full bootstrap, real named-instance installation and external
provider/chat/recovery acceptance remain pending at this checkpoint. Source
tests are not a successful VPS installation.

## Previous client-instance validation — 11.14

Local verification on 2026-09-05, after the client-owned OS instance implementation:

- Full Station/Factory suite: **691 passed** (687 Station + 4 Factory).
- A final narrow maturity correction then distinguished an incomplete first
  installation from degradation of a previously configured instance. Its impacted
  lifecycle, instance, CLI and onboarding suites passed **161 tests**, including
  one additional regression. Final inventory: **692 tests** (688 Station + 4 Factory).
- Shipped AGK-TUI component suite: **224 passed, 1 sandbox-denied socket test,
  2 skipped** on its first run. The exact socket test passed with the required
  local Unix-socket permission (**225 unique passing tests**). The two skips are
  absent local Crawl4AI/ScrapeGraphAI libraries; dedicated CI jobs exercise them.
- Builder/Librarian deterministic gates: **7/7 passed**.
- Repository Doctor: **PASS**, no issues or warnings.
- Shell syntax, Python AST, JSON/YAML parsing, release schema, exact inventory and
  deterministic SBOM/provenance checks: **PASS**.
- README/atlas presentation: **20 focused contract tests**, **113 local links**
  and **16 new CLI examples** checked; four changed SVGs rendered and visually
  inspected at 830px and 390px. Mermaid source was reviewed, not live-rendered on GitHub.

Tests use temporary filesystem fixtures and simulated native Hermes commands where
needed. The new cross-module regression registers a real Organization over its
canonical client Zone, compiles the real DevOps source into two instances, installs
both complete teams through a fake native installer, verifies them and resolves
their distinct Directors/Hermes homes/native service names through actual
onboarding and gateway builders. No Project owner is required. Legacy runtime
tests remain covered. All six source packages compile instance-local voice defaults.

This is source/local evidence for a **READY_FOR_SETUP** foundation, not a real VPS
or `OPERATIONAL` claim. Native Linux publication, platform behavior and external
accounts require their corresponding evidence. The separately dispatched disposable
VPS workflow was not run for this local validation. No live bot, paid provider,
Strix scan or off-Host recovery acceptance is implied.

Same-Zone instances share a Unix UID and canonical Zone HOME; declared Project
scope is not a filesystem sandbox. Restored/replaced instance roots need reviewed
repair because their inode evidence cannot be silently adopted. The guided broker
and legacy AGK client/dashboard do not automatically become instance-aware.

Follow the [first-mission sequence](docs/operations/06_FIRST_MISSION.md),
[setup gates](SETUP.md) and [instance contract](docs/organization/05_OS_INSTANCES.md).
The [11.13 audit](docs/audit/2026-09-05-operational-control-plane.md) records the prior lifecycle review.
[`VALIDATION_11_12.md`](VALIDATION_11_12.md) remains historical release evidence.
