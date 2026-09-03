from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import CATEGORIES, PRODUCT_VERSION, SPEC_SCHEMA_VERSION
from .errors import ValidationError
from .identifiers import (
    normalize_deploy_environment,
    normalize_environment,
    validate_identifier,
    validate_operation_id,
    validate_optional_identifier,
    validate_version,
)

ROLES = {"core", "client", "project", "lab", "worker"}


def new_operation_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"op-{timestamp}-{uuid.uuid4().hex[:8]}"


def _strict_bool(value: Any, field: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValidationError(f"{field} must be a JSON boolean")
    return value


def _reject_unknown(value: dict[str, Any], allowed: set[str], scope: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValidationError(f"Unknown {scope} field(s): {', '.join(unknown)}")


@dataclass(frozen=True)
class SeedSpec:
    category: str
    name: str
    environment: str
    organization: str | None = None
    project: str | None = None

    def __post_init__(self) -> None:
        category = self.category.upper()
        if category not in {"CLIENTS", "PROJECTS"}:
            raise ValidationError("Seed category must be CLIENTS or PROJECTS")
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "name", validate_identifier(self.name, "seed name"))
        object.__setattr__(self, "environment", normalize_deploy_environment(self.environment))
        object.__setattr__(self, "organization", validate_optional_identifier(self.organization, "organization"))
        object.__setattr__(self, "project", validate_optional_identifier(self.project, "project"))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SeedSpec":
        _reject_unknown(value, {"category", "name", "environment", "organization", "project"}, "seed")
        for required in ("category", "name", "environment"):
            if required not in value:
                raise ValidationError(f"SeedSpec is missing {required}")
        return cls(
            category=str(value["category"]),
            name=str(value["name"]),
            environment=str(value["environment"]),
            organization=value.get("organization"),
            project=value.get("project"),
        )


@dataclass(frozen=True)
class InstallSpec:
    schema_version: int = SPEC_SCHEMA_VERSION
    release_version: str = PRODUCT_VERSION
    operation_id: str = ""
    host_id: str = "gareth-core-01"
    role: str = "core"
    install_system_packages: bool = True
    configure_fail2ban: bool = True
    enable_doctor_timer: bool = True
    seed: SeedSpec | None = None

    def __post_init__(self) -> None:
        if self.schema_version != SPEC_SCHEMA_VERSION:
            raise ValidationError(
                f"Unsupported InstallSpec schema_version {self.schema_version}; expected {SPEC_SCHEMA_VERSION}"
            )
        object.__setattr__(self, "release_version", validate_version(self.release_version))
        operation_id = self.operation_id or new_operation_id()
        object.__setattr__(self, "operation_id", validate_operation_id(operation_id))
        object.__setattr__(self, "host_id", validate_identifier(self.host_id, "host_id"))
        if self.role not in ROLES:
            raise ValidationError(f"Unsupported host role: {self.role!r}")
        if not all(
            isinstance(value, bool)
            for value in (self.install_system_packages, self.configure_fail2ban, self.enable_doctor_timer)
        ):
            raise ValidationError("InstallSpec feature switches must be booleans")
        if self.role == "client" and self.seed and self.seed.category != "CLIENTS":
            raise ValidationError("A client Host may only seed a CLIENTS Zone")
        if self.role == "project" and self.seed and self.seed.category != "PROJECTS":
            raise ValidationError("A project Host may only seed a PROJECTS Zone")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "InstallSpec":
        _reject_unknown(
            value,
            {
                "schema_version",
                "release_version",
                "operation_id",
                "host_id",
                "role",
                "install_system_packages",
                "configure_fail2ban",
                "enable_doctor_timer",
                "seed",
            },
            "InstallSpec",
        )
        seed = value.get("seed")
        if seed is not None and not isinstance(seed, dict):
            raise ValidationError("InstallSpec seed must be an object or null")
        schema_version = value.get("schema_version", SPEC_SCHEMA_VERSION)
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValidationError("schema_version must be an integer")
        return cls(
            schema_version=schema_version,
            release_version=str(value.get("release_version", PRODUCT_VERSION)),
            operation_id=str(value.get("operation_id") or ""),
            host_id=str(value.get("host_id", "gareth-core-01")),
            role=str(value.get("role", "core")),
            install_system_packages=_strict_bool(value.get("install_system_packages"), "install_system_packages", True),
            configure_fail2ban=_strict_bool(value.get("configure_fail2ban"), "configure_fail2ban", True),
            enable_doctor_timer=_strict_bool(value.get("enable_doctor_timer"), "enable_doctor_timer", True),
            seed=SeedSpec.from_dict(seed) if seed is not None else None,
        )

    @classmethod
    def load(cls, path: Path) -> "InstallSpec":
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValidationError(f"InstallSpec must be a regular non-symlink JSON file: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Cannot read InstallSpec {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValidationError("InstallSpec root must be an object")
        return cls.from_dict(payload)

    def write(self, path: Path) -> None:
        """Write an InstallSpec atomically to a caller-owned local directory."""

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            raise ValidationError(f"Refusing to replace existing InstallSpec: {path}")
        temp = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temp, flags, 0o600)
        try:
            payload = self.to_json().encode("utf-8")
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, path)


@dataclass(frozen=True)
class ZoneSpec:
    category: str
    name: str
    environment: str
    host_id: str
    organization: str | None = None

    def __post_init__(self) -> None:
        category = self.category.upper()
        if category not in CATEGORIES:
            raise ValidationError(f"Unsupported Zone category: {category!r}")
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "name", validate_identifier(self.name, "Zone name"))
        object.__setattr__(self, "environment", normalize_environment(self.environment))
        object.__setattr__(self, "host_id", validate_identifier(self.host_id, "host_id"))
        object.__setattr__(self, "organization", validate_optional_identifier(self.organization, "organization"))
        allowed_by_category = {
            "SYSTEM": {"system"},
            "PRIVATE": {"private"},
            "AGENTIK": {"development", "staging", "production"},
            "CLIENTS": {"development", "staging", "production"},
            "PROJECTS": {"development", "staging", "production"},
            "FACTORY": {"factory"},
            "LAB": {"lab"},
        }
        if self.environment not in allowed_by_category[category]:
            raise ValidationError(
                f"Environment {self.environment!r} is invalid for Zone category {category}"
            )

    @property
    def zone_id(self) -> str:
        from .identifiers import environment_slug

        return f"{self.name}-{environment_slug(self.environment)}" if self.category in {"CLIENTS", "PROJECTS"} else self.name
