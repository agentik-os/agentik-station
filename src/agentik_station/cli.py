from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .constants import PRODUCT_VERSION
from .doctor import repo_doctor, station_doctor
from .errors import StationError, ValidationError
from .filesystem import SafeFS
from .identifiers import (
    environment_slug,
    validate_identifier,
    validate_optional_identifier,
    validate_remote_target,
    validate_version,
)
from .installer import StationInstaller, build_seed
from .maturity import load_catalog
from .models import InstallSpec, new_operation_id
from .paths import LayoutPaths


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _add_install_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", type=Path, help="Versioned JSON InstallSpec. Other desired-state arguments must be omitted.")
    parser.add_argument("--host-id", default="gareth-core-01")
    parser.add_argument("--role", choices=["core", "client", "project", "lab", "worker"], default="core")
    parser.add_argument("--seed-category", choices=["CLIENTS", "PROJECTS"])
    parser.add_argument("--seed-name")
    parser.add_argument("--seed-env")
    parser.add_argument("--seed-organization")
    parser.add_argument("--seed-project")
    parser.add_argument("--skip-system-packages", action="store_true")
    parser.add_argument("--skip-fail2ban", action="store_true")
    parser.add_argument("--disable-doctor-timer", action="store_true")
    parser.add_argument("--non-interactive", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--core-only", action="store_true", help=argparse.SUPPRESS)


def _spec_from_args(args: argparse.Namespace) -> InstallSpec:
    if args.spec:
        overrides = [
            args.host_id != "gareth-core-01",
            args.role != "core",
            args.seed_category,
            args.seed_name,
            args.seed_env,
            args.seed_organization,
            args.seed_project,
            args.skip_system_packages,
            args.skip_fail2ban,
            args.disable_doctor_timer,
        ]
        if any(overrides):
            raise ValidationError("Do not combine --spec with desired-state override arguments")
        return InstallSpec.load(args.spec)
    seed = build_seed(
        args.seed_category,
        args.seed_name,
        args.seed_env,
        args.seed_organization,
        args.seed_project,
    )
    return InstallSpec(
        release_version=PRODUCT_VERSION,
        host_id=args.host_id,
        role=args.role,
        install_system_packages=not args.skip_system_packages,
        configure_fail2ban=not args.skip_fail2ban,
        enable_doctor_timer=not args.disable_doctor_timer,
        seed=seed,
    )


def cmd_plan(args: argparse.Namespace) -> int:
    spec = _spec_from_args(args)
    StationInstaller(repository_root(), spec, dry_run=True).print_plan(as_json=args.json)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    spec = _spec_from_args(args)
    state = StationInstaller(repository_root(), spec).apply()
    print(f"STATE: {state}")
    return 0


def _print_doctor(result: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return
    for check in result.checks:
        print("PASS", check["name"], check.get("detail", ""))
    for warning in result.warnings:
        print("WARN", warning["name"], warning["message"])
        if warning.get("next_repair_action"):
            print("     NEXT:", warning["next_repair_action"])
    for issue in result.issues:
        print("FAIL", issue["name"], issue["message"])
        print("     NEXT:", issue["next_repair_action"])
    print("DOCTOR", "PASS" if result.ok else "FAIL")


def cmd_doctor(args: argparse.Namespace) -> int:
    paths = LayoutPaths.live()
    if args.repo:
        result = repo_doctor(repository_root())
    else:
        result = station_doctor(paths, repo_root=repository_root(), full=args.full)
    if args.record and not args.repo:
        if os.geteuid() != 0:
            raise StationError("--record requires root so the Doctor result can be stored safely")
        fs = SafeFS(paths.allowed_roots)
        fs.mkdir(paths.varlib / "doctor", 0o750)
        fs.write_text(
            paths.varlib / "doctor" / "latest.json",
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            0o640,
        )
    _print_doctor(result, args.json)
    return 0 if result.ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    path = LayoutPaths.live().observed / "host.json"
    if path.is_symlink() or not path.is_file():
        payload = {
            "state": "NOT_INSTALLED",
            "next_repair_action": "Run ./station plan, review it, then sudo ./install on a supported Host.",
        }
        print(json.dumps(payload, indent=2) if args.json else "NOT_INSTALLED\nNEXT: " + payload["next_repair_action"])
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload.get("state", "UNKNOWN"))
        print("Host:", payload.get("host_id"))
        print("Release:", payload.get("release_version"))
        print("Zones:", ", ".join(payload.get("zones", [])) or "none")
        for module in payload.get("modules", []):
            print(f"- {module['id']}: design={module['maturity']} runtime={module.get('runtime_readiness', 'UNKNOWN')}")
        if payload.get("next_repair_action"):
            print("NEXT:", payload["next_repair_action"])
    return 0 if payload.get("state") not in {"NOT_INSTALLED", "DEGRADED"} else 1


def cmd_setup(_: argparse.Namespace) -> int:
    print(
        "Station v11 setup gates\n\n"
        "1. Tailscale: install/enroll, verify Host identity and SSH reachability.\n"
        "2. Hermes: install/configure, compile Zone profiles, run Hermes and plugin Doctor.\n"
        "3. Ponytail: enable only in Builder/DevOps engineering profiles, then verify registration.\n"
        "4. Discord: enroll one dedicated Nano Director bot per OS, provision and read back the control surface.\n"
        "5. Composio: map Station principals, restrict toolkits/accounts, verify session/MCP boundaries.\n"
        "6. GitHub/providers: enroll only the narrow credentials required by each Zone/Project.\n"
        "7. Backups: configure off-Host encrypted backups and execute a restore rehearsal.\n"
        "8. Fresh session: run the OS from deployed context/tools/state only.\n"
        "9. Raise a module to OPERATIONAL only after external readback and acceptance evidence.\n"
    )
    return 0


def _load_installed_host() -> tuple[str, str]:
    path = LayoutPaths.live().config / "station.json"
    if path.is_symlink() or not path.is_file():
        raise StationError("Station desired state is not installed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_identifier(str(payload["host_id"]), "host_id"), str(payload["role"])


def cmd_zone_create(args: argparse.Namespace) -> int:
    host_id, role = _load_installed_host()
    target_host = validate_identifier(args.host or host_id, "host_id")
    if target_host != host_id:
        if os.geteuid() != 0:
            raise StationError("Registering remote desired state requires root")
        paths = LayoutPaths.live()
        fs = SafeFS(paths.allowed_roots)
        from .models import SeedSpec

        seed = SeedSpec(args.category, args.name, args.env, args.organization, args.project)
        zone_id = f"{seed.name}-{environment_slug(seed.environment)}"
        payload = {
            "schema_version": 1,
            "id": zone_id,
            "category": seed.category,
            "organization": seed.organization,
            "environment": seed.environment,
            "host_id": target_host,
            "placement": "REMOTE_DESIRED_NOT_APPLIED",
            "runtime_state": "NOT_INSTALLED",
            "next_repair_action": "Bootstrap/reconcile the target Host with this desired Zone spec.",
        }
        fs.write_text(
            paths.config / "zones.d" / f"remote-{target_host}-{zone_id}.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            0o640,
        )
        print("REGISTERED_REMOTE_DESIRED_STATE", payload["id"])
        return 0

    seed = build_seed(args.category, args.name, args.env, args.organization, args.project)
    assert seed is not None
    spec = InstallSpec(
        release_version=PRODUCT_VERSION,
        host_id=host_id,
        role=role,
        install_system_packages=False,
        configure_fail2ban=False,
        enable_doctor_timer=True,
        seed=seed,
    )
    if args.plan:
        StationInstaller(repository_root(), spec, dry_run=True).print_plan(as_json=args.json)
    else:
        state = StationInstaller(repository_root(), spec).apply()
        print("STATE:", state)
    return 0

def cmd_host_register(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise StationError("Host desired-state registration requires root")
    host_id = validate_identifier(args.id, "host_id")
    tailscale_name = validate_optional_identifier(args.tailscale_name, "tailscale_name")
    address = args.address
    if address:
        remote = validate_remote_target(address, 22)
        if remote.user:
            raise ValidationError("Host address must not contain a remote user")
        address = remote.host
    paths = LayoutPaths.live()
    fs = SafeFS(paths.allowed_roots)
    payload = {
        "schema_version": 1,
        "id": host_id,
        "role": args.role,
        "tailscale_name": tailscale_name,
        "address": address,
        "state": "DESIRED_ONLY",
    }
    fs.write_text(
        paths.config / "hosts.d" / f"{host_id}.json",
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        0o640,
    )
    print("REGISTERED_DESIRED_HOST", host_id)
    return 0

def _bootstrap_spec(args: argparse.Namespace) -> InstallSpec:
    seed = build_seed(args.zone_category, args.zone_name, args.env, args.organization, args.project)
    return InstallSpec(
        operation_id=new_operation_id(),
        release_version=PRODUCT_VERSION,
        host_id=args.id,
        role=args.role,
        install_system_packages=not args.skip_system_packages,
        configure_fail2ban=not args.skip_fail2ban,
        enable_doctor_timer=not args.disable_doctor_timer,
        seed=seed,
    )


def cmd_host_bootstrap(args: argparse.Namespace) -> int:
    from .remote import remote_bootstrap

    spec = _bootstrap_spec(args)
    payload = remote_bootstrap(
        repository_root(),
        args.target,
        args.port,
        spec,
        accept_new_host_key=args.accept_new_host_key,
        plan_only=args.plan,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0

def cmd_remote_doctor(args: argparse.Namespace) -> int:
    target = validate_remote_target(args.target, args.port)
    strict = "accept-new" if args.accept_new_host_key else "yes"
    argv = [
        "ssh",
        "-p",
        str(target.port),
        "-o",
        "BatchMode=yes",
        "-o",
        f"StrictHostKeyChecking={strict}",
        target.destination,
        "/usr/bin/sudo",
        "/usr/local/bin/station",
        "doctor",
        "--full",
        "--json",
    ]
    if args.plan:
        print(json.dumps({"state": "PLAN_READY", "argv": argv}, indent=2))
        return 0
    return subprocess.run(argv, check=False).returncode

def cmd_module_status(args: argparse.Namespace) -> int:
    catalog = load_catalog(repository_root() / "modules" / "catalog.json")
    if args.json:
        print(json.dumps(catalog, indent=2, sort_keys=True))
    else:
        for module in catalog["modules"]:
            print(f"{module['id']}: {module['maturity']} — {module['claim']}")
            if module.get("next_repair_action"):
                print("  NEXT:", module["next_repair_action"])
    return 0


def cmd_provider_status(args: argparse.Namespace) -> int:
    payload = {
        "Hermes": {"binary": shutil.which("hermes"), "readiness": "UNKNOWN_UNTIL_DOCTOR_AND_PROFILE_READBACK"},
        "Composio": {"binary": shutil.which("composio"), "readiness": "UNKNOWN_UNTIL_PRINCIPAL_AND_SESSION_READBACK"},
        "Tailscale": {"binary": shutil.which("tailscale"), "readiness": "UNKNOWN_UNTIL_IDENTITY_AND_CONNECTIVITY_READBACK"},
        "Podman": {"binary": shutil.which("podman"), "readiness": "UNKNOWN_UNTIL_ZONE_ISOLATION_TEST"},
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for name, state in payload.items():
            print(f"{name}: binary={state['binary'] or 'ABSENT'} readiness={state['readiness']}")
    return 0


def cmd_release_list(_: argparse.Namespace) -> int:
    paths = LayoutPaths.live()
    if not paths.releases.is_dir():
        print("No releases installed")
        return 1
    current = os.readlink(paths.current) if paths.current.is_symlink() else None
    for release in sorted(paths.releases.iterdir()):
        if release.is_dir() and not release.is_symlink():
            marker = " *" if current == f"releases/{release.name}" else ""
            print(release.name + marker)
    return 0


def cmd_release_rollback(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise StationError("Release rollback requires root")
    version = validate_version(args.to)
    paths = LayoutPaths.live()
    release = paths.releases / version
    if release.is_symlink() or not release.is_dir():
        raise StationError(f"Release is unavailable: {version}")
    fs = SafeFS(paths.allowed_roots)
    fs.replace_symlink(paths.current, f"releases/{version}", allowed_existing_prefix="releases/")
    print("ACTIVE_RELEASE", version)
    print("NEXT: run station doctor --full and verify runtime compatibility before further mutation.")
    return 0

def cmd_hermes_check(args: argparse.Namespace) -> int:
    from .hermes_updates import run_check

    result = run_check(LayoutPaths.live(), record=args.record)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PLAN_READY" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="station", description="Agentik Station v11 safe kernel")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Compile and display the exact typed installation plan; nothing runs")
    _add_install_options(plan)
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(handler=cmd_plan)

    apply = sub.add_parser("apply", help="Reconcile the typed desired state on this Host")
    _add_install_options(apply)
    apply.set_defaults(handler=cmd_apply)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--repo", action="store_true")
    doctor.add_argument("--full", action="store_true")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--record", action="store_true")
    doctor.set_defaults(handler=cmd_doctor)

    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=cmd_status)

    setup = sub.add_parser("setup")
    setup.set_defaults(handler=cmd_setup)

    zone = sub.add_parser("zone")
    zone_sub = zone.add_subparsers(dest="zone_command", required=True)
    create = zone_sub.add_parser("create")
    create.add_argument("--category", required=True, choices=["CLIENTS", "PROJECTS"])
    create.add_argument("--name", required=True)
    create.add_argument("--env", required=True)
    create.add_argument("--organization")
    create.add_argument("--project")
    create.add_argument("--host")
    create.add_argument("--plan", action="store_true")
    create.add_argument("--json", action="store_true")
    create.set_defaults(handler=cmd_zone_create)

    host = sub.add_parser("host")
    host_sub = host.add_subparsers(dest="host_command", required=True)
    register = host_sub.add_parser("register")
    register.add_argument("--id", required=True)
    register.add_argument("--role", required=True, choices=["core", "client", "project", "lab", "worker"])
    register.add_argument("--tailscale-name")
    register.add_argument("--address")
    register.set_defaults(handler=cmd_host_register)

    bootstrap = host_sub.add_parser("bootstrap")
    bootstrap.add_argument("--target", required=True)
    bootstrap.add_argument("--port", type=int, default=22)
    bootstrap.add_argument("--accept-new-host-key", action="store_true", help="Explicitly allow first-use host-key enrollment; strict checking is the default.")
    bootstrap.add_argument("--id", required=True)
    bootstrap.add_argument("--role", required=True, choices=["client", "project", "lab", "worker"])
    bootstrap.add_argument("--zone-category", choices=["CLIENTS", "PROJECTS"])
    bootstrap.add_argument("--zone-name")
    bootstrap.add_argument("--env")
    bootstrap.add_argument("--organization")
    bootstrap.add_argument("--project")
    bootstrap.add_argument("--skip-system-packages", action="store_true")
    bootstrap.add_argument("--skip-fail2ban", action="store_true")
    bootstrap.add_argument("--disable-doctor-timer", action="store_true")
    bootstrap.add_argument("--plan", action="store_true")
    bootstrap.set_defaults(handler=cmd_host_bootstrap)

    remote = sub.add_parser("remote")
    remote_sub = remote.add_subparsers(dest="remote_command", required=True)
    remote_doctor = remote_sub.add_parser("doctor")
    remote_doctor.add_argument("--target", required=True)
    remote_doctor.add_argument("--port", type=int, default=22)
    remote_doctor.add_argument("--accept-new-host-key", action="store_true")
    remote_doctor.add_argument("--plan", action="store_true")
    remote_doctor.set_defaults(handler=cmd_remote_doctor)

    module = sub.add_parser("module")
    module_sub = module.add_subparsers(dest="module_command", required=True)
    module_status = module_sub.add_parser("status")
    module_status.add_argument("--json", action="store_true")
    module_status.set_defaults(handler=cmd_module_status)

    provider = sub.add_parser("provider")
    provider_sub = provider.add_subparsers(dest="provider_command", required=True)
    provider_status = provider_sub.add_parser("status")
    provider_status.add_argument("--json", action="store_true")
    provider_status.set_defaults(handler=cmd_provider_status)

    release = sub.add_parser("release")
    release_sub = release.add_subparsers(dest="release_command", required=True)
    release_list = release_sub.add_parser("list")
    release_list.set_defaults(handler=cmd_release_list)
    rollback = release_sub.add_parser("rollback")
    rollback.add_argument("--to", required=True)
    rollback.set_defaults(handler=cmd_release_rollback)

    hermes = sub.add_parser("hermes")
    hermes_sub = hermes.add_subparsers(dest="hermes_command", required=True)
    hermes_check = hermes_sub.add_parser("check")
    hermes_check.add_argument("--record", action="store_true")
    hermes_check.set_defaults(handler=cmd_hermes_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except StationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("STATE: DEGRADED", file=sys.stderr)
        print("NEXT: repair the explicit error, then rerun plan/Doctor before apply.", file=sys.stderr)
        return 2


def install_main(argv: list[str] | None = None) -> int:
    return main(["apply", *(argv if argv is not None else sys.argv[1:])])
