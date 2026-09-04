# Dedicated OS Bot Topology

Canonical rule:

```text
1 installed OS
 -> 1 Nano Director Hermes Profile/Bot
 -> 1 dedicated Discord application/bot identity
 -> 1 primary OS channel
 -> slash commands + how-to surface
```

Internal NanoTeam specialists are not separate Discord applications by default.

## Wake path

```text
OS channel/thread
  + @DedicatedOSBot
  -> Hermes session
  -> Nano Director
  -> plan-first gate
  -> mission when operative work is required
```

## Bootstrap reality

The desired Station provisioner creates/adopts guild structure, roles, channels, permissions, command registration and bindings after credentials are enrolled. Discord application creation/token enrollment remains an explicit human-controlled step unless a separately authorized application-management process is introduced. In release 11.12 the complete provisioner still requires external test-guild acceptance and is not `OPERATIONAL`.

Temporary broad bootstrap permission is granted and later removed by the server owner. Station must read back least-privilege runtime permissions; the bot is not trusted to demote its own highest/equal role.


## Hermes gateway deployment

Each OS Nano Director is a distinct Hermes profile with its own Discord token. On a Station with many OSs, Hermes multiplexed gateway mode may be used to serve many profiles from one gateway process while preserving per-profile config, secrets, sessions and token identity. Unique Discord tokens remain mandatory per profile.

## Cross-OS collaboration

Do **not** make dedicated Hermes Discord bots reply to each other in Discord. Keep Discord bot-to-bot ingress disabled by default to avoid mention/reply loops. Cross-OS work is orchestrated internally through AGK/Hermes team communication, missions and capability contracts; Discord shows the human-facing result/progress only.
