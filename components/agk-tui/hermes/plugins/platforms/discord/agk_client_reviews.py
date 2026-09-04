"""Authorized Discord component bridge for AGK client review cards."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from typing import Any


_CUSTOM_ID = re.compile(
    r"^agk:review:[a-z0-9][a-z0-9-]{1,48}[a-z0-9]:"
    r"WORK-[A-F0-9]{12}:(changes|approve|deploy)$"
)


def is_agk_client_review(custom_id: object) -> bool:
    return bool(_CUSTOM_ID.fullmatch(str(custom_id or "")))


def run_agk_review_action(
    custom_id: str,
    *,
    actor: str,
    decision_id: str,
    feedback: str | None = None,
) -> dict[str, Any]:
    if not is_agk_client_review(custom_id):
        raise RuntimeError("invalid AGK client review action")
    executable = shutil.which("agk")
    if not executable:
        raise RuntimeError("AGK launcher is unavailable to the Hermes gateway")
    command = [
        executable,
        "client",
        "work",
        "review-action",
        custom_id,
        "--actor",
        actor,
        "--decision-id",
        decision_id,
    ]
    if feedback is not None:
        command.extend(["--feedback", feedback])
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        message = (
            result.stderr.strip().splitlines()[-1]
            if result.stderr.strip()
            else "AGK rejected the review action"
        )
        raise RuntimeError(message)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("AGK returned an invalid review response") from error
    if not isinstance(value, dict):
        raise RuntimeError("AGK returned an invalid review response")
    return value


def register_agk_client_review_listener(bot: Any, adapter: Any) -> None:
    """Register one raw component listener without replacing slash handling."""

    import discord

    async def execute(
        interaction: Any, custom_id: str, feedback: str | None = None
    ) -> None:
        actor = f"discord:{getattr(getattr(interaction, 'user', None), 'id', '')}"
        decision_id = f"discord-{getattr(interaction, 'id', '')}"
        try:
            value = await asyncio.to_thread(
                run_agk_review_action,
                custom_id,
                actor=actor,
                decision_id=decision_id,
                feedback=feedback,
            )
            action = str(value.get("action") or "review").replace("_", " ").upper()
            status = str(value.get("status") or "recorded").replace("_", " ").upper()
            suffix = " · SAME SESSION RESUMED" if value.get("session_resumed") else ""
            await interaction.edit_original_response(
                content=f"AGK · {action} · {status}{suffix}"
            )
        except Exception as error:
            await interaction.edit_original_response(
                content=f"AGK rejected this action: {error}"
            )

    @bot.listen("on_interaction")
    async def on_agk_client_review(interaction: Any) -> None:
        data = getattr(interaction, "data", None)
        custom_id = data.get("custom_id") if isinstance(data, dict) else None
        if not is_agk_client_review(custom_id):
            return
        if not await adapter._check_slash_authorization(interaction, str(custom_id)):
            return
        action = str(custom_id).rsplit(":", 1)[-1]
        if action != "changes":
            await interaction.response.defer(ephemeral=True)
            await execute(interaction, str(custom_id))
            return

        class RequestChangesModal(discord.ui.Modal, title="Request changes"):
            feedback = discord.ui.TextInput(
                label="What needs to change?",
                style=discord.TextStyle.paragraph,
                min_length=1,
                max_length=4000,
                required=True,
            )

            async def on_submit(self, modal_interaction: Any) -> None:
                await modal_interaction.response.defer(ephemeral=True)
                await execute(
                    modal_interaction,
                    str(custom_id),
                    str(self.feedback.value),
                )

        await interaction.response.send_modal(RequestChangesModal())
