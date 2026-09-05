"""Fixed, read-only Linux Host software audit; never an installer or account probe.

Native check scripts own disposable-HOME isolation for client imports/version
checks. This module aggregates independent failures without replaying native
output, reading credentials, starting services, or weakening Ponytail's guard.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import pwd
import re
import stat
import subprocess
from typing import Callable

from .errors import SecurityError, ValidationError
from .filesystem import SafeFS
from .native_process import OUTPUT_LIMIT, run_bounded_native
from .os_runtime import require_root_owned_directory_chain
from . import service_software


@dataclass(frozen=True)
class Component:
    id: str
    members: tuple[str, ...]
    scope: str
    repair: str


# A failed or unsupported component cannot disappear through a caller-supplied
# selection, a directory-presence heuristic, or an optional-plugin exception.
COMPONENTS = (
    Component("toolchain", ("python", "python-ai", "node", "npm", "uv", "github-cli",
              "vercel-cli", "codex-cli", "composio-cli", "shadcn-cli", "chatbotx-cli",
              "discord.js", "hermes"), "pinned-native-client-software",
              "Repair the pinned Host toolchain and rerun its isolated --check."),
    Component("agk", ("agk-launcher", "agk-controller", "agk-tui", "rmux"),
              "installed-artifacts-help-and-rmux-capabilities-not-interactive-tui",
              "Repair the operator AGK installation; separately accept interactive TUI/session behavior."),
    Component("hermes-clients", ("hermes-native-imports", "honcho-native-client", "hindsight-native-client",
              "langfuse-sdk", "mcp-sdk", "httpx2", "starlette"),
              "pinned-hermes-native-imports-no-profile-connection",
              "Repair the pinned Hermes client extras and rerun --check-hermes-clients."),
    Component("web-runtimes", ("scrapegraphai", "crawl4ai", "playwright", "chromium"),
              "native-imports-and-local-browser-probe-no-external-extraction",
              "Repair both web runtimes and rerun --check-web."),
    Component("strix", ("strix-cli",), "cli-software-only-no-lab-authorization",
              "Repair Strix software; separately authorize a disposable LAB before execution."),
    Component("memory-clients", ("honcho-sdk", "hindsight-sdk"),
              "pinned-native-client-imports-no-memory-account",
              "Repair the memory SDK environments and rerun --check-memory."),
    Component("voice", ("hermes-voice", "hermes-messaging", "discord.py", "numpy", "faster-whisper",
              "pynacl-aead", "sounddevice", "portaudio", "opus", "ffmpeg"),
              "native-imports-and-codecs-no-provider-account",
              "Repair Hermes voice/messaging dependencies and rerun --check-voice."),
    *(Component(name, (name + "-server-bundle",), "all-pinned-oci-images-and-bound-receipt",
                "Install/repair the complete reviewed server image bundle; configure it separately.")
      for name in ("langfuse", "honcho", "hindsight", "chatbotx")),
    Component("ponytail", ("ponytail-native-plugin",), "native-security-acceptance-required",
              "Obtain a reviewed upstream correction and a new native full-tree scan; do not bypass the guard."),
    Component("tigervnc", ("tigervnc-standalone-server", "tigervnc-viewer"),
              "native-dpkg-installed-packages-not-display-authorization",
              "Install both TigerVNC packages; configure an authenticated private display separately."),
    Component("parakeet", ("parakeet-image", "parakeet-service", "parakeet-transcribe"),
              "exact-image-unit-helper-and-local-loopback-health-not-transcription-acceptance",
              "Repair the pinned Parakeet image/unit/helper and inspect its local service health."),
    Component("guided-setup", ("station-kernel-launcher", "guided-setup-program", "guided-setup-service"),
              "current-kernel-program-exact-unit-and-loopback-health-not-tailnet-token-or-account-readiness",
              "Repair the reviewed guided-setup program/unit and its local broker health; enroll Tailnet and accounts separately."),
    Component("hermes-updater", ("hermes-update-helper", "hermes-update-service", "hermes-update-timer"),
              "exact-installed-unit-artifacts-and-registration-not-scheduling-or-successful-upgrade",
              "Repair the reviewed Hermes updater files and unit registration; select scheduled updates separately."),
    Component("tailscale", ("tailscale-client",), "native-minimum-version-no-tailnet-identity",
              "Repair Tailscale software; enroll and verify the intended tailnet identity separately."),
    Component("preferred-web-resources", ("next.js-recipe", "react-recipe", "convex-recipe", "clerk-recipe",
              "stripe-recipe", "tailwindcss-recipe", "shadcn-resource", "lucide-resource", "vercel-recipe"),
              "resource-delivery-only-not-project-dependency-installation",
              "Restore the reviewed web-product recipe and resource declarations; install dependencies only in an owning Project."),
)
_SERVICES = frozenset({"langfuse", "honcho", "hindsight", "chatbotx"})
_CHECK_FLAGS = {"hermes-clients": "--check-hermes-clients", "web-runtimes": "--check-web",
                "strix": "--check-strix", "memory-clients": "--check-memory", "voice": "--check-voice"}
_CANONICAL = tuple(Path(p) for p in ("/etc", "/opt", "/srv", "/usr", "/home", "/root",
                                  "/var/lib", "/var/log", "/var/backups", "/run"))
_PIN_KEYS = frozenset({"PARAKEET_IMAGE", "PARAKEET_PORT", "TAILSCALE_MIN_VERSION", "RMUX_VERSION",
                       "SHADCN_CLI_VERSION", "LUCIDE_REACT_VERSION"})


def _absolute(value: Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise SecurityError("Full-stack paths must be absolute without parent traversal")
    return path


def _read(path: Path, *, uid: int | None) -> bytes:
    return service_software._read(path, uid=uid)


def _regular(path: Path, *, owner: int, executable: bool = False,
             single_link: bool = True, privileged: bool = False) -> None:
    SafeFS._assert_existing_absolute_chain(path.parent)
    if privileged and owner == 0:
        require_root_owned_directory_chain(path.parent)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or (single_link and info.st_nlink != 1) or info.st_uid != owner
            or info.st_mode & 0o022 or (executable and not info.st_mode & 0o111)):
        raise SecurityError("Untrusted full-stack software artifact")


def _pins(repo: Path, *, uid: int | None) -> dict[str, str]:
    values = {}
    for line in _read(repo / "config/versions.lock", uid=uid).decode("utf-8").splitlines():
        key, separator, value = line.partition("=")
        if key in _PIN_KEYS:
            if not separator or key in values or not value or not value.isprintable():
                raise ValidationError("Invalid full-stack software pin")
            values[key] = value
    if (set(values) != _PIN_KEYS
            or not re.fullmatch(r"ghcr\.io/achetronic/parakeet@sha256:[a-f0-9]{64}", values["PARAKEET_IMAGE"])
            or not re.fullmatch(r"[0-9]{1,5}", values["PARAKEET_PORT"])
            or not 1 <= int(values["PARAKEET_PORT"]) <= 65535
            or any(not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", values[k])
                   for k in ("TAILSCALE_MIN_VERSION", "RMUX_VERSION", "SHADCN_CLI_VERSION", "LUCIDE_REACT_VERSION"))):
        raise ValidationError("Missing or invalid full-stack software pins")
    return values


def _row(component: Component, state: str, *, verified: bool = False,
         installed: bool = False, reason: str | None = None) -> dict:
    row = {"component": component.id, "required": True, "members": list(component.members),
           "verification_scope": component.scope, "state": state,
           "requirement_verified": verified, "software_installed": installed,
           "configuration_required": True, "operational": False,
           "account_readback": "NOT_CHECKED", "repair": component.repair}
    if reason:
        row["reason_code"] = reason
    if component.id == "hermes-updater":
        row["scheduling"] = "NOT_CHECKED"
    return row


def _report(rows: list[dict], *, mode: str, synthetic: bool = False) -> dict:
    return {"schema_version": 1, "mode": mode, "platform": "linux/amd64", "synthetic": synthetic,
            "full_software_verified": not synthetic and all(r["requirement_verified"] for r in rows),
            "configuration_required": True, "operational": False, "account_readback": "NOT_CHECKED",
            "components": rows, "required_count": len(COMPONENTS),
            "verified_count": sum(r["requirement_verified"] for r in rows),
            "limitations": ["Software evidence never proves account, gateway, service or mission acceptance.",
                            "Ponytail's reviewed native security rejection remains a required blocking gate.",
                            "AGK help/artifacts do not accept an interactive TUI or RMUX session.",
                            "Guided-setup loopback health does not verify Tailnet exposure, setup tokens or connected accounts.",
                            "Preferred web resources are delivered recipes, not installed Project dependencies."]}


def plan(repo: Path) -> dict:
    """Describe every fixed requirement without looking at the live Host."""
    repo = _absolute(repo)
    SafeFS._assert_existing_absolute_chain(repo)
    _pins(repo, uid=None)
    return _report([_row(item, "PLANNED") for item in COMPONENTS], mode="plan")


def check(repo: Path, *, operator: str = "agk-station", operator_home: Path | None = None,
          root: Path = Path("/"), run: Callable | None = None,
          bundle_check: Callable | None = None) -> dict:
    """Audit independently; a failed row never prevents later rows being checked.

    Injected probes require an explicit noncanonical fixture root and cannot
    fall back to live native execution or establish live verification.
    """
    repo, root = _absolute(repo), _absolute(root)
    if not isinstance(operator, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", operator):
        raise ValidationError("Invalid full-stack operator identifier")
    home = _absolute(operator_home if operator_home is not None else Path("/home") / operator)
    if home == Path("/") or home in _CANONICAL:
        raise SecurityError("Full-stack operator requires a concrete private home")
    synthetic = root != Path("/")
    if synthetic:
        if (run is None or bundle_check is None or len(root.parts) < 3
                or root in (Path("/tmp"), Path("/private/tmp"), Path("/var/tmp"))
                or any(root == p or p in root.parents for p in _CANONICAL)):
            raise SecurityError("Synthetic full-stack probes require a noncanonical fixture root and both executors")
    elif run is not None or bundle_check is not None:
        raise SecurityError("Injected executors cannot audit canonical Host paths")
    if not synthetic and (os.geteuid() != 0 or platform.system() != "Linux"
                          or platform.machine() not in {"x86_64", "amd64"}):
        raise SecurityError("Full-stack live audit requires root on Linux AMD64")
    for path in (repo, root):
        SafeFS._assert_existing_absolute_chain(path)
        if not path.is_dir():
            raise SecurityError("Full-stack root/repository must be existing directories")
    if not synthetic:
        require_root_owned_directory_chain(repo)
        require_root_owned_directory_chain(repo / "config")
        try:
            account = pwd.getpwnam(operator)
        except KeyError:
            raise ValidationError("Full-stack operator account is not installed") from None
        if account.pw_uid <= 0 or account.pw_gid <= 0 or account.pw_dir != str(home):
            raise SecurityError("Full-stack operator identity/home mismatch")
        operator_uid = account.pw_uid
    else:
        operator_uid = os.geteuid()
    uid = os.geteuid() if synthetic else 0
    pins = _pins(repo, uid=uid)

    def target(path: Path | str) -> Path:
        return root / Path(path).relative_to("/")

    def regular(path: Path, *, owner: int, executable: bool = False, single_link: bool = True) -> None:
        _regular(path, owner=owner, executable=executable, single_link=single_link, privileged=not synthetic)

    def installed_copy(source: Path, destination: Path, *, owner: int, executable: bool = False) -> None:
        regular(destination, owner=owner, executable=executable)
        if _read(source, uid=uid) != _read(destination, uid=owner):
            raise SecurityError("Installed software artifact differs from the reviewed release")

    def native(args: list[str], *, timeout: int = 60, as_operator: bool = False) -> str:
        # No ambient credentials, BASH_ENV, Python path, container remote setting,
        # curl rc, or real account HOME enters a probe. Script checks create their
        # own disposable native homes; pure help/system utilities need no home.
        env = ["/usr/bin/env", "-i", "PATH=/usr/sbin:/usr/bin:/sbin:/bin", "LANG=C.UTF-8",
               "LC_ALL=C.UTF-8", "HOME=/nonexistent", "HERMES_HOME=/nonexistent/.hermes",
               "HERMES_MANAGED_DIR=/nonexistent/.managed", "XDG_CONFIG_HOME=/nonexistent/.config",
               "XDG_CACHE_HOME=/nonexistent/.cache", "PYTHONDONTWRITEBYTECODE=1", "CI=1",
               "DO_NOT_TRACK=1", "STATION_USER=" + operator, "STATION_HOME=" + str(target(home))]
        argv = env + args
        if as_operator:
            argv = ["/usr/sbin/runuser", "--user", operator, "--", *argv]
        if not synthetic:
            for binary in (Path("/usr/bin/env"), Path(args[0]),
                           *((Path("/usr/sbin/runuser"),) if as_operator else ())):
                # Distribution-owned executable aliases (e.g. merged /usr) are
                # accepted only after resolving to a trusted root-owned target.
                resolved = binary.resolve(strict=True)
                require_root_owned_directory_chain(resolved.parent)
                # Distro multicall executables (Ubuntu Rust coreutils) have
                # root-owned hardlinks. This exception is only for the fixed
                # native commands; Station artifact reads remain single-link.
                regular(resolved, owner=0, executable=True, single_link=False)
        result = (run or run_bounded_native)(argv, timeout=timeout, capture=True)
        if result.returncode != 0:
            raise subprocess.SubprocessError("Native software check failed")
        output = result.stdout or b""
        errors = result.stderr or b""
        if not isinstance(output, (str, bytes)) or not isinstance(errors, (str, bytes)):
            raise ValidationError("Unsupported native result")
        if len(output) > OUTPUT_LIMIT or len(errors) > OUTPUT_LIMIT:
            raise ValidationError("Native software check exceeded its output bound")
        return output.decode("utf-8") if isinstance(output, bytes) else output

    def script(name: str, flag: str) -> None:
        path = repo / "scripts" / name
        regular(path, owner=uid)
        native(["/usr/bin/bash", str(path), flag], timeout=900)

    def agk() -> None:
        installed = target(home / ".local/lib/agk-terminal")
        launcher = target(home / ".local/bin/agk")
        installed_copy(repo / "components/agk-tui/bin/agk", launcher, owner=operator_uid, executable=True)
        installed_copy(repo / "components/agk-tui/scripts/agk_control.py",
                       installed / "scripts/agk_control.py", owner=operator_uid, executable=True)
        regular(installed / "bin/agk-tui", owner=operator_uid, executable=True)
        # The installed shell help branch exits before registry/TUI initialization.
        output = native(["/usr/bin/bash", str(launcher), "help"], as_operator=True)
        if "AGK-TUI" not in output:
            raise ValidationError("AGK native help did not identify the software")
        rmux = installed / "bin/rmux"
        # Upstream intentionally uses an RMUX alias. Resolve only this named
        # native alias, never a generic executable search through operator PATH.
        resolved = rmux.resolve(strict=True)
        if synthetic and root not in resolved.parents:
            raise SecurityError("Synthetic RMUX alias escapes its fixture")
        regular(resolved, owner=resolved.stat().st_uid, executable=True)
        if not synthetic and resolved.stat().st_uid not in {0, operator_uid}:
            raise SecurityError("RMUX belongs to an unrelated identity")
        report = json.loads(native(["/usr/bin/env", "AGK_TERMINAL_ROOT=" + str(installed),
                                    str(rmux), "capabilities", "--json"], as_operator=True))
        required = {"protocol.capabilities", "protocol.framed_errors", "rpc.detached"}
        if (report.get("version") != pins["RMUX_VERSION"] or type(report.get("wire_version")) is not int
                or report["wire_version"] != 8 or type(report.get("binary_contract_version")) is not int
                or report["binary_contract_version"] != 1 or not isinstance(report.get("capabilities"), list)
                or any(not isinstance(item, str) for item in report["capabilities"])
                or not required.issubset(report["capabilities"])):
            raise ValidationError("RMUX native capabilities differ from the required contract")

    def unit(source: Path, name: str, *, properties: dict[str, str] | None = None) -> None:
        path = target(Path("/etc/systemd/system") / name)
        installed_copy(source, path, owner=uid)
        # Restrict output to nonsecret registration properties, never `cat`,
        # Environment, status logs, or complete show/inspect output.
        expected = {"LoadState": "loaded", "FragmentPath": str(path), "DropInPaths": ""}
        expected.update(properties or {})
        output = native(["/usr/bin/systemctl", "show", name,
                         *("--property=" + key for key in expected), "--no-pager"])
        if dict(line.split("=", 1) for line in output.splitlines() if "=" in line) != expected:
            raise ValidationError("Systemd unit registration differs from the reviewed artifact")

    def guided_setup() -> dict:
        # The canonical kernel copies this unit verbatim. Its program is loaded
        # through precisely two installer-owned aliases; no Zone record, setup
        # session, token or credential file needs to be opened to check it.
        version = _read(repo / "VERSION", uid=uid).decode("ascii").strip()
        if not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", version):
            raise ValidationError("Unsupported installed Station version")
        current = target("/opt/station/current")
        public = target("/usr/local/bin/station")
        for alias, expected in ((current, "releases/" + version),
                                (public, "/opt/station/current/station")):
            SafeFS._assert_existing_absolute_chain(alias.parent)
            if not synthetic:
                require_root_owned_directory_chain(alias.parent)
            info = alias.lstat()
            if (not stat.S_ISLNK(info.st_mode) or info.st_uid != uid or info.st_nlink != 1
                    or os.readlink(alias) != expected):
                raise SecurityError("Station launcher/current alias differs from the canonical kernel installation")
        if current.resolve(strict=True) != repo:
            raise SecurityError("Guided-setup program is not bound to the audited active release")
        regular(repo / "station", owner=uid, executable=True)
        regular(repo / "src/agentik_station/guided_setup.py", owner=uid)
        name = "station-guided-setup.service"
        unit(repo / "runtime/systemd" / name, name,
             properties={"User": "z-system-discord", "Group": "z-system-discord", "NeedDaemonReload": "no"})
        try:
            native(["/usr/bin/systemctl", "is-active", "--quiet", name])
            health = native(["/usr/bin/curl", "--disable", "--proxy", "", "--noproxy", "*", "--fail", "--silent",
                             "--max-time", "2", "--max-filesize", "1024", "http://127.0.0.1:8787/health"], timeout=5)
            if json.loads(health) != {"status": "ok"}:
                raise ValidationError("Guided-setup loopback health response differs from the broker contract")
        except (OSError, ValueError, subprocess.SubprocessError, ValidationError, SecurityError):
            return {"installed": True, "verified": False, "state": "SOFTWARE_INSTALLED_LOCAL_CHECK_FAILED",
                    "reason": "LOCAL_SERVICE_NOT_VERIFIED"}
        return {"installed": True, "verified": True, "state": "SOFTWARE_VERIFIED"}

    def parakeet() -> dict:
        reference = pins["PARAKEET_IMAGE"]
        podman = ["/usr/bin/podman", "--remote=false", "--root", str(target("/var/lib/containers/storage")),
                  "--runroot", str(target("/run/containers/storage"))]
        observed = native([*podman, "image", "inspect", "--format", "{{.Id}} {{.Digest}} {{.Os}}/{{.Architecture}}",
                           "--", reference]).strip().split()
        if (len(observed) != 3 or not re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", observed[0])
                or observed[1:] != [reference.split("@", 1)[1], "linux/amd64"]):
            raise ValidationError("Parakeet image identity mismatch")
        unit(repo / "runtime/systemd/station-parakeet.service", "station-parakeet.service")
        installed_copy(repo / "scripts/station_parakeet_transcribe.sh",
                       target("/usr/local/libexec/station-parakeet-transcribe"), owner=uid, executable=True)
        try:
            native(["/usr/bin/systemctl", "is-active", "--quiet", "station-parakeet.service"])
            running = native([*podman, "container", "inspect", "--format", "{{.Image}} {{.State.Running}}",
                              "--", "station-parakeet"]).strip().split()
            if len(running) != 2 or running[0].removeprefix("sha256:") != observed[0].removeprefix("sha256:") or running[1] != "true":
                raise ValidationError("Parakeet running container identity mismatch")
            native(["/usr/bin/curl", "--disable", "--proxy", "", "--noproxy", "*", "--fail", "--silent",
                    "--max-time", "2", "--output", "/dev/null", "http://127.0.0.1:" + pins["PARAKEET_PORT"] + "/health"], timeout=5)
        except (OSError, ValueError, subprocess.SubprocessError, ValidationError, SecurityError):
            return {"installed": True, "verified": False, "state": "SOFTWARE_INSTALLED_LOCAL_CHECK_FAILED",
                    "reason": "LOCAL_SERVICE_NOT_VERIFIED"}
        return {"installed": True, "verified": True, "state": "SOFTWARE_VERIFIED"}

    def updater() -> None:
        for suffix in ("service", "timer"):
            name = "station-hermes-update." + suffix
            unit(repo / "scripts/systemd" / name, name)
        installed_copy(repo / "scripts/station_hermes_update.sh",
                       target("/usr/local/libexec/station-hermes-update"), owner=uid, executable=True)
        # Full installations may explicitly opt out of scheduled updates.
        # Software evidence covers exact artifacts/registration, not activation.

    def probe(component: Component) -> dict:
        name = component.id
        if name == "toolchain":
            script("station_toolchain_install.sh", "--check")
        elif name in _CHECK_FLAGS:
            script("station_deps_install.sh", _CHECK_FLAGS[name])
        elif name == "agk":
            agk()
        elif name in _SERVICES:
            result = (bundle_check or service_software.check_bundle)(
                repo, name, evidence_root=target(service_software.EVIDENCE_ROOT))
            if (not isinstance(result, dict) or result.get("component") != name
                    or result.get("software_installed") is not True or result.get("state") != "SOFTWARE_INSTALLED"
                    or result.get("configuration_required") is not True or result.get("operational") is not False):
                raise ValidationError("Server bundle is not verified")
        elif name == "tigervnc":
            output = native(["/usr/bin/dpkg-query", "-W", "-f=${binary:Package}\t${db:Status-Status}\t${Version}\n",
                             "tigervnc-standalone-server", "tigervnc-viewer"])
            records = [line.split("\t") for line in output.splitlines()]
            if (len(records) != 2 or {r[0].split(":", 1)[0] for r in records if len(r) == 3} != set(component.members)
                    or any(len(r) != 3 or r[1] != "installed" or not re.fullmatch(r"[0-9][A-Za-z0-9.+:~_-]{0,99}", r[2]) for r in records)):
                raise ValidationError("TigerVNC packages are not installed")
        elif name == "parakeet":
            return parakeet()
        elif name == "guided-setup":
            return guided_setup()
        elif name == "hermes-updater":
            updater()
        elif name == "tailscale":
            observed = native(["/usr/bin/tailscale", "version"]).splitlines()[0].strip()
            if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", observed):
                raise ValidationError("Unsupported Tailscale version output")
            if tuple(map(int, observed.split("."))) < tuple(map(int, pins["TAILSCALE_MIN_VERSION"].split("."))):
                raise ValidationError("Tailscale is below the required minimum")
        elif name == "preferred-web-resources":
            resources = (("resources/stacks/web-product/STACK.json", "web-product"),
                         ("resources/frontend/shadcn-ui/RESOURCE.json", "shadcn-ui"),
                         ("resources/frontend/lucide/RESOURCE.json", "lucide"))
            for relative, identity in resources:
                value = json.loads(_read(repo / relative, uid=uid))
                if (not isinstance(value, dict) or value.get("id") != identity
                        or type(value.get("schema_version")) is not int or value["schema_version"] != 1):
                    raise ValidationError("Missing preferred web resource declaration")
                if identity == "web-product":
                    expected = {"frontend": ["next", "react", "tailwindcss", "shadcn-ui", "lucide"],
                                "backend_and_state": ["convex"], "identity": ["clerk"],
                                "payments": ["stripe"], "deployment": ["vercel"], "policy": "preferred-not-exclusive"}
                    if any(value.get(key) != desired for key, desired in expected.items()):
                        raise ValidationError("Preferred web-product recipe differs from its required contract")
                elif value.get("version") != pins["SHADCN_CLI_VERSION" if identity == "shadcn-ui" else "LUCIDE_REACT_VERSION"]:
                    raise ValidationError("Preferred frontend resource version drift")
            return {"verified": True, "installed": False, "state": "DELIVERED_NOT_PROJECT_INSTALLED"}
        else:
            raise ValidationError("No read-only probe exists for a required component")
        return {"verified": True, "installed": True, "state": "SOFTWARE_VERIFIED"}

    rows = []
    for component in COMPONENTS:
        if component.id == "ponytail":
            rows.append(_row(component, "BLOCKED_NOT_VERIFIED", reason="NATIVE_SECURITY_SCAN_REJECTED"))
            continue
        try:
            rows.append(_row(component, **probe(component)))
        except Exception:
            # Deliberately omit all native/exception text, paths from failures,
            # profile output and injected metadata. KeyboardInterrupt/SystemExit
            # still interrupt rather than pretending the audit completed.
            rows.append(_row(component, "NOT_VERIFIED", reason="SOFTWARE_CHECK_FAILED"))
    return _report(rows, mode="check", synthetic=synthetic)
