"""Agentik OS business command layer.

Hermes remains the runtime. This plugin owns the persistent business objects
and their command grammar without adding model-tool schema to the core.
"""

from __future__ import annotations

from .commands import AgentikCommandService
from .runtime_tool import RUNTIME_TOOL_SCHEMA, handle_runtime, runtime_available
from .agent_registry import AGENT_TOOL_SCHEMA, AgentCommandService, agent_router_prompt, handle_agent
from .rules import rules_prompt
from .scrapegraph_tool import SCRAPEGRAPH_TOOL_SCHEMA, handle_scrapegraph


def register(ctx) -> None:
    service = AgentikCommandService.from_runtime()
    for name in service.command_names:
        ctx.register_command(
            name,
            handler=service.handler(name),
            description=service.description(name),
            args_hint="<action> [target] [options]",
        )
    ctx.register_tool(
        name="agentik_runtime",
        toolset="terminal",
        schema=RUNTIME_TOOL_SCHEMA,
        handler=handle_runtime,
        check_fn=runtime_available,
        description="Persistent per-user Hermes, Claude and Codex orchestration through AGK/RMUX.",
        emoji="🧭",
    )
    agent_service = AgentCommandService()
    ctx.register_command(
        "agent",
        handler=agent_service.dispatch,
        description="List and operate specialized agents through durable AGK/RMUX sessions.",
        args_hint="list|start|status|message|logs <agent> [instruction]",
    )
    ctx.register_tool(
        name="agentik_agent",
        toolset="terminal",
        schema=AGENT_TOOL_SCHEMA,
        handler=handle_agent,
        check_fn=runtime_available,
        description="Specialized Hermes agents backed by persistent AGK/RMUX runtimes.",
        emoji="🤖",
    )
    ctx.register_tool(
        name="station_scrapegraph",
        toolset="web-research",
        schema=SCRAPEGRAPH_TOOL_SCHEMA,
        handler=handle_scrapegraph,
        description="Zone-local, bounded HTTP(S) extraction through the pinned ScrapeGraphAI worker.",
        emoji="🕷️",
    )
    ctx.register_system_prompt_section(
        "agentik.agent-router",
        agent_router_prompt,
        position="after_memory",
        max_chars=1400,
    )
    ctx.register_system_prompt_section(
        "agentik.global-rules",
        rules_prompt,
        position="after_memory",
        max_chars=4000,
    )
