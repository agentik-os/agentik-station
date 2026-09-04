# Conversation continuity

AGK treats the Hermes session ID as the durable identity of a conversation.
Discord, the terminal and the AGK registries are views over that identity; they
do not copy transcripts into separate stores.

```text
                         Hermes state.db
                    canonical conversation ID
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
     Discord bot          AGK Sessions         AGK Agents
   profile command UI    profile conversations  agent-profile conversations
          │                    │                    │
          └────────────── Hermes turn lease ───────┘
```

## Continue a terminal conversation on Discord

From a Hermes terminal conversation, run:

```text
/handoff discord
```

Hermes binds the current conversation to the profile's Discord bot. The next
message sent through Discord continues with the same history and memory.

If the terminal is no longer available, open the bot's `/panel`, choose
**Sessions**, then select one of the recent conversations. AGK validates that
the Discord caller is an authorized profile administrator before it exposes
cross-platform sessions. The selector uses the protected Hermes
`/resume --all` path and never displays tool, cron, hidden or archived runs.
During profile synchronization, AGK promotes only the numeric identities
already present in that profile's `DISCORD_ALLOWED_USERS` to explicit DM and
group slash administrators. This satisfies Hermes' cross-origin protection
without sharing an identity list with another profile.

## Continue a Discord conversation in AGK

Open **Sessions** in AGK. Active Discord and other supported messaging
conversations from the current Hermes profile appear beside RMUX sessions as
resumable entries. Press `Enter`: AGK creates a durable RMUX terminal wrapper,
starts Hermes with the same native session ID and focuses the provider input.

Named specialist-profile conversations are also grouped under **Agents**.
Select an agent, press `Enter` to see its conversations, then press `Enter` on
the desired conversation. `n` creates a dedicated new conversation for that
agent. Read-only messaging history is never deleted by `x`; only an active
AGK/RMUX wrapper can be stopped and archived.

Hermes' turn lease serializes competing writes. A conversation may therefore
be visible on several surfaces, but only one turn is executed at a time.

## Profile isolation and new bots

Every bot is configured against a `profile_id`, not a Linux username. A main
profile uses `~/.hermes/state.db`; a named agent profile uses
`~/.hermes/profiles/<profile>/state.db`. Future bots and catalog agents inherit
the same session selector, authorization checks, UI-only command mode and
quiet restart policy when synchronized by the AGK installer.

The boundaries remain strict:

- Operator, Agentik, Mission and Private do not share conversation stores.
- Named profiles do not expose their sessions through another profile's bot.
- Provider tokens and Discord tokens stay in the owning profile's home.
- The session picker returns at most 100 recent eligible conversations and
  uses stable identifiers rather than mutable display names.

## Gateway notifications

Routine gateway shutdown and online messages are disabled. A system watchdog
checks all configured profile gateways every minute. If one remains unhealthy
for ten continuous minutes, it sends exactly one alert to the Operator bot's
Discord `#general` channel. Recovery is silent, and a later outage can create a
new alert only after the gateway became healthy in between.

Inherited named-profile bot configuration is not mistaken for a separate bot:
a profile is monitored after its gateway has written `gateway_state.json`, or
when provisioning explicitly sets Discord
`extra.offline_alert_enabled: true` before the first start.

The watchdog stores only outage timing and notification state in
`/var/lib/agk-terminal/gateway-watchdog.json`; it never writes bot tokens to
logs or state files.
