# Agentik Station 11.32 Validation

## Native role-routing semantics — 11.32

The final 11.31 local run passed 1,983 Station/Factory tests (21 Linux-only skips),
and all nine GitHub jobs passed, including native Linux Workstation installation
and update lifecycle. The VPS installed 29 default-team profiles, passed all 18
Stepper evals as its Zone identity and all 192 full Doctor checks; 17 protected
files and the tracked services remained unchanged. Builder selection passed
under the real operator UID after a six-file, recoverably backed-up repair.

A later source review identified stale role-routing guidance, not a failed
installer: native transient children do not select persistent role profiles.
11.32 corrects the generated SOUL/shared skill and publishes new default OS
package versions without overwriting immutable 11.31 bundles. Its initial
focused compiler/defaults regression passed 49 tests. Live paid-model and
role-to-role task acceptance remain separate, unexercised gates.

## Stepper and native orchestration — 11.31

Implementation and acceptance are tracked in
`docs/audit/2026-09-05-stepper-orchestration-plan.md`. New gates cover Stepper's
typed artifacts and negative cases, compiled Director/team assets, personal
native OS installation, the dedicated operator's Builder route and native
Hermes configuration. The historical results below are not a new live
acceptance claim for these changes.

The extracted npm artifact installed and read back 29 native profiles across
Stepper, Builder and Librarian; all three dedicated launchers passed native
help checks. The npm regression run passed 263 tests, and AGK passed 461 tests
with two local native-web skips. The Station/Factory run passed 1,975 tests with
21 Linux-only skips; another 93 focused checks passed after interactive terminal
hardening. Live accounts, model calls, chat admission and existing enrolled-profile
migration remain distinct acceptance gates.

## Native watcher receipt correction — 11.30

11.29's actual Host systemd readback exposed a non-root `SafeFS` ancestor-open
failure beneath `/var/lib/station` mode `0711`, despite 192 passing Doctor checks
and a successful weekly discovery oneshot. The [audit plan](docs/audit/2026-09-05-coordinated-updates-plan.md)
records the exact cause and separate 11.30 fix. Native watcher-UID and hardened
systemd receipt writes, unchanged Zone permissions and protected-file readback
are acceptance gates; mocked metadata checks do not substitute for them.
The final focused suite passed 50 tests, including actual execute-only-ancestor
traversal and root/watcher dispatch. All nine 11.29 CI jobs also passed, including
native Linux Workstation installation and synthetic-successor update lifecycle;
this does not erase the separate Host watcher failure recorded above.

## Coordinated updates — 11.29

The [update mission plan](docs/audit/2026-09-05-coordinated-updates-plan.md)
separates upstream discovery, compatibility acceptance, npm software migration
and production deployment. All 203 npm tests pass, including predecessor drift,
inactive runtime gates, interrupted/concurrent recovery and corrupt-baseline
refusal. Native packed macOS installation passed 21 required checks, service/MCP
templates, TUI and synthetic sessions, with 14 personal files unchanged. Native
software migration with a synthetic successor label and unchanged upstream pins
also passed, including protected in-root configuration comparison. Final Linux
CI and installed Host readback are independent gates; no future upstream
compatibility, legacy adoption or unattended database migration is inferred.
The final complete Station/Factory run passed **1,874 tests**, with 21 Linux-only
skips on macOS. Repository Doctor, deterministic metadata and the exact packed
consumer installation/launcher smoke test passed.

## Required full Host stack — 11.28

The default selection now includes every requested Host component. Independent
dependency subprocesses retain per-component exit evidence and cannot convert a
failed internal command into a successful installer. Server software manifests
pin exact Linux AMD64 image bytes for Langfuse, Honcho, Hindsight and ChatbotX.
The native inventory separates artifact/import verification from activation,
profile/account enrollment and live acceptance. Ponytail remains a required,
security-blocked component; no full-stack operational claim is made.

The complete local run passed 1,845 cases with 21 Linux-only skips and exposed
one obsolete Ponytail contract expectation. After replacing that expectation
with the enforced immutable security block, all 87 contract/Ponytail checks
passed. AGK's initial component run passed 425 cases (two local native-web skips);
the subsequent reviewed 11.25-controls migration passed 91 focused checks. All
168 npm tests and the packed-consumer smoke test passed. The final published
commit's CI and installed Host readback remain independent acceptance gates.

Current run evidence and remaining limitations are recorded in the
[full-stack installation audit](docs/audit/2026-09-05-full-stack-install-plan.md).

## Default ChatbotX client — 11.27

The [integration acceptance record](docs/audit/2026-09-05-chatbotx-acceptance.md)
tracks pinned default installation on Host and Workstation, explicit Node
launchers, account-free probes, actual Hermes MCP SDK support and disabled
connection/tool defaults. Software, native template compatibility, live accounts,
production VPS deployment and npm publication are distinct gates.

Local validation passed 1,572 Station/Factory tests (21 Linux-only skips), 168
npm tests and 170 final focused checks. A fresh packed macOS consumer passed all
21 required software checks, actual SDK/template compatibility, 10 TUI views,
three terminal sizes and synthetic session lifecycle. All 14 protected personal
files were unchanged. Native Linux acceptance is also a mandatory CI job; live
accounts, production deployment and npm publication are not inferred from it.

## Personal Workstation — 11.26

The [portable installation mission](docs/audit/2026-09-05-portable-install-plan.md)
defines the independent branch owners, native macOS acceptance, npm packaging,
security regressions and service-activation limits. Earlier release counts below
remain historical and are not claims for the changed Workstation implementation.

The [acceptance record](docs/audit/2026-09-05-workstation-acceptance.md) records
1,513 Station/Factory passes, 160 npm tests, 561 AGK tests and the fresh installed
macOS package acceptance: 20 required native checks, 10 TUI views, three sizes,
synthetic session lifecycle and zero observed changes to 12 protected personal
files. Live accounts, service activation and npm publication are separate gates.

## Isolated installation-version probes — 11.25

The final AGK Host audit below led to an additional native-startup finding:
`hermes --version` is not guaranteed free of configuration/cache writes. The
[audit record](docs/audit/2026-09-05-agk-tui-acceptance.md) preserves both the
successful 11.24 software acceptance and the unattributed operator-config drift,
and defines the separate isolation fix and regression gate for 11.25.

Final verification: **1,513 Station/Factory tests passed**, with 21 Linux-only
cases skipped locally; 80 final release/contract checks also passed. Focused
probe/launcher tests passed 41 cases (six Linux skips). The exact candidate
probe passed all twelve real installed VPS tool/SDK targets; all 17 newly
fingerprinted protected files remained unchanged. The AGK software is unchanged
from the 520-test component and native acceptance recorded for 11.24. This does
not identify the writer of the earlier configuration changes or accept accounts.

## AGK feature audit and Discord setup — 11.24

The [mission plan and acceptance matrix](docs/audit/2026-09-05-agk-tui-acceptance.md)
track this release's verification, reproduced defects and external limitations.
Earlier release evidence below remains historical; it does not substitute for
testing changed controls or accepting live accounts in this release.

Final source verification: **1,503 Station/Factory tests passed** (15 Linux-only
process cases skipped on macOS), and **520 AGK tests passed** (112 Rust, 384
Python, 24 JavaScript; two optional local web-library skips). Format, Clippy,
three TypeScript configurations, client/server builds, Node syntax, all 85
repository Doctor checks and deterministic release metadata passed. Native
installed acceptance and protected-file readback are separate Host gates.

## SSH operator and systemd repair — 11.23

The live `moonbase` SSH account on `capital` reproduced a missing public `agk`
command. The private operator installation did render its real Rust TUI over
SSH/PTY and exited cleanly on `q`; a help-only check had not tested that public
entrypoint. Source review also found that failed-install evidence could reset
`/var/lib/station` to `0750`, and the Doctor's closed link policy had no native
Hermes user-systemd enablement case. The existing live parent was `0711`:
`z-system-discord` could read its own `.env`, while access to `dev/home` was denied.
No credential contents were printed or copied.

The old live release then reproduced the precise systemd contradiction through
`station platform install --zone discord-bootstrap`: native Hermes installed
and enabled its standard user service, created the absolute sibling-unit
symlink, and the 11.22 Doctor failed **only** that link. A subsequent systemd
readback exposed another defect: the native CLI's headless `install` defaults
to immediate startup, although its underlying installer function does not.
The gateway was observed active and explicitly stopped. No chat or model
round-trip was accepted; this observation cannot establish absence of network
activity during startup. The link is retained for corrected Doctor readback,
not removed to conceal the failure. Station now supplies `--no-start-now` and
`--start-on-login` explicitly and tests the public argv, not only the helper.

This release repairs those paths and adds adversarial regression coverage.
Publication, live launcher/service-link readback and final Doctor results are
separate gates; none proves a Discord message or a paid model request worked.

The final local Station/Factory suite passed **1,489 tests**, with **15 Linux-only
process tests skipped on macOS**. The shipped AGK component suite passed **271
tests**, with two absent local web-library skips covered separately by CI/VPS.
Repository Doctor passed all **85 checks**; shell syntax, diff hygiene and
deterministic metadata passed. Independent reviews covered both the constrained
systemd-link policy and the privilege-dropping operator launcher. Initial
headless-start changes also required updating two exact-argv regression
expectations; the final complete run passed after those corrections.

On the VPS, the first controls-only attempt correctly refused the operator
checkout's `0775` source directories before changing either target. Both
installed files matched their reviewed 11.22 hashes. The repair procedure now
uses the published immutable release as its source; neither the guard nor the
operator checkout permissions were weakened.

## Native profile voice provider — 11.22

The published commit `266e62d0c4bcd8c948d50735f11818296fb4a2e9` subsequently
passed all six CI jobs and was deployed as immutable 11.22. The full VPS
acceptance rerun passed its nine gates and final Doctor (**188 checks, zero
issues**). All **256** focused voice/enrollment/process tests passed on Linux,
including the cases skipped on macOS. Atlas's normal native plugin installation
and discovery succeeded; the actual installed dispatcher used loopback Parakeet
when a test-only OpenAI failure was simulated, and did not retry successful
silence. Five other profiles, credentials and the immutable DevOps OS 11.12
bundle were preserved. Live Discord and paid OpenAI acceptance were not performed.
The following paragraphs retain the earlier staged evidence and its limitations.

This release adds opt-in, one-role enrollment of a native Hermes transcription
provider. It leaves independently versioned OS bundles and other profiles intact.
OpenAI success, silence, failures, compatibility errors, fixed local execution
and adversarial filesystem cases have separate unit coverage. Native installation,
dispatcher/audio readback and full release gates must pass before VPS acceptance;
none of these substitutes for an authenticated OpenAI or live Discord round-trip.

Before publication, the corrected plugin payload passed the VPS's pinned native
Hermes security guard with a `SAFE` verdict (one medium subprocess-use finding,
allowed by the normal policy) and native plugin Doctor's import/registration
checks. No scan setting, trust exception or force flag was used. A direct native
provider-ABC call, with OpenAI failure deliberately simulated, invoked the real
loopback Parakeet adapter as `z-agentik` and matched the clear synthetic fixture.
The native OpenAI helper signature was checked without making a paid request.
This staged check is not installed-profile dispatcher or Discord acceptance.

Independent review caught and corrected cross-UID audio-path substitution,
raw-versus-managed configuration ambiguity, native subprocess timeout cleanup
and a cancellation race during child creation. Real VPS `runuser --user`
readback confirmed the child retains the supervisor's new session/process group.
The bounded command supervisor deliberately supports the Linux Host target only;
macOS skips its real Linux process tests, which require CI/VPS execution. It is
not containment for hostile daemons that create another session, or for a
supervisor killed with SIGKILL.

The complete 11.22 Station/Factory suite passed **1,345 tests**, with **15
Linux-only process cases skipped on macOS**. Focused coverage includes 116 voice
provider, 108 enrollment and 17 locally executable supervisor cases. Repository
Doctor and deterministic release metadata checks passed. Real Linux process
tests, installed-profile dispatch and deployment readback remain separate gates.

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

All six 11.19 CI jobs passed. The sixth full bootstrap completed Hermes,
toolchain, voice, AGK-TUI, immutable kernel publication and kernel readback.
It installed all seven core Zones, then stopped at Ponytail's native dangerous
security verdict. That failed attempt remains recorded; the guard was not
bypassed. The [Ponytail review](docs/audit/2026-09-05-ponytail-native-scan.md)
explains the benchmark findings and outstanding upstream resolution.

Independent component installs subsequently succeeded for Langfuse source,
Honcho/Hindsight SDKs, TigerVNC and Parakeet. No Langfuse server, authenticated
memory backend or VNC display was started. The actual Parakeet container passed
loopback health and readback of its pinned image, non-root UID, read-only root,
no-new-privileges, local port binding and CPU/memory/PID/tmpfs limits. This is not
live speech recognition or cross-Zone service isolation acceptance.

A subsequent real adapter request as `z-agentik` transcribed a clear synthetic
voice sample as “Hello, this is a test. The station is ready.” with a private
0600 output. An earlier robotic-voice sample was poorly recognized (“I am.”),
so this does not establish general recognition quality. No Discord upload or
OpenAI request was used; the observed success is local HTTP/adapter transcription.

The `dev/engineering` DevOps instance installed all six native Hermes profiles,
and an unchanged-input retry preserved them. Director, Forge and Discord setup
plans resolved the expected namespaced profile and instance Hermes root. Native
Doctor then exposed root-owned `.config` parents inside the Zone HOME. The current
root-level Doctor had not caught this, and local verification correctly remained
failed. A second gap prevented Zones from seeing coding CLIs kept in the private
operator prefix. Both require code-only/ownership repair and fresh Zone readback;
no private home permissions or credentials were shared to hide the failures.

Guided setup initially timed out while Tailscale obtained its first HTTPS
certificate. Subsequent native TLS validation, GET `/station-setup/health` and
a complete guided-setup retry passed on the VPS. No public Funnel was enabled;
the current local development machine cannot resolve this private Tailnet
hostname, so off-Host client access is not claimed. External account, Discord,
speech and recovery acceptance remain pending.

The frozen 11.20 Station/Factory suite passed **998 tests**. This includes 68
shared-toolchain security cases, 30 Zone HOME ownership cases and 29 guided-setup
cases. Repository Doctor, regenerated release metadata and diff hygiene passed.
Live publication of the shared CLIs and repaired Zone parents still requires
unprivileged VPS readback; these local tests are not that acceptance.

The first shared-toolchain VPS publication correctly stopped before any shared
release or public launcher was created: the native Node archive includes an
empty `lib/node_modules/npm/.npmrc` placeholder. The correction omits only this
exact empty, trusted regular single-link file without reading its contents.
Nonempty configuration, links, special files and other `.npmrc` paths remain
refused. Separately, voice documentation now distinguishes the implemented
Discord voice-channel Parakeet hook from uploaded voice-note attachments, whose
native Hermes transcription path is not connected to that hook.

The final pre-deployment 11.20 suite passed **1,047 tests**, including 85
shared-toolchain cases and 67 combined VPS evidence/Zone toolchain acceptance
cases. Independent reviews found no blocker in the ownership, TLS, shared-code
or Zone-probe changes. The actual VPS acceptance additionally requires all eleven
public CLI pins under a real Zone identity with its canonical HOME/HERMES_HOME
and an isolated network namespace; this does not authenticate any provider.

All six final 11.20 CI jobs passed for commit
`338ba8e79382f2ebe72837815641eb07aafdbcde`. Actual shared-code publication passed,
including native versions and relocated Python runtime/venv probes; its unchanged
retry also passed after a complete operator-toolchain reinstall. The operator
home remained 0750 and no authentication was copied.

The seventh bootstrap, `op-20260905-035321-f5537068`, completed **all 19 selected
stages** successfully and activated the immutable 11.20 kernel. It used normal
full mode, not `--with-ai-stack`: Ponytail remained blocked/not installed, while
the other optional components had been installed separately as described above.
Guided HTTPS setup, the weekly Hermes update timer, inventory and redacted AGK
metadata synchronization all completed. Timer readback showed its first scheduled
run on 2026-09-07; no native Hermes update/restore was executed during acceptance.

All six `dev/engineering` native profile Doctors and complete local readback then
passed. Its ledger advanced to `VERIFIED`, **not OPERATIONAL**. The owning Zone
could read its Director config; the Factory Zone could not. Unknown-role routing
was refused, and Discord setup still resolved only the instance's namespaced
Director with its canonical Zone HOME and dedicated instance HERMES_HOME.

The initial full VPS acceptance passed all nine gates: real Zone traversal and
cross-Zone denial, eleven public CLI pins under network isolation, web runtimes
and Chromium, AGK, timer and Parakeet health. **A subsequent fresh Station Doctor
failed**, exposing a missing post-execution gate: Codex `--version` and native
Hermes Doctor had created legitimate Codex/uv cache links that the blanket Zone
symlink check rejected. The earlier receipt is retained as historical evidence,
not final clean-state acceptance. No caches or links were deleted to hide this.
11.21 adds a governed, bounded read-only link inspection and a final fresh Doctor;
the immutable 11.20 release is preserved rather than patched in place.

The frozen 11.21 Station/Factory suite passed **1,104 tests**. Its focused link
and existing boundary suite passed 92 cases; acceptance/evidence tests passed 71
cases, including shell execution proving a failed final Doctor prevents success
publication. Independent review found and corrected an immutable-directory
permission check before final validation. Repository Doctor, deterministic
metadata, shell syntax and diff checks passed. Live cache-policy and post-probe
acceptance readback are required before accepting the new deployment.

The final 11.21 commit, `534bba5fe52377911584dba4b8c4406342cde25a`, then passed
all six GitHub Actions jobs. The eighth actual VPS bootstrap,
`op-20260905-040517-17806b86`, completed **19/19 stages**, publishing immutable
11.21 beside 11.20. Full VPS acceptance passed all nine gates and the final fresh
Doctor: **188 checks, zero issues**. Evidence is retained at
`/tmp/station-vps-acceptance.20260905-11-21.json` on that VPS; its claim is
`VERIFIED_INSTALL_READY_FOR_EXTERNAL_SETUP`, with external accounts explicitly
false. A later read-only Doctor rerun again passed all 188 checks.

All six `dev/engineering` native profile Doctors and local readback passed again;
the ledger is `VERIFIED`, not operational. Its immutable DevOps OS 11.12 bundle
remained unchanged. A fresh direct Parakeet adapter request again transcribed the
clear synthetic sample successfully with private output. No paid audio request,
Discord delivery, Hermes update/restore or off-Host recovery was executed.
Ponytail remains security-blocked; its dated upstream recheck found no installable
fix and did not bypass or rerun the blocked installation.

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
