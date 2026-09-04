from __future__ import annotations

import argparse
import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .constants import CATEGORIES, PRODUCT_VERSION
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
from .maturity import load_catalog, load_os_catalog
from .models import InstallSpec, new_operation_id
from .paths import LayoutPaths


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _add_install_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", type=Path, help="Versioned JSON InstallSpec. Other desired-state arguments must be omitted.")
    parser.add_argument("--host-id", default="station-core-01")
    parser.add_argument("--role", choices=["core", "team", "project", "lab", "worker"], default="core")
    parser.add_argument("--seed-category", choices=["ORGANIZATIONS", "PROJECTS"])
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
            args.host_id != "station-core-01",
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




def cmd_spec(args: argparse.Namespace) -> int:
    seed = build_seed(
        args.seed_category,
        args.seed_name,
        args.seed_env,
        args.seed_organization,
        args.seed_project,
    )
    spec = InstallSpec(
        release_version=PRODUCT_VERSION,
        host_id=args.host_id,
        role=args.role,
        install_system_packages=not args.skip_system_packages,
        configure_fail2ban=not args.skip_fail2ban,
        enable_doctor_timer=not args.disable_doctor_timer,
        seed=seed,
    )
    if args.output:
        spec.write(args.output)
        print(args.output)
    else:
        print(spec.to_json(), end="")
    return 0

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


def _organization_member_root(organization: str, environment: str, member_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    organization = validate_identifier(organization, "organization")
    environment = environment_slug(environment)
    human = LayoutPaths.live().runtime / "2_ZONES" / CATEGORIES["ORGANIZATIONS"] / organization / environment
    zone_descriptor = human / "ZONE.json"
    if zone_descriptor.is_symlink() or not zone_descriptor.is_file():
        raise StationError(f"Organization Zone is not installed: {human}")
    payload = json.loads(zone_descriptor.read_text(encoding="utf-8"))
    if payload.get("category") != "ORGANIZATIONS" or payload.get("name") != organization:
        raise StationError("Organization Zone descriptor does not match the requested organization")
    return (human / "members" / validate_identifier(member_id, "member_id") if member_id else human / "members", payload)


def cmd_member_add(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise StationError("Adding an Organization member requires root so Station can preserve Zone ownership")
    target, zone = _organization_member_root(args.organization, args.env, args.id)
    if args.discord_user_id is not None and not str(args.discord_user_id).isdigit():
        raise ValidationError("discord_user_id must contain digits only")
    paths = LayoutPaths.live()
    fs = SafeFS(paths.allowed_roots)
    user = pwd.getpwnam(str(zone["unix_user"]))
    owner = (user.pw_uid, user.pw_gid)
    fs.mkdir(target, 0o700, owner)
    member_id = validate_identifier(args.id, "member_id")
    organization = validate_identifier(args.organization, "organization")
    principal = f"{organization}:member:{member_id}"
    payload = {
        "schema_version": 1,
        "member_id": member_id,
        "organization": organization,
        "principal_id": principal,
        "discord_user_id": str(args.discord_user_id) if args.discord_user_id is not None else None,
        "composio_user_id": args.composio_user_id or principal,
        "memory_namespace": f"{organization}/member/{member_id}",
        "credential_namespace": f"{organization}/member/{member_id}",
        "privacy": "member-scoped",
    }
    fs.write_text(target / "MEMBER.json", json.dumps(payload, indent=2, sort_keys=True) + "\n", 0o600, owner)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_member_list(args: argparse.Namespace) -> int:
    root, _ = _organization_member_root(args.organization, args.env)
    members = []
    if root.is_dir() and not root.is_symlink():
        for descriptor in sorted(root.glob("*/MEMBER.json")):
            if descriptor.is_symlink() or not descriptor.is_file():
                continue
            members.append(json.loads(descriptor.read_text(encoding="utf-8")))
    print(json.dumps(members, indent=2, sort_keys=True))
    return 0


def cmd_setup(_: argparse.Namespace) -> int:
    print(
        "Station 11.12 setup gates\n\n"
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


def _os_catalog_entry(os_id: str) -> tuple[dict[str, Any], Path]:
    os_id = validate_identifier(os_id, "OS id")
    catalog = load_os_catalog(repository_root() / "os" / "CATALOG.json")
    for item in catalog["packages"]:
        if item["id"] == os_id:
            return item, repository_root() / str(item["path"])
    raise ValidationError(f"Unknown OS id: {os_id}")


def cmd_os_doctor(args: argparse.Namespace) -> int:
    from .os_contract import doctor_os_source
    catalog = load_os_catalog(repository_root() / "os" / "CATALOG.json")
    selected = catalog["packages"] if args.all else [next((x for x in catalog["packages"] if x["id"] == validate_identifier(args.id, "OS id")), None)]
    if selected == [None]:
        raise ValidationError(f"Unknown OS id: {args.id}")
    payload = []
    ok = True
    for item in selected:
        assert item is not None
        result = doctor_os_source(repository_root() / str(item["path"]), expected_id=str(item["id"]))
        payload.append(result.to_dict())
        ok = ok and result.ok
    if args.json:
        print(json.dumps({"schema_version": 1, "ok": ok, "results": payload}, indent=2, sort_keys=True))
    else:
        for result in payload:
            print(result["os_id"], "PASS" if result["ok"] else "FAIL")
            for issue in result["issues"]:
                print("  FAIL", issue["name"], issue["message"])
                print("  NEXT", issue["next_repair_action"])
    return 0 if ok else 1


def cmd_os_compile(args: argparse.Namespace) -> int:
    from .os_runtime import compile_os_to_hermes
    item, source = _os_catalog_entry(args.id)
    payload = compile_os_to_hermes(
        source,
        Path(args.output),
        project_root=Path(args.project_root),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_os_catalog(args: argparse.Namespace) -> int:
    catalog = load_os_catalog(repository_root() / "os" / "CATALOG.json")
    if args.json:
        print(json.dumps(catalog, indent=2, sort_keys=True))
    else:
        for item in catalog["packages"]:
            print(f"{item['id']}: source={item['maturity']} runtime={item['runtime_state']} path={item['path']}")
    return 0


def _load_zone_record(zone_id: str) -> dict[str, Any]:
    zone_id = validate_identifier(zone_id, "zone_id")
    path = LayoutPaths.live().config / "zones.d" / f"{zone_id}.json"
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"Local Zone desired state not found: {zone_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("id") != zone_id or payload.get("placement") != "local":
        raise ValidationError(f"Zone {zone_id} is not a local reconciled Zone")
    return payload


def _chown_generated_tree(root: Path, uid: int, gid: int) -> None:
    import stat
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink():
            raise StationError(f"Generated tree contains a symlink: {current_path}")
        os.chown(current_path, uid, gid, follow_symlinks=False)
        for name in files:
            path = current_path / name
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise StationError(f"Generated tree contains an unsafe file: {path}")
            os.chown(path, uid, gid, follow_symlinks=False)


def cmd_os_install(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise StationError("OS runtime installation requires root so Station can cross into the target Zone identity safely")
    import pwd
    import tempfile
    from .os_runtime import compile_os_to_hermes, install_compiled_bundle

    item, source = _os_catalog_entry(args.id)
    zone = _load_zone_record(args.zone)
    project_id = validate_identifier(args.project, "project_id")
    project_root = Path(str(zone["human_root"])) / "projects" / project_id
    if project_root.is_symlink() or not project_root.is_dir():
        raise ValidationError(f"Project does not exist in Zone {args.zone}: {project_id}")
    state_root = Path(str(zone["state_root"]))
    hermes_home = Path(str(zone["hermes_home"]))
    unix_user = validate_identifier(str(zone["unix_user"]), "Zone Unix user")
    entry = pwd.getpwnam(unix_user)
    hermes = shutil.which("hermes")
    runuser = shutil.which("runuser")
    if not hermes or not runuser:
        raise StationError("Hermes and runuser must be available before OS runtime installation")

    version = str(item["version"])
    final = state_root / "hermes" / "distributions" / str(item["id"]) / version
    if final.exists() or final.is_symlink():
        raise StationError(f"Immutable compiled OS distribution already exists: {final}")

    staging_parent = state_root / "hermes" / "compile-staging"
    staging_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=f"{item['id']}-", dir=staging_parent) as td:
        generated = Path(td) / "bundle"
        compiled = compile_os_to_hermes(source, generated, project_root=project_root)
        final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.replace(generated, final)
    _chown_generated_tree(final, entry.pw_uid, entry.pw_gid)

    result = install_compiled_bundle(
        final,
        hermes_home=hermes_home,
        unix_user=unix_user,
        hermes_binary=hermes,
        runuser_binary=runuser,
    )
    record = {
        "schema_version": 1,
        "os_id": item["id"],
        "os_version": version,
        "zone_id": args.zone,
        "project_id": project_id,
        "compiled_distribution": str(final),
        "runtime": result,
        "state": result["state"],
        "claim": "CONFIGURED_NOT_OPERATIONAL" if result["state"] == "CONFIGURED" else "DEGRADED",
    }
    output = Path(str(zone["human_root"])) / "os" / f"{item['id']}.runtime.json"
    fs = SafeFS(LayoutPaths.live().allowed_roots)
    fs.write_text(output, json.dumps(record, indent=2, sort_keys=True) + "\n", 0o640, (entry.pw_uid, entry.pw_gid))
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if result["state"] == "CONFIGURED" else 1


def cmd_os_verify(args: argparse.Namespace) -> int:
    import pwd
    zone = _load_zone_record(args.zone)
    item, _ = _os_catalog_entry(args.id)
    unix_user = validate_identifier(str(zone["unix_user"]), "Zone Unix user")
    hermes_home = Path(str(zone["hermes_home"]))
    hermes = shutil.which("hermes")
    runuser = shutil.which("runuser")
    if not hermes or not runuser:
        raise StationError("Hermes and runuser are required for OS verification")
    record_path = Path(str(zone["human_root"])) / "os" / f"{item['id']}.runtime.json"
    if record_path.is_symlink() or not record_path.is_file():
        raise ValidationError("OS runtime record is missing; install the OS first")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    profiles = record.get("runtime", {}).get("profiles", [])
    profile_ids = [str(x.get("profile")) for x in profiles if x.get("profile")]
    observations = []
    ok = bool(profile_ids)
    for profile in profile_ids:
        argv = [runuser, "--user", unix_user, "--", "/usr/bin/env", f"HERMES_HOME={hermes_home}", hermes, "-p", profile, "doctor"]
        completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=300)
        observations.append({"profile": profile, "returncode": completed.returncode, "stdout": completed.stdout[-8000:], "stderr": completed.stderr[-8000:]})
        ok = ok and completed.returncode == 0
    payload = {
        "schema_version": 1,
        "os_id": item["id"],
        "zone_id": args.zone,
        "state": "VERIFIED" if ok else "DEGRADED",
        "observations": observations,
        "operational": False,
        "next_repair_action": "Complete dedicated Discord/connector readback and fresh-session acceptance before OPERATIONAL." if ok else "Repair failing Hermes profile Doctor results.",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if ok else 1


def cmd_composio_validate(args: argparse.Namespace) -> int:
    from .providers.composio import load_binding
    binding = load_binding(Path(args.binding))
    print(json.dumps({"state":"VALID","principal":binding.principal,"session_config":binding.to_session_config()}, indent=2, sort_keys=True))
    return 0


def cmd_discord_validate(args: argparse.Namespace) -> int:
    from .providers.discord import verify_binding
    path = Path(args.binding)
    if path.is_symlink() or not path.is_file():
        raise ValidationError("Discord binding must be a regular file")
    binding = verify_binding(json.loads(path.read_text(encoding="utf-8")))
    safe = dict(binding)
    safe["token_file"] = "<credential-reference>"
    print(json.dumps({"state":"VALID","binding":safe}, indent=2, sort_keys=True))
    return 0


def cmd_rootless_status(args: argparse.Namespace) -> int:
    from .providers.rootless import zone_readiness
    zone = _load_zone_record(args.zone)
    payload = zone_readiness(Path(str(zone["state_root"])))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0



def cmd_backup_plan(args: argparse.Namespace) -> int:
    from .providers.backup import plan_backup
    zone = _load_zone_record(args.zone)
    roots = [Path(str(zone["human_root"])), Path(str(zone["state_root"]))]
    payload = plan_backup(args.zone, roots, Path(args.repository_file), Path(args.password_file))
    if args.output:
        out = Path(args.output)
        if not out.is_absolute():
            raise ValidationError("backup plan output must be an absolute path")
        if out.is_symlink():
            raise ValidationError("backup plan output may not be a symlink")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _load_backup_plan(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if path.is_symlink() or not path.is_file():
        raise ValidationError("backup plan must be a regular file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("provider") != "restic" or payload.get("claim") != "PLAN_NOT_RUN":
        raise ValidationError("unsupported or malformed backup plan")
    return payload


def cmd_backup_run(args: argparse.Namespace) -> int:
    from .providers.backup import run_backup
    payload = run_backup(_load_backup_plan(args.plan))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("returncode") == 0 else 1


def cmd_backup_check(args: argparse.Namespace) -> int:
    from .providers.backup import check_repository
    plan = _load_backup_plan(args.plan)
    payload = check_repository(Path(plan["repository_file"]), Path(plan["password_file"]))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("verified") else 1



def cmd_tui(args: argparse.Namespace) -> int:
    """Open AGK-TUI (Hermes / Codex / Claude Code / terminal sessions via RMUX)."""
    import os
    import shutil
    # Prefer installed launcher, then repo-local component wrapper.
    candidates = []
    which = shutil.which('agk')
    if which:
        candidates.append(which)
    home = Path.home()
    candidates.extend([
        home / '.local' / 'bin' / 'agk',
        Path('/usr/local/bin/agk'),
    ])
    repo = Path(__file__).resolve().parents[2]
    candidates.append(repo / 'components' / 'agk-tui' / 'bin' / 'agk')
    target = next((Path(p) for p in candidates if Path(p).exists() and os.access(p, os.X_OK)), None)
    if target is None:
        print('ERROR: AGK-TUI launcher `agk` not found. Install via bootstrap or components/agk-tui/install.sh.', file=sys.stderr)
        print('STATE: DEGRADED', file=sys.stderr)
        print('NEXT: sudo ./bootstrap.sh (or re-run with AGK-TUI enabled), then station tui.', file=sys.stderr)
        return 2
    os.environ.setdefault('AGK_ENVIRONMENT', os.environ.get('USER') or Path.home().name)
    # Forward remaining argv after `tui`
    extra = list(getattr(args, 'tui_args', []) or [])
    os.execv(str(target), [str(target), *extra])
    return 0  # unreachable


def cmd_recovery_rehearse(args: argparse.Namespace) -> int:
    from .providers.backup import restore_to_staging
    plan = _load_backup_plan(args.plan)
    payload = restore_to_staging(plan, Path(args.target), snapshot=args.snapshot)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("returncode") == 0 else 1

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="station", description="Agentik Station 11.12")
    sub = parser.add_subparsers(dest="command", required=True)


    spec_cmd = sub.add_parser("spec", help="Create a validated versioned InstallSpec without mutating the Host")
    spec_cmd.add_argument("--host-id", default="station-core-01")
    spec_cmd.add_argument("--role", choices=["core", "team", "project", "lab", "worker"], default="core")
    spec_cmd.add_argument("--seed-category", choices=["ORGANIZATIONS", "PROJECTS"])
    spec_cmd.add_argument("--seed-name")
    spec_cmd.add_argument("--seed-env")
    spec_cmd.add_argument("--seed-organization")
    spec_cmd.add_argument("--seed-project")
    spec_cmd.add_argument("--skip-system-packages", action="store_true")
    spec_cmd.add_argument("--skip-fail2ban", action="store_true")
    spec_cmd.add_argument("--disable-doctor-timer", action="store_true")
    spec_cmd.add_argument("--output", type=Path)
    spec_cmd.set_defaults(handler=cmd_spec)

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
    create.add_argument("--category", required=True, choices=["ORGANIZATIONS", "PROJECTS"])
    create.add_argument("--name", required=True)
    create.add_argument("--env", required=True)
    create.add_argument("--organization")
    create.add_argument("--project")
    create.add_argument("--host")
    create.add_argument("--plan", action="store_true")
    create.add_argument("--json", action="store_true")
    create.set_defaults(handler=cmd_zone_create)

    member = sub.add_parser("member", help="Manage logical human principals inside an Organization Zone")
    member_sub = member.add_subparsers(dest="member_command", required=True)
    member_add = member_sub.add_parser("add")
    member_add.add_argument("--organization", required=True)
    member_add.add_argument("--env", default="development")
    member_add.add_argument("--id", required=True)
    member_add.add_argument("--discord-user-id")
    member_add.add_argument("--composio-user-id")
    member_add.set_defaults(handler=cmd_member_add)
    member_list = member_sub.add_parser("list")
    member_list.add_argument("--organization", required=True)
    member_list.add_argument("--env", default="development")
    member_list.set_defaults(handler=cmd_member_list)

    host = sub.add_parser("host")
    host_sub = host.add_subparsers(dest="host_command", required=True)
    register = host_sub.add_parser("register")
    register.add_argument("--id", required=True)
    register.add_argument("--role", required=True, choices=["core", "team", "project", "lab", "worker"])
    register.add_argument("--tailscale-name")
    register.add_argument("--address")
    register.set_defaults(handler=cmd_host_register)

    bootstrap = host_sub.add_parser("bootstrap")
    bootstrap.add_argument("--target", required=True)
    bootstrap.add_argument("--port", type=int, default=22)
    bootstrap.add_argument("--accept-new-host-key", action="store_true", help="Explicitly allow first-use host-key enrollment; strict checking is the default.")
    bootstrap.add_argument("--id", required=True)
    bootstrap.add_argument("--role", required=True, choices=["team", "project", "lab", "worker"])
    bootstrap.add_argument("--zone-category", choices=["ORGANIZATIONS", "PROJECTS"])
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
    composio_validate = provider_sub.add_parser("composio-validate")
    composio_validate.add_argument("--binding", required=True)
    composio_validate.set_defaults(handler=cmd_composio_validate)
    discord_validate = provider_sub.add_parser("discord-validate")
    discord_validate.add_argument("--binding", required=True)
    discord_validate.set_defaults(handler=cmd_discord_validate)

    os_cmd = sub.add_parser("os")
    os_sub = os_cmd.add_subparsers(dest="os_command", required=True)
    os_catalog = os_sub.add_parser("catalog")
    os_catalog.add_argument("--json", action="store_true")
    os_catalog.set_defaults(handler=cmd_os_catalog)
    os_doctor = os_sub.add_parser("doctor")
    group = os_doctor.add_mutually_exclusive_group(required=True)
    group.add_argument("--id")
    group.add_argument("--all", action="store_true")
    os_doctor.add_argument("--json", action="store_true")
    os_doctor.set_defaults(handler=cmd_os_doctor)
    os_compile = os_sub.add_parser("compile")
    os_compile.add_argument("--id", required=True)
    os_compile.add_argument("--project-root", required=True)
    os_compile.add_argument("--output", required=True)
    os_compile.set_defaults(handler=cmd_os_compile)
    os_install = os_sub.add_parser("install")
    os_install.add_argument("--id", required=True)
    os_install.add_argument("--zone", required=True)
    os_install.add_argument("--project", required=True)
    os_install.set_defaults(handler=cmd_os_install)
    os_verify = os_sub.add_parser("verify")
    os_verify.add_argument("--id", required=True)
    os_verify.add_argument("--zone", required=True)
    os_verify.set_defaults(handler=cmd_os_verify)

    rootless = sub.add_parser("rootless")
    rootless_sub = rootless.add_subparsers(dest="rootless_command", required=True)
    rootless_status = rootless_sub.add_parser("status")
    rootless_status.add_argument("--zone", required=True)
    rootless_status.set_defaults(handler=cmd_rootless_status)

    backup = sub.add_parser("backup")
    backup_sub = backup.add_subparsers(dest="backup_command", required=True)
    backup_plan = backup_sub.add_parser("plan")
    backup_plan.add_argument("--zone", required=True)
    backup_plan.add_argument("--repository-file", required=True)
    backup_plan.add_argument("--password-file", required=True)
    backup_plan.add_argument("--output")
    backup_plan.set_defaults(handler=cmd_backup_plan)
    backup_run = backup_sub.add_parser("run")
    backup_run.add_argument("--plan", required=True)
    backup_run.set_defaults(handler=cmd_backup_run)
    backup_check = backup_sub.add_parser("check")
    backup_check.add_argument("--plan", required=True)
    backup_check.set_defaults(handler=cmd_backup_check)

    recovery = sub.add_parser("recovery")
    recovery_sub = recovery.add_subparsers(dest="recovery_command", required=True)
    rehearse = recovery_sub.add_parser("rehearse")
    rehearse.add_argument("--plan", required=True)
    rehearse.add_argument("--target", required=True)
    rehearse.add_argument("--snapshot", default="latest")
    rehearse.set_defaults(handler=cmd_recovery_rehearse)

    release = sub.add_parser("release")
    release_sub = release.add_subparsers(dest="release_command", required=True)
    release_list = release_sub.add_parser("list")
    release_list.set_defaults(handler=cmd_release_list)
    rollback = release_sub.add_parser("rollback")
    rollback.add_argument("--to", required=True)
    rollback.set_defaults(handler=cmd_release_rollback)


    tui = sub.add_parser("tui", help="Open AGK-TUI live sessions (Hermes, Codex, Claude Code, terminal)")
    tui.add_argument("tui_args", nargs=argparse.REMAINDER, help="Optional args forwarded to agk")
    tui.set_defaults(handler=cmd_tui)

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
