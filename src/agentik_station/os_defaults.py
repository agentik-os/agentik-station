"""Explicit default native teams; no credentials, gateway activation or adoption.

The completed kernel receipt, not a scan of client directories, selects the
Factory or team seed Zone. Existing instances are inspected and preserved.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import os_instances, os_lifecycle, organizations
from .configuration import compile_zones, load_station_config
from .errors import SecurityError, StationError, ValidationError
from .identifiers import validate_operation_id, validate_version
from .models import InstallSpec, ZoneSpec
from .paths import LayoutPaths


DEFAULTS = (("stepper", "stepper-os"), ("builder", "builder-os"), ("librarian", "librarian-os"))


def _host_spec(paths: LayoutPaths) -> InstallSpec:
    desired = os_lifecycle._trusted_json(paths.config / "station.json", paths, paths.config)
    observed = os_lifecycle._trusted_json(paths.observed / "host.json", paths, paths.varlib)
    operation = validate_operation_id(desired.get("operation_id"))
    receipt = os_lifecycle._trusted_json(paths.receipts / f"{operation}.json", paths, paths.varlib)
    if (type(desired.get("schema_version")) is not int or desired["schema_version"] != 1
            or type(observed.get("schema_version")) is not int or observed["schema_version"] != 1
            or type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1
            or receipt.get("status") != "COMPLETED" or receipt.get("state") != "READY_FOR_SETUP"
            or observed.get("state") != "READY_FOR_SETUP"):
        raise ValidationError("Default OS installation requires completed kernel readback")
    if not isinstance(receipt.get("spec"), dict):
        raise ValidationError("Default OS kernel receipt requires its exact typed InstallSpec")
    spec = InstallSpec.from_dict(receipt["spec"])
    expected = {"host_id": spec.host_id, "role": spec.role,
                "release_version": spec.release_version, "operation_id": spec.operation_id}
    if (any(record.get(key) != value for record in (desired, observed) for key, value in expected.items())
            or receipt.get("operation_id") != spec.operation_id
            or receipt.get("release_version") != spec.release_version):
        raise SecurityError("Default OS inputs refer to different Host/kernel operations")
    return spec


def _source_packages(repo_root: Path, paths: LayoutPaths) -> dict[str, dict]:
    # Validate authority before using the normal semantic loaders. Live callers
    # must use the root-owned release, never an operator-writable checkout.
    os_lifecycle._trusted_json(repo_root / "config/station.default.json", paths, repo_root)
    catalog = os_lifecycle._trusted_json(repo_root / "os/CATALOG.json", paths, repo_root)
    packages = catalog.get("packages")
    if not isinstance(packages, list):
        raise ValidationError("Default OS source catalog is invalid")
    result = {}
    for instance_id, os_id in DEFAULTS:
        matches = [item for item in packages if isinstance(item, dict) and item.get("id") == os_id]
        if len(matches) != 1 or matches[0].get("path") != f"os/{instance_id}":
            raise ValidationError(f"Default OS package is missing or ambiguous: {os_id}")
        validate_version(matches[0].get("version"))
        source = repo_root / "os" / instance_id
        contract = os_lifecycle._trusted_json(source / "CONTRACT.json", paths, repo_root)
        if (contract.get("schema_version") != "agk-os/v2" or contract.get("os_id") != os_id
                or contract.get("version") != matches[0].get("version")):
            raise ValidationError("Default OS package/catalog identity mismatch")
        result[instance_id] = {**matches[0], "source": source}
    return result


def _target_zone(repo_root: Path, paths: LayoutPaths, spec: InstallSpec) -> dict | None:
    zones, _ = compile_zones(spec, load_station_config(repo_root))
    target = None
    if spec.role == "core":
        expected = ZoneSpec(category="FACTORY", name="os", environment="factory",
                            host_id=spec.host_id, organization="agentik")
        if expected not in zones:
            raise ValidationError("The core Host has no canonical Factory OS Zone")
        target = expected
    elif spec.role == "team" and spec.seed is not None:
        if spec.seed.category != "ORGANIZATIONS":
            raise ValidationError("Default team OS installation requires its explicit Organization seed")
        target = ZoneSpec(category=spec.seed.category, name=spec.seed.name,
                          environment=spec.seed.environment, host_id=spec.host_id,
                          organization=spec.seed.organization)
        if target not in zones:
            raise ValidationError("Team seed Zone differs from the canonical Host declaration")
    if target is None:
        return None
    path = paths.config / "zones.d" / f"{target.zone_id}.json"
    zone = os_lifecycle._trusted_json(path, paths, paths.config)
    context = os_lifecycle._context(paths, zone)
    if context["spec"] != target:
        raise SecurityError("Default OS Zone differs from the completed Host's intended owner")
    return zone


def _existing(paths: LayoutPaths, zone: dict, instance_id: str) -> dict | None:
    ledger = os_instances.instance_paths(paths, zone, instance_id)["ledger"]
    if not os_instances._directory_exists(ledger):
        return None
    record = os_instances.load_os_instance_record(paths, zone=zone, instance_id=instance_id)
    if record["state"] in {"CONFIGURED", "VERIFIED"}:
        try:
            return os_instances.load_os_instance_record(paths, zone=zone, instance_id=instance_id,
                                                        require_configured=True)
        except (StationError, OSError, ValueError):
            # Preserve the existing authority record, but do not mistake a stale
            # ledger for installed native profiles or attempt automatic repair.
            return {**record, "default_readback_failed": True}
    return record


def _plan(repo_root: Path, paths: LayoutPaths) -> tuple[dict, dict | None, dict]:
    repo_root = Path(repo_root)
    spec = _host_spec(paths)
    packages = _source_packages(repo_root, paths)
    zone = _target_zone(repo_root, paths, spec)
    report = {"schema_version": 1, "kind": "DefaultOSPlan", "host_id": spec.host_id,
              "role": spec.role, "operation_id": spec.operation_id, "state": "NOT_APPLICABLE",
              "ok": True, "mutates": False, "operational": False,
              "configuration_required": True, "organization": None, "instances": []}
    if zone is None:
        return report, zone, packages
    organization_id = zone["organization"] if zone["category"] == "ORGANIZATIONS" else None
    if organization_id is not None:
        try:
            organizations.validate_organization_zone(paths, organization_id=organization_id, zone=zone)
            registration = {"state": "PRESERVED", "id": organization_id, "argv": []}
        except FileNotFoundError:
            organizations.register_organization(paths, organization_id=organization_id,
                                                 zone_ids=[zone["id"]], plan=True)
            registration = {"state": "INSTALL_REQUIRED", "id": organization_id,
                            "argv": ["station", "organization", "register", "--id", organization_id,
                                     "--zone", zone["id"]]}
        report["organization"] = registration
    for instance_id, os_id in DEFAULTS:
        package = packages[instance_id]
        old = _existing(paths, zone, instance_id)
        argv = ["station", "os", "instance", "install", "--zone", zone["id"],
                "--instance", instance_id, "--id", os_id]
        if organization_id is not None:
            argv += ["--organization", organization_id]
        item = {"zone_id": zone["id"], "instance_id": instance_id, "os_id": os_id,
                "version": package["version"], "organization_id": organization_id,
                "state": "INSTALL_REQUIRED", "argv": argv, "operational": False}
        if old is not None:
            matches = old["os_id"] == os_id and old["organization_id"] == organization_id
            ready = old["state"] in {"CONFIGURED", "VERIFIED"} and not old.get("default_readback_failed")
            item.update(state="PRESERVED" if matches else "CONFLICT", argv=[],
                        recorded_os_id=old["os_id"], recorded_version=old["os_version"],
                        recorded_state=old["state"],
                        source_version_matches=matches and old["os_version"] == package["version"])
            if not matches or not ready:
                report["ok"] = False
                item["next_repair_action"] = "Inspect the existing instance; defaults never migrate or resume it."
            elif not item["source_version_matches"]:
                item["next_repair_action"] = (
                    "A different package version is delivered, but this native team was preserved. "
                    "Review a scoped profile migration before claiming its new capabilities; do not force-reinstall.")
        report["instances"].append(item)
    report["state"] = "PLAN_READY" if report["ok"] else "REVIEW_REQUIRED"
    return report, zone, packages


def plan_default_os(repo_root: Path, paths: LayoutPaths) -> dict:
    """Read trusted metadata and return typed argv; never execute or create files."""
    return _plan(repo_root, paths)[0]


def install_default_os(repo_root: Path, paths: LayoutPaths, *, hermes_binary: str,
                       runuser_binary: str) -> dict:
    """Install only absent default instance teams; preserve all existing state."""
    if not paths.test_mode and (os.geteuid() != 0 or os.uname().sysname != "Linux"):
        raise SecurityError("Default OS installation requires the Linux Station root authority")
    report, zone, packages = _plan(repo_root, paths)
    report.update(kind="DefaultOSInstallation", mutates=True)
    if zone is None or not report["ok"]:
        return report
    initial_spec = _host_spec(paths)
    if report["organization"] and report["organization"]["state"] == "INSTALL_REQUIRED":
        organizations.register_organization(paths, organization_id=report["organization"]["id"],
                                             zone_ids=[zone["id"]])
        report["organization"]["state"] = "REGISTERED"
    for item in report["instances"]:
        if item["state"] != "INSTALL_REQUIRED":
            continue
        # Re-read Host and Zone authority before each independently locked native
        # operation. An interrupted instance is left for explicit repair.
        if _host_spec(paths) != initial_spec:
            raise SecurityError("Host desired state changed during default OS installation")
        os_lifecycle._context(paths, zone)
        if _existing(paths, zone, item["instance_id"]) is not None:
            item.update(state="PRESERVED", argv=[], next_repair_action="A concurrent instance appeared; inspect its record.")
            report["ok"] = False
            continue
        try:
            result = os_instances.install_os_instance(packages[item["instance_id"]]["source"],
                paths=paths, zone=zone, instance_id=item["instance_id"],
                organization_id=item["organization_id"], allowed_project_ids=(),
                os_id=item["os_id"], os_version=item["version"],
                hermes_binary=hermes_binary, runuser_binary=runuser_binary)
            item.update(state=result["state"], profile_count=len(result["expected_profiles"]),
                        nano_director=result["nano_director"], hermes_home=result["hermes_home"])
            if result["state"] not in {"CONFIGURED", "VERIFIED"}:
                report["ok"] = False
        except (StationError, OSError, ValueError):
            item.update(state="INCOMPLETE", next_repair_action="Inspect this instance's native installation record; no automatic retry.")
            report["ok"] = False
    report["state"] = "CONFIGURED" if report["ok"] else "INCOMPLETE"
    return report
