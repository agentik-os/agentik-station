# Setup and Acceptance Gates

A successful base install means `READY_FOR_SETUP`, not `OPERATIONAL`.

## Gate 1 — Host identity and private connectivity

- enroll the Host in the approved Tailscale network;
- match the observed device identity to the declared `host_id`;
- verify operator SSH access before tightening firewall policy;
- record connectivity evidence;
- never infer readiness from the presence of the `tailscale` binary.

## Gate 2 — Hermes runtime/compiler

- install the approved Hermes release/commit through the release-ring workflow;
- keep shared executable code in `/opt/station/tools/hermes/current` and never store Zone credentials there;
- assign an independent `HERMES_HOME` to each Zone;
- compile AGK OS definitions into Hermes Profile Distributions, profiles/Bots, Skills, plugins, MCP/tool filters, boards, cron, and gateway bindings;
- configure Project `cwd` and allowed roots;
- enable Ponytail only for Builder/DevOps/engineering profiles that require it;
- run Hermes Doctor and `hermes plugins doctor ... --ci` for Station plugins;
- execute Zone-boundary negative tests;
- store receipts/evidence before raising readiness.

Until this exists, desired OS packages remain `NOT_INSTALLED`.

## Gate 3 — GitHub and coding executors

- run `station deps toolchain-check` and compare observed versions with `config/versions.lock`;
- authenticate GitHub CLI with `gh auth login`, then verify with `gh auth status`;
- authenticate Vercel only where deployment is required, then verify with `vercel whoami`;
- authenticate Composio with `composio login`, install its native agent integration with `composio setup --target auto`, and verify only the declared connections;
- sign in to Codex through its current interactive flow; never copy a personal token into a shared Zone;
- bind each Project only to its declared repositories;
- use development/staging credentials by default;
- keep production mutation behind explicit approval;
- verify actual read/write scope with safe probes;
- map executor-neutral roles to available Hermes/Codex/Claude executors;
- require observed tests/review/CI before merge-readiness claims.

## Gate 4 — Composio connected capability plane

- map a stable Station principal to the correct organization and Zone;
- configure only declared toolkits and connected accounts;
- never use a generic production principal;
- validate `available → authenticated → scoped → verified_ready`;
- use sessions/MCP/triggers through the Station capability policy;
- route triggers through Station ingress, context resolution, and mission policy;
- prove cross-Zone and cross-account isolation with negative tests.

## Gate 5 — Dedicated Discord OS bots

For every OS instance that is actually installed:

- have a human server owner create one dedicated Nano Director Discord application/bot, authorize it to the guild, and retain control of token rotation;
- enter the token only through `station platform setup --zone <zone-id> --platform discord` (the Zone-isolated Hermes wizard), never a CLI argument or Git file;
- provision the dedicated channel, roles, permissions, commands, pins, and bindings;
- grant temporary bootstrap administration only for an approved maintenance window and only when narrower permissions are insufficient;
- require the human server owner to remove the elevation, then read back and verify least-privilege runtime permissions;
- configure semantic Mission Progress Cards instead of raw tool noise;
- use Components V2-compatible layouts, short action labels, select menus/modals for complex input, and linked details/evidence/graphs;
- verify command registration, message creation/edit, interactions, authorization, rate-limit recovery, and external readback in a test guild;
- keep Bot-to-Bot collaboration inside Hermes/AGK rather than recursive Discord auto-replies.

The bot token cannot create other Discord applications or mint their tokens. Release 11.12 does not yet claim the full guild topology provisioner is externally accepted; use a test guild and keep the module `INSTALLABLE` until its create/edit/permission/command/readback gate passes.

## Gate 6 — Backup and recovery

- choose and configure an encrypted off-Host backup provider;
- define per-Zone inclusion/exclusion and retention;
- snapshot desired state, Project assets, runtime databases, Hermes state, and required evidence without exporting unrelated secrets;
- destroy a disposable target and restore it;
- rebind external credentials/accounts safely;
- run Doctor and fresh-session acceptance after restore;
- only then claim recovery readiness.

## Gate 7 — Fresh-session acceptance

Every persistent automation starts disabled.

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

Use the owning Zone, not the global operator home:

```bash
sudo station platform setup --zone organization-alpha-dev --platform slack
sudo station platform install --zone organization-alpha-dev
sudo station platform start --zone organization-alpha-dev
sudo station platform status --zone organization-alpha-dev
sudo station platform doctor --zone organization-alpha-dev
```

Add `--plan` to any of these commands to inspect the exact `runuser`/`HERMES_HOME` invocation before execution. `setup` opens Hermes' interactive gateway wizard; the platform flag validates operator intent and includes it in the emitted result, but tokens are entered only through Hermes. `install` enables linger and starts the Zone's systemd user manager so the gateway survives logout/reboot.

Details: `docs/dependencies/HERMES_PLATFORMS.md` and https://hermes-agent.nousresearch.com/docs/user-guide/messaging

Keep tokens in the Zone's dedicated `HERMES_HOME`. Do not claim OPERATIONAL for a platform until bidirectional live message readback passes.

## Gate — Optional dependency stack

Langfuse, Honcho, Hindsight, Ponytail, Crawl4AI, TigerVNC are declared in `config/deps/stack.yaml`.

```bash
./scripts/station_deps_install.sh --list
sudo ./scripts/station_deps_install.sh --component <id>
./scripts/station_hermes_update.sh update
sudo ./scripts/station_deps_install.sh --enable-hermes-auto-update
```

See `docs/dependencies/STACK.md`. Install/readback state is reported separately from repository maturity; no component becomes OPERATIONAL merely because its package or source is present.
