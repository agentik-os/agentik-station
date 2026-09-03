# Hermes Display Policy for Discord

Hermes remains the execution kernel. Station changes only the human projection.

## Default dedicated OS-bot policy

```yaml
display:
  platforms:
    discord:
      tool_progress: log
      interim_assistant_messages: false
      show_reasoning: false
      show_commentary: false
      cleanup_progress: true
      busy_ack_detail: false
      long_running_notifications: false
```

The Station Mission Progress Controller owns the semantic live card.

## Why

Raw tool breadcrumbs are useful for debugging but poor default product UX. Hermes logs remain the audit source. Station subscribes to Hermes lifecycle hooks and explicit mission-plan/progress events, then projects only meaningful mission changes into Discord.

## Native capabilities we still use

- Hermes sessions and Discord gateway;
- native message-edit capable surface;
- gateway/plugin hooks;
- logs and tool traces;
- Kanban events;
- plugin tools and slash commands;
- native streaming can be enabled for special debug profiles, but is off for the canonical mission card path.

## Debug escape hatch

Authorized operators can enable a debug view per session without changing the public UX contract. Debug output belongs in a dedicated diagnostics channel or ephemeral/operator-only interaction whenever possible.
