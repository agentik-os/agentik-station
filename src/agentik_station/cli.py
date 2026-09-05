from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import shutil
import stat
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


def cmd_setup(args: argparse.Namespace) -> int:
    from .onboarding import build_onboarding_report, render_onboarding_report

    report = build_onboarding_report(
        LayoutPaths.live(), repository_root(),
        zone_id=args.zone, project_id=args.project, os_id=args.os, probe=args.probe,
        organization_id=args.organization, instance_id=args.instance,
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_onboarding_report(report))
    return 0


def cmd_organization(args: argparse.Namespace) -> int:
    from .organizations import load_organization, register_organization

    paths = LayoutPaths.live()
    if args.organization_command == "register":
        result = register_organization(paths, organization_id=args.id, zone_ids=args.zone, plan=args.plan)
    else:
        result = load_organization(paths, organization_id=args.id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_project_create(args: argparse.Namespace) -> int:
    from .projects import create_project

    result = create_project(
        LayoutPaths.live(), repository_root(), zone=_load_zone_record(args.zone),
        project_id=args.id, plan=args.plan,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_setup_link(args: argparse.Namespace) -> int:
    """Create or serve one-time, Tailnet-only setup redirects."""
    from .guided_setup import SetupLinkStore, serve_setup_links, setup_link_card

    store = SetupLinkStore(Path(args.state_root))
    if args.setup_link_command == "serve":
        serve_setup_links(store, host=args.host, port=args.port)
        return 0
    if args.target_url_file:
        target_file = Path(args.target_url_file)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target_file, os.O_RDONLY | nofollow)
        except OSError as exc:
            raise ValidationError("setup target URL file must be an owned regular non-symlink file") from exc
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_size > 4096:
                raise ValidationError("setup target URL file must be an owned regular file of at most 4096 bytes")
            target_url = os.read(descriptor, 4097).decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ValidationError("setup target URL file must contain UTF-8 text") from exc
        finally:
            os.close(descriptor)
    else:
        target_url = str(args.target_url or "")
        if args.purpose == "composio-oauth":
            raise ValidationError("Composio Connect Links must use --target-url-file, never a process argument")
    link = store.create(
        base_url=args.base_url,
        target_url=target_url,
        zone_id=args.zone,
        principal_id=args.principal,
        provider=args.provider,
        purpose=args.purpose,
        ttl_seconds=args.ttl,
    )
    payload = link.to_dict()
    payload["card"] = setup_link_card(link)
    print(json.dumps(payload, indent=2, sort_keys=True))
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
        paths = LayoutPaths.live()
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
        if args.plan:
            print(json.dumps({"kind": "RemoteZoneRegistrationPlan", "desired": payload,
                              "mutates": False, "operational": False}, indent=2, sort_keys=True))
            return 0
        if os.geteuid() != 0:
            raise StationError("Registering remote desired state requires root")
        fs = SafeFS(paths.allowed_roots)
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


def _resource_catalog() -> dict[str, Any]:
    from .resources import load_resource_catalog

    return load_resource_catalog(repository_root() / "resources" / "CATALOG.json")


def cmd_resource_list(args: argparse.Namespace) -> int:
    catalog = _resource_catalog()
    if args.json:
        print(json.dumps(catalog, indent=2, sort_keys=True))
    else:
        for item in catalog["resources"]:
            print(f"resource {item['id']}: {item['kind']} {item.get('package', '')}@{item.get('version', '')}")
        for item in catalog["stacks"]:
            marker = " (default)" if item["id"] == catalog["default_stack"] else ""
            print(f"stack {item['id']}{marker}: {item['purpose']}")
        print("POLICY: preferred recipes are open to reviewed alternative stacks")
    return 0


def cmd_resource_show(args: argparse.Namespace) -> int:
    from .resources import find_resource

    print(json.dumps(find_resource(_resource_catalog(), args.id), indent=2, sort_keys=True))
    return 0


def cmd_resource_stack_plan(args: argparse.Namespace) -> int:
    from .resources import build_stack_plan

    print(json.dumps(build_stack_plan(_resource_catalog(), args.id), indent=2, sort_keys=True))
    return 0


def _canonical_agent_rules() -> str:
    path = repository_root() / "rules" / "STATION_AGENT_RULES.md"
    if path.is_symlink() or not path.is_file():
        raise StationError(f"Canonical Station rules are missing or unsafe: {path}")
    return path.read_text(encoding="utf-8")


def cmd_rules_show(_: argparse.Namespace) -> int:
    print(_canonical_agent_rules(), end="")
    return 0


def cmd_rules_install(args: argparse.Namespace) -> int:
    from .agent_rules import install_agent_rules

    if not args.plan and os.geteuid() == 0:
        raise StationError("Install repository rules as the owning Project user, not root; use --plan for root inspection")
    payload = install_agent_rules(Path(args.repo), _canonical_agent_rules(), plan_only=args.plan)
    print(json.dumps(payload, indent=2, sort_keys=True))
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


def _agk_launcher() -> Path:
    from .agk_launcher import PUBLIC_LAUNCHER, validate_public_launcher

    # Prefer the administrator-published identity handoff, not private software
    # found in root's inherited PATH. The source component is not an install.
    if PUBLIC_LAUNCHER.exists() or PUBLIC_LAUNCHER.is_symlink():
        try:
            validate_public_launcher()
        except OSError:
            raise StationError("The public AGK launcher is unsafe; administrator repair is required") from None
        return PUBLIC_LAUNCHER
    candidates: list[Path] = []
    if os.geteuid() != 0:
        discovered = shutil.which("agk")
        if discovered:
            candidates.append(Path(discovered))
        candidates.append(Path.home() / ".local/bin/agk")
    target = next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)
                   and (path.resolve().parent.parent / "lib/agk-terminal/bin/agk-tui").is_file()), None)
    if target is None:
        raise StationError(
            "AGK is not publicly installed. Ask the administrator to run "
            "station tui-install --operator agk-station; existing operators can use sudo -iu agk-station."
        )
    return target


def cmd_client(args: argparse.Namespace) -> int:
    """Explicit compatibility entrypoint, not Station Organization enrollment."""
    if not args.legacy:
        raise ValidationError(
            "The legacy AGK client controller uses operator-home workspaces/profiles, not Station Zones. "
            "Use station organization register and station os instance for new clients. "
            "Only for an inspected existing legacy deployment, opt in with station client --legacy <arguments>."
        )
    target = _agk_launcher()
    forwarded = list(args.client_args or [])
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        forwarded = ["--help"]
    completed = subprocess.run([str(target), "client", *forwarded], check=False)
    return int(completed.returncode)


def _composio_binary() -> Path:
    candidates = [
        Path(shutil.which("composio") or ""),
        Path("/home/agk-station/.local/bin/composio"),
        Path("/usr/local/bin/composio"),
    ]
    target = next(
        (path for path in candidates if path.is_absolute() and path.is_file() and os.access(path, os.X_OK)),
        None,
    )
    if target is None:
        raise StationError("Pinned Composio CLI is missing; run `station deps toolchain-install` first")
    return target


def cmd_composio_discord(args: argparse.Namespace) -> int:
    """Plan, authorize or read back the Zone-scoped Composio Discord adapter."""
    from .providers.composio import stable_principal

    zone = _load_zone_record(args.zone)
    action = args.composio_discord_command
    organization = str(zone.get("organization") or "") or None
    principal = stable_principal(args.zone, organization, "atlas")
    commands = {
        "link": ["connected-accounts", "link", "discord"],
        "verify": ["connected-accounts", "list", "--toolkits", "discord"],
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "adapter": "composio-discord",
        "role": "zone-scoped-tool-adapter",
        "gateway": "hermes-native",
        "zone_id": args.zone,
        "principal": principal,
        "policy": "config/composio/discord-tool-policy.json",
        "operational": False,
    }
    if action == "plan":
        payload.update(
            {
                "state": "READY_FOR_SETUP",
                "commands": [
                    ["composio", *commands["link"]],
                    ["composio", *commands["verify"]],
                    ["composio", "tools", "list", "--toolkit", "discord"],
                ],
                "next_repair_action": (
                    "Run the link action as the owning Zone identity, complete OAuth, then run verify and a "
                    "read-only tool before accepting the adapter."
                ),
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if os.geteuid() != 0:
        raise StationError("Composio Discord link/verify requires root for Zone identity switching")
    binary = _composio_binary()
    unix_user = validate_identifier(str(zone.get("unix_user", "")), "Zone Unix user")
    entry = pwd.getpwnam(unix_user)
    runuser = Path(shutil.which("runuser") or "/usr/sbin/runuser")
    if not runuser.is_file():
        raise StationError("runuser is required for Zone-isolated Composio setup")
    home = Path(entry.pw_dir)
    argv = [
        str(runuser),
        "--user",
        unix_user,
        "--",
        "/usr/bin/env",
        "-i",
        f"HOME={home}",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        f"COMPOSIO_USER_ID={principal}",
        str(binary),
        *commands[action],
    ]
    interactive = action == "link"
    completed = subprocess.run(
        argv,
        check=False,
        text=True,
        capture_output=not interactive,
        timeout=None if interactive else 120,
    )
    payload["returncode"] = completed.returncode
    payload["state"] = (
        "AUTH_FLOW_COMPLETED_NOT_VERIFIED"
        if action == "link" and completed.returncode == 0
        else ("OBSERVED_NOT_ACCEPTED" if completed.returncode == 0 else "DEGRADED")
    )
    if not interactive:
        payload["stdout"] = completed.stdout[-12000:]
        payload["stderr"] = completed.stderr[-12000:]
    payload["next_repair_action"] = (
        f"Run `station provider composio-discord verify --zone {args.zone}`, then execute and read back an "
        "approved read-only Discord tool."
        if action == "link" and completed.returncode == 0
        else "Accept only after account ACTIVE status, policy validation and a read-only Discord tool readback."
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return int(completed.returncode)


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


def cmd_hermes_update(args: argparse.Namespace) -> int:
    """Apply a backed-up, Doctor-gated Hermes update with a durable receipt."""
    import os
    script = repository_root() / "scripts" / "station_hermes_update.sh"
    if not script.is_file():
        raise StationError(f"missing {script}")
    mode = "check" if args.check_only else "update"
    cmd = ["bash", str(script), mode]
    print("RUNNING", " ".join(cmd))
    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode)


def cmd_deps(args: argparse.Namespace) -> int:
    """Required Host software inventory, independent installers and native checks."""
    if args.deps_command in {"full-plan", "full-check"}:
        from .full_stack import check, plan
        result = (plan(repository_root()) if args.deps_command == "full-plan" else
                  check(repository_root(), operator=args.operator))
        print(json.dumps(result, indent=2))
        return 0 if args.deps_command == "full-plan" or result["full_software_verified"] else 1
    if args.deps_command in {"service-plan", "service-check"}:
        from .service_software import check_bundle, install_bundle
        result = (install_bundle(repository_root(), args.component, plan=True)
                  if args.deps_command == "service-plan" else check_bundle(repository_root(), args.component))
        print(json.dumps(result, indent=2))
        return 0 if args.deps_command == "service-plan" or result["software_installed"] else 1
    if args.deps_command.startswith("toolchain-"):
        script = repository_root() / "scripts" / "station_toolchain_install.sh"
        if not script.is_file():
            raise StationError(f"missing {script}")
        mode = args.deps_command.removeprefix("toolchain-")
        cmd = ["bash", str(script), f"--{mode}"]
        print("RUNNING", " ".join(cmd))
        return int(subprocess.run(cmd, check=False).returncode)
    script = repository_root() / "scripts" / "station_deps_install.sh"
    if not script.is_file():
        raise StationError(f"missing {script}")
    cmd = ["bash", str(script)]
    if args.deps_command == "list":
        cmd.append("--list")
    elif args.deps_command == "platforms":
        cmd.append("--platforms-guide")
    elif args.deps_command == "enable-auto-update":
        cmd.append("--enable-hermes-auto-update")
    elif args.deps_command == "web-check":
        cmd.append("--check-web")
    elif args.deps_command == "install":
        if args.all:
            cmd.append("--all")
        for item in args.component or []:
            cmd.extend(["--component", item])
        if len(cmd) == 2:
            raise ValidationError("pass --all or --component ID")
    else:
        raise ValidationError(f"unknown deps command: {args.deps_command}")
    print("RUNNING", " ".join(cmd))
    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode)


def cmd_platform_gateway(args: argparse.Namespace) -> int:
    """Run the native Hermes gateway under the owning Zone identity and HERMES_HOME."""
    from .hermes_platforms import build_gateway_argv, normalize_platform, platform_setup_guidance
    from .native_process import run_bounded_native

    zone = _load_zone_record(args.zone)
    requested_platform = normalize_platform(getattr(args, "platform", None))
    runtime = None
    instance_id = getattr(args, "instance", None)
    role = getattr(args, "role", None)
    if role and not instance_id:
        raise ValidationError("An explicit team --role requires --instance")
    if instance_id and getattr(args, "os", None):
        raise ValidationError("Select either --instance or legacy --os, never both")
    if instance_id:
        from .os_instances import load_os_instance_record
        runtime = load_os_instance_record(
            LayoutPaths.live(), zone=zone, instance_id=instance_id, require_configured=True,
        )
    elif getattr(args, "os", None):
        from .os_lifecycle import load_os_runtime_record
        runtime = load_os_runtime_record(
            LayoutPaths.live(), zone=zone, os_id=args.os, require_configured=True,
        )
    if runtime and runtime["state"] == "DEGRADED" and args.platform_command in {"install", "start", "restart"}:
        raise ValidationError("Repair the selected Director and rerun OS verification before starting its gateway")
    profile = runtime["nano_director"] if runtime else "default"
    if role:
        role = validate_identifier(role, "OS team role")
        profile = runtime["role_profile_map"].get(role)
        if profile is None:
            raise ValidationError("Requested role is not in this instance's trusted Hermes team")
    hermes = next(
        (path for path in (Path("/usr/local/bin/hermes"), Path(shutil.which("hermes") or "")) if path.is_absolute() and path.is_file()),
        None,
    )
    runuser = Path(shutil.which("runuser") or "/usr/sbin/runuser")
    if hermes is None:
        raise StationError("Shared Hermes launcher is missing; rerun bootstrap.sh with Hermes enabled")
    if not runuser.is_file():
        raise StationError("runuser is required for Zone-isolated Hermes gateways")
    unix_user = validate_identifier(str(zone.get("unix_user", "")), "Zone Unix user")
    try:
        zone_user = pwd.getpwnam(unix_user)
        zone_group = grp.getgrnam(unix_user)
    except KeyError as exc:
        raise StationError(f"Zone Unix user/group is missing: {unix_user}") from exc
    if (zone_user.pw_uid == 0 or zone_user.pw_gid == 0
            or zone_user.pw_gid != zone_group.gr_gid
            or Path(zone_user.pw_dir) != Path(zone["state_root"]) / "home"
            or zone_user.pw_shell not in {"/usr/sbin/nologin", "/sbin/nologin", "/bin/false"}):
        raise ValidationError("Zone Unix identity does not match its canonical home/group/shell")
    argv = build_gateway_argv(
        zone,
        args.platform_command,
        runtime_uid=zone_user.pw_uid,
        hermes_binary=hermes,
        runuser_binary=runuser,
        director_profile=profile,
        instance_id=instance_id,
    )
    payload = {
        "schema_version": 1,
        "zone_id": args.zone,
        "os_id": runtime["os_id"] if runtime else None,
        "project_id": runtime.get("project_id") if runtime else None,
        "instance_id": instance_id,
        "organization_id": runtime.get("organization_id") if runtime else None,
        "allowed_project_ids": runtime.get("allowed_project_ids", []) if runtime else [],
        "profile": profile,
        "role": role,
        "bundle_sha256": runtime["bundle_sha256"] if runtime else None,
        "platform": requested_platform,
        "platform_selection": "operator-intent-only; actions target the selected profile's whole gateway",
        "action": args.platform_command,
        "argv": argv,
        "claim": "PREPARED_NOT_RUN" if args.plan else "OBSERVED_NOT_ACCEPTED",
        "operational": False,
        "next_repair_action": (
            "Complete the Hermes wizard/service action, then send and receive a live message on the named "
            "platform before recording ACCEPTED."
        ),
    }
    if args.platform_command == "setup":
        payload["setup_guidance"] = list(platform_setup_guidance(requested_platform))
    if args.plan:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if os.geteuid() != 0:
        raise StationError("Executing a Zone gateway action requires root for runuser identity switching")
    if args.platform_command == "setup":
        print(f"Station setup scope: Zone {args.zone}, profile {profile}", file=sys.stderr)
        for instruction in payload["setup_guidance"]:
            print(f"  - {instruction}", file=sys.stderr)
    if args.platform_command == "install":
        loginctl = shutil.which("loginctl")
        systemctl = shutil.which("systemctl")
        if not loginctl or not systemctl or not Path("/run/systemd/system").is_dir():
            raise StationError("Hermes gateway service installation requires a running systemd/loginctl Host")
        for command, label in (
            ([loginctl, "enable-linger", unix_user], "enable Zone systemd linger"),
            ([systemctl, "start", f"user@{zone_user.pw_uid}.service"], "start the Zone systemd user manager"),
        ):
            try:
                prerequisite = run_bounded_native(command, timeout=30)
            except (OSError, subprocess.SubprocessError):
                raise StationError(f"Could not {label} within its time limit; inspect Host service logs before retrying") from None
            if prerequisite.returncode != 0:
                raise StationError(f"Could not {label}; inspect Host service logs before retrying")
    interactive = args.platform_command in {"setup", "configure"}
    try:
        # Wizards retain the human's TTY. Service actions have no interactive
        # input and must clean up the runuser child group on timeout/cancel.
        completed = (subprocess.run(argv, check=False) if interactive
                     else run_bounded_native(argv, timeout=300))
        returncode = completed.returncode
    except subprocess.TimeoutExpired:
        returncode = 124
        payload["error"] = "Native Hermes command exceeded its time limit; inspect the owning Zone logs."
    except (OSError, subprocess.SubprocessError):
        returncode = 127
        payload["error"] = "Native Hermes command could not complete safely; verify the shared launcher, Zone identity and logs."
    payload["returncode"] = returncode
    if not interactive:
        # JSON is consumed by bots and UI surfaces. Native output may contain
        # provider/account material; never export it into that projection.
        payload["native_output_exported"] = False
    payload["claim"] = "OBSERVED_COMMAND_SUCCEEDED_NOT_ACCEPTED" if returncode == 0 else "COMMAND_FAILED_NOT_ACCEPTED"
    print(json.dumps(payload, indent=2, sort_keys=True))
    return int(returncode)


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
    from .os_lifecycle import read_runtime_json

    zone_id = validate_identifier(zone_id, "zone_id")
    layout = LayoutPaths.live()
    path = layout.config / "zones.d" / f"{zone_id}.json"
    SafeFS._assert_existing_absolute_chain(path.parent)
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"Local Zone desired state not found: {zone_id}")
    payload = read_runtime_json(
        path, uid=os.getuid() if layout.test_mode else 0, immutable=True,
        trusted_root=layout.config if layout.test_mode else None,
    )
    if not isinstance(payload, dict) or payload.get("id") != zone_id or payload.get("placement") != "local":
        raise ValidationError(f"Zone {zone_id} is not a local reconciled Zone")
    from .doctor import _validate_local_zone_record
    try:
        _validate_local_zone_record(payload, record_path=path, paths=layout, expected_host_id=None)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValidationError(f"Zone desired record does not match canonical ownership/layout: {zone_id}") from exc
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
        raise StationError("OS runtime installation requires root for the owning Zone identity")
    from .os_lifecycle import install_os_runtime

    item, source = _os_catalog_entry(args.id)
    zone = _load_zone_record(args.zone)
    hermes, runuser = shutil.which("hermes"), shutil.which("runuser")
    if not hermes or not runuser:
        raise StationError("Hermes and runuser must be available before OS runtime installation")
    record = install_os_runtime(
        source, paths=LayoutPaths.live(), zone=zone,
        project_id=args.project, os_id=item["id"], os_version=item["version"],
        hermes_binary=hermes, runuser_binary=runuser,
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if record["state"] in {"CONFIGURED", "VERIFIED"} else 1


def cmd_os_verify(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise StationError("OS runtime verification requires root for trusted evidence and Zone execution")
    from .os_lifecycle import verify_os_runtime

    item, _ = _os_catalog_entry(args.id)
    zone = _load_zone_record(args.zone)
    hermes, runuser = shutil.which("hermes"), shutil.which("runuser")
    if not hermes or not runuser:
        raise StationError("Hermes and runuser are required for OS verification")
    record = verify_os_runtime(
        LayoutPaths.live(), zone=zone, os_id=item["id"],
        hermes_binary=hermes, runuser_binary=runuser,
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if record["state"] == "VERIFIED" else 1


def cmd_os_setup(args: argparse.Namespace) -> int:
    """Open the selected Director's native provider wizard, never a global login."""
    args.os = args.id
    args.platform_command = "configure"
    return cmd_platform_gateway(args)


def cmd_os_instance(args: argparse.Namespace) -> int:
    """Resolve an instance explicitly; a reusable package is never a tenant."""
    if args.instance_command == "setup":
        args.os = None
        args.platform_command = "configure"
        return cmd_platform_gateway(args)
    from .os_instances import install_os_instance, load_os_instance_record, verify_os_instance

    paths, zone = LayoutPaths.live(), _load_zone_record(args.zone)
    if args.instance_command == "show":
        record = load_os_instance_record(paths, zone=zone, instance_id=args.instance, require_configured=False)
    else:
        if os.geteuid() != 0:
            raise StationError("OS instance installation/verification requires the Station root authority")
        hermes, runuser = shutil.which("hermes"), shutil.which("runuser")
        if not hermes or not runuser:
            raise StationError("Hermes and runuser must be available before OS instance execution")
        if args.instance_command == "install":
            item, source = _os_catalog_entry(args.id)
            record = install_os_instance(
                source, paths=paths, zone=zone, instance_id=args.instance,
                organization_id=args.organization, allowed_project_ids=args.allow_project,
                os_id=item["id"], os_version=item["version"],
                hermes_binary=hermes, runuser_binary=runuser,
            )
        else:
            record = verify_os_instance(paths, zone=zone, instance_id=args.instance,
                                        hermes_binary=hermes, runuser_binary=runuser)
    print(json.dumps(record, indent=2, sort_keys=True))
    if args.instance_command == "show":
        return 0
    return 0 if record["state"] in ({"VERIFIED"} if args.instance_command == "verify" else {"CONFIGURED", "VERIFIED"}) else 1


def cmd_voice_setup(args: argparse.Namespace) -> int:
    """Explicit, native-plugin enrollment for one trusted OS instance role."""
    from .voice import enroll_voice_profile, prepare_voice_enrollment

    hermes, runuser = shutil.which("hermes"), shutil.which("runuser")
    if not hermes or not runuser:
        raise StationError("Hermes and runuser must be installed before voice enrollment")
    action = prepare_voice_enrollment if args.plan else enroll_voice_profile
    try:
        result = action(
            LayoutPaths.live(), zone=_load_zone_record(args.zone),
            instance_id=args.instance, role=args.role, revision=args.revision,
            hermes_binary=hermes, runuser_binary=runuser,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        raise StationError("Voice enrollment could not read or execute the selected profile safely; inspect its native state before retrying.") from None
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("state") == "INCOMPLETE" else 0


def cmd_strix(args: argparse.Namespace) -> int:
    try:
        return _cmd_strix(args)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise StationError("Strix prerequisite or evidence unavailable: check Zone reconciliation, approved scope, CLI/image/network, private credential and job files. No operational claim.") from None


def _cmd_strix(args: argparse.Namespace) -> int:
    from . import strix
    zone_id = validate_identifier(args.zone, "zone")
    layout = LayoutPaths.live()
    if os.geteuid() == 0:
        zone = _load_zone_record(zone_id)
    else:
        zone = strix.read_json(layout.varlib / "zone-bindings" / f"{zone_id}.json", uid=0, immutable=True)
        if zone.get("id") != zone_id or zone.get("placement") != "local":
            raise ValidationError("Invalid local Zone binding projection; reconcile the Zone")
    project_id = validate_identifier(args.project, "project")
    project = Path(str(zone["human_root"])) / "projects" / project_id
    uid = pwd.getpwnam(validate_identifier(str(zone["unix_user"]))).pw_uid
    common = {"zone": args.zone, "project_id": project_id, "uid": uid}
    policy = layout.varlib / "security" / "strix" / args.zone / project_id
    if args.strix_action == "prepare":
        result = strix.prepare(project, args.repo, **common, model=args.model,
                               budget=args.budget_usd, timeout=args.timeout_seconds)
    elif args.strix_action == "approve":
        result = strix.approve(project, job=args.job, **common, policy_root=policy,
                              host_record=layout.observed / "host.json", network=args.network,
                              acceptance_sha256=args.worker_acceptance_sha256,
                              source_upload_approved=args.allow_source_to_model,
                              dedicated_lab=args.disposable_lab_confirmed)
    elif args.strix_action == "run":
        result = strix.run(project, job=args.job, **common, policy_root=policy,
                          credential_file=Path(str(zone["state_root"])) / "credentials" / "strix-api-key")
    elif args.strix_action == "status":
        result = strix.status(project, job=args.job, **common, policy_root=policy)
    else:
        if os.geteuid() != uid or uid == 0:
            raise StationError("Read Strix evidence as the owning non-root Zone identity")
        job = validate_identifier(args.job, "Strix job")
        path = project / "evidence" / "strix" / job / "summary.json"
        result = strix.read_json(path, uid=uid)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("state") == "INCOMPLETE" else 0


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
    target = _agk_launcher()
    # Forward remaining argv after `tui`
    extra = list(getattr(args, 'tui_args', []) or [])
    if extra and extra[0] == "--":
        extra = extra[1:]
    os.execv(str(target), [str(target), *extra])
    return 0  # unreachable


def cmd_tui_install(args: argparse.Namespace) -> int:
    from .agk_launcher import install_agk_launcher

    try:
        result = install_agk_launcher(LayoutPaths.live(), operator=args.operator, plan=args.plan)
    except OSError:
        raise StationError("AGK installation paths are unavailable or unsafe; repair the dedicated operator installation") from None
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_recovery_rehearse(args: argparse.Namespace) -> int:
    from .providers.backup import restore_to_staging
    plan = _load_backup_plan(args.plan)
    payload = restore_to_staging(plan, Path(args.target), snapshot=args.snapshot)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("returncode") == 0 else 1

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="station", description=f"Agentik Station {PRODUCT_VERSION}")
    sub = parser.add_subparsers(dest="command")


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
    setup.add_argument("--zone", help="Inspect a specific owning Zone")
    setup.add_argument("--project", help="Project inside the selected Zone")
    setup.add_argument("--organization", help="Owning Organization registry identity")
    setup_selector = setup.add_mutually_exclusive_group()
    setup_selector.add_argument("--os", help="Legacy Project-bound OS package selector")
    setup_selector.add_argument("--instance", help="Client/Zone-owned OS instance whose Director to inspect")
    setup.add_argument("--json", action="store_true", help="Machine-readable observations and next actions")
    setup.add_argument("--probe", action="store_true", help="Explicit bounded read-only local service observation")
    setup.set_defaults(handler=cmd_setup)

    organization = sub.add_parser("organization", help="Register an Organization over its existing environment Zones")
    organization_sub = organization.add_subparsers(dest="organization_command", required=True)
    organization_register = organization_sub.add_parser("register")
    organization_register.add_argument("--id", required=True)
    organization_register.add_argument("--zone", action="append", required=True, help="Repeat for each existing local environment Zone")
    organization_register.add_argument("--plan", action="store_true")
    organization_register.set_defaults(handler=cmd_organization)
    organization_show = organization_sub.add_parser("show")
    organization_show.add_argument("--id", required=True)
    organization_show.set_defaults(handler=cmd_organization)

    project = sub.add_parser("project", help="Create a new owned Project without re-running Host installation")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_create = project_sub.add_parser("create")
    project_create.add_argument("--zone", required=True)
    project_create.add_argument("--id", required=True)
    project_create.add_argument("--plan", action="store_true")
    project_create.set_defaults(handler=cmd_project_create)

    setup_link = sub.add_parser("setup-link", help="Tailnet-only one-time redirects for bot-guided provider setup")
    setup_link_sub = setup_link.add_subparsers(dest="setup_link_command", required=True)
    setup_link_create = setup_link_sub.add_parser("create")
    setup_link_create.add_argument("--state-root", required=True)
    setup_link_create.add_argument("--base-url", required=True)
    setup_link_create.add_argument("--zone", required=True)
    setup_link_create.add_argument("--principal", required=True)
    setup_link_create.add_argument("--provider", required=True)
    setup_link_create.add_argument(
        "--purpose",
        required=True,
        choices=["station-secret", "hermes-credentials", "composio-oauth", "cli-device-auth"],
    )
    target_group = setup_link_create.add_mutually_exclusive_group()
    target_group.add_argument("--target-url")
    target_group.add_argument("--target-url-file")
    setup_link_create.add_argument("--ttl", type=int, default=600)
    setup_link_create.set_defaults(handler=cmd_setup_link)
    setup_link_serve = setup_link_sub.add_parser("serve")
    setup_link_serve.add_argument("--state-root", required=True)
    setup_link_serve.add_argument("--host", default="127.0.0.1")
    setup_link_serve.add_argument("--port", type=int, default=8787)
    setup_link_serve.set_defaults(handler=cmd_setup_link)

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

    resource = sub.add_parser("resource", help="Inspect versioned Station resources and stack recipes")
    resource_sub = resource.add_subparsers(dest="resource_command", required=True)
    resource_list = resource_sub.add_parser("list")
    resource_list.add_argument("--json", action="store_true")
    resource_list.set_defaults(handler=cmd_resource_list)
    resource_show = resource_sub.add_parser("show")
    resource_show.add_argument("--id", required=True)
    resource_show.set_defaults(handler=cmd_resource_show)
    resource_plan = resource_sub.add_parser("stack-plan")
    resource_plan.add_argument("--id", default="web-product")
    resource_plan.set_defaults(handler=cmd_resource_stack_plan)

    rules = sub.add_parser("rules", help="Inspect or install Station rules for LLM coding executors")
    rules_sub = rules.add_subparsers(dest="rules_command", required=True)
    rules_show = rules_sub.add_parser("show")
    rules_show.set_defaults(handler=cmd_rules_show)
    rules_install = rules_sub.add_parser("install")
    rules_install.add_argument("--repo", required=True)
    rules_install.add_argument("--plan", action="store_true")
    rules_install.set_defaults(handler=cmd_rules_install)

    security = sub.add_parser("security", help="Governed security tools; never an implicit scan authorization")
    security_sub = security.add_subparsers(dest="security_command", required=True)
    strix_parser = security_sub.add_parser("strix", help="Local-source assessment on an explicitly accepted disposable LAB Host")
    strix_sub = strix_parser.add_subparsers(dest="strix_action", required=True)
    for action in ("prepare", "approve", "run", "status", "report"):
        command = strix_sub.add_parser(action)
        command.add_argument("--zone", required=True)
        command.add_argument("--project", required=True)
        if action == "prepare":
            command.add_argument("--repo", required=True, help="Relative path under the owning Project's repos directory")
            command.add_argument("--model", required=True, help="Explicit provider/model route; no custom API endpoints")
            command.add_argument("--budget-usd", type=float, default=5.0)
            command.add_argument("--timeout-seconds", type=int, default=600)
        else:
            command.add_argument("--job", required=True)
        if action == "approve":
            command.add_argument("--network", required=True)
            command.add_argument("--worker-acceptance-sha256", required=True)
            command.add_argument("--allow-source-to-model", action="store_true")
            command.add_argument("--disposable-lab-confirmed", action="store_true")
        command.set_defaults(handler=cmd_strix)

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
    composio_discord = provider_sub.add_parser(
        "composio-discord",
        help="Zone-scoped Composio Discord tools; Hermes remains the messaging gateway",
    )
    composio_discord_sub = composio_discord.add_subparsers(dest="composio_discord_command", required=True)
    for action in ("plan", "link", "verify"):
        command = composio_discord_sub.add_parser(action)
        command.add_argument("--zone", required=True)
        command.set_defaults(handler=cmd_composio_discord)

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
    os_setup = os_sub.add_parser("setup", help="Configure the selected Director through Hermes' native provider wizard")
    os_setup.add_argument("--id", required=True)
    os_setup.add_argument("--zone", required=True)
    os_setup.add_argument("--plan", action="store_true")
    os_setup.set_defaults(handler=cmd_os_setup)
    os_verify = os_sub.add_parser("verify")
    os_verify.add_argument("--id", required=True)
    os_verify.add_argument("--zone", required=True)
    os_verify.set_defaults(handler=cmd_os_verify)

    os_instance = os_sub.add_parser("instance", help="First-class Zone-owned OS teams; no mandatory owning Project")
    instance_sub = os_instance.add_subparsers(dest="instance_command", required=True)
    for action in ("install", "setup", "verify", "show"):
        command = instance_sub.add_parser(action)
        command.add_argument("--zone", required=True)
        command.add_argument("--instance", required=True)
        if action == "install":
            command.add_argument("--id", required=True, help="Reusable OS package id")
            command.add_argument("--organization", help="Required for an ORGANIZATIONS Zone")
            command.add_argument("--allow-project", action="append", default=[], help="Explicit Project scope; repeat to authorize multiple existing Projects")
        if action == "setup":
            command.add_argument("--plan", action="store_true")
            command.add_argument("--role", help="Configure this canonical team role; default is the Director")
        command.set_defaults(handler=cmd_os_instance)

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

    tui_install = sub.add_parser("tui-install", help="Publish the existing private AGK installation through a sudo-authorized operator handoff")
    tui_install.add_argument("--operator", required=True, choices=["agk-station"])
    tui_install.add_argument("--plan", action="store_true")
    tui_install.set_defaults(handler=cmd_tui_install)

    client = sub.add_parser("client", help="Legacy AGK controller compatibility; new clients use organization/OS instances")
    client.add_argument("--legacy", action="store_true", help="Explicitly use the older operator-home client workspace/profile model")
    client.add_argument("client_args", nargs=argparse.REMAINDER, help="Arguments forwarded to `agk client`")
    client.set_defaults(handler=cmd_client)

    hermes = sub.add_parser("hermes")
    hermes_sub = hermes.add_subparsers(dest="hermes_command", required=True)
    hermes_check = hermes_sub.add_parser("check", help="Plan-only Hermes update check (never applies)")
    hermes_check.add_argument("--record", action="store_true")
    hermes_check.set_defaults(handler=cmd_hermes_check)
    hermes_update = hermes_sub.add_parser("update", help="Apply Hermes update with backup, Doctor and receipt")
    hermes_update.add_argument("--check-only", action="store_true")
    hermes_update.set_defaults(handler=cmd_hermes_update)

    deps = sub.add_parser("deps", help="Full Host dependency stack: installation is distinct from service/account readiness")
    deps_sub = deps.add_subparsers(dest="deps_command", required=True)
    for action in ("full-plan", "full-check"):
        command = deps_sub.add_parser(action, help="Exhaustive required software inventory; never infers account readiness")
        if action == "full-check":
            command.add_argument("--operator", default="agk-station")
        command.set_defaults(handler=cmd_deps)
    for action in ("service-plan", "service-check"):
        command = deps_sub.add_parser(action, help="Reviewed server image bundle; does not activate containers")
        command.add_argument("--component", required=True, choices=("langfuse", "honcho", "hindsight", "chatbotx"))
        command.set_defaults(handler=cmd_deps)
    deps_list = deps_sub.add_parser("list")
    deps_list.set_defaults(handler=cmd_deps)
    deps_platforms = deps_sub.add_parser("platforms")
    deps_platforms.set_defaults(handler=cmd_deps)
    deps_auto = deps_sub.add_parser("enable-auto-update")
    deps_auto.set_defaults(handler=cmd_deps)
    deps_web_check = deps_sub.add_parser("web-check")
    deps_web_check.set_defaults(handler=cmd_deps)
    deps_install = deps_sub.add_parser("install")
    deps_install.add_argument("--all", action="store_true")
    deps_install.add_argument("--component", action="append", default=[])
    deps_install.set_defaults(handler=cmd_deps)
    for action in ("plan", "install", "check"):
        toolchain = deps_sub.add_parser(f"toolchain-{action}")
        toolchain.set_defaults(handler=cmd_deps)

    platform = sub.add_parser("platform", help="Zone-isolated Hermes messaging gateway")
    platform_sub = platform.add_subparsers(dest="platform_command", required=True)
    for action in ("configure", "setup", "install", "start", "restart", "status", "doctor"):
        command = platform_sub.add_parser(action)
        command.add_argument("--zone", required=True)
        command.add_argument("--platform", help="Platform intent/name; native actions affect the selected profile's whole gateway")
        selector = command.add_mutually_exclusive_group()
        selector.add_argument("--os", help="Legacy installed OS Director instead of the Zone's default profile")
        selector.add_argument("--instance", help="Installed OS instance Director; never inferred from a package name")
        command.add_argument("--role", help="Explicit instance team role; requires --instance and a justified external bot topology")
        command.add_argument("--plan", action="store_true")
        command.set_defaults(handler=cmd_platform_gateway)

    voice = sub.add_parser("voice", help="Explicit profile-scoped native speech transcription")
    voice_sub = voice.add_subparsers(dest="voice_command", required=True)
    voice_setup = voice_sub.add_parser("setup", help="Enroll one instance role: OpenAI then local Parakeet")
    voice_setup.add_argument("--zone", required=True)
    voice_setup.add_argument("--instance", required=True)
    voice_setup.add_argument("--role", required=True)
    voice_setup.add_argument("--revision", required=True, help="Reviewed immutable Station Git commit (40 hex characters)")
    voice_setup.add_argument("--plan", action="store_true")
    voice_setup.set_defaults(handler=cmd_voice_setup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return int(args.handler(args))
    except StationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("STATE: DEGRADED", file=sys.stderr)
        print("NEXT: repair the explicit error, then rerun plan/Doctor before apply.", file=sys.stderr)
        return 2


def install_main(argv: list[str] | None = None) -> int:
    return main(["apply", *(argv if argv is not None else sys.argv[1:])])
