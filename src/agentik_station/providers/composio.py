from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ValidationError
from ..identifiers import validate_identifier


def stable_principal(zone_id: str, organization_id: str | None, subject_id: str) -> str:
    zone = validate_identifier(zone_id, "zone_id")
    subject = validate_identifier(subject_id, "subject_id")
    org = validate_identifier(organization_id, "organization_id") if organization_id else "personal"
    return f"station:{org}:{zone}:{subject}"


@dataclass(frozen=True)
class ComposioBinding:
    zone_id: str
    organization_id: str | None
    subject_id: str
    toolkits: tuple[str, ...]
    connected_accounts: dict[str, tuple[str, ...]]

    @property
    def principal(self) -> str:
        return stable_principal(self.zone_id, self.organization_id, self.subject_id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ComposioBinding":
        allowed = {"zone_id", "organization_id", "subject_id", "toolkits", "connected_accounts"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValidationError(f"Unknown Composio binding fields: {unknown}")
        zone_id = validate_identifier(str(payload.get("zone_id", "")), "zone_id")
        organization = payload.get("organization_id")
        if organization is not None:
            organization = validate_identifier(str(organization), "organization_id")
        subject = validate_identifier(str(payload.get("subject_id", "")), "subject_id")
        raw_toolkits = payload.get("toolkits")
        if not isinstance(raw_toolkits, list) or not raw_toolkits:
            raise ValidationError("Composio toolkits must be an explicit non-empty allowlist")
        toolkits = tuple(validate_identifier(str(value), "Composio toolkit") for value in raw_toolkits)
        accounts = payload.get("connected_accounts", {})
        if not isinstance(accounts, dict):
            raise ValidationError("connected_accounts must be an object")
        normalized: dict[str, tuple[str, ...]] = {}
        for toolkit, values in accounts.items():
            key = validate_identifier(str(toolkit), "connected account toolkit")
            if key not in toolkits:
                raise ValidationError(f"Connected account toolkit {key} is not in the explicit toolkit allowlist")
            if not isinstance(values, list):
                raise ValidationError(f"Connected accounts for {key} must be an array")
            normalized[key] = tuple(str(value) for value in values)
        return cls(zone_id, organization, subject, toolkits, normalized)

    def to_session_config(self) -> dict[str, Any]:
        return {
            "user_id": self.principal,
            "toolkits": list(self.toolkits),
            "connected_accounts": {key: list(value) for key, value in self.connected_accounts.items()},
            "mcp": True,
        }


def load_binding(path: Path) -> ComposioBinding:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"Composio binding must be a regular file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError("Composio binding root must be an object")
    return ComposioBinding.from_dict(payload)


def create_session(binding: ComposioBinding, api_key: str) -> dict[str, Any]:
    """Create a real Composio session when the optional SDK is installed.

    The API key is accepted in memory only and is never persisted by this helper.
    """
    if not api_key or any(ch.isspace() for ch in api_key):
        raise ValidationError("Composio API key is missing or malformed")
    try:
        from composio import Composio  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Install the supported `composio` Python SDK before running the Composio setup gate") from exc
    client = Composio(api_key=api_key)
    config = binding.to_session_config()
    # Current Composio SDK accepts user_id plus scoped configuration; keep
    # unknown/unsupported adapter details out of Station's persisted state.
    session = client.create(
        user_id=config["user_id"],
        toolkits=config["toolkits"],
        connected_accounts=config["connected_accounts"] or None,
        mcp=True,
    )
    result: dict[str, Any] = {
        "principal": binding.principal,
        "session_id": getattr(session, "session_id", None),
        "toolkits": list(binding.toolkits),
        "connected_accounts": {key: list(value) for key, value in binding.connected_accounts.items()},
        "claim": "SESSION_CREATED_NOT_YET_READ_BACK",
    }
    mcp = getattr(session, "mcp", None)
    if mcp is not None:
        result["mcp_url"] = getattr(mcp, "url", None)
    return result
