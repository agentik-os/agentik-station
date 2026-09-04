# Easy Hermes multi-platform bots

Hermes Messaging Gateway is **one background process** that connects your bot to many platforms.

Official surfaces include: Telegram, Discord, Slack, WhatsApp, Signal, SMS, Email, Home Assistant, Mattermost, Matrix, DingTalk, Feishu/Lark, WeCom, Weixin, BlueBubbles/iMessage, QQ, Yuanbao, Microsoft Teams, LINE, ntfy, and browser chat.

Guide: https://hermes-agent.nousresearch.com/docs/user-guide/messaging

## Fast path on Station (`agk-station`)

```bash
sudo -iu agk-station
# 1) Provider + tools (model keys stay host-owned)
hermes setup

# 2) Interactive platform wizard — pick any Hermes-supported platform
hermes gateway setup

# 3) Start the single gateway (all configured platforms)
hermes gateway start
hermes gateway status
```

Then message the bot from that platform. Same conversation can continue in AGK-TUI (`agk` / `station tui`) when session sync is enabled.

## Station rules

- Tokens stay in the owning Hermes profile home (`HERMES_HOME`) — never commit them.
- Discord/Composio remain separate Station modules with their own Doctor gates.
- Bot-to-bot collaboration stays inside Hermes/AGK (see `SETUP.md`); do not recurse Discord auto-replies.
- Claim **READY_FOR_SETUP** after bootstrap; platforms become usable only after gateway setup + live readback.

## Useful commands

| Goal | Command |
|------|---------|
| Configure platforms | `hermes gateway setup` |
| Start / status | `hermes gateway start` / `hermes gateway status` |
| CLI chat | `hermes` |
| Live terminal sessions | `agk` or `station tui` |
| Update Hermes | `./scripts/station_hermes_update.sh update` |
