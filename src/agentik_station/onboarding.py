"""Local onboarding evidence and next steps, never an execution controller.

The default report performs no writes, subprocess calls, or authentication.
An explicit probe only queries the selected native systemd user service: Hermes
CLI startup itself can synchronize skills, even for a status subcommand.
"""
from __future__ import annotations

import os
import pwd
import shlex
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .doctor import _validate_local_zone_record
from .errors import SecurityError, StationError, ValidationError
from .filesystem import SafeFS
from .hermes_platforms import build_gateway_argv, gateway_service_name
from .identifiers import validate_identifier
from .paths import LayoutPaths


@contextmanager
def _directory(path: Path):
    """Read-only descriptor traversal; unlike SafeFS._open_dir, creates nothing."""
    if not path.is_absolute() or ".." in path.parts:
        raise SecurityError("Expected an absolute metadata path without traversal")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _metadata(paths: LayoutPaths, path: Path) -> tuple[str, dict[str, Any]]:
    """Bounded, non-following reads; failure details never echo file contents."""
    from .os_lifecycle import read_runtime_json

    anchor = SafeFS(paths.allowed_roots).anchor_for(path)
    try:
        value = read_runtime_json(path, uid=os.getuid() if paths.test_mode else 0, immutable=True,
                                  trusted_root=anchor if paths.test_mode else None)
        return "READ", value
    except FileNotFoundError:
        return "MISSING", {}
    except PermissionError:
        return "UNREADABLE", {}
    except (OSError, ValueError, UnicodeError, StationError):
        return "INVALID", {}


def _names(path: Path, *, suffix: str | None = None) -> list[str]:
    try:
        with _directory(path) as fd:
            names = sorted(os.listdir(fd))
            result = []
            for name in names[:1000]:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if suffix is not None:
                    if not name.endswith(suffix) or not stat.S_ISREG(info.st_mode):
                        continue
                    name = name[:-len(suffix)]
                elif not stat.S_ISDIR(info.st_mode):
                    continue
                try:
                    result.append(validate_identifier(name))
                except ValidationError:
                    continue
            return result
    except (OSError, StationError):
        return []


def _action(argv: list[str], human_action: str, *, sudo: bool = False, mutates: bool = False) -> dict[str, Any]:
    return {"argv": argv, "requires_sudo": sudo, "human_action": human_action, "mutates": mutates}


def _gate(name: str, state: str, summary: str, *, satisfied: bool = False,
          depends_on: tuple[str, ...] = (), action: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": name, "state": state, "summary": summary, "satisfied": satisfied,
            "depends_on": list(depends_on), "next_action": action, "operational": False}


def _bootstrap(paths: LayoutPaths) -> dict[str, Any]:
    from .bootstrap_state import load_bootstrap_report

    return load_bootstrap_report(paths.varlib / "bootstrap", paths.run / "bootstrap",
                                 _owner_uid=os.getuid() if paths.test_mode else 0)


def _os_record(paths: LayoutPaths, zone: dict[str, Any], os_id: str, *, configured: bool) -> dict[str, Any]:
    from .os_lifecycle import load_os_runtime_record

    return load_os_runtime_record(paths, zone=zone, os_id=os_id, require_configured=configured)


def _project_state(paths: LayoutPaths, zone: dict[str, Any], project_id: str) -> str:
    from .os_lifecycle import _context

    try:
        _context(paths, zone)
    except PermissionError:
        return "UNKNOWN_UNREADABLE"
    except (OSError, ValueError, StationError):
        return "INVALID_ZONE_RUNTIME"
    try:
        context = _context(paths, zone, project_id)
        with _directory(paths.zones_state / zone["id"] / "projects" / project_id) as fd:
            info = os.fstat(fd)
            if info.st_uid != context["uid"] or info.st_mode & 0o022:
                return "INVALID_PROJECT"
        return "LOCAL_PROJECT"
    except FileNotFoundError:
        # A missing descriptor inside an existing root is partial state, not
        # permission to create over it. The creator independently refuses it.
        for root in (Path(zone["human_root"]), paths.zones_state / zone["id"]):
            try:
                with _directory(root / "projects") as parent:
                    os.stat(project_id, dir_fd=parent, follow_symlinks=False)
                return "PARTIAL_PROJECT"
            except FileNotFoundError:
                continue
            except PermissionError:
                return "UNKNOWN_UNREADABLE"
            except OSError:
                return "INVALID_PROJECT"
        return "NOT_CREATED"
    except PermissionError:
        return "UNKNOWN_UNREADABLE"
    except (OSError, ValueError, StationError):
        return "INVALID_PROJECT"


def _probe_gateway(zone: dict[str, Any], director: str) -> dict[str, Any]:
    """Query one service without invoking Hermes, enabling linger, or starting it."""
    result: dict[str, Any] = {"state": "UNKNOWN", "service": gateway_service_name(director),
                              "claim": "SERVICE_STATUS_ONLY_NOT_ACCOUNT_OR_CHAT_ACCEPTANCE"}
    if os.geteuid() != 0:
        result["reason"] = "ROOT_REQUIRED_FOR_ZONE_IDENTITY"
        return result
    if not Path("/run/systemd/system").is_dir():
        result["reason"] = "SYSTEMD_UNAVAILABLE"
        return result
    try:
        account = pwd.getpwnam(zone["unix_user"])
        prefix = build_gateway_argv(zone, "status", runtime_uid=account.pw_uid,
                                    hermes_binary=Path("/usr/local/bin/hermes"), director_profile=director)[:-5]
        argv = [*prefix, "/usr/bin/systemctl", "--user", "--no-pager", "show", result["service"],
                "--property=LoadState", "--property=ActiveState"]
        completed = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, timeout=10, check=False,
                                   env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        result["returncode"] = completed.returncode
        # Only fixed vocabulary reaches the report; never relay native output.
        fields = dict(line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line)
        load = fields.get("LoadState")
        active = fields.get("ActiveState")
        if completed.returncode == 0 and load in {"loaded", "not-found", "masked", "error"}:
            result["load_state"] = load
            if active in {"active", "inactive", "failed", "activating", "deactivating", "reloading"}:
                result["active_state"] = active
            result["state"] = "OBSERVED_ACTIVE" if load == "loaded" and active == "active" else "OBSERVED_NOT_ACTIVE"
        else:
            result["reason"] = "SERVICE_STATUS_UNAVAILABLE"
    except subprocess.TimeoutExpired:
        result["reason"] = "PROBE_TIMEOUT"
    except (OSError, KeyError, StationError):
        result["reason"] = "SERVICE_STATUS_UNAVAILABLE"
    return result


def build_onboarding_report(paths: LayoutPaths, repo_root: Path, *, zone_id: str | None = None,
                            project_id: str | None = None, os_id: str | None = None,
                            probe: bool = False) -> dict[str, Any]:
    for value, label in ((zone_id, "zone_id"), (project_id, "project_id"), (os_id, "os_id")):
        if value is not None:
            validate_identifier(value, label)
    if project_id is not None and zone_id is None:
        raise ValidationError("Select --zone before --project")
    report: dict[str, Any] = {
        "schema_version": 1, "kind": "StationOnboardingReport", "claim": "LOCAL_EVIDENCE_NOT_LIVE_ACCEPTANCE",
        "operational": False, "read_only": True, "probe_requested": probe,
        "scope": {"zone_id": zone_id, "project_id": project_id, "os_id": os_id},
        "choices": {"zones": [], "projects": [], "os": []}, "gates": [],
    }
    try:
        from .maturity import load_os_catalog

        catalog = load_os_catalog(Path(repo_root) / "os" / "CATALOG.json")
        report["choices"]["os"] = [item["id"] for item in catalog["packages"]]
        report["catalog_claim"] = "SOURCE_PACKAGES_ONLY_NOT_INSTALLED_RUNTIME"
    except (OSError, ValueError, StationError):
        report["catalog_claim"] = "SOURCE_CATALOG_UNAVAILABLE"
    try:
        report["bootstrap"] = _bootstrap(paths)
    except PermissionError:
        report["bootstrap"] = {"status": "unreadable", "operational": False}
    except (OSError, ValueError, StationError):
        report["bootstrap"] = {"status": "invalid", "operational": False}
    host_read, host = _metadata(paths, paths.observed / "host.json")
    host_state = host.get("state") if host.get("schema_version") == 1 else None
    bootstrap_status = report["bootstrap"].get("status")
    foundation_state = "OBSERVED_READY_FOR_SETUP" if host_state == "READY_FOR_SETUP" else {
        "MISSING": "NOT_INSTALLED", "UNREADABLE": "UNKNOWN_UNREADABLE", "INVALID": "INVALID_EVIDENCE",
    }.get(host_read, "REPAIR_REQUIRED")
    if bootstrap_status in {"failed", "interrupted", "running"}:
        foundation_state = "BOOTSTRAP_" + bootstrap_status.upper()
    elif bootstrap_status in {"unreadable", "unavailable", "invalid"}:
        foundation_state = "UNKNOWN_BOOTSTRAP_EVIDENCE"
    ready = foundation_state == "OBSERVED_READY_FOR_SETUP"
    foundation_action = _action(
        ["station", "doctor", "--full", "--json"] if host_read != "MISSING" else ["./bootstrap.sh", "--plan"],
        "Inspect the bootstrap receipt and repair the failed stage; review the same installation plan before rerunning."
        if bootstrap_status in {"failed", "interrupted", "unavailable", "invalid"} else
        "Review the installation plan and complete Host bootstrap; do not infer installation from the source catalog.",
        sudo=host_read != "MISSING")
    if bootstrap_status == "unreadable" or host_read == "UNREADABLE":
        readback = ["station", "setup", "--json"]
        for flag, value in (("--zone", zone_id), ("--project", project_id), ("--os", os_id)):
            if value:
                readback.extend([flag, value])
        foundation_action = _action(readback, "Read the protected bootstrap/Host evidence through an authorized operator. Do not reinstall solely because the evidence is unreadable.", sudo=True)
    gates = report["gates"]
    gates.append(_gate("foundation", foundation_state,
                       "Host metadata and bootstrap receipts are local observations, not a fresh Host or provider check. "
                       "When bootstrap is not-started, only the kernel foundation is observed; toolchain setup remains unobserved.",
                       satisfied=ready, action=None if ready else foundation_action))
    zone: dict[str, Any] | None = None
    zone_state = "SELECTION_REQUIRED"
    report["choices"]["zones"] = _names(paths.config / "zones.d", suffix=".json")
    if zone_id:
        zone_read, candidate = _metadata(paths, paths.config / "zones.d" / f"{zone_id}.json")
        zone_state = {"MISSING": "ZONE_NOT_FOUND", "UNREADABLE": "UNKNOWN_UNREADABLE", "INVALID": "INVALID_ZONE"}.get(zone_read, "INVALID_ZONE")
        if zone_read == "READ":
            try:
                _validate_local_zone_record(candidate, record_path=paths.config / "zones.d" / f"{zone_id}.json",
                                            paths=paths, expected_host_id=host.get("host_id"))
                zone = candidate
                zone_state = "SELECTED"
                report["choices"]["projects"] = _names(Path(zone["human_root"]) / "projects")
            except (ValueError, KeyError, StationError):
                pass
    gates.append(_gate("scope", zone_state, "Select the owning local Zone; no default Zone or Project is guessed.",
                       satisfied=zone is not None, depends_on=("foundation",), action=None if zone else _action(
                           [], "Choose a reconciled Zone from choices.zones and rerun station setup --zone <id>; repair invalid Zone metadata with Station Doctor.")))
    record: dict[str, Any] | None = None
    bound_project: str | None = None
    os_state = "SELECTION_REQUIRED" if not os_id else "ZONE_REQUIRED"
    if zone and os_id:
        ledger_read, _ = _metadata(paths, paths.varlib / "registry" / "os" / zone_id / f"{os_id}.json")
        os_state = {"MISSING": "NOT_INSTALLED", "UNREADABLE": "UNKNOWN_UNREADABLE", "INVALID": "INVALID_LOCAL_INSTALL"}.get(ledger_read, "INVALID_LOCAL_INSTALL")
        if ledger_read == "READ":
            try:
                candidate = _os_record(paths, zone, os_id, configured=False)
                bound_project = candidate["project_id"]
                if project_id and candidate["project_id"] != project_id:
                    raise ValidationError("OS belongs to another Project")
                if candidate["state"] in {"CONFIGURED", "VERIFIED", "DEGRADED"}:
                    record = _os_record(paths, zone, os_id, configured=True)
                    os_state = "LOCAL_" + record["state"]
                    report["scope"]["project_id"] = record["project_id"]
                    report["scope"]["director_profile"] = record["nano_director"]
                else:
                    os_state = "INSTALL_INCOMPLETE"
            except PermissionError:
                os_state = "UNKNOWN_UNREADABLE"
            except (OSError, ValueError, KeyError, StationError):
                os_state = "INVALID_LOCAL_INSTALL"
    selected_project = report["scope"]["project_id"]
    project_state = _project_state(paths, zone, selected_project) if zone and selected_project else "SELECTION_REQUIRED"
    project_action = _action([], "Choose an existing Project from choices.projects or a new Project id, then rerun setup with --project. No owning Project is guessed.")
    if bound_project and project_id and project_id != bound_project:
        project_state = "OS_PROJECT_CONFLICT"
        project_action = _action([], f"This OS is already bound to Project {bound_project}; select that Project or another OS. Do not create a different Project to bypass the binding.")
    elif project_state == "NOT_CREATED":
        project_action = _action(["station", "project", "create", "--zone", zone_id, "--id", selected_project, "--plan"],
                                 "Review this new Project's plan, then create it without --plan. Existing or partial Projects are never overwritten.", sudo=True)
    elif project_state not in {"SELECTION_REQUIRED", "LOCAL_PROJECT"}:
        project_action = _action(["station", "doctor", "--full", "--json"],
                                 "Inspect the existing Project/Zone metadata and identity. Do not overwrite partial or invalid Project roots.", sudo=True)
    gates.append(_gate("project", project_state, "A Project owns the OS workspace, source, credentials, and evidence.",
                       satisfied=project_state == "LOCAL_PROJECT", depends_on=("scope",),
                       action=None if project_state == "LOCAL_PROJECT" else project_action))
    os_argv = ["station", "os", "install", "--id", os_id, "--zone", zone_id, "--project", selected_project] if zone and os_id and project_state == "LOCAL_PROJECT" else []
    if os_state == "INVALID_LOCAL_INSTALL" and zone and os_id:
        os_argv = ["station", "os", "verify", "--id", os_id, "--zone", zone_id]
    if os_state == "LOCAL_DEGRADED":
        os_argv = ["station", "os", "setup", "--id", os_id, "--zone", zone_id]
    gates.append(_gate("os", os_state, "Only the root-owned installation ledger and native profile readback establish a local OS installation.",
                       satisfied=record is not None and os_state != "LOCAL_DEGRADED", depends_on=("foundation", "scope", "project"), action=None if record and os_state != "LOCAL_DEGRADED" else _action(
                           os_argv, "Select an OS and existing owning Project, then install/resume its Hermes profiles. For a locally complete but degraded OS, repair provider setup and rerun OS verify; do not reinstall over it.",
                           sudo=bool(os_argv), mutates=bool(os_argv))))
    scope_args = ["--zone", zone_id, "--os", os_id] if zone and os_id else []
    gates.append(_gate("accounts", "UNKNOWN_NOT_AUTHENTICATED", "No credential values are included; account authentication, scopes, and provider APIs have not been verified.",
                       depends_on=("os",), action=_action(
                           ["station", "os", "setup", "--id", os_id, "--zone", zone_id] if record else [],
                           "Use the selected Director's native model/provider setup. Enroll only required Zone/Project accounts, then verify exact principal, scopes, and provider readback.",
                           sudo=bool(record), mutates=bool(record))))
    gateway = _probe_gateway(zone, record["nano_director"]) if probe and zone and record and project_state == "LOCAL_PROJECT" else {
        "state": "UNKNOWN_NOT_PROBED", "claim": "NO_SERVICE_OR_CHAT_READBACK"}
    report["gateway_observation"] = gateway
    gates.append(_gate("gateway", gateway["state"], "An active native service does not prove the dedicated bot, channel binding, or live send/receive works.",
                       depends_on=("os", "accounts"), action=_action(
                           ["station", "platform", "setup", *scope_args] if record else [],
                           "Configure the selected Director's dedicated bot and primary channel. Rerun OS verify after changing model or gateway configuration, before platform install/start with the same --zone and --os. Existing setup links target the Zone default profile, not this Director.",
                           sudo=bool(record), mutates=bool(record))))
    gates.append(_gate("os_verification", "LOCAL_VERIFIED" if os_state == "LOCAL_VERIFIED" else "PENDING_LOCAL_VERIFICATION",
                       "OS verification runs native profile Doctor and local readback; it does not accept providers or live chat.",
                       satisfied=os_state == "LOCAL_VERIFIED", depends_on=("os",),
                       action=None if os_state == "LOCAL_VERIFIED" else _action(
                           ["station", "os", "verify", "--id", os_id, "--zone", zone_id] if record else [],
                           "After model/provider and gateway setup, run local OS verification. Repair Doctor failures and verify again before starting the native gateway service.",
                           sudo=bool(record), mutates=bool(record))))
    gates.append(_gate("live_acceptance", "PENDING_HUMAN_ACCEPTANCE", "Local configuration and service status never imply OPERATIONAL or accepted external behavior.",
                       depends_on=("accounts", "gateway", "os_verification"), action=_action(
                           [], "Verify exact bot identity/channel and bidirectional messages, scoped account readback, fresh-session OS behavior, and required backup/restore evidence. Record human acceptance only after those checks pass.")))
    satisfied: set[str] = set()
    for gate in gates:
        if gate["satisfied"] and all(dependency in satisfied for dependency in gate["depends_on"]):
            satisfied.add(gate["id"])
    report["next_actions"] = [dict(gate["next_action"], gate=gate["id"], depends_on=gate["depends_on"],
                                   ready=all(dependency in satisfied for dependency in gate["depends_on"]))
                              for gate in gates if gate["next_action"] is not None]
    report["next_action"] = next((action for action in report["next_actions"] if action["ready"]), None)
    return report


def render_onboarding_report(report: dict[str, Any]) -> str:
    lines = ["Station setup — local evidence, not live acceptance"]
    for gate in report["gates"]:
        lines.append(f"{gate['id']}: {gate['state']}")
    action = report.get("next_action")
    if action:
        lines.extend(["", "NEXT: " + action["human_action"]])
        if action["argv"]:
            lines.append(("sudo " if action["requires_sudo"] else "") + shlex.join(action["argv"]))
    if report["scope"].get("director_profile"):
        lines.extend(["", "Remaining human-led sequence (account/chat acceptance is not inferred):"])
        for pending in report["next_actions"]:
            if action and pending["gate"] == action["gate"]:
                continue
            lines.append(f"- {pending['gate']}: {pending['human_action']}")
            if pending["argv"]:
                lines.append("  " + ("sudo " if pending["requires_sudo"] else "") + shlex.join(pending["argv"]))
    if report["choices"]["zones"] and not report["scope"]["zone_id"]:
        lines.append("Zones: " + ", ".join(report["choices"]["zones"]))
    if not report["scope"]["os_id"]:
        lines.append("OS source choices (not installed runtimes): " + ", ".join(report["choices"]["os"]))
    return "\n".join(lines)
