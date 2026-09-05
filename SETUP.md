# Setup and Acceptance Gates

For the personal macOS/Linux installer, use the separate
[Workstation setup and acceptance sequence](docs/distribution/workstation.md#connect-discord-privately).
The Host/Zone instructions below do not apply to a same-user Workstation namespace.

A successful base install means `READY_FOR_SETUP`, not `OPERATIONAL`.

Fresh 11.31 full/core and team bootstrap prepares the native Stepper, Builder
and Librarian instances without accounts or bots. Select them with
`station os resolve --name stepper` and, on Host, explicit `--zone`/`--instance`.
The equivalent personal npm installation keeps the teams under its own private
`station` root. See [first use and OS cooperation](docs/os/08_STEPPER_AND_BUILDING.md).
No existing provider enrollment, profile or approved dispatcher is overwritten
by those defaults. New compiled teams start with dispatch/API inactive until
their selected work, accounts and delivery path are accepted.

For the 11.14 client-owned instance sequence, follow [the first-mission guide](docs/operations/06_FIRST_MISSION.md).
Start with `sudo station setup --json`. This is a read-only local report of the
bootstrap, Organization/Zone/instance and Project evidence and the next ordered
actions—not an automatic executor. Select `--organization`, `--zone` and `--instance` to make
the actions specific. `--probe` adds only a bounded read of the selected systemd
user service; it does not start Hermes or authenticate an account.

For the first Station bot, use the explicit `discord-bootstrap` Zone, not a bare
Hermes command in the `agk-station` operator home:

```bash
sudo station platform configure --zone discord-bootstrap --plan
sudo station platform configure --zone discord-bootstrap
sudo station platform setup --zone discord-bootstrap --platform discord --plan
sudo station platform setup --zone discord-bootstrap --platform discord
```

`configure` opens only native model/provider enrollment. `setup` opens the native
platform picker with a Station safety briefing; choose Discord and decline its
service install/start/restart offers. The human creates/invites the bot and supplies
its token only at the masked prompt. Set explicit human **and** channel allowlists,
then follow [verify → install → start → live acceptance](docs/dependencies/HERMES_PLATFORMS.md#keep-the-existing-first-station-bot-in-discord-bootstrap--default).
This route does not install a Control OS instance, grant sudo or enroll Atlas.
Preserve any existing token in its current Zone/profile.

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
- Ponytail remains required but security-blocked and NOT_INSTALLED; do not enable
  it or repeatedly retry the rejected tree. A reviewed upstream correction and
  fresh full native security acceptance must precede any scoped
  Builder/DevOps/engineering enablement;
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

The Station OS setup commands use native `hermes setup model`, not the full
wizard. Full `hermes setup` and `hermes setup gateway` can install/start services
before Station's separate verification gate; do not substitute those commands.

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

OS-scoped `platform install`, `start` and `restart` require this current
full-team `VERIFIED` result, including their plans. A missing or stale result
returns the exact scoped `station os instance verify` (or legacy `os verify`)
command. Provider/platform setup and observation remain available for repair;
the separate Zone-default bot route keeps its native Doctor sequence.

To reuse the operator Hermes model without repeated provider selection, follow
[model inheritance](docs/operations/11_MODEL_INHERITANCE.md). An explicit Zone
inference grant enrolls missing model preferences for the complete named OS teams;
it never copies the operator's account, memory or tools. Explicit choices remain.

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
- explicitly enroll each intended OS role through `station voice setup`; this selects the composite provider for all native STT in that profile, not other profiles;
- force primary transcription to fail and verify both a native voice note and a voice-channel sample transcribe through Parakeet; the older AGK operator adapter's fallback remains channel-only;
- verify a real OpenAI STT/TTS round-trip and billing/account scope before claiming the paid path ready;
- verify Discord `/voice` reply mode and voice-channel permissions with external readback.

Details: [`docs/dependencies/VOICE_AND_GUIDED_SETUP.md`](docs/dependencies/VOICE_AND_GUIDED_SETUP.md).

## Gate 3 — GitHub and coding executors

- run `station deps toolchain-check` and compare observed versions with `config/versions.lock`;
- authenticate GitHub CLI with `gh auth login`, then verify with `gh auth status`;
- authenticate Vercel only where deployment is required, then verify with `vercel whoami`;
- authenticate Composio only for the owning principal after reviewing its developer
  project binding; the Station Discord facade's plan explains the outstanding
  project/workdir requirement and does not authenticate a connection;
- sign in to Codex through its current interactive flow; never copy a personal token into a shared Zone;
- bind each Project only to its declared repositories;
- use development/staging credentials by default;
- keep production mutation behind explicit approval;
- verify actual read/write scope with safe probes;
- map executor-neutral roles to available Hermes/Codex/Claude executors;
- require observed tests/review/CI before merge-readiness claims.

Station's Zone Composio commands use only the pinned root-owned public export
at `/usr/local/bin/composio`, not the operator's private executable or ambient
PATH. If that export is missing or changed, repair the shared software; do not
open the operator's home permissions or copy its Composio account into a Zone.

## Gate 4 — Composio connected capability plane

ChatbotX is a separate default-installed client capability. Follow
[resources/chatbotx/README.md](resources/chatbotx/README.md) for its private
workspace credentials, API/schema-origin review and optional disabled Hermes
MCP template. Its native CLI has no masked setup prompt: never put a workspace
token in `config set` flags. Installing it neither authenticates Composio nor
deploys a ChatbotX server or enables marketing actions.

- map a stable Station principal to the correct organization and Zone;
- inspect `station provider composio-discord plan --zone <zone-id>`;
- establish an explicit trusted Composio developer project/workdir binding before
  executing an OAuth or account-list command; the current `link`/`verify` facade
  refuses without this implemented binding rather than falling back to a consumer
  identity or the caller's project;
- follow [the pinned developer binding requirements](docs/dependencies/COMPOSIO_DEVELOPER_BINDING.md);
  scoped OAuth, ACTIVE-account readback and an approved read-only tool test remain
  acceptance gates, not results of the current plan;
- configure only declared toolkits and connected accounts;
- enforce `config/composio/discord-tool-policy.json`; unknown execution is denied;
- keep Hermes as the only messaging Gateway; neither Composio nor discord.js owns sessions or chat ingress;
- never use a generic production principal;
- validate `available → authenticated → scoped → verified_ready`;
- use sessions/MCP/triggers through the Station capability policy;
- route triggers through Station ingress, context resolution, and mission policy;
- prove cross-Zone and cross-account isolation with negative tests.

## Gate 5 — Dedicated Discord OS bots

Choose the bot's existing ownership first. If the first Station token is already
in `/var/lib/station/zones/discord-bootstrap/hermes/.env`, keep the
[`discord-bootstrap / default` route](docs/dependencies/HERMES_PLATFORMS.md#keep-the-existing-first-station-bot-in-discord-bootstrap--default):
configure its own provider and gateway, without printing that file or moving its
token into Atlas. That first Station bot does not require a control OS instance.

For a separate installed instance, use its own enrollment, not the operator home
or another bot's credentials. In the DevOps instance `dev / engineering`, the
default human-facing Director is Atlas:

```bash
sudo station os instance show --zone dev --instance engineering
sudo station os instance setup --zone dev --instance engineering --plan
sudo station os instance setup --zone dev --instance engineering
sudo station platform setup --zone dev --instance engineering --platform discord --plan
sudo station platform setup --zone dev --instance engineering --platform discord
# Finish the human and channel restrictions below before continuing.
sudo station os instance verify --zone dev --instance engineering
sudo station platform install --zone dev --instance engineering
sudo station platform start --zone dev --instance engineering
sudo station setup --zone dev --instance engineering --probe --json
```

In the native platform wizard, choose Discord, enter the token at the masked
prompt, supply explicit numeric authorized-user IDs, choose the home channel,
then finish with **Done**. Decline any early gateway start, install or restart
offer, including one at wizard entry: keep **configure → verify → install →
start**. Do not leave human admission empty or enable wildcard/allow-all or
public bot-to-bot replies.

The home channel is for notifications, not authorization. Configure
`discord.allowed_channels` separately, review any existing environment or managed
policy overrides, and test both a wrong user and a wrong channel. Enable Message
Content Intent; at the pinned Hermes revision, Members Intent is conditional on
username/role admission, not numeric user IDs alone. Grant only the needed
channel permissions, not runtime Administrator. The
[complete Discord walkthrough](docs/dependencies/HERMES_PLATFORMS.md) includes
the exact Atlas channel-ACL command, official sources and live acceptance gates.

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

The System Zone `discord-bootstrap` is a separate choice. Without `--instance`,
its platform wizard selects Zone `default`; that neither installs
`discord-bootstrap-os` nor grants admin authority. See the
[Control / Bootstrap OS contract](docs/os/07_CONTROL_BOOTSTRAP_OS.md).

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

After the first bot and Tailscale enrollment, run `sudo ./scripts/station_guided_setup_enable.sh`. Supported Station chat surfaces can then return an ephemeral one-time Tailnet button; broker installation alone does not prove a native Director exposes the AGK account picker. The bearer token is stored only as a hash, expires in at most 15 minutes and is consumed once. Secret forms write directly to the owning Zone's mode-0600 Hermes environment; Composio/OAuth/device flows redirect only to an allowlisted host. Never paste the credential into Discord. Slack/Telegram can reuse the provider-neutral card contract, but their live renderers remain an acceptance gate.

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
the weekly read-only dependency discovery and the enrolled guided-setup broker as documented.

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

Add `--plan` to the `station platform` commands to inspect the exact `runuser`/`HERMES_HOME` invocation before execution. `platform configure` opens only model/provider enrollment; `platform setup` opens Hermes' interactive gateway wizard with a safety briefing. The platform flag validates operator intent and includes it in the emitted result, but does not filter the picker. Tokens are entered only through Hermes. Decline native service offers until verification; `install` then enables linger and starts the Zone's systemd user manager so the gateway survives logout/reboot.

Here `--plan` applies to `station platform` actions; `station setup` is already a
read-only report. With neither `--instance` nor legacy `--os`, the platform command
explicitly selects Zone `default`; that does not enroll an instance.
Native `station platform status/doctor` remain available, but upstream Hermes can
synchronize bundled Skills at startup; they are not the pure setup report.

Details: `docs/dependencies/HERMES_PLATFORMS.md` and https://hermes-agent.nousresearch.com/docs/user-guide/messaging

Keep Hermes tokens in the selected instance/profile's credential configuration;
Zone-base broker credentials are not instance enrollment. Do not claim OPERATIONAL
for a platform until bidirectional live message readback passes.

## Gate — Required Host dependency stack

ScrapeGraphAI/Playwright, Langfuse, Honcho, Hindsight, Ponytail, Crawl4AI, TigerVNC,
Parakeet and the isolated discord.js SDK are declared in `config/deps/stack.yaml`
and selected by the default full Host installation. Skips deliberately select a
partial installation and require `--minimal`; they do not clear full-stack
acceptance. Ponytail remains security-blocked, and server images still require
separate service/account setup. Run `sudo station deps full-check`, then
`sudo station deps web-check` and a fresh-session extraction in the owning Zone.
The automatic adapters process public HTML without JavaScript; see
[web limits and profile activation](resources/scrapegraphai/README.md).

```bash
./scripts/station_deps_install.sh --list
sudo ./scripts/station_deps_install.sh --component <id>
station update plan
station update check
sudo ./scripts/station_deps_install.sh --enable-hermes-auto-update
```

See `docs/dependencies/STACK.md` and the [coordinated update contract](docs/operations/COORDINATED_UPDATES.md). The timer only discovers candidates; a reviewed compatible release is required before deployment. Install/readback state is reported separately from repository maturity; no component becomes OPERATIONAL merely because its package or source is present.
