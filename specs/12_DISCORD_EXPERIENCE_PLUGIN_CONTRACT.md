# Station Discord Experience Hermes Plugin Contract

Plugin id: `station-discord-experience`

## Registered model tools

```text
station_mission_plan
station_plan_update
station_progress
station_blocker
station_verification
station_mission_close
```

These tools update durable Station mission-display state. They do **not** accept arbitrary Discord channel/token destinations from the model.

## Hooks

- `on_session_start`: attach session to an existing host-owned Discord/thread binding when present;
- `pre_tool_call`: enforce plan-first gate on operative/mutating tools;
- `post_tool_call`: append low-level evidence and heartbeat metadata without chat spam;
- Kanban claimed/completed hooks: reconcile graph node state;
- session end: leave durable mission state intact.

## Renderer/transport split

```text
Hermes plugin -> durable mission display state -> Discord Experience Worker -> Discord API
```

The worker resolves guild/channel/message from bootstrap/session bindings owned by Station. The LLM never supplies the destination authority.
