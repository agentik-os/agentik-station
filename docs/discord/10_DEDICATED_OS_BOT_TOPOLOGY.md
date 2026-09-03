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

Station can provision guild structure, roles, channels, permissions, command registration and bindings after credentials are enrolled. Discord application creation/token enrollment remains an explicit secure provisioning step unless an external authorized application-management process is introduced.


## Hermes gateway deployment

Each OS Nano Director is a distinct Hermes profile with its own Discord token. On a Station with many OSs, Hermes multiplexed gateway mode may be used to serve many profiles from one gateway process while preserving per-profile config, secrets, sessions and token identity. Unique Discord tokens remain mandatory per profile.

## Cross-OS collaboration

Do **not** make dedicated Hermes Discord bots reply to each other in Discord. Keep Discord bot-to-bot ingress disabled by default to avoid mention/reply loops. Cross-OS work is orchestrated internally through AGK/Hermes team communication, missions and capability contracts; Discord shows the human-facing result/progress only.
