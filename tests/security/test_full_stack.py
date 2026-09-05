from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from agentik_station import full_stack
from agentik_station.errors import SecurityError, ValidationError


REPO = Path(__file__).resolve().parents[2]
IMAGE_ID = "a" * 64
SOURCE_FILES = (
    "VERSION", "station", "src/agentik_station/guided_setup.py", "runtime/systemd/station-guided-setup.service",
    "config/versions.lock", "scripts/station_deps_install.sh", "scripts/station_toolchain_install.sh",
    "components/agk-tui/bin/agk", "components/agk-tui/scripts/agk_control.py",
    "runtime/systemd/station-parakeet.service", "scripts/station_parakeet_transcribe.sh",
    "scripts/station_hermes_update.sh", "scripts/systemd/station-hermes-update.service",
    "scripts/systemd/station-hermes-update.timer", "resources/stacks/web-product/STACK.json",
    "resources/frontend/shadcn-ui/RESOURCE.json", "resources/frontend/lucide/RESOURCE.json",
)


class AuditFixture:
    def __init__(self, tmp_path):
        self.root = tmp_path.resolve() / "fixture-host"
        self.root.mkdir()
        self.repo = self.root / "opt/station/releases" / (REPO / "VERSION").read_text().strip()
        for relative in SOURCE_FILES:
            self.copy(REPO / relative, self.repo / relative)
        (self.repo / "station").chmod(0o755)
        (self.root / "opt/station/current").symlink_to("releases/" + self.repo.name, target_is_directory=True)
        (self.root / "usr/local/bin").mkdir(parents=True)
        (self.root / "usr/local/bin/station").symlink_to("/opt/station/current/station")
        home = self.root / "home/agk-station"
        self.agk = home / ".local/lib/agk-terminal"
        self.copy(self.repo / "components/agk-tui/bin/agk", home / ".local/bin/agk", executable=True)
        self.copy(self.repo / "components/agk-tui/scripts/agk_control.py", self.agk / "scripts/agk_control.py", executable=True)
        for binary in (self.agk / "bin/agk-tui", self.agk / "bin/rmux"):
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b"\x7fELFsynthetic-not-executable-code")
            binary.chmod(0o755)
        for source, destination in (
            ("runtime/systemd/station-guided-setup.service", "etc/systemd/system/station-guided-setup.service"),
            ("runtime/systemd/station-parakeet.service", "etc/systemd/system/station-parakeet.service"),
            ("scripts/station_parakeet_transcribe.sh", "usr/local/libexec/station-parakeet-transcribe"),
            ("scripts/station_hermes_update.sh", "usr/local/libexec/station-hermes-update"),
            ("scripts/systemd/station-hermes-update.service", "etc/systemd/system/station-hermes-update.service"),
            ("scripts/systemd/station-hermes-update.timer", "etc/systemd/system/station-hermes-update.timer"),
        ):
            self.copy(self.repo / source, self.root / destination, executable="libexec" in destination)
        self.pins = full_stack._pins(self.repo, uid=os.geteuid())
        self.commands = []
        self.bundles = []
        self.fail_on = None
        self.output_override = None
        self.bundle_override = None
        self.container_id = IMAGE_ID
        self.image_digest = self.pins["PARAKEET_IMAGE"].split("@", 1)[1]
        self.guided_health = '{"status":"ok"}\n'
        self.guided_user = "z-system-discord"
        self.guided_reload = "no"
        self.guided_active = True

    @staticmethod
    def copy(source, destination, *, executable=False):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755 if executable else 0o644)

    def run(self, argv, *, timeout, capture):
        assert capture is True
        assert 0 < timeout <= 900
        assert isinstance(argv, list) and all(isinstance(item, str) for item in argv)
        self.commands.append(argv)
        if self.fail_on is not None and any(self.fail_on in item for item in argv):
            return subprocess.CompletedProcess(argv, 1, b"secret-native-stdout", b"secret-native-stderr")
        if not self.guided_active and "is-active" in argv and argv[-1] == "station-guided-setup.service":
            return subprocess.CompletedProcess(argv, 1, b"", b"")
        if self.output_override is not None:
            return subprocess.CompletedProcess(argv, 0, self.output_override, b"")
        output = ""
        if argv[-1] == "help":
            output = "AGK-TUI · RMUX control plane\n"
        elif argv[-2:] == ["capabilities", "--json"]:
            output = json.dumps({"version": self.pins["RMUX_VERSION"], "wire_version": 8,
                                 "binary_contract_version": 1,
                                 "capabilities": ["protocol.capabilities", "protocol.framed_errors", "rpc.detached"]})
        elif "/usr/bin/dpkg-query" in argv:
            output = "tigervnc-standalone-server\tinstalled\t1.13.1+dfsg-2\ntigervnc-viewer\tinstalled\t1.13.1+dfsg-2\n"
        elif "/usr/bin/tailscale" in argv:
            output = self.pins["TAILSCALE_MIN_VERSION"] + "\n  build details\n"
        elif "/usr/bin/systemctl" in argv and "show" in argv:
            unit = argv[argv.index("show") + 1]
            output = f"LoadState=loaded\nFragmentPath={self.root / 'etc/systemd/system' / unit}\nDropInPaths=\n"
            if unit == "station-guided-setup.service":
                output += f"User={self.guided_user}\nGroup=z-system-discord\nNeedDaemonReload={self.guided_reload}\n"
        elif "/usr/bin/podman" in argv and "image" in argv:
            output = f"{IMAGE_ID} {self.image_digest} linux/amd64\n"
        elif "/usr/bin/podman" in argv and "container" in argv:
            output = f"{self.container_id} true\n"
        elif argv[-1] == "http://127.0.0.1:8787/health":
            output = self.guided_health
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

    def bundle_check(self, repo, component, *, evidence_root):
        assert repo == self.repo
        assert evidence_root == self.root / full_stack.service_software.EVIDENCE_ROOT.relative_to("/")
        self.bundles.append(component)
        if self.bundle_override is not None:
            return self.bundle_override(component)
        return {"component": component, "state": "SOFTWARE_INSTALLED", "software_installed": True,
                "configuration_required": True, "operational": False}

    def check(self, **kwargs):
        return full_stack.check(self.repo, root=self.root, run=self.run, bundle_check=self.bundle_check, **kwargs)


@pytest.fixture
def fixture(tmp_path):
    return AuditFixture(tmp_path)


def rows(report):
    return {row["component"]: row for row in report["components"]}


def snapshot(root):
    return {str(path.relative_to(root)): (path.lstat().st_mode, path.read_bytes())
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()}


def test_fixed_plan_has_every_required_group_and_never_executes(fixture, monkeypatch):
    monkeypatch.setattr(full_stack, "run_bounded_native", lambda *a, **k: pytest.fail("plan ran software"))
    report = full_stack.plan(fixture.repo)
    expected = {"toolchain", "agk", "hermes-clients", "web-runtimes", "strix", "memory-clients", "voice",
                "langfuse", "honcho", "hindsight", "chatbotx", "ponytail", "tigervnc", "parakeet",
                "guided-setup", "hermes-updater", "tailscale", "preferred-web-resources"}
    assert set(rows(report)) == expected
    assert report["required_count"] == len(expected)
    assert all(row["required"] and row["state"] == "PLANNED" for row in report["components"])
    assert {"python", "python-ai", "node", "npm", "uv", "github-cli", "vercel-cli", "codex-cli",
            "composio-cli", "shadcn-cli", "chatbotx-cli", "discord.js", "hermes"} == set(rows(report)["toolchain"]["members"])
    assert report["full_software_verified"] is False
    assert report["operational"] is False
    assert report["account_readback"] == "NOT_CHECKED"


def test_successful_probes_still_leave_ponytail_blocked_and_no_live_claim(fixture, monkeypatch):
    monkeypatch.setattr(full_stack, "run_bounded_native", lambda *a, **k: pytest.fail("synthetic reached live executor"))
    before = snapshot(fixture.root)
    report = fixture.check()
    observed = rows(report)
    assert report["verified_count"] == 17
    assert report["full_software_verified"] is False and report["synthetic"] is True
    assert observed["ponytail"]["state"] == "BLOCKED_NOT_VERIFIED"
    assert observed["ponytail"]["reason_code"] == "NATIVE_SECURITY_SCAN_REJECTED"
    assert observed["preferred-web-resources"]["state"] == "DELIVERED_NOT_PROJECT_INSTALLED"
    assert observed["preferred-web-resources"]["software_installed"] is False
    assert all(row["operational"] is False and row["account_readback"] == "NOT_CHECKED" for row in observed.values())
    assert fixture.bundles == ["langfuse", "honcho", "hindsight", "chatbotx"]
    assert before == snapshot(fixture.root)


def test_commands_are_fixed_clean_environment_checks_without_activation(fixture, monkeypatch):
    monkeypatch.setenv("CHATBOTX_API_KEY", "secret-parent-token")
    monkeypatch.setenv("BASH_ENV", "/malicious/startup")
    monkeypatch.setenv("CONTAINER_HOST", "ssh://wrong-host")
    fixture.check()
    serialized = json.dumps(fixture.commands)
    assert not any(secret in serialized for secret in ("secret-parent-token", "/malicious/startup", "ssh://wrong-host"))
    forbidden = {"pull", "up", "start", "restart", "enable", "login", "status", "--all", "--install", "plugins", "list-sessions"}
    assert not any(forbidden.intersection(command) for command in fixture.commands)
    flags = {command[-1] for command in fixture.commands if "station_deps_install.sh" in command[-2]}
    assert flags == {"--check-web", "--check-hermes-clients", "--check-memory", "--check-voice", "--check-strix"}
    for command in fixture.commands:
        assert "/usr/bin/env" in command and "-i" in command
        assert "HOME=/nonexistent" in command
        assert "HERMES_HOME=/nonexistent/.hermes" in command
    agk_commands = [command for command in fixture.commands if command[-1] == "help" or command[-2:] == ["capabilities", "--json"]]
    assert all(command[:4] == ["/usr/sbin/runuser", "--user", "agk-station", "--"] for command in agk_commands)


@pytest.mark.parametrize("flag,failed", [("--check", "toolchain"), ("--check-web", "web-runtimes"),
                                       ("--check-memory", "memory-clients"), ("--check-voice", "voice"),
                                       ("--check-hermes-clients", "hermes-clients"), ("--check-strix", "strix")])
def test_native_failure_is_redacted_and_later_components_still_checked(fixture, flag, failed):
    fixture.fail_on = flag
    report = fixture.check()
    assert rows(report)[failed]["state"] == "NOT_VERIFIED"
    assert rows(report)["tailscale"]["requirement_verified"] is True
    assert fixture.bundles == ["langfuse", "honcho", "hindsight", "chatbotx"]
    assert "secret-native" not in json.dumps(report)


def test_bundle_exception_never_leaks_or_stops_other_bundles(fixture):
    def checker(component):
        if component == "langfuse":
            raise RuntimeError("secret-provider-config-content")
        return {"component": component, "state": "SOFTWARE_INSTALLED", "software_installed": True,
                "configuration_required": True, "operational": False, "secret": "must-not-copy"}
    fixture.bundle_override = checker
    report = fixture.check()
    assert rows(report)["langfuse"]["state"] == "NOT_VERIFIED"
    assert rows(report)["chatbotx"]["software_installed"] is True
    assert "secret-provider" not in json.dumps(report) and "must-not-copy" not in json.dumps(report)
    assert len(fixture.bundles) == 4


@pytest.mark.parametrize("changes", [{"software_installed": "yes"}, {"state": "PLANNED"},
                                     {"component": "another"}, {"operational": True}, {"configuration_required": False}])
def test_unverified_or_overclaimed_bundle_cannot_pass(fixture, changes):
    fixture.bundle_override = lambda component: {"component": component, "state": "SOFTWARE_INSTALLED",
        "software_installed": True, "configuration_required": True, "operational": False, **changes}
    report = fixture.check()
    assert all(rows(report)[name]["state"] == "NOT_VERIFIED" for name in fixture.bundles)


def test_oversized_native_output_is_not_accepted_or_replayed(fixture):
    fixture.output_override = b"secret-output" * full_stack.OUTPUT_LIMIT
    report = fixture.check()
    assert rows(report)["toolchain"]["state"] == "NOT_VERIFIED"
    assert "secret-output" not in json.dumps(report)


@pytest.mark.parametrize("operator", ["root;id", "-u", "../agk", "agk station", "agk\nstation", "A"])
def test_operator_command_injection_is_rejected_before_probes(fixture, operator):
    with pytest.raises(ValidationError):
        fixture.check(operator=operator)
    assert fixture.commands == []


@pytest.mark.parametrize("home", [Path("relative"), Path("/"), Path("/home"), Path("/home/a/../b")])
def test_unsafe_operator_home_is_rejected(fixture, home):
    with pytest.raises(SecurityError):
        fixture.check(operator_home=home)
    assert fixture.commands == []


@pytest.mark.parametrize("root", [Path("/"), Path("/opt/station/test"), Path("/var/lib/station/test"),
                                Path("/home/test/fixture"), Path("/etc/test"), Path("/tmp")])
def test_injected_executor_cannot_target_canonical_or_broad_paths(fixture, root):
    with pytest.raises(SecurityError):
        full_stack.check(fixture.repo, root=root, run=fixture.run, bundle_check=fixture.bundle_check)
    assert fixture.commands == []


def test_synthetic_root_requires_both_executors_no_live_fallback(fixture):
    with pytest.raises(SecurityError):
        full_stack.check(fixture.repo, root=fixture.root, run=fixture.run)
    with pytest.raises(SecurityError):
        full_stack.check(fixture.repo, root=fixture.root, bundle_check=fixture.bundle_check)
    with pytest.raises(SecurityError):
        full_stack.check(fixture.repo, root=fixture.root)


def test_live_audit_rejects_nonlinux_or_nonroot_before_execution(fixture, monkeypatch):
    monkeypatch.setattr(full_stack.os, "geteuid", lambda: 1001)
    monkeypatch.setattr(full_stack, "run_bounded_native", lambda *a, **k: pytest.fail("live probe ran"))
    with pytest.raises(SecurityError):
        full_stack.check(fixture.repo)


def test_symlink_fixture_root_is_rejected(fixture, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(fixture.root, target_is_directory=True)
    with pytest.raises(SecurityError):
        full_stack.check(fixture.repo, root=alias, run=fixture.run, bundle_check=fixture.bundle_check)


def test_symlink_unit_is_not_accepted_or_followed(fixture):
    path = fixture.root / "etc/systemd/system/station-parakeet.service"
    path.unlink()
    path.symlink_to(fixture.repo / "runtime/systemd/station-parakeet.service")
    report = fixture.check()
    assert rows(report)["parakeet"]["state"] == "NOT_VERIFIED"
    assert rows(report)["tailscale"]["requirement_verified"] is True


def test_distro_native_hardlinks_are_allowed_without_relaxing_artifacts(tmp_path):
    native = tmp_path / "coreutils-env"
    native.write_bytes(b"synthetic-not-executed")
    native.chmod(0o755)
    os.link(native, tmp_path / "coreutils-multicall")
    assert native.stat().st_nlink == 2
    full_stack._regular(native, owner=os.geteuid(), executable=True, single_link=False)
    with pytest.raises(SecurityError):
        full_stack._regular(native, owner=os.geteuid(), executable=True)
    with pytest.raises(SecurityError):
        full_stack._read(native, uid=os.geteuid())


@pytest.mark.parametrize("unsafe", ["owner", "writable", "symlink", "untrusted-parent"])
def test_native_hardlink_exception_retains_owner_mode_and_ancestry_checks(tmp_path, unsafe):
    native = tmp_path / "native"
    native.write_bytes(b"synthetic-not-executed")
    native.chmod(0o755)
    os.link(native, tmp_path / "multicall")
    owner = os.geteuid()
    options = {}
    if unsafe == "owner":
        owner += 1
    elif unsafe == "writable":
        native.chmod(0o777)
    elif unsafe == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(native)
        native = alias
    else:
        # The native path always requests root ownership and a trusted root
        # chain. A temporary/user-writable ancestor must still fail first.
        owner = 0
        options["privileged"] = True
    with pytest.raises(SecurityError):
        full_stack._regular(native, owner=owner, executable=True, single_link=False, **options)


def test_hardlinked_station_updater_artifact_still_fails(fixture):
    helper = fixture.root / "usr/local/libexec/station-hermes-update"
    os.link(helper, helper.parent / "unexpected-update-alias")
    row = rows(fixture.check())["hermes-updater"]
    assert row["software_installed"] is False and row["state"] == "NOT_VERIFIED"


def test_agk_changed_launcher_is_not_executed_and_no_tui_claim(fixture):
    path = fixture.root / "home/agk-station/.local/bin/agk"
    path.write_text("#!/bin/sh\necho unreviewed\n")
    report = fixture.check()
    assert rows(report)["agk"]["state"] == "NOT_VERIFIED"
    assert not any(command[-1] == "help" for command in fixture.commands)
    assert "not-interactive-tui" in rows(report)["agk"]["verification_scope"]


def test_rmux_native_alias_cannot_escape_synthetic_root(fixture, tmp_path):
    path = fixture.agk / "bin/rmux"
    path.unlink()
    outside = tmp_path / "outside-native"
    outside.write_bytes(b"unreviewed")
    outside.chmod(0o755)
    path.symlink_to(outside)
    assert rows(fixture.check())["agk"]["state"] == "NOT_VERIFIED"
    assert not any(command[-2:] == ["capabilities", "--json"] for command in fixture.commands)


def test_parakeet_software_is_distinct_from_failed_local_health(fixture):
    fixture.fail_on = "/health"
    report = fixture.check()
    row = rows(report)["parakeet"]
    assert row["software_installed"] is True
    assert row["state"] == "SOFTWARE_INSTALLED_LOCAL_CHECK_FAILED"
    assert row["requirement_verified"] is False and row["operational"] is False


def test_parakeet_wrong_running_image_fails_local_gate(fixture):
    fixture.container_id = "b" * 64
    row = rows(fixture.check())["parakeet"]
    assert row["software_installed"] is True and row["requirement_verified"] is False
    assert not any(command[-1] == "http://127.0.0.1:5092/health" for command in fixture.commands)


def test_parakeet_wrong_installed_digest_cannot_claim_software(fixture):
    fixture.image_digest = "sha256:" + "b" * 64
    row = rows(fixture.check())["parakeet"]
    assert row["software_installed"] is False and row["state"] == "NOT_VERIFIED"


def test_updater_drift_fails_without_running_updater(fixture):
    (fixture.root / "usr/local/libexec/station-hermes-update").write_text("modified updater")
    row = rows(fixture.check())["hermes-updater"]
    assert row["state"] == "NOT_VERIFIED"
    assert not any(command[-1] == "auto" for command in fixture.commands)


def test_disabled_updater_timer_does_not_fail_software_acceptance(fixture):
    original = fixture.run
    schedule_probes = []
    def disabled_timer(argv, **kwargs):
        if ("/usr/bin/systemctl" in argv and "station-hermes-update.timer" in argv
                and {"is-enabled", "is-active"}.intersection(argv)):
            schedule_probes.append(argv)
            return subprocess.CompletedProcess(argv, 1, b"disabled/inactive", b"")
        return original(argv, **kwargs)
    fixture.run = disabled_timer
    row = rows(fixture.check())["hermes-updater"]
    assert row["software_installed"] is True and row["requirement_verified"] is True
    assert row["scheduling"] == "NOT_CHECKED"
    assert row["configuration_required"] is True and row["operational"] is False
    assert schedule_probes == []
    assert "not-scheduling" in row["verification_scope"]


def test_guided_setup_is_required_but_local_health_never_claims_accounts(fixture, monkeypatch):
    original_read = full_stack._read

    def no_zone_state(path, **kwargs):
        assert "/zones/" not in str(path) and "setup-links" not in str(path)
        return original_read(path, **kwargs)

    monkeypatch.setattr(full_stack, "_read", no_zone_state)
    report = fixture.check()
    row = rows(report)["guided-setup"]
    assert row["required"] is True and row["software_installed"] is True
    assert row["requirement_verified"] is True
    assert row["operational"] is False and row["configuration_required"] is True
    assert row["account_readback"] == "NOT_CHECKED"
    assert "not-tailnet-token-or-account-readiness" in row["verification_scope"]
    assert not any(command[-2:] == ["status", "--json"] or "serve" in command for command in fixture.commands)
    assert not any("--property=Environment" in command or "--property=ExecStart" in command for command in fixture.commands)
    assert report["required_count"] == 18


@pytest.mark.parametrize("health", ['{"status":"bad"}', 'secret-unexpected-body', '{"status":"ok","token":"secret-token"}'])
def test_guided_setup_unhealthy_body_preserves_software_but_redacts_body(fixture, health):
    fixture.guided_health = health
    report = fixture.check()
    row = rows(report)["guided-setup"]
    assert row["software_installed"] is True and row["requirement_verified"] is False
    assert row["state"] == "SOFTWARE_INSTALLED_LOCAL_CHECK_FAILED"
    assert "secret-" not in json.dumps(report)
    assert rows(report)["tailscale"]["requirement_verified"] is True


def test_guided_setup_inactive_service_does_not_call_health_or_activate(fixture):
    fixture.guided_active = False
    row = rows(fixture.check())["guided-setup"]
    assert row["software_installed"] is True
    assert row["state"] == "SOFTWARE_INSTALLED_LOCAL_CHECK_FAILED"
    assert row["requirement_verified"] is False
    assert not any(command[-1] == "http://127.0.0.1:8787/health" for command in fixture.commands)
    assert not any("start" in command or "enable" in command for command in fixture.commands)


@pytest.mark.parametrize("changed", ["user", "reload", "unit", "program", "public-alias", "current-alias"])
def test_guided_setup_artifact_identity_and_loaded_unit_drift_fail_closed(fixture, changed):
    if changed == "user":
        fixture.guided_user = "root"
    elif changed == "reload":
        fixture.guided_reload = "yes"
    elif changed == "unit":
        path = fixture.root / "etc/systemd/system/station-guided-setup.service"
        path.write_text(path.read_text().replace("--host 127.0.0.1", "--host 0.0.0.0"))
    elif changed == "program":
        path = fixture.repo / "src/agentik_station/guided_setup.py"
        path.unlink()
        path.symlink_to(fixture.repo / "station")
    else:
        path = fixture.root / ("usr/local/bin/station" if changed == "public-alias" else "opt/station/current")
        path.unlink()
        path.symlink_to("/unrelated/software")
    row = rows(fixture.check())["guided-setup"]
    assert row["state"] == "NOT_VERIFIED" and row["software_installed"] is False
    assert not any(command[-1] == "http://127.0.0.1:8787/health" for command in fixture.commands)


def test_existing_ponytail_directory_never_clears_guard(fixture):
    plugin = fixture.root / "home/agk-station/.hermes/plugins/ponytail"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text("enabled: true\n")
    report = fixture.check()
    assert rows(report)["ponytail"]["software_installed"] is False
    assert rows(report)["ponytail"]["state"] == "BLOCKED_NOT_VERIFIED"
    assert report["full_software_verified"] is False


def test_resource_identity_or_pin_drift_is_not_delivery(fixture):
    resource = fixture.repo / "resources/frontend/lucide/RESOURCE.json"
    resource.write_text(json.dumps({"schema_version": 1, "id": "lucide", "version": "0.0.0"}))
    assert rows(fixture.check())["preferred-web-resources"]["state"] == "NOT_VERIFIED"


def test_duplicate_or_malicious_pin_is_rejected_before_any_probe(fixture):
    lock = fixture.repo / "config/versions.lock"
    lock.write_text(lock.read_text() + "PARAKEET_PORT=5092;id\n")
    with pytest.raises(ValidationError):
        fixture.check()
    assert fixture.commands == []
