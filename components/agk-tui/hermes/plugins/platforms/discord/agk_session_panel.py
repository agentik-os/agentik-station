"""Safe, presentation-only helpers for the AGK Discord session picker.

Hermes remains the authority for authorization and session switching.  This
module only turns already-authorized ``SessionDB.list_sessions_rich`` rows into
bounded Discord select options and builds the native ``/resume`` command.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable


_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
_HIDDEN_SOURCES = {"cron", "tool"}


def _single_line(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _source_label(row: dict[str, Any]) -> str:
    source = _single_line(row.get("source"), 24).lower() or "hermes"
    profile = _single_line(row.get("profile_name"), 30)
    return f"{source} · {profile}" if profile else source


def _last_active_label(row: dict[str, Any]) -> str:
    raw = row.get("last_active", row.get("last_activity_at", row.get("started_at")))
    try:
        timestamp = float(raw)
    except (TypeError, ValueError):
        return "activity unknown"
    if timestamp <= 0:
        return "activity unknown"
    return datetime.fromtimestamp(timestamp).astimezone().strftime("%d %b · %H:%M")


def session_picker_rows(
    rows: Iterable[dict[str, Any]], *, limit: int = 100
) -> list[dict[str, str]]:
    """Return sanitized, de-duplicated, resumable rows for Discord.

    Tool/cron sessions and hidden/archived rows are never presented.  Session
    IDs are validated before they can become command arguments.
    """

    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        session_id = str(row.get("id") or "").strip()
        if session_id in seen or not _SESSION_ID_RE.fullmatch(session_id):
            continue
        if str(row.get("source") or "").lower() in _HIDDEN_SOURCES:
            continue
        if bool(row.get("hidden")) or bool(row.get("archived")):
            continue
        seen.add(session_id)
        title = _single_line(row.get("title"), 88)
        if not title:
            preview = _single_line(row.get("preview"), 68)
            title = preview or f"Hermes session {session_id[-8:]}"
        description = _single_line(
            f"{_source_label(row)} · {_last_active_label(row)}", 100
        )
        output.append(
            {
                "id": session_id,
                "label": title,
                "description": description,
            }
        )
        if len(output) >= max(1, min(int(limit), 100)):
            break
    return output


def resume_all_command(session_id: str) -> str:
    """Build the native admin-scoped command for one validated session ID."""

    normalized = str(session_id or "").strip()
    if not _SESSION_ID_RE.fullmatch(normalized):
        raise ValueError("invalid Hermes session id")
    return f"/resume --all {normalized}"
