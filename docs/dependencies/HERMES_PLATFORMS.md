# Connect an OS instance to Hermes messaging

An instance's Director is its default human-facing bot. Hermes owns messaging,
sessions and agent execution; Station selects the owning Zone, instance and
profile. Projects are optional work targets, **not containers for clients or OS
instances**. Client-owned instances and Projects are siblings inside a Zone.

Discord, Telegram, Slack and the other [Hermes platforms](https://hermes-agent.nousresearch.com/docs/user-guide/messaging)
use the same Station lifecycle. `--platform` records the intended platform; it
does not filter the wizard or restrict a service to one adapter. Select the
platform inside Hermes. Service actions affect that profile's entire gateway.

## Which bot are you connecting?

| Station selection | Runtime selected | What it does not mean |
| --- | --- | --- |
| `--zone dev --instance engineering` | Atlas, the mapped DevOps Director in the installed `engineering` instance | No system-wide sudo or automatic access to other Zones |
| `--zone discord-bootstrap` | That System Zone's explicit `default` profile | Not an installed `discord-bootstrap-os` instance or its named Director |
| `--zone discord-bootstrap --instance control` | The Director of `control`, **if that instance was explicitly installed** | No automatically created bot application, guild or Administrator grant |
| `--zone acme-dev --instance engineering` | The client's own installed instance | No inheritance of Agentik's bot token or provider accounts |

Omitting both `--instance` and legacy `--os` always selects Zone `default`, not
Hermes' sticky active profile. `--os` remains for existing schema-2 Project-bound
runtimes only; this guide does not migrate or adopt them. See the
[instance contract](../organization/05_OS_INSTANCES.md) and
[System Bootstrap OS](../os/07_CONTROL_BOOTSTRAP_OS.md).

## Keep the existing first Station bot in `discord-bootstrap / default`

If the first bot token is already in
`/var/lib/station/zones/discord-bootstrap/hermes/.env`, keep that existing route.
Do not print the file, paste its contents into chat, copy the token into Atlas,
or install a second gateway with that identity. This is the System Zone's native
`default` profile, separate from both an installed control instance and Atlas.

Inspect the scope without reading secrets:

```bash
sudo station setup --zone discord-bootstrap --json
sudo station platform setup --zone discord-bootstrap --platform discord --plan
```

The plan must show `z-system-discord`, the Zone's canonical home and
`--profile default`. If model/provider enrollment is needed, use the explicit
native command below: there is no public `station platform configure` action.
This Bash example also opens the platform wizard and configures a nonsecret
channel ACL. Replace the placeholder first; retain the existing bot identity
unless deliberately rotating its token.

```bash
set -euo pipefail
station_discord_channel='REPLACE_WITH_NUMERIC_CHANNEL_ID'
[[ "$station_discord_channel" =~ ^[0-9]{5,24}$ ]]
station_bootstrap_hermes() (
  cd /
  sudo /usr/sbin/runuser --user z-system-discord -- /usr/bin/env -i \
    HOME=/var/lib/station/zones/discord-bootstrap/home \
    HERMES_HOME=/var/lib/station/zones/discord-bootstrap/hermes \
    PATH=/usr/local/bin:/usr/bin:/bin \
    /usr/local/bin/hermes --profile default "$@"
)
# If the intended model/provider is already enrolled, skip this setup command.
station_bootstrap_hermes setup
# Select Discord, explicit numeric human IDs, and the intended home channel.
# Decline all early service install/start/restart offers, including at entry.
sudo station platform setup --zone discord-bootstrap --platform discord
station_bootstrap_hermes config set discord.allowed_channels "[\"$station_discord_channel\"]"
station_bootstrap_hermes config get discord.allowed_channels --json
unset -f station_bootstrap_hermes
unset station_discord_channel
```

Follow the identity, intent, human-allowlist and environment-override precautions
in the Discord steps below. A YAML readback alone does not prove the effective
ACL. Never replace a known existing token just to repeat setup; any required
entry belongs only in the native masked token prompt.

After configuration, check the default profile and then install/start its service:

```bash
sudo station platform doctor --zone discord-bootstrap
sudo station platform install --zone discord-bootstrap --plan
sudo station platform install --zone discord-bootstrap
sudo station platform start --zone discord-bootstrap
```

Stop on Doctor failures; it invokes native Hermes and can synchronize startup
resources, unlike the read-only setup report. If the gateway was already running,
use `station platform restart --zone discord-bootstrap` after configuration and
checks. The current `station setup --probe` does not probe this unbound Zone-base
gateway; it remains `NOT_PROBED` without an eligible OS runtime. For bounded,
read-only service-state evidence, run this separate Bash command:

```bash
set -euo pipefail
station_discord_uid="$(id -u z-system-discord)"
[[ "$station_discord_uid" =~ ^[0-9]+$ ]]
(
  cd /
  sudo /usr/bin/timeout 10 /usr/sbin/runuser --user z-system-discord -- /usr/bin/env -i \
    HOME=/var/lib/station/zones/discord-bootstrap/home \
    XDG_RUNTIME_DIR="/run/user/$station_discord_uid" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$station_discord_uid/bus" \
    PATH=/usr/local/bin:/usr/bin:/bin \
    /usr/bin/systemctl --user show hermes-gateway.service \
    --property=LoadState,ActiveState,SubState,UnitFileState --no-pager
)
unset station_discord_uid
```

`station platform status --zone discord-bootstrap` is also available, but invokes
native Hermes rather than this pure systemd readback. Neither proves delivery.
Prove real inbound/outbound delivery and wrong-user/wrong-channel denial
before calling this bot ready. No instance verification ledger is created for
this Zone-base route: `discord-bootstrap-os` can still be `NOT_INSTALLED`, and the
bot does not acquire Linux sudo or guild Administrator. Connecting Atlas later
is a separate, explicit enrollment using the next section, not a credential move.

## Separate instance bot: Atlas in `dev / engineering`

This example requires that `dev` and the `engineering` instance already exist.
Inspect them first; do not rerun Host bootstrap to add a bot:

```bash
sudo station os instance show --zone dev --instance engineering
sudo station setup --zone dev --instance engineering --json
sudo station os instance setup --zone dev --instance engineering --plan
sudo station os instance setup --zone dev --instance engineering
```

The last command opens the selected Director's model/provider wizard. Enroll
only its intended account; separately verify any specialist accounts needed for
delegation. Do not copy credentials between profiles, instances or Zones.

### 1. Create and invite the Discord identity

A human server owner creates the application in the
[Discord Developer Portal](https://discord.com/developers/applications), retains
control of token rotation, and authorizes its bot to the intended server. Use
Guild Install with the `bot` and `applications.commands` scopes. Keep the bot
token out of chat, screenshots, shell arguments and Git; enter it in the masked
Hermes prompt in step 2. Follow Discord's
[application and installation guide](https://docs.discord.com/developers/quick-start/getting-started).

Start with channel-scoped View Channel, Send Messages, Read Message History,
Embed Links and Attach Files. Add reactions or thread permissions only for the
features you use; add Connect and Speak for voice channels. Runtime
Administrator is not required. Creating other bot applications and generating
their tokens remain human account operations, not powers granted by a bot token.

Enable **Message Content Intent**. At the pinned Hermes revision, Server Members
Intent is needed for username or role-based admission; numeric user-ID allowlists
alone do not require it. Presence Intent is not needed. Check Discord's current
privileged-intent eligibility requirements before a broader deployment. Evidence:
[Discord intents](https://docs.discord.com/developers/events/gateway#privileged-intents)
and the [pinned Hermes adapter](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/plugins/platforms/discord/adapter.py).

### 2. Enter the token and human allowlist in the correct profile

```bash
sudo station platform setup --zone dev --instance engineering --platform discord --plan
sudo station platform setup --zone dev --instance engineering --platform discord
```

Check that the plan selects Zone user `z-agentik`, the `engineering` instance's
Hermes home and Atlas's mapped profile. In the native wizard:

1. Choose Discord.
2. Enter the token only at the masked bot-token prompt.
3. Enter explicit numeric Discord user IDs for authorized humans. Do not leave
   the allowlist empty or enable wildcard/allow-all access. Keep bot admission
   disabled (`DISCORD_ALLOW_BOTS=none`) for the normal Director topology.
4. Choose the home channel for notifications. This is **not** a channel ACL.
5. Finish configuration with **Done**, then decline gateway installation,
   start or restart offers. Also decline any start offer at wizard entry.

The native wizard can offer service actions before Station's verification gate.
Keep the order **configure → verify → install → start**. Its empty-allowlist hint
is not an authorization guarantee; use explicit IDs and the negative tests below.
These behaviors are revision-specific: see the
[pinned Discord setup](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/plugins/platforms/discord/adapter.py)
and [gateway wizard](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/gateway.py).

### 3. Restrict the channel separately

Keep both an explicit human allowlist and an explicit channel allowlist. The home
channel controls notifications, not admission. Channel-only authorization can
admit other humans in that channel; it does not replace a user allowlist. Direct
messages have their own authorization path and must be tested separately if used.

For the exact `dev / engineering` layout above, this Bash snippet resolves Atlas
from the trusted instance ledger and writes only the nonsecret channel setting.
Replace the placeholder with the intended numeric channel ID. For another Zone,
resolve its own user, home and instance paths from its platform plan; do not reuse
these Agentik paths for a client.

```bash
set -euo pipefail
station_discord_channel='REPLACE_WITH_NUMERIC_CHANNEL_ID'
[[ "$station_discord_channel" =~ ^[0-9]{5,24}$ ]]
station_atlas_profile="$(sudo station os instance show --zone dev --instance engineering | jq -er '.role_profile_map.atlas')"
[[ "$station_atlas_profile" =~ ^i-[a-z0-9-]+-atlas$ ]]

station_atlas_config() (
  cd /
  sudo /usr/sbin/runuser --user z-agentik -- /usr/bin/env -i \
    HOME=/var/lib/station/zones/dev/home \
    HERMES_HOME=/var/lib/station/zones/dev/os-instances/engineering/hermes \
    PATH=/usr/local/bin:/usr/bin:/bin \
    /usr/local/bin/hermes --profile "$station_atlas_profile" config "$@"
)
station_atlas_config set discord.allowed_channels "[\"$station_discord_channel\"]"
station_atlas_config get discord.allowed_channels --json
unset -f station_atlas_config
unset station_atlas_profile station_discord_channel
```

This uses the pinned native
[config set/get interface](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/config.py).
The readback proves the YAML value, **not** absence of an environment or managed
policy override. In an existing profile, review `DISCORD_ALLOWED_CHANNELS`, user
and role admission overrides locally without dumping its secret environment;
resolve conflicts through the owning policy instead of forcing a write. A
wrong-channel negative test is still required before acceptance.

### 4. Verify, install, start and observe

Only after the identity, human allowlist and channel restrictions are configured:

```bash
sudo station os instance verify --zone dev --instance engineering
sudo station platform install --zone dev --instance engineering --plan
sudo station platform install --zone dev --instance engineering
sudo station platform start --zone dev --instance engineering
sudo station setup --zone dev --instance engineering --probe --json
```

Stop if verification fails; do not force through it. A configuration change
invalidates previous verification, so verify again before service actions. For an
already-running gateway, use `station platform restart` with the same selectors
after verification. `install` enables linger and starts the Zone's systemd user
manager before installing the profile-specific native service. Station explicitly
passes `--no-start-now --start-on-login`: the native headless CLI would otherwise
start immediately. Use the separate `platform start` action after verification.
Installing over an already-running service does not stop it.
Starting a previously stopped user manager may also activate its already-enabled
units. For an existing unchanged unit, verify `UnitFileState=enabled` explicitly:
the pinned native installer can leave a previously disabled current unit disabled.

`station setup --probe` is a bounded systemd observation: it does not start Hermes,
authenticate a provider or prove Discord delivery. Native `platform status/doctor`
can run Hermes startup synchronization and are not the pure local setup report.

### 5. Accept the real route

A running service is not `OPERATIONAL`. Record evidence without credential data:

1. Match the bot, server and channel IDs to the intended Zone, instance and
   Director; verify one inbound message and its outbound reply.
2. Use a mention such as `@Atlas` where the configured mention gate requires it.
   Complete one small, approved team mission and verify its result and role route.
3. Prove that an unauthorized user, a wrong channel and an unrelated bot cannot
   trigger work. Test direct-message admission separately if it is enabled.
4. Verify registered commands and any buttons, attachments or voice features you
   actually expose, including the required scoped permissions.
5. Verify restart/reboot persistence and read back the final permissions in Discord.

Specialists normally remain internal Hermes delegates. Give a specialist a
separate bot only for an explicitly approved topology, using its canonical
`--role` and a separate token. Never run two gateways with one token or create
recursive public-platform bot reply loops.

## Runtime boundaries and guided setup

Station launches the shared Hermes code as the owning Zone Unix user. The Zone
keeps its canonical `HOME`; a named instance gets its own `HERMES_HOME`, and the
trusted role map selects the Director's native profile. Profile-specific gateway
services namespace configuration and sessions, **not Unix authority**. Instances
in one Zone share its UID and may share CLI account state through Zone `HOME`;
they are not separate filesystem or account sandboxes. Clients requiring a hard
boundary must use separate Zones.

Never place platform credentials in `/etc/station`, Git, shared Hermes code or
another Zone. A Discord token grants no Linux sudo authority and no automatic
rights over another instance. Any exceptional guild-provisioning elevation needs
an explicit maintenance approval, human removal and least-privilege readback.

After the first bot and Tailscale enrollment, supported Station chat surfaces can
offer short-lived private setup links. Installing the broker alone does not give
every native Director the AGK account picker. The current secret forms target
**Zone-base** credentials, not named instance/profile enrollment: use the selected
native wizards above for those, with no automatic credential copying. See
[`VOICE_AND_GUIDED_SETUP.md`](VOICE_AND_GUIDED_SETUP.md) for implemented surfaces
and remaining live acceptance gates.
