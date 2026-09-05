"""Local fake-Hermes regressions: no provider, runuser, services or root writes."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agentik_station import os_lifecycle as lifecycle
from agentik_station.doctor import _expected_zone_human_path
from agentik_station.errors import SecurityError, ValidationError
from agentik_station.identity import zone_unix_user
from agentik_station.models import ZoneSpec
from agentik_station.paths import LayoutPaths


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve())
    spec = ZoneSpec("LAB", "lab", "lab", "station-core-01")
    human = _expected_zone_human_path(paths, spec)
    state = paths.zones_state / spec.zone_id
    user = zone_unix_user(spec.category, spec.name, spec.environment)
    zone = {"schema_version": 2, "id": spec.zone_id, "name": spec.name,
            "category": spec.category, "organization": spec.organization,
            "environment": spec.environment, "host_id": spec.host_id, "unix_user": user,
            "human_root": str(human), "state_root": str(state), "hermes_home": str(state / "hermes"),
            "log_root": str(paths.log / "zones" / spec.zone_id),
            "runtime_root": str(paths.run / "zones" / spec.zone_id),
            "backup_staging_root": str(paths.backups / "zones" / spec.zone_id), "placement": "local",
            "isolation": {"filesystem": "unix-identity", "hermes_home": "dedicated", "credentials": "zone-scoped", "cross_zone_mounts": "deny"}}
    for path in (paths.config / "zones.d", paths.software, paths.varlib, human, state / "home", state / "hermes"):
        path.mkdir(parents=True, exist_ok=True, mode=0o750)
    zone_file = paths.config / "zones.d" / f"{spec.zone_id}.json"
    zone_file.write_text(json.dumps(zone))
    zone_file.chmod(0o600)
    for project_id in ("one", "two"):
        project = human / "projects" / project_id
        project.mkdir(parents=True, mode=0o750)
        (project / "PROJECT.json").write_text(json.dumps({"schema_version": 2, "id": project_id,
            "zone_id": spec.zone_id, "organization": spec.organization, "environment": spec.environment,
            "human_root": str(project), "runtime_state_root": str(state / "projects" / project_id),
            "repos": [], "credential_references": []}))
    monkeypatch.setattr(lifecycle.pwd, "getpwnam", lambda name: SimpleNamespace(
        pw_dir=str(state / "home"), pw_uid=os.getuid(), pw_gid=os.getgid()))
    monkeypatch.setattr(lifecycle.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()))
    data = SimpleNamespace(paths=paths, zone=zone, calls=[], fail=None, zero_without_files=False,
                           crash_after_copy=False, doctor_fail=False, tamper_final=False,
                           source_text="static payload", profiles=["director", "worker"])

    def compile_bundle(source, output, *, project_root):
        output.mkdir(parents=True)
        profiles = data.profiles
        for name in profiles:
            root = output / "profiles" / name
            (root / "plugins/station-web").mkdir(parents=True)
            (root / "plugins/station-web/plugin.yaml").write_text("name: station-web\n")
            (root / "SOUL.md").write_text(data.source_text)
            (root / "distribution.yaml").write_text(yaml.safe_dump({"name": name, "version": "11.12",
                "distribution_owned": ["SOUL.md", "config.yaml", "plugins/station-web/", "distribution.yaml"]}))
            (root / "config.yaml").write_text(yaml.safe_dump({"profile": {"id": name},
                "terminal": {"cwd": str(project_root), "home_mode": "profile"},
                "plugins": {"enabled": ["station-web"], "entries": {"station-web": {"allow_tool_override": False}}}}))
        manifest = {"schema_version": 2, "os_id": "fixture-os", "os_version": "11.12",
                    "profiles": profiles, "nano_director": profiles[0], "project_root": str(project_root)}
        (output / "COMPILED.json").write_text(json.dumps(manifest, sort_keys=True))
        return manifest

    def run(argv, **kwargs):
        assert argv[:6] == ["/fake/runuser", "--user", user, "--", "/usr/bin/env", "-i"]
        assert f"HOME={state / 'home'}" in argv
        assert f"HERMES_HOME={state / 'hermes'}" in argv
        assert kwargs["stdout"] == subprocess.DEVNULL and kwargs["stderr"] == subprocess.DEVNULL
        assert "--force" not in argv
        args = argv[argv.index("/fake/hermes") + 1:]
        data.calls.append(args)
        if args[-1] == "doctor":
            return SimpleNamespace(returncode=1 if data.doctor_fail else 0, stdout="secret", stderr="secret")
        assert args[:2] == ["--profile", "default"]
        args = args[2:]
        profile = args[args.index("--name") + 1]
        if profile == data.fail:
            return SimpleNamespace(returncode=1, stdout="provider-secret", stderr="provider-secret")
        if data.zero_without_files:
            return SimpleNamespace(returncode=0)
        source = Path(args[2])
        target = state / "hermes/profiles" / profile
        target.parent.mkdir(exist_ok=True)
        shutil.copytree(source, target)
        for current, dirs, files in os.walk(target):
            Path(current).chmod(0o750)
            for filename in files:
                (Path(current) / filename).chmod(0o640)
        metadata = yaml.safe_load((target / "distribution.yaml").read_text())
        metadata.update(source=str(source), installed_at="2026-09-05T00:00:00+00:00")
        metadata["distribution_owned"] = [name.rstrip("/") for name in metadata["distribution_owned"]]
        (target / "distribution.yaml").write_text(yaml.safe_dump(metadata))
        if data.tamper_final and profile == "worker":
            (state / "hermes/profiles/director/SOUL.md").write_text("changed by later native startup")
        if data.crash_after_copy:
            data.crash_after_copy = False
            raise KeyboardInterrupt()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle, "compile_os_to_hermes", compile_bundle)
    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    data.install = lambda **kwargs: lifecycle.install_os_runtime(Path("/unused/source"), paths=paths, zone=zone,
        project_id=kwargs.pop("project_id", "one"), os_id=kwargs.pop("os_id", "fixture-os"),
        os_version=kwargs.pop("os_version", "11.12"), hermes_binary="/fake/hermes", runuser_binary="/fake/runuser", **kwargs)
    data.load = lambda **kwargs: lifecycle.load_os_runtime_record(paths, zone=zone, os_id="fixture-os", **kwargs)
    data.verify = lambda: lifecycle.verify_os_runtime(paths, zone=zone, os_id="fixture-os", hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
    data.ledger = paths.varlib / "registry/os" / spec.zone_id / "fixture-os.json"
    data.native = lambda name="director": state / "hermes/profiles" / name
    return data


def test_install_complete_team_and_ledger_no_secrets(runtime):
    record = runtime.install()
    assert record["state"] == "CONFIGURED" and record["operational"] is False
    assert set(record["profile_states"]) == {"director", "worker"}
    assert len(runtime.calls) == 2
    assert runtime.ledger.stat().st_mode & 0o777 == 0o600
    assert runtime.ledger.parent.stat().st_mode & 0o777 == 0o700
    assert "secret" not in runtime.ledger.read_text()
    assert runtime.load(require_configured=True)["state"] == "CONFIGURED"


def test_resume_installs_only_missing_profile_and_preserves_provider(runtime):
    runtime.fail = "worker"
    assert runtime.install()["state"] == "INSTALLABLE"
    config = runtime.native() / "config.yaml"
    value = yaml.safe_load(config.read_text())
    value["model"] = {"provider": "private-provider", "api_key": "do-not-record-this"}
    config.write_text(yaml.safe_dump(value))
    (runtime.native() / ".env").write_text("PRIVATE_SECRET=untouched\n")
    runtime.fail = None
    assert runtime.install()["state"] == "CONFIGURED"
    assert [args[-2] for args in runtime.calls] == ["director", "worker", "worker"]
    assert config.read_text() == yaml.safe_dump(value)
    assert (runtime.native() / ".env").read_text() == "PRIVATE_SECRET=untouched\n"
    assert "do-not-record-this" not in runtime.ledger.read_text()


def test_crash_after_complete_native_install_can_resume(runtime):
    runtime.crash_after_copy = True
    with pytest.raises(KeyboardInterrupt):
        runtime.install()
    assert runtime.load()["profile_states"]["director"]["state"] == "INSTALLING"
    assert runtime.install()["state"] == "CONFIGURED"
    assert len(runtime.calls) == 2


def test_existing_identical_bundle_is_reused(runtime):
    original = runtime.install()
    assert runtime.install()["bundle_sha256"] == original["bundle_sha256"]
    assert len(runtime.calls) == 2


@pytest.mark.parametrize("change", [{"project_id": "two"}, {"os_version": "11.13"}])
def test_project_or_version_conflict_precedes_native_mutation(runtime, change):
    runtime.install()
    before = runtime.ledger.read_bytes()
    with pytest.raises(ValidationError, match="another Project/version"):
        runtime.install(**change)
    assert runtime.ledger.read_bytes() == before and len(runtime.calls) == 2


def test_same_version_source_change_is_rejected(runtime):
    runtime.install()
    before = runtime.ledger.read_bytes()
    runtime.source_text = "different source"
    with pytest.raises(ValidationError, match="Same-version"):
        runtime.install()
    assert runtime.ledger.read_bytes() == before and len(runtime.calls) == 2


def test_untracked_native_profile_is_not_adopted(runtime):
    runtime.native().mkdir(parents=True)
    with pytest.raises(ValidationError, match="Untracked"):
        runtime.install()
    assert not runtime.ledger.exists() and not runtime.calls


def test_zero_exit_without_installed_content_fails_readback(runtime):
    runtime.zero_without_files = True
    record = runtime.install()
    assert record["state"] == "INSTALLABLE"
    assert record["profile_states"]["director"]["state"] == "FAILED"
    assert record["profile_states"]["director"]["returncode"] == 0


def test_install_rechecks_complete_team_after_last_native_action(runtime):
    runtime.tamper_final = True
    record = runtime.install()
    assert record["state"] == "INSTALLABLE"
    assert record["profile_states"]["director"]["reason"] == "Final complete-team readback failed"


def test_partial_existing_profile_requires_explicit_repair(runtime):
    runtime.fail = "worker"
    runtime.install()
    runtime.native("worker").mkdir()
    runtime.fail = None
    record = runtime.install()
    assert record["state"] == "INSTALLABLE" and len(runtime.calls) == 2
    assert "explicit repair" in record["profile_states"]["worker"]["reason"]


def test_subset_ledger_is_not_authority(runtime):
    runtime.install()
    value = json.loads(runtime.ledger.read_text())
    value["expected_profiles"] = ["director"]
    value["profile_states"].pop("worker")
    runtime.ledger.write_text(json.dumps(value))
    with pytest.raises(SecurityError, match="bytes/team"):
        runtime.load(require_configured=True)
    assert len(runtime.calls) == 2


def test_mutable_zone_projection_does_not_enable_routing(runtime):
    projection = Path(runtime.zone["human_root"]) / "os/fixture-os.runtime.json"
    projection.parent.mkdir()
    projection.write_text('{"state":"VERIFIED","profiles":["director"]}')
    with pytest.raises(FileNotFoundError):
        runtime.load(require_configured=True)
    assert not runtime.ledger.parent.exists()


@pytest.mark.parametrize("tamper", ["cwd", "source", "payload", "symlink", "hardlink"])
def test_native_readback_rejects_tampering_without_commands(runtime, tamper):
    runtime.install()
    root = runtime.native()
    if tamper == "cwd":
        path = root / "config.yaml"
        data = yaml.safe_load(path.read_text())
        data["terminal"]["cwd"] = "/root"
        path.write_text(yaml.safe_dump(data))
    elif tamper == "source":
        path = root / "distribution.yaml"
        data = yaml.safe_load(path.read_text())
        data["source"] = "/another/distribution"
        path.write_text(yaml.safe_dump(data))
    elif tamper == "payload":
        (root / "SOUL.md").write_text("modified")
    else:
        path = root / "SOUL.md"
        original = root / "copy.txt"
        path.rename(original)
        if tamper == "symlink":
            path.symlink_to(original)
        else:
            os.link(original, path)
    with pytest.raises((OSError, ValidationError, SecurityError)):
        runtime.load(require_configured=True)
    assert len(runtime.calls) == 2


def test_forged_zone_paths_rejected_before_use(runtime):
    forged = dict(runtime.zone, human_root="/root")
    with pytest.raises(SecurityError, match="trusted desired"):
        lifecycle.load_os_runtime_record(runtime.paths, zone=forged, os_id="fixture-os")
    assert not runtime.calls


def test_project_ancestor_symlink_rejected(runtime):
    project = Path(runtime.zone["human_root"]) / "projects/one"
    saved = project.with_name("saved")
    project.rename(saved)
    project.symlink_to(saved, target_is_directory=True)
    with pytest.raises(OSError):
        runtime.install()
    assert not runtime.calls and not runtime.ledger.exists()


@pytest.mark.parametrize("relative", [".staging", "os-distributions/lab/one"])
def test_publication_parent_must_already_be_trusted(runtime, relative):
    parent = runtime.paths.software / relative
    parent.mkdir(parents=True)
    parent.chmod(0o777)
    with pytest.raises(SecurityError, match="directory"):
        runtime.install()
    assert parent.stat().st_mode & 0o777 == 0o777  # no ownership/permission takeover
    assert not runtime.calls and not runtime.ledger.exists()


def test_verify_exact_full_team_local_only_and_invalidate_changed_config(runtime):
    runtime.install()
    result = runtime.verify()
    assert result["state"] == "VERIFIED" and result["operational"] is False
    assert runtime.calls[-2:] == [["--profile", "director", "doctor"], ["--profile", "worker", "doctor"]]
    assert set(result["verification"]["profiles"]) == {"director", "worker"}
    path = runtime.native() / "config.yaml"
    data = yaml.safe_load(path.read_text())
    data["model"] = "new-model"
    path.write_text(yaml.safe_dump(data))
    before = runtime.ledger.read_bytes()
    assert runtime.load(require_configured=True)["state"] == "CONFIGURED"
    assert runtime.ledger.read_bytes() == before  # read-only even when evidence is stale
    assert len(runtime.calls) == 4


def test_doctor_failure_persists_fixed_summary(runtime):
    runtime.install()
    runtime.doctor_fail = True
    result = runtime.verify()
    assert result["state"] == "DEGRADED" and result["next_repair_action"]
    assert "secret" not in runtime.ledger.read_text()


def test_doctor_failure_allows_configuration_repair_and_reverification(runtime):
    runtime.install()
    runtime.doctor_fail = True
    assert runtime.verify()["state"] == "DEGRADED"
    # The provider wizard resolver can still identify the completely installed
    # Director; no reinstallation or overwriting the provider config is needed.
    assert runtime.load(require_configured=True)["nano_director"] == "director"
    config = runtime.native() / "config.yaml"
    value = yaml.safe_load(config.read_text())
    value["model"] = "repaired-model"
    config.write_text(yaml.safe_dump(value))
    runtime.doctor_fail = False
    assert runtime.verify()["state"] == "VERIFIED"
    assert sum("install" in args for args in runtime.calls) == 2


def test_completed_tree_with_installing_checkpoint_needs_resume(runtime):
    runtime.crash_after_copy = True
    with pytest.raises(KeyboardInterrupt):
        runtime.install()
    with pytest.raises(ValidationError, match="not completely installed"):
        runtime.load(require_configured=True)


def test_install_explicitly_ignores_sticky_active_profile(runtime):
    active = Path(runtime.zone["hermes_home"]) / "active_profile"
    active.write_text("unrelated-profile\n")
    runtime.install()
    assert all(args[:2] == ["--profile", "default"] for args in runtime.calls)
    assert active.read_text() == "unrelated-profile\n"


def test_native_tombstone_blocks_routing_and_automatic_recreation(runtime):
    runtime.install()
    deleted = Path(runtime.zone["hermes_home"]) / "profiles/.deleted"
    deleted.mkdir()
    (deleted / "director").write_text("deleted\n")
    with pytest.raises(ValidationError, match="tombstoned"):
        runtime.load(require_configured=True)
    with pytest.raises(ValidationError, match="tombstoned"):
        runtime.install()
    assert len(runtime.calls) == 2


def test_real_devops_compiler_installs_full_team_with_fake_native_runtime(runtime, monkeypatch):
    from agentik_station.os_runtime import compile_os_to_hermes
    monkeypatch.setattr(lifecycle, "compile_os_to_hermes", compile_os_to_hermes)
    source = Path(__file__).resolve().parents[2] / "os/devops"
    contract = json.loads((source / "CONTRACT.json").read_text())
    result = lifecycle.install_os_runtime(source, paths=runtime.paths, zone=runtime.zone,
        project_id="one", os_id=contract["os_id"], os_version=contract["version"],
        hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
    assert result["state"] == "CONFIGURED"
    assert set(result["expected_profiles"]) == {contract["nano_director"], *contract["nanoteam"]}
    assert len(runtime.calls) == len(result["expected_profiles"])


def test_created_project_to_real_devops_team_and_selected_director_onboarding(runtime, monkeypatch):
    """Cross-module path with canonical templates/compiler and fake native process.

    Host metadata here is a synthetic reconciled-Zone fixture, not VPS acceptance.
    No provider setup, service activation or live chat is performed.
    """
    from agentik_station import onboarding, projects
    from agentik_station.hermes_platforms import build_gateway_argv
    from agentik_station.os_runtime import compile_os_to_hermes

    paths, zone = runtime.paths, runtime.zone
    repo = Path(__file__).resolve().parents[2]
    (Path(zone["state_root"]) / "projects").mkdir()
    paths.observed.mkdir()
    (paths.observed / "host.json").write_text(json.dumps({
        "schema_version": 1, "host_id": zone["host_id"], "state": "READY_FOR_SETUP"}))
    initial = onboarding.build_onboarding_report(paths, repo, zone_id=zone["id"], project_id="mission", os_id="devops-os")
    assert initial["next_action"]["argv"][1:3] == ["project", "create"]
    result = projects.create_project(paths, repo, zone=zone, project_id="mission")
    assert result["claim"] == "PROJECT_LAYOUT_CREATED_NOT_OS_INSTALLED"
    prepared = onboarding.build_onboarding_report(paths, repo, zone_id=zone["id"], project_id="mission", os_id="devops-os")
    assert prepared["next_action"]["argv"][1:3] == ["os", "install"]

    monkeypatch.setattr(lifecycle, "compile_os_to_hermes", compile_os_to_hermes)
    contract = json.loads((repo / "os/devops/CONTRACT.json").read_text())
    installed = lifecycle.install_os_runtime(repo / "os/devops", paths=paths, zone=zone,
        project_id="mission", os_id=contract["os_id"], os_version=contract["version"],
        hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
    assert installed["state"] == "CONFIGURED"
    assert len(runtime.calls) == len(installed["expected_profiles"])
    verified = lifecycle.verify_os_runtime(paths, zone=zone, os_id=contract["os_id"],
        hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
    assert verified["state"] == "VERIFIED"
    report = onboarding.build_onboarding_report(paths, repo, zone_id=zone["id"], os_id=contract["os_id"])
    assert report["scope"]["project_id"] == "mission"
    assert report["scope"]["director_profile"] == contract["nano_director"]
    assert report["next_action"]["argv"][1:3] == ["os", "setup"]
    assert report["gateway_observation"]["state"] == "UNKNOWN_NOT_PROBED"
    assert report["operational"] is False
    argv = build_gateway_argv(zone, "start", runtime_uid=os.getuid(),
        hermes_binary=Path("/fake/hermes"), runuser_binary=Path("/fake/runuser"),
        director_profile=report["scope"]["director_profile"])
    assert argv[-4:] == ["--profile", contract["nano_director"], "gateway", "start"]
    assert len(runtime.calls) == 2 * len(installed["expected_profiles"])


def test_missing_team_cannot_verify(runtime):
    runtime.install()
    (runtime.native("worker") / "SOUL.md").unlink()
    with pytest.raises(FileNotFoundError):
        runtime.verify()
    assert len(runtime.calls) == 2


@pytest.mark.parametrize("profile", ["default", "root", "hermes", "sudo", "tmp", "test"])
def test_native_reserved_names_are_rejected(runtime, profile):
    runtime.profiles = [profile]
    with pytest.raises(ValidationError, match="reserved native"):
        runtime.install()
    assert not runtime.calls


@pytest.mark.parametrize("payload", ['{"x":1,"x":2}', '[]', '{"a":NaN}', '{"nested":{"a":1,"a":2}}'])
def test_read_only_json_rejects_ambiguous_data(tmp_path, payload):
    path = tmp_path / "record.json"
    path.write_text(payload)
    with pytest.raises(ValidationError):
        lifecycle.read_runtime_json(path, uid=os.getuid())


def test_read_only_json_no_create_and_bounded(tmp_path):
    with pytest.raises(FileNotFoundError):
        lifecycle.read_runtime_json(tmp_path / "missing/record.json", uid=os.getuid())
    assert not (tmp_path / "missing").exists()
    path = tmp_path / "record.json"
    path.write_text('{"big":"' + "x" * 100 + '"}')
    with pytest.raises(ValidationError, match="size limit"):
        lifecycle.read_runtime_json(path, uid=os.getuid(), limit=32)


def test_trusted_json_rejects_writable_directory_and_hardlink(tmp_path):
    tmp_path = tmp_path.resolve()
    directory = tmp_path / "authority"
    directory.mkdir(mode=0o700)
    path = directory / "record.json"
    path.write_text("{}")
    directory.chmod(0o777)
    with pytest.raises(SecurityError, match="directory"):
        lifecycle.read_runtime_json(path, uid=os.getuid(), immutable=True, trusted_root=tmp_path)
    directory.chmod(0o700)
    os.link(path, directory / "alias.json")
    with pytest.raises(SecurityError, match="single-link"):
        lifecycle.read_runtime_json(path, uid=os.getuid(), immutable=True, trusted_root=tmp_path)
