# Hermes Discord Gateway in Station

Hermes supplies the Discord gateway/session/tooling primitive. Station does not fork the gateway merely to improve presentation.

Canonical Station behavior:

- one dedicated Discord bot per installed canonical OS;
- bot maps to that OS Nano Director profile;
- server-channel wake path uses @mention unless explicitly configured otherwise;
- threads are Hermes conversation/session surfaces;
- raw tool progress/reasoning is quiet by default;
- Station Discord Experience plugin projects structured mission state into one editable Components V2 progress card;
- Hermes logs retain low-level execution evidence;
- Discord admin toolset is bootstrap/operator-scoped, never normal agent entitlement.

Use `19_DISCORD_EXPERIENCE/` as the product UX contract.
