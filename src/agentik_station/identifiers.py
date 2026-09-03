from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .errors import ValidationError

_IDENTIFIER = re.compile(r"^[a-z](?:[a-z0-9-]{0,46}[a-z0-9])?$")
_VERSION = re.compile(r"^[0-9A-Za-z](?:[0-9A-Za-z.+-]{0,62}[0-9A-Za-z])?$")
_OPERATION = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_REMOTE_USER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,31}$")
_DNS = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)

ENV_ALIASES = {
    "dev": "development",
    "development": "development",
    "stg": "staging",
    "stage": "staging",
    "staging": "staging",
    "prod": "production",
    "production": "production",
    "system": "system",
    "private": "private",
    "factory": "factory",
    "lab": "lab",
}


def _require_ascii_normalized(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} is required")
    if not value.isascii():
        raise ValidationError(f"Invalid {field}: ASCII characters only")
    if value != unicodedata.normalize("NFKC", value):
        raise ValidationError(f"Invalid {field}: value must already be NFKC-normalized")
    return value


def validate_identifier(value: str, field: str = "identifier") -> str:
    value = _require_ascii_normalized(value, field)
    if not _IDENTIFIER.fullmatch(value):
        raise ValidationError(
            f"Invalid {field}: {value!r}. Use lowercase ASCII letters, digits, and internal hyphens; "
            "start with a letter, end with a letter or digit, maximum 48 characters."
        )
    return value


def validate_optional_identifier(value: str | None, field: str) -> str | None:
    return None if value in (None, "") else validate_identifier(value, field)


def validate_version(value: str) -> str:
    value = _require_ascii_normalized(value, "release version")
    if not _VERSION.fullmatch(value):
        raise ValidationError(f"Invalid release version: {value!r}")
    return value


def validate_operation_id(value: str) -> str:
    value = _require_ascii_normalized(value, "operation_id")
    if not _OPERATION.fullmatch(value):
        raise ValidationError(f"Invalid operation_id: {value!r}")
    return value


@dataclass(frozen=True)
class RemoteTarget:
    host: str
    user: str | None = None
    port: int = 22

    @property
    def destination(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host


def validate_remote_target(value: str, port: int = 22) -> RemoteTarget:
    value = _require_ascii_normalized(value, "remote target")
    if value.startswith("-") or any(ch.isspace() for ch in value):
        raise ValidationError("Remote target may not contain options or whitespace")
    if any(ch in value for ch in ";|&$`(){}<>\\\"'"):
        raise ValidationError("Remote target contains forbidden shell syntax")
    if not 1 <= int(port) <= 65535:
        raise ValidationError("Remote port must be between 1 and 65535")

    user: str | None = None
    host = value
    if "@" in value:
        if value.count("@") != 1:
            raise ValidationError("Remote target may contain at most one @")
        user, host = value.split("@", 1)
        if not _REMOTE_USER.fullmatch(user):
            raise ValidationError("Invalid remote user")

    if host.startswith("[") and host.endswith("]"):
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError as exc:
            raise ValidationError("Invalid IPv6 remote host") from exc
    else:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not _DNS.fullmatch(host):
                raise ValidationError("Remote host must be a valid DNS name or IP address")
    return RemoteTarget(host=host, user=user, port=int(port))


def validate_ssh_target(value: str) -> str:
    """Backward-compatible destination validation used by older call sites."""

    return validate_remote_target(value).destination


def normalize_environment(value: str) -> str:
    try:
        return ENV_ALIASES[value]
    except (KeyError, TypeError):
        raise ValidationError(f"Unsupported environment: {value!r}") from None


def normalize_deploy_environment(value: str) -> str:
    normalized = normalize_environment(value)
    if normalized not in {"development", "staging", "production"}:
        raise ValidationError(
            f"Client/Project environment must be development, staging, or production; got {value!r}"
        )
    return normalized


def environment_slug(value: str) -> str:
    normalized = normalize_environment(value)
    return {"development": "dev", "staging": "staging", "production": "prod"}.get(normalized, normalized)


def validate_local_file(path: Path, field: str = "file") -> Path:
    path = Path(path)
    if path.is_symlink():
        raise ValidationError(f"{field} must not be a symlink: {path}")
    if not path.is_file():
        raise ValidationError(f"{field} does not exist or is not a regular file: {path}")
    return path
