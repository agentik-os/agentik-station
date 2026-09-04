# Zone-isolated Hermes multi-platform bots

Hermes Messaging Gateway is the common bot protocol and process model for Telegram, Discord, Slack, WhatsApp, Signal, SMS, Email, Home Assistant, Mattermost, Matrix, DingTalk, Feishu/Lark, WeCom, Weixin, BlueBubbles/iMessage, QQ, Yuanbao, Microsoft Teams, LINE, ntfy and browser chat.

Station does not reimplement those adapters. It supplies the isolation and lifecycle wrapper around Hermes native gateway commands.

## Fast path

```bash
# Inspect the exact Zone identity and HERMES_HOME first.
sudo station platform setup \
  --zone organization-alpha-dev \
  --platform slack \
  --plan

# Run Hermes' interactive provider/platform wizard as the Zone Unix user.
sudo station platform setup \
  --zone organization-alpha-dev \
  --platform slack

# Install/start the Hermes user service for that Zone, then observe it.
sudo station platform install --zone organization-alpha-dev
sudo station platform start --zone organization-alpha-dev
sudo station platform status --zone organization-alpha-dev
sudo station platform doctor --zone organization-alpha-dev
```

The `--platform` value validates intent and guides the operator; credentials are accepted only by Hermes' own wizard. Aliases such as `teams`, `lark`, `feishu`, `imessage` and `homeassistant` normalize to canonical platform ids.

## Isolation contract

Every Station invocation uses:

```text
runuser --user <zone-unix-user>
HOME=<zone-state-root>/home
HERMES_HOME=<zone-state-root>/hermes
XDG_RUNTIME_DIR=/run/user/<zone-uid>
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<zone-uid>/bus
/usr/local/bin/hermes gateway <action>
```

`station platform install` also enables systemd linger for the Zone identity and starts its user manager before asking Hermes to install the service.

The launcher is shared code installed at `/opt/station/tools/hermes/current`; tokens, sessions, pairing data, memory and bot configuration are not shared. Never put platform secrets in `/etc/station`, the Git repository, the shared Hermes code directory or another Zone.

## Done-when

A successful `gateway status` is only observed process state. Acceptance also requires:

1. outbound message delivery to the intended account/channel;
2. inbound message receipt and correct Zone/profile routing;
3. unauthorized-user and wrong-channel negative tests;
4. restart/reboot persistence;
5. recorded readback evidence without token material.

Bot-to-bot work stays inside Hermes delegation/message-agent mechanisms. Do not create recursive public-platform reply loops.

Official gateway guide: [Hermes Messaging](https://hermes-agent.nousresearch.com/docs/user-guide/messaging).
