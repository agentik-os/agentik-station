# Shared Hermes runtime

The shared runtime installation is intentionally explicit and must run as root:

```bash
sudo agk-terminal hermes install-shared
```

It performs the following guarded sequence:

1. Back up each `~/.hermes`, `~/.agentik`, gateway unit, and Discord state
   manifest below `/srv/agk/migrations/<timestamp>`.
2. Install official Hermes in `/opt/agk-terminal/hermes-agent` from the
   NousResearch repository and verify its Git origin.
3. Install the official pinned Discord dependencies, web/TUI bundles and one
   shared Chrome engine for browser tools.
4. Synchronize the AGK plugins, Master OS Builder and built-in Hermes skills.
5. Point gateway/headless services at the official virtual environment.
6. Restart only services that were already active and verify they stay active.
7. Preserve existing live-session dependencies until RMUX no longer maps them.

Configuration, sessions, memories, Discord thread mappings, gateway recovery
databases, and credentials are user data. They are never deleted during a
clean software reinstall.
