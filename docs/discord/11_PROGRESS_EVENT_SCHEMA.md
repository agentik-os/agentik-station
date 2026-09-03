# Mission Progress Event Schema

Canonical event envelope:

```json
{
  "event_version": "1.0",
  "event_id": "evt_...",
  "mission_id": "mis_...",
  "os_id": "...",
  "profile_id": "...",
  "session_id": "...",
  "event_type": "node_completed",
  "node_id": "verify",
  "status": "running",
  "summary": "Verification suite passed.",
  "plan_revision": 2,
  "loop": {"id": "gauntlet", "round": 1, "max_rounds": 3},
  "evidence_refs": [],
  "timestamp": "RFC3339"
}
```

Events are append-only evidence. The Discord message is a replaceable projection produced from current durable state.
