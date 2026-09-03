from __future__ import annotations

import json
from pathlib import Path

from agentik_station.doctor import station_doctor
from agentik_station.installer import StationInstaller
from agentik_station.models import InstallSpec
from agentik_station.paths import LayoutPaths

ROOT = Path(__file__).resolve().parents[2]


def test_core_host_reconciles_all_seven_categories_without_false_os_install_claims(tmp_path: Path) -> None:
    paths = LayoutPaths.under(tmp_path / "root")
    spec = InstallSpec(
        operation_id="op-core-temp-install",
        host_id="gareth-core-01",
        role="core",
        install_system_packages=False,
        configure_fail2ban=False,
        enable_doctor_timer=False,
    )
    assert StationInstaller(ROOT, spec, paths=paths).apply() == "READY_FOR_SETUP"

    zones_root = paths.runtime / "2_ZONES"
    for category in [
        "1_SYSTEM",
        "2_PRIVATE",
        "3_AGENTIK",
        "4_CLIENTS",
        "5_PROJECTS",
        "6_FACTORY",
        "7_LAB",
    ]:
        assert (zones_root / category).is_dir()

    expected = {
        "1_SYSTEM/station-maintainer",
        "1_SYSTEM/discord-bootstrap",
        "1_SYSTEM/fleet-operator",
        "2_PRIVATE/gareth",
        "3_AGENTIK/dev",
        "6_FACTORY/os",
        "7_LAB/hermes-edge",
    }
    for relative in expected:
        zone = zones_root / relative
        assert zone.is_dir(), relative
        desired = json.loads((zone / "os" / "DESIRED.json").read_text())
        assert all(item["runtime_state"] == "NOT_INSTALLED" for item in desired["packages"])

    assert station_doctor(paths, repo_root=ROOT, full=True).ok
