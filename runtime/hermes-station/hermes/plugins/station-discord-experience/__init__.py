from __future__ import annotations

import os

from . import schemas, state, tools

SAFE_BEFORE_PLAN = {
    "station_mission_plan",
    "skill_view",
    "memory",
    "read_file",
    "list_files",
    "search_files",
}
MUTATING_HINTS = (
    "write",
    "edit",
    "delete",
    "send",
    "deploy",
    "create",
    "update",
    "execute",
    "terminal",
    "shell",
    "discord_admin",
    "apply",
    "merge",
)


def _is_mutating(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return any(hint in lowered for hint in MUTATING_HINTS)


def _pre_tool(tool_name=None, args=None, task_id=None, **kwargs):
    """Hermes pre_tool_call hook.

    The pinned runtime adapter must inject STATION_CURRENT_MISSION_ID. Operative
    mutation fails closed when mission context or a plan is unavailable.
    """
    name = str(tool_name or "")
    if name in SAFE_BEFORE_PLAN or not _is_mutating(name):
        return None
    mission_id = os.environ.get("STATION_CURRENT_MISSION_ID", "").strip()
    if not mission_id:
        return {
            "action": "block",
            "message": "Station mission context is unresolved; mutating work is blocked until a Mission is bound.",
        }
    if not state.load(mission_id):
        return {
            "action": "block",
            "message": "Plan-first gate: call station_mission_plan before operative or mutating work.",
        }
    return None


def register(ctx):
    ctx.register_tool(
        name="station_mission_plan",
        toolset="station-experience",
        schema=schemas.MISSION_PLAN,
        handler=tools.mission_plan,
    )
    ctx.register_tool(
        name="station_plan_update",
        toolset="station-experience",
        schema=schemas.PLAN_UPDATE,
        handler=tools.plan_update,
    )
    ctx.register_tool(
        name="station_progress",
        toolset="station-experience",
        schema=schemas.PROGRESS,
        handler=tools.progress,
    )
    ctx.register_tool(
        name="station_mission_close",
        toolset="station-experience",
        schema=schemas.CLOSE,
        handler=tools.close,
    )
    ctx.register_hook("pre_tool_call", _pre_tool)
