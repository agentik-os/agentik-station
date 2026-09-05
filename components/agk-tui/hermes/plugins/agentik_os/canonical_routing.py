"""Non-executing Station OS handoff shared by AGK's plugin and controller.

AGK's operator-local agent catalog is not the privileged Station instance ledger.
These aliases select a capability, never a Zone, profile, version or authority.
"""
from __future__ import annotations

import re


OS_ALIASES = {
    "builder": "builder-os", "builderos": "builder-os", "build-os": "builder-os",
    "builder-os": "builder-os", "master-os-builder": "builder-os",
    "stepper": "stepper-os", "steper": "stepper-os", "steper-os": "stepper-os",
    "stepper-os": "stepper-os", "librarian": "librarian-os", "librarian-os": "librarian-os",
}
LEGACY_BUILDER = "legacy-master-os-builder"
_SELECTOR = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


def canonical_handoff(agent_id: str, *, zone=None, instance=None) -> dict | None:
    os_id = OS_ALIASES.get(agent_id)
    if os_id is None:
        return None
    for label, value in (("zone", zone), ("instance", instance)):
        if value is not None and (not isinstance(value, str) or not _SELECTOR.fullmatch(value)):
            raise ValueError(f"{label} must be a Station identifier")
    if (zone is None) != (instance is None):
        raise ValueError("Select both the owning Zone and OS instance; neither can be inferred")
    selector = ["--zone", zone or "<zone>", "--instance", instance or "<instance>"]
    resolve = ["sudo", "station", "os", "resolve", "--name", os_id, *selector]
    chat_plan = ["sudo", "station", "os", "instance", "chat", *selector, "--plan"]
    return {
        "success": False,
        "status": "STATION_HANDOFF_REQUIRED",
        "agent": os_id,
        "executed": False,
        "canonical_source": "active Station release os/ catalog",
        "installed_version": None,
        "director_profile": None,
        "scope": {"zone": zone, "instance": instance},
        "commands_are_templates": zone is None,
        "resolve_argv": resolve,
        "chat_plan_argv": chat_plan,
        "next_action": (
            "Select the owning Host, Zone and installed instance, then have the authorized Station "
            "operator resolve its current package and inspect its exact Director chat plan: "
            + " ".join(resolve) + "; " + " ".join(chat_plan) + ". "
            "These commands have not run. This AGK agent tool does not read the privileged instance "
            "ledger or grant cross-Zone execution. A successful current-version plan is not live "
            "provider/chat acceptance. Do not start a generic Hermes session or use bundled "
            "master-os-builder as a substitute. In personal Workstation mode, use its owning "
            "Station OS workflow instead; do not apply Host sudo commands there."
        ),
    }
