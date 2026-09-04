# Isolated discord.js SDK

This resource is for typed Station extensions that must use the Discord API
directly. It is deliberately not a bot runtime and must not start a second
Gateway connection. Hermes owns chat ingress, egress, sessions, voice routing
and platform portability.

Install it through the pinned Station toolchain. Code using it must run under
the owning Zone identity, consume a credential reference rather than a token in
source or argv, obey `config/composio/discord-tool-policy.json`, and record a
readback after every external mutation.
