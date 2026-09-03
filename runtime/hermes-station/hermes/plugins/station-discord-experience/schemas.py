MISSION_PLAN = {
    "name": "station_mission_plan",
    "description": "Create the required structured mission plan before operative work begins.",
    "parameters": {
        "type": "object",
        "required": ["mission_id", "objective", "acceptance", "nodes"],
        "properties": {
            "mission_id": {"type": "string"},
            "objective": {"type": "string"},
            "acceptance": {"type": "array", "items": {"type": "string"}},
            "nodes": {"type": "array", "items": {"type": "object"}}
        }
    }
}
PLAN_UPDATE = {
    "name": "station_plan_update",
    "description": "Revise a persisted mission plan when evidence changes the execution graph.",
    "parameters": {"type":"object","required":["mission_id","reason","nodes"],"properties":{"mission_id":{"type":"string"},"reason":{"type":"string"},"nodes":{"type":"array","items":{"type":"object"}}}}
}
PROGRESS = {
    "name": "station_progress",
    "description": "Update semantic mission/node progress. Do not report every low-level tool call.",
    "parameters": {"type":"object","required":["mission_id","event_type","summary"],"properties":{"mission_id":{"type":"string"},"event_type":{"type":"string"},"node_id":{"type":["string","null"]},"summary":{"type":"string"}}}
}
CLOSE = {
    "name": "station_mission_close",
    "description": "Close a mission with a verified final report state.",
    "parameters": {"type":"object","required":["mission_id","status","outcome"],"properties":{"mission_id":{"type":"string"},"status":{"enum":["done","failed","cancelled"]},"outcome":{"type":"string"},"problems":{"type":"array","items":{"type":"string"}},"artifacts":{"type":"array","items":{"type":"string"}}}}
}
