# AGK Discord control-center patchset

This user plugin shadows Hermes' bundled `discord` plugin. It preserves the
Agentik bot mappings and interactive `/panel`, `/account`, and `/clear`
controls while the official Hermes repository does not provide them.

This compatibility layer is maintained directly in AGK-TUI and validated
against the shared official Hermes runtime during installation.

No Discord token, guild ID, channel ID, thread mapping, account credential, or
gateway state is stored here. Those remain per-user data under `~/.hermes` and
are preserved by every installation and runtime refresh.
