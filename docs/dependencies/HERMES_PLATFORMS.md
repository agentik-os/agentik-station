# Zone-isolated Hermes multi-platform bots

Hermes Messaging Gateway is the common bot protocol and process model for Telegram, Discord, Slack, WhatsApp, Signal, SMS, Email, Home Assistant, Mattermost, Matrix, DingTalk, Feishu/Lark, WeCom, Weixin, BlueBubbles/iMessage, QQ, Yuanbao, Microsoft Teams, LINE, ntfy and browser chat.

Station does not reimplement those adapters. It supplies the isolation and lifecycle wrapper around Hermes native gateway commands.

## Fast path

```bash
# Inspect the exact Zone identity and HERMES_HOME first.
sudo station platform setup \
  --zone organization-alpha-dev \
  --os devops-os \
  --platform slack \
  --plan

# Run Hermes' interactive provider/platform wizard as the Zone Unix user.
sudo station platform setup \
  --zone organization-alpha-dev \
  --os devops-os \
  --platform slack

# Install/start the Hermes user service for that Zone, then observe it.
sudo station os verify --zone organization-alpha-dev --id devops-os
sudo station platform install --zone organization-alpha-dev --os devops-os
sudo station platform start --zone organization-alpha-dev --os devops-os
sudo station setup --zone organization-alpha-dev --os devops-os --probe --json
```

The `--platform` value validates intent and guides the operator; credentials are accepted only by Hermes' own wizard. Aliases such as `teams`, `lark`, `feishu`, `imessage` and `homeassistant` normalize to canonical platform ids.

It is not an adapter filter: native service actions affect the selected Director's
whole gateway and all its configured adapters. Make platform choices inside the
native setup wizard. Station's command result records intent separately.

First install the OS into its Project, then run `station os setup --zone <zone-id>
--id <os-id>` for its model/provider wizard. `--os` resolves the Nano Director from
the root-owned full-team installation ledger; incomplete or conflicting records
fail closed. Different OS teams can have separate Director services, but the same
OS cannot be rebound to another Project in the same Zone. Omitting `--os` selects
the Zone's explicit `default` profile, never a sticky active profile.

## Isolation contract

Every Station invocation uses:

```text
runuser --user <zone-unix-user>
HOME=<zone-state-root>/home
HERMES_HOME=<zone-state-root>/hermes
XDG_RUNTIME_DIR=/run/user/<zone-uid>
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<zone-uid>/bus
/usr/local/bin/hermes --profile <director-or-default> gateway <action>
```

`station platform install` also enables systemd linger for the Zone identity and starts its user manager before asking Hermes to install the service.

The launcher is shared code installed at `/opt/station/tools/hermes/current`; tokens, sessions, pairing data, memory and bot configuration are not shared. Never put platform secrets in `/etc/station`, the Git repository, the shared Hermes code directory or another Zone.

Named profiles remain inside the owning Zone's native Hermes profile tree; they
are not separate Unix sandboxes. The gateway user service is profile-specific
(`hermes-gateway-<profile>.service` for a named Director). `station os setup` uses
`hermes --profile <director> setup`, not the gateway's platform wizard.

After the first platform bot and Tailscale enrollment, Station can render short-lived private setup links instead of asking for secrets in chat. Discord's ephemeral SDK button path is implemented; the `station.guided_setup` card is deliberately provider-neutral for Slack, Telegram and other Hermes adapters. See [`VOICE_AND_GUIDED_SETUP.md`](VOICE_AND_GUIDED_SETUP.md). The first bot token remains human-created because a bot cannot mint its own platform identity.

The current broker's secret forms target the Zone-base environment. Per-Director
credentials still use the selected native wizards; no automatic cross-profile
credential copying is promised. Native `platform status/doctor` commands can run
Hermes startup synchronization. For a pure bounded process observation, use
`station setup --zone <zone-id> --os <os-id> --probe --json`: it calls only systemd
readback, without provider calls, secret reads or service activation.

## Done-when

A successful `gateway status` is only observed process state. Acceptance also requires:

1. outbound message delivery to the intended account/channel;
2. inbound message receipt and correct Zone/profile routing;
3. unauthorized-user and wrong-channel negative tests;
4. restart/reboot persistence;
5. recorded readback evidence without token material.

Bot-to-bot work stays inside Hermes delegation/message-agent mechanisms. Do not create recursive public-platform reply loops.

Official gateway guide: [Hermes Messaging](https://hermes-agent.nousresearch.com/docs/user-guide/messaging).
