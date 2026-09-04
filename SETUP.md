# Setup and Acceptance Gates

A successful base install means `READY_FOR_SETUP`, not `OPERATIONAL`.

## Gate 1 — Host identity and private connectivity

- enroll the Host in the approved Tailscale network;
- match the observed device identity to the declared `host_id`;
- verify operator SSH access before tightening firewall policy;
- record connectivity evidence;
- never infer readiness from the presence of the `tailscale` binary.

## Gate 2 — Hermes runtime/compiler

- install an approved Hermes version through the release-ring workflow;
- assign an independent `HERMES_HOME` to each Zone;
- compile AGK OS definitions into Hermes Profile Distributions, profiles/Bots, Skills, plugins, MCP/tool filters, boards, cron, and gateway bindings;
- configure Project `cwd` and allowed roots;
- enable Ponytail only for Builder/DevOps/engineering profiles that require it;
- run Hermes Doctor and `hermes plugins doctor ... --ci` for Station plugins;
- execute Zone-boundary negative tests;
- store receipts/evidence before raising readiness.

Until this exists, desired OS packages remain `NOT_INSTALLED`.

## Gate 3 — GitHub and coding executors

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

- enroll one dedicated Nano Director Discord bot identity and token;
- provision the dedicated channel, roles, permissions, commands, pins, and bindings;
- grant temporary bootstrap administration only for the provisioning transaction;
- remove administration and verify least-privilege runtime permissions;
- configure semantic Mission Progress Cards instead of raw tool noise;
- use Components V2-compatible layouts, short action labels, select menus/modals for complex input, and linked details/evidence/graphs;
- verify command registration, message creation/edit, interactions, authorization, rate-limit recovery, and external readback in a test guild;
- keep Bot-to-Bot collaboration inside Hermes/AGK rather than recursive Discord auto-replies.

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

```bash
sudo -iu agk-station
hermes setup
hermes gateway setup    # pick any supported platform
hermes gateway start
hermes gateway status
```

Details: `docs/dependencies/HERMES_PLATFORMS.md` and https://hermes-agent.nousresearch.com/docs/user-guide/messaging

Keep tokens in `HERMES_HOME`. Do not claim OPERATIONAL for a platform until live message readback passes.

## Gate — Optional dependency stack

Langfuse, Honcho, Hindsight, Ponytail, Crawl4AI, TigerVNC are declared in `config/deps/stack.yaml`.

```bash
./scripts/station_deps_install.sh --list
sudo ./scripts/station_deps_install.sh --component <id>
./scripts/station_hermes_update.sh update
sudo ./scripts/station_deps_install.sh --enable-hermes-auto-update
```

See `docs/dependencies/STACK.md`. These remain SCAFFOLDED until component Doctor/readback.
