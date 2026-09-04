from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ReconcileError, SecurityError, ValidationError
from ..identifiers import validate_identifier

API_BASE = "https://discord.com/api/v10"


def _token_from_file(path: Path) -> str:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise SecurityError(f"Discord token reference must be a regular file: {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not token or any(ch.isspace() for ch in token):
        raise ValidationError("Discord token file is empty or malformed")
    return token


@dataclass
class DiscordTransport:
    token_file: Path
    api_base: str = API_BASE
    max_retries: int = 4

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        token = _token_from_file(self.token_file)
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        url = self.api_base.rstrip("/") + "/" + path.lstrip("/")
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=data,
                method=method,
                headers={
                    "Authorization": f"Bot {token}",
                    "Content-Type": "application/json",
                    "User-Agent": "Agentik-Station/11.12",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8")
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 and attempt < self.max_retries:
                    retry_after = 1.0
                    try:
                        retry_after = float(json.loads(raw).get("retry_after", 1.0))
                    except Exception:
                        header = exc.headers.get("Retry-After")
                        if header:
                            retry_after = float(header)
                    time.sleep(min(max(retry_after, 0.05), 15.0))
                    continue
                raise ReconcileError(f"Discord API {method} {path} failed with HTTP {exc.code}: {raw[:1000]}") from exc
            except urllib.error.URLError as exc:
                raise ReconcileError(f"Discord API unavailable for {method} {path}: {exc.reason}") from exc
        raise ReconcileError("Discord API retry budget exhausted")

    def create_message(self, channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not channel_id.isdigit():
            raise ValidationError("Discord channel_id must be numeric")
        return self._request("POST", f"channels/{channel_id}/messages", payload)

    def edit_message(self, channel_id: str, message_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not channel_id.isdigit() or not message_id.isdigit():
            raise ValidationError("Discord channel/message IDs must be numeric")
        return self._request("PATCH", f"channels/{channel_id}/messages/{message_id}", payload)

    def read_message(self, channel_id: str, message_id: str) -> dict[str, Any]:
        if not channel_id.isdigit() or not message_id.isdigit():
            raise ValidationError("Discord channel/message IDs must be numeric")
        return self._request("GET", f"channels/{channel_id}/messages/{message_id}")

    def get_current_application(self) -> dict[str, Any]:
        return self._request("GET", "oauth2/applications/@me")


def verify_binding(binding: dict[str, Any]) -> dict[str, Any]:
    required = {"zone_id", "os_id", "profile_id", "guild_id", "channel_id", "token_file"}
    missing = sorted(required - set(binding))
    if missing:
        raise ValidationError(f"Discord binding missing fields: {missing}")
    validate_identifier(str(binding["zone_id"]), "zone_id")
    validate_identifier(str(binding["os_id"]), "os_id")
    validate_identifier(str(binding["profile_id"]), "profile_id")
    for field in ("guild_id", "channel_id"):
        if not str(binding[field]).isdigit():
            raise ValidationError(f"{field} must be numeric")
    token_file = Path(str(binding["token_file"]))
    if not token_file.is_absolute():
        raise ValidationError("token_file must be an absolute credential reference")
    return dict(binding)
