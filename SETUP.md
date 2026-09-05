# Setup and Acceptance Gates

A successful base install means `READY_FOR_SETUP`, not `OPERATIONAL`.

For the 11.14 client-owned instance sequence, follow [the first-mission guide](docs/operations/06_FIRST_MISSION.md).
Start with `sudo station setup --json`. This is a read-only local report of the
bootstrap, Organization/Zone/instance and Project evidence and the next ordered
actions—not an automatic executor. Select `--organization`, `--zone` and `--instance` to make
the actions specific. `--probe` adds only a bounded read of the selected systemd
user service; it does not start Hermes or authenticate an account.

## Gate 1 — Host identity and private connectivity

- enroll the Host in the approved Tailscale network;
- match the observed device identity to the declared `host_id`;
- verify operator SSH access before tightening firewall policy;
- record connectivity evidence;
- never infer readiness from the presence of the `tailscale` binary.

## Gate 2 — Hermes runtime/compiler

- install the approved Hermes release/commit through the release-ring workflow;
- keep shared executable code in `/opt/station/tools/hermes/current` and never store Zone credentials there;
- assign an independent runtime namespace to each Zone and a dedicated `HERMES_HOME` to each named OS instance;
- compile AGK OS definitions into Hermes Profile Distributions, profiles/Bots, Skills, plugins, MCP/tool filters, boards, cron, and gateway bindings;
- configure the instance workspace and explicit allowed Projects; these are routing/policy declarations, not a same-Zone filesystem sandbox;
- enable Ponytail only for Builder/DevOps/engineering profiles that require it;
- run Hermes Doctor and `hermes plugins doctor ... --ci` for Station plugins;
- execute Zone-boundary negative tests;
- store receipts/evidence before raising readiness.

Instance Hermes homes namespace profiles, configuration and sessions, not all
account state: gateways retain the canonical Zone `HOME`, where other CLI logins
and caches may be shared. Do not copy authentication automatically or treat
same-Zone instances as separate account/Unix sandboxes.

For a client, register its already reconciled ORGANIZATIONS Zone, install an
instance, then configure the exact Director. A Project is not required:

```bash
sudo station organization register --id acme --zone acme-dev --plan
sudo station organization register --id acme --zone acme-dev
sudo station os instance install --zone acme-dev --instance engineering --organization acme --id devops-os
sudo station os instance setup --zone acme-dev --instance engineering --plan
sudo station os instance setup --zone acme-dev --instance engineering
sudo station os instance show --zone acme-dev --instance engineering
```

An untouched desired OS remains `NOT_INSTALLED`. Successful installation records
`CONFIGURED` for the entire native team, not provider authentication. The root-owned
schema-3 ledger keys `(Zone, instance)` to its client-owned workspace, bundle and
complete `role_profile_map`; a Zone can contain sibling instances and Projects.
Use `--allow-project <id>` at install when a mission must serve an existing Project.
Safe unchanged-input retries preserve
completed profiles; collisions, changed bundles and ambiguous partial files require
repair. `sudo station os instance verify --zone acme-dev --instance engineering` records local full-team
Doctor evidence, never live mission acceptance. Reconfigure first, then verify:
changing a profile's configuration invalidates its previous verification.

Configure a worker's provider only when its role needs separate enrollment; the
canonical role is resolved through the trusted map, not a guessed native name:

```bash
sudo station os instance setup --zone acme-dev --instance engineering --role forge --plan
sudo station os instance setup --zone acme-dev --instance engineering --role forge
```

The full OS includes domain state, schema-backed views, workflows, capabilities
and recovery. Installing its profiles does not automatically implement or accept
all those planes. Legacy schema-2 Project-bound `os install/setup/verify` and
gateway `--os` remain available without automatic adoption or migration; prefer
the [instance contract](docs/organization/05_OS_INSTANCES.md) for new client runtimes.

## Gate 2a — Hermes voice and local Discord audio failover

- verify Hermes was installed with the explicit `voice` and `messaging` extras;
- keep OpenAI `gpt-transcribe` as primary STT and `gpt-4o-mini-tts`/`alloy` as TTS unless the owning Zone declares another reviewed route;
- store `OPENAI_API_KEY` or `VOICE_TOOLS_OPENAI_KEY` only in the owning Zone's Hermes credential store/environment;
- verify `station-parakeet.service` binds only to `127.0.0.1:5092` and passes `/health`;
- force native Discord voice-channel transcription to fail and verify the channel sample transcribes through Parakeet;
- test uploaded voice notes separately through Hermes' native message path; Station's Parakeet hook is not connected to attachments yet;
- verify a real OpenAI STT/TTS round-trip and billing/account scope before claiming the paid path ready;
- verify Discord `/voice` reply mode and voice-channel permissions with external readback.

Details: [`docs/dependencies/VOICE_AND_GUIDED_SETUP.md`](docs/dependencies/VOICE_AND_GUIDED_SETUP.md).

## Gate 3 — GitHub and coding executors

- run `station deps toolchain-check` and compare observed versions with `config/versions.lock`;
- authenticate GitHub CLI with `gh auth login`, then verify with `gh auth status`;
- authenticate Vercel only where deployment is required, then verify with `vercel whoami`;
- authenticate Composio with `composio login` only for the owning principal, then use the explicit provider plan/link/verify flow and verify only the declared connections;
- sign in to Codex through its current interactive flow; never copy a personal token into a shared Zone;
- bind each Project only to its declared repositories;
- use development/staging credentials by default;
- keep production mutation behind explicit approval;
- verify actual read/write scope with safe probes;
- map executor-neutral roles to available Hermes/Codex/Claude executors;
- require observed tests/review/CI before merge-readiness claims.

## Gate 4 — Composio connected capability plane

- map a stable Station principal to the correct organization and Zone;
- inspect `station provider composio-discord plan --zone <zone-id>`;
- run `sudo station provider composio-discord link --zone <zone-id>` and complete the hosted OAuth flow;
- run `sudo station provider composio-discord verify --zone <zone-id>` and one approved read-only tool probe;
- configure only declared toolkits and connected accounts;
- enforce `config/composio/discord-tool-policy.json`; unknown execution is denied;
- keep Hermes as the only messaging Gateway; neither Composio nor discord.js owns sessions or chat ingress;
- never use a generic production principal;
- validate `available → authenticated → scoped → verified_ready`;
- use sessions/MCP/triggers through the Station capability policy;
- route triggers through Station ingress, context resolution, and mission policy;
- prove cross-Zone and cross-account isolation with negative tests.

## Gate 5 — Dedicated Discord OS bots

For every OS instance that is actually installed:

- have a human server owner create one dedicated Nano Director Discord application/bot, authorize it to the guild, and retain control of token rotation;
- enter the token only through `sudo station platform setup --zone <zone-id> --instance <instance-id> --platform discord` (the selected Director's Hermes wizard), never a CLI argument or Git file;
- provision the dedicated channel, roles, permissions, commands, pins, and bindings;
- grant temporary bootstrap administration only for an approved maintenance window and only when narrower permissions are insufficient;
- require the human server owner to remove the elevation, then read back and verify least-privilege runtime permissions;
- configure semantic Mission Progress Cards instead of raw tool noise;
- use Components V2-compatible layouts, short action labels, select menus/modals for complex input, and linked details/evidence/graphs;
- verify command registration, message creation/edit, interactions, authorization, rate-limit recovery, and external readback in a test guild;
- keep Bot-to-Bot collaboration inside Hermes/AGK rather than recursive Discord auto-replies.

The bot token cannot create other Discord applications or mint their tokens. The
full guild topology provisioner is not claimed externally accepted; use a test
guild and keep the module below operational acceptance until its
create/edit/permission/command/readback gate passes.

Specialists remain internal by default. Only for a justified external topology,
select a canonical worker role explicitly, for example:

```bash
sudo station platform setup --zone acme-dev --instance engineering --role forge --platform discord --plan
# After separate bot identity, channel scope and human approval are established:
sudo station platform setup --zone acme-dev --instance engineering --role forge --platform discord
```

This selects Forge's mapped profile; it does not approve the topology or create a
token. Enroll a separate intended bot identity, verify least-privilege permissions,
then test route/restart/readback. Never run two gateways concurrently with one token.

After the first bot and Tailscale enrollment, run `sudo ./scripts/station_guided_setup_enable.sh`. The Discord account picker can then return an ephemeral one-time Tailnet button. The bearer token is stored only as a hash, expires in at most 15 minutes and is consumed once. Secret forms write directly to the owning Zone's mode-0600 Hermes environment; Composio/OAuth/device flows redirect only to an allowlisted host. Never paste the credential into Discord. Slack/Telegram can reuse the provider-neutral card contract, but their live renderers remain an acceptance gate.

That broker currently writes **Zone-base** credentials, not every named Director's
private profile or instance. Use `station os instance setup` and
`station platform setup --instance` for enrollment. Do not infer that a Zone connection authenticates all of
its profiles or that a bot has Linux sudo authority.

## Gate 6 — Backup and recovery

- choose and configure an encrypted off-Host backup provider;
- define per-Zone inclusion/exclusion and retention;
- snapshot desired state, Project assets, runtime databases, Hermes state, and required evidence without exporting unrelated secrets;
- destroy a disposable target and restore it;
- rebind external credentials/accounts safely;
- run Doctor and fresh-session acceptance after restore;
- only then claim recovery readiness.

## Gate 7 — Fresh-session acceptance

OS mission automations stay disabled until their applicable acceptance gates pass.
Infrastructure services/timers are separate: bootstrap can enable Station Doctor,
the weekly Hermes updater and the enrolled guided-setup broker as documented.

Acceptance uses only:

- deployed package/configuration;
- installed Skills and tools;
- durable state;
- declared inputs;
- current scoped credentials.

It must not rely on hidden context from a previous debugging session. After the manual fresh-session workflow passes, enable the cron/automation, trigger it, and verify delivery/readback.

## Final state

Only raise the Host/OS to `OPERATIONAL` when all applicable module gates have observed evidence, external readback, and acceptance. Otherwise retain the exact lower maturity/readiness state and a next repair action.


## Gate — Hermes multi-platform bots (easy connect)

Use the Hermes Messaging Gateway — one process for Telegram, Discord, Slack, WhatsApp, Signal, Email, Teams, and more.

Use the owning Zone and installed instance, not the global operator home:

```bash
sudo station platform setup --zone acme-dev --instance engineering --platform slack
sudo station os instance verify --zone acme-dev --instance engineering
sudo station platform install --zone acme-dev --instance engineering
sudo station platform start --zone acme-dev --instance engineering
sudo station setup --organization acme --zone acme-dev --instance engineering --probe --json
```

Add `--plan` to the `station platform` commands to inspect the exact `runuser`/`HERMES_HOME` invocation before execution. `platform setup` opens Hermes' interactive gateway wizard; the platform flag validates operator intent and includes it in the emitted result, but tokens are entered only through Hermes. `install` enables linger and starts the Zone's systemd user manager so the gateway survives logout/reboot.

Here `--plan` applies to `station platform` actions; `station setup` is already a
read-only report. With neither `--instance` nor legacy `--os`, the platform command
explicitly selects Zone `default`; that does not enroll an instance.
Native `station platform status/doctor` remain available, but upstream Hermes can
synchronize bundled Skills at startup; they are not the pure setup report.

Details: `docs/dependencies/HERMES_PLATFORMS.md` and https://hermes-agent.nousresearch.com/docs/user-guide/messaging

Keep Hermes tokens in the selected instance/profile's credential configuration;
Zone-base broker credentials are not instance enrollment. Do not claim OPERATIONAL
for a platform until bidirectional live message readback passes.

## Gate — Optional dependency stack

ScrapeGraphAI/Playwright, Langfuse, Honcho, Hindsight, Ponytail, Crawl4AI, TigerVNC, Parakeet and the isolated discord.js SDK are declared in `config/deps/stack.yaml`. ScrapeGraphAI and Crawl4AI install by default; `--skip-scrapegraphai` / `--skip-crawl4ai` deliberately omit the selected runtime. Run `sudo station deps web-check`, then a fresh-session extraction in the owning Zone. The automatic adapters process public HTML without JavaScript; see [web limits and profile activation](resources/scrapegraphai/README.md).

```bash
./scripts/station_deps_install.sh --list
sudo ./scripts/station_deps_install.sh --component <id>
./scripts/station_hermes_update.sh update
sudo ./scripts/station_deps_install.sh --enable-hermes-auto-update
```

See `docs/dependencies/STACK.md`. Install/readback state is reported separately from repository maturity; no component becomes OPERATIONAL merely because its package or source is present.
