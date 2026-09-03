from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .configuration import StationConfig, compile_zones
from .constants import SYSTEM_PACKAGES
from .identity import zone_unix_user
from .models import InstallSpec, ZoneSpec


@dataclass(frozen=True)
class PlanStep:
    id: str
    description: str
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "description": self.description, "detail": self.detail}


def zone_specs(spec: InstallSpec, config: StationConfig) -> list[ZoneSpec]:
    zones, _ = compile_zones(spec, config)
    for zone in zones:
        zone_unix_user(zone.category, zone.name, zone.environment)
    return zones


def build_plan(spec: InstallSpec, config: StationConfig) -> list[PlanStep]:
    zones, desired_by_zone = compile_zones(spec, config)
    steps: list[PlanStep] = [
        PlanStep(
            "validate-host",
            "Validate the supported Ubuntu/Debian + systemd Host, canonical config, and typed InstallSpec.",
            {
                "host_id": spec.host_id,
                "role": spec.role,
                "schema_version": spec.schema_version,
                "config_schema": config.schema_version,
            },
        )
    ]
    if spec.install_system_packages:
        steps.append(
            PlanStep(
                "system-packages",
                "Install the allowlisted Station host package set through apt without executing network scripts.",
                {"packages": SYSTEM_PACKAGES},
            )
        )
    steps.extend(
        [
            PlanStep(
                "station-identity",
                "Reconcile the non-interactive station-system Unix identity.",
                {"home": "/var/lib/station/system"},
            ),
            PlanStep(
                "fhs-layout",
                "Reconcile /etc, /opt/releases, /srv, /var/lib, /var/log, backups, and /run responsibilities.",
                {"control_in_srv_is_projection_only": True},
            ),
            PlanStep(
                "versioned-release",
                "Stage the repository as an immutable release and atomically activate /opt/station/current.",
                {"release_version": spec.release_version},
            ),
            PlanStep(
                "desired-state",
                "Write validated Host desired state under /etc/station and observed state under /var/lib/station.",
                {"host_id": spec.host_id, "role": spec.role, "station_id": config.station_id},
            ),
        ]
    )
    for zone in zones:
        steps.append(
            PlanStep(
                f"zone-{zone.zone_id}",
                "Reconcile one isolated Zone across human, service-state, log, runtime, and backup roots.",
                {
                    "zone_id": zone.zone_id,
                    "category": zone.category,
                    "environment": zone.environment,
                    "unix_user": zone_unix_user(zone.category, zone.name, zone.environment),
                    "desired_os": list(desired_by_zone.get(zone.zone_id, ())),
                    "os_runtime_claim": "DECLARED_ONLY",
                },
            )
        )
    if spec.seed and spec.seed.project:
        steps.append(
            PlanStep(
                f"project-{spec.seed.project}",
                "Reconcile the Project inside the seeded Zone with correct Zone ownership.",
                {"project_id": spec.seed.project, "zone_id": zones[-1].zone_id},
            )
        )
    steps.extend(
        [
            PlanStep(
                "systemd",
                "Install the single canonical systemd unit set; enable only the deterministic Doctor timer.",
                {"doctor_timer": spec.enable_doctor_timer, "hermes_watch_enabled": False},
            ),
            PlanStep(
                "host-security",
                "Enable fail2ban when requested; do not activate a firewall policy before SSH/Tailscale readback.",
                {"fail2ban": spec.configure_fail2ban, "firewall_auto_enabled": False},
            ),
            PlanStep(
                "doctor",
                "Run the Station Kernel Doctor and persist observed evidence before the final state claim.",
                {},
            ),
            PlanStep(
                "receipt",
                "Persist a durable operation receipt with exact state and next actions.",
                {"operation_id": spec.operation_id},
            ),
        ]
    )
    return steps
