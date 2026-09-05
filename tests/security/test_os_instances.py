"""Instance authority/native-routing regressions; no provider or service calls."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agentik_station import os_instances as instances, os_lifecycle as lifecycle
from agentik_station.errors import SecurityError, ValidationError
from agentik_station.hermes_platforms import build_gateway_argv, gateway_service_name
from agentik_station.os_runtime import compile_os_to_hermes, instance_profile_map
from test_os_lifecycle import runtime as legacy_runtime


@pytest.fixture
def runtime(legacy_runtime, monkeypatch):
    data = legacy_runtime
    (Path(data.zone["human_root"]) / "os").mkdir()
    legacy_compile = lifecycle.compile_os_to_hermes
    data.argv = []
    data.replace_root = False

    def compile_instance(source, output, *, workspace_root, zone_id, instance_id,
                         organization_id=None, allowed_project_ids=()):
        manifest = legacy_compile(source, output, project_root=workspace_root)
        mapping = instance_profile_map(zone_id, instance_id, data.profiles)
        for role, native in mapping.items():
            path = output / "profiles" / role
            path.rename(output / "profiles" / native)
            path = output / "profiles" / native
            config = yaml.safe_load((path / "config.yaml").read_text())
            config["profile"]["id"] = native
            (path / "config.yaml").write_text(yaml.safe_dump(config))
            dist = yaml.safe_load((path / "distribution.yaml").read_text())
            dist["name"] = native
            (path / "distribution.yaml").write_text(yaml.safe_dump(dist))
        manifest.pop("project_root")
        manifest.update(schema_version=3, zone_id=zone_id, instance_id=instance_id,
                        organization_id=organization_id, allowed_project_ids=sorted(allowed_project_ids),
                        workspace_root=str(workspace_root), role_profile_map=mapping,
                        nano_director=mapping[data.profiles[0]], profiles=list(mapping.values()))
        (output / "COMPILED.json").write_text(json.dumps(manifest, sort_keys=True))
        return manifest

    def run(argv, **kwargs):
        assert argv[:6] == ["/fake/runuser", "--user", data.zone["unix_user"], "--", "/usr/bin/env", "-i"]
        assert f"HOME={Path(data.zone['state_root']) / 'home'}" in argv
        assert kwargs["stdout"] == subprocess.DEVNULL and kwargs["stderr"] == subprocess.DEVNULL
        assert "--force" not in argv
        data.argv.append(argv)
        home = Path(next(item.split("=", 1)[1] for item in argv if item.startswith("HERMES_HOME=")))
        assert home.parent.parent == Path(data.zone["state_root"]) / "os-instances"
        args = argv[argv.index("/fake/hermes") + 1:]
        data.calls.append(args)
        if args[-1] == "doctor":
            return SimpleNamespace(returncode=1 if data.doctor_fail else 0)
        assert args[:4] == ["--profile", "default", "profile", "install"]
        profile = args[args.index("--name") + 1]
        if profile.endswith("-" + str(data.fail)):
            return SimpleNamespace(returncode=1, stdout="provider-secret", stderr="provider-secret")
        if data.zero_without_files:
            return SimpleNamespace(returncode=0)
        source = Path(args[4])
        target = home / "profiles" / profile
        target.parent.mkdir(exist_ok=True)
        shutil.copytree(source, target)
        for current, _, files in os.walk(target):
            Path(current).chmod(0o750)
            for filename in files:
                (Path(current) / filename).chmod(0o640)
        metadata = yaml.safe_load((target / "distribution.yaml").read_text())
        metadata.update(source=str(source), installed_at="2026-09-05T00:00:00+00:00")
        metadata["distribution_owned"] = [item.rstrip("/") for item in metadata["distribution_owned"]]
        (target / "distribution.yaml").write_text(yaml.safe_dump(metadata))
        if data.replace_root:
            data.replace_root = False
            home.parent.rename(home.parent.with_name("replaced"))
            home.mkdir(parents=True)
        if data.crash_after_copy:
            data.crash_after_copy = False
            raise KeyboardInterrupt()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(instances, "compile_os_to_hermes", compile_instance)
    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    data.install_legacy = data.install
    data.install = lambda **kwargs: instances.install_os_instance(Path("/unused/source"),
        paths=data.paths, zone=data.zone, instance_id=kwargs.pop("instance_id", "alpha"),
        os_id=kwargs.pop("os_id", "fixture-os"), os_version=kwargs.pop("os_version", "11.12"),
        hermes_binary="/fake/hermes", runuser_binary="/fake/runuser", **kwargs)
    data.load = lambda **kwargs: instances.load_os_instance_record(data.paths, zone=data.zone,
        instance_id=kwargs.pop("instance_id", "alpha"), **kwargs)
    data.verify = lambda: instances.verify_os_instance(data.paths, zone=data.zone, instance_id="alpha",
        hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
    data.ledger = instances.instance_paths(data.paths, data.zone, "alpha")["ledger"]
    data.native = lambda role="director", instance="alpha": (
        instances.instance_paths(data.paths, data.zone, instance)["hermes_home"] / "profiles"
        / instance_profile_map(data.zone["id"], instance, data.profiles)[role])
    return data


def test_install_owns_workspace_without_mandatory_project(runtime):
    record = runtime.install()
    assert record["schema_version"] == 3 and record["state"] == "CONFIGURED"
    assert record["organization_id"] is None and record["allowed_project_ids"] == []
    assert record["operational"] is False and "project_id" not in record
    assert record["runtime_state"] == "READY" and set(record["runtime_roots"]) == set(instances.RUNTIME_DIRECTORIES)
    assert Path(record["workspace_root"]).is_dir()
    assert Path(record["workspace_root"]).stat().st_mode & 0o777 == 0o700
    assert "os-instance-distributions" in record["compiled_distribution"]
    assert runtime.ledger.stat().st_mode & 0o777 == 0o600
    assert not list(Path(runtime.zone["hermes_home"]).iterdir())
    assert runtime.load(require_configured=True)["state"] == "CONFIGURED"


def test_same_zone_instances_have_distinct_entire_native_team_and_services(runtime):
    first = runtime.install(allowed_project_ids=["one"])
    second = runtime.install(instance_id="beta", allowed_project_ids=["two"])
    assert not set(first["expected_profiles"]) & set(second["expected_profiles"])
    assert first["hermes_home"] != second["hermes_home"]
    assert first["workspace_root"] != second["workspace_root"]
    assert gateway_service_name(first["nano_director"]) != gateway_service_name(second["nano_director"])
    assert len(runtime.calls) == 4


def test_resume_preserves_provider_configuration_and_credentials(runtime):
    runtime.fail = "worker"
    assert runtime.install()["state"] == "INSTALLABLE"
    config_path = runtime.native() / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["model"] = {"provider": "private-provider", "api_key": "private-value"}
    config_path.write_text(yaml.safe_dump(config))
    (runtime.native() / ".env").write_text("SECRET=untouched\n")
    runtime.fail = None
    assert runtime.install()["state"] == "CONFIGURED"
    assert len(runtime.calls) == 3
    assert config_path.read_text() == yaml.safe_dump(config)
    assert (runtime.native() / ".env").read_text() == "SECRET=untouched\n"
    assert "secret" not in runtime.ledger.read_text().lower()
    assert "private-value" not in runtime.ledger.read_text()


def test_crash_after_native_copy_resumes_without_force(runtime):
    runtime.crash_after_copy = True
    with pytest.raises(KeyboardInterrupt):
        runtime.install()
    assert any(item["state"] == "INSTALLING" for item in runtime.load()["profile_states"].values())
    with pytest.raises(ValidationError, match="completely installed"):
        runtime.load(require_configured=True)
    assert runtime.install()["state"] == "CONFIGURED" and len(runtime.calls) == 2


def test_exact_retry_does_not_reinstall(runtime):
    first = runtime.install(allowed_project_ids=["two", "one"])
    second = runtime.install(allowed_project_ids=["one", "two"])
    assert first["bundle_sha256"] == second["bundle_sha256"] and len(runtime.calls) == 2


@pytest.mark.parametrize("change", [{"allowed_project_ids": ["two"]}, {"os_version": "11.13"}, {"os_id": "other-os"}])
def test_declaration_changes_fail_before_mutation(runtime, change):
    runtime.install(allowed_project_ids=["one"])
    before = runtime.ledger.read_bytes()
    with pytest.raises(ValidationError, match="immutable"):
        runtime.install(**change)
    assert runtime.ledger.read_bytes() == before and len(runtime.calls) == 2


def test_changed_same_version_bundle_is_not_republished(runtime):
    runtime.install()
    before = runtime.ledger.read_bytes()
    runtime.source_text = "changed canonical source"
    with pytest.raises(ValidationError, match="Same-version"):
        runtime.install()
    assert runtime.ledger.read_bytes() == before and len(runtime.calls) == 2


@pytest.mark.parametrize("options", [{"organization_id": "client"}, {"allowed_project_ids": ["missing"]},
                                    {"allowed_project_ids": ["one", "one"]}, {"instance_id": "../escape"}])
def test_invalid_declarations_make_no_runtime_or_ledger(runtime, options):
    with pytest.raises((ValidationError, FileNotFoundError)):
        runtime.install(**options)
    assert not runtime.ledger.exists() and not runtime.calls


@pytest.mark.parametrize("kind", ["human", "state"])
def test_untracked_roots_never_adopted(runtime, kind):
    root = instances.instance_paths(runtime.paths, runtime.zone, "alpha")[kind]
    root.mkdir(parents=True)
    marker = root / "existing-owner"
    marker.write_text("preserve")
    before = root.stat()
    with pytest.raises(ValidationError, match="Untracked"):
        runtime.install()
    assert marker.read_text() == "preserve" and root.stat().st_ino == before.st_ino
    assert not runtime.ledger.exists() and not runtime.calls


def test_symlink_namespace_does_not_redirect_root_writes(runtime, tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (Path(runtime.zone["human_root"]) / "os/instances").symlink_to(victim, target_is_directory=True)
    with pytest.raises((SecurityError, OSError)):
        runtime.install()
    assert not list(victim.iterdir()) and not runtime.calls


def test_replaced_runtime_root_requires_explicit_repair(runtime):
    record = runtime.install()
    root = Path(record["hermes_home"]).parent
    root.rename(root.with_name("old-alpha"))
    (root / "hermes").mkdir(parents=True)
    with pytest.raises(SecurityError, match="replaced"):
        runtime.load(require_configured=True)
    with pytest.raises(SecurityError, match="replaced"):
        runtime.install()
    assert len(runtime.calls) == 2


def test_root_replacement_during_native_work_cannot_record_success(runtime):
    runtime.replace_root = True
    with pytest.raises(SecurityError, match="roots changed"):
        runtime.install()
    record = runtime.load()
    assert record["state"] == "INSTALLABLE" and record["runtime_state"] == "REPAIR_REQUIRED"
    assert len(runtime.calls) == 1


def test_configured_retry_root_replacement_retains_prior_maturity(runtime, monkeypatch):
    configured = runtime.install()
    original = lifecycle._readback
    replaced = False
    def readback(*args, **kwargs):
        nonlocal replaced
        result = original(*args, **kwargs)
        if not replaced:
            replaced = True
            root = Path(configured["hermes_home"]).parent
            root.rename(root.with_name("replaced"))
            (root / "hermes").mkdir(parents=True)
        return result
    monkeypatch.setattr(lifecycle, "_readback", readback)
    with pytest.raises(SecurityError, match="roots changed"):
        runtime.install()
    record = runtime.load()
    assert record["state"] == "DEGRADED" and record["runtime_state"] == "REPAIR_REQUIRED"


@pytest.mark.parametrize("key", ["workspace_root", "hermes_home"])
def test_runtime_children_also_have_pinned_identity(runtime, key):
    record = runtime.install()
    root = Path(record[key])
    root.rename(root.with_name("previous-" + root.name))
    root.mkdir(mode=0o700)
    with pytest.raises(SecurityError, match="replaced"):
        runtime.load(require_configured=True)


def test_native_config_change_invalidates_previous_verification_readonly(runtime):
    runtime.install()
    runtime.verify()
    before = runtime.ledger.read_bytes()
    path = runtime.native() / "config.yaml"
    config = yaml.safe_load(path.read_text())
    config["model"] = {"provider": "new-provider"}
    path.write_text(yaml.safe_dump(config))
    assert runtime.load(require_configured=True)["state"] == "CONFIGURED"
    assert runtime.ledger.read_bytes() == before


def test_atomic_publication_never_overwrites_concurrent_zone_tree(runtime, monkeypatch):
    from agentik_station import projects

    original = projects._rename_noreplace
    def race(source_fd, source, target_fd, target):
        if target == "alpha":
            os.mkdir(target, mode=0o700, dir_fd=target_fd)
        return original(source_fd, source, target_fd, target)
    monkeypatch.setattr(projects, "_rename_noreplace", race)
    with pytest.raises(FileExistsError):
        runtime.install()
    root = instances.instance_paths(runtime.paths, runtime.zone, "alpha")["human"]
    assert root.is_dir() and not list(root.iterdir()) and not runtime.calls
    with pytest.raises(ValidationError, match="never adopted"):
        runtime.install()


def test_zero_exit_requires_native_readback(runtime):
    runtime.zero_without_files = True
    assert runtime.install()["state"] == "INSTALLABLE"
    with pytest.raises(ValidationError):
        runtime.load(require_configured=True)


def test_verify_degraded_recovery_without_profile_reinstallation(runtime):
    runtime.install()
    runtime.doctor_fail = True
    assert runtime.verify()["state"] == "DEGRADED"
    assert runtime.load(require_configured=True)["state"] == "DEGRADED"
    runtime.doctor_fail = False
    assert runtime.verify()["state"] == "VERIFIED"
    assert sum("install" in args for args in runtime.calls) == 2
    assert runtime.load(require_configured=True)["operational"] is False


def test_readonly_load_does_not_run_subprocess_or_rewrite_evidence(runtime, monkeypatch):
    runtime.install()
    runtime.verify()
    before = runtime.ledger.read_bytes()
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda *a, **k: pytest.fail("local read invoked native Hermes"))
    assert runtime.load(require_configured=True)["state"] == "VERIFIED"
    assert runtime.ledger.read_bytes() == before


@pytest.mark.parametrize("field,value", [("workspace_root", "/root"), ("hermes_home", "/root"),
                                       ("instance_id", "beta"), ("role_profile_map", {"director": "director"}),
                                       ("expected_profiles", ["director"]), ("operational", True)])
def test_tampered_ledger_cannot_route(runtime, field, value):
    runtime.install()
    record = json.loads(runtime.ledger.read_text())
    record[field] = value
    runtime.ledger.write_text(json.dumps(record))
    with pytest.raises((SecurityError, ValidationError)):
        runtime.load(require_configured=True)


def test_instance_service_collision_precedes_install(runtime):
    profile = instance_profile_map(runtime.zone["id"], "alpha", runtime.profiles)["director"]
    service = Path(runtime.zone["state_root"]) / "home/.config/systemd/user" / gateway_service_name(profile)
    service.parent.mkdir(parents=True)
    service.write_text("unmanaged service")
    with pytest.raises(ValidationError, match="service"):
        runtime.install()
    assert not runtime.ledger.exists() and not runtime.calls


def test_legacy_install_respects_instance_service_reservation(runtime):
    record = runtime.install()
    runtime.profiles = record["expected_profiles"]
    with pytest.raises(ValidationError, match="instance reserves"):
        runtime.install_legacy()
    assert len(runtime.calls) == 2


def test_instance_qualification_is_stable_bounded_and_zone_specific():
    roles = ["a" * 24 + "-" + "long-role", "director"]
    first = instance_profile_map("lab", "alpha", roles)
    assert first == instance_profile_map("lab", "alpha", roles)
    assert all(len(value) <= 48 and not value.endswith("-") for value in first.values())
    assert not set(first.values()) & set(instance_profile_map("other", "alpha", roles).values())


@pytest.mark.parametrize("package", ["builder", "devops", "librarian", "station-maintainer", "fleet-operator", "discord-bootstrap"])
def test_real_instance_compiler_maps_entire_team_and_structured_routing(tmp_path, package):
    repo = Path(__file__).resolve().parents[2]
    workspace = tmp_path.resolve() / "workspace"
    output = tmp_path.resolve() / "compiled"
    manifest = compile_os_to_hermes(repo / "os" / package, output, workspace_root=workspace,
        zone_id="lab", instance_id="alpha", allowed_project_ids=("one",))
    mapping = manifest["role_profile_map"]
    assert manifest["schema_version"] == 3 and "project_root" not in manifest
    assert set(manifest["profiles"]) == set(mapping.values())
    for profile in manifest["profiles"]:
        root = output / "profiles" / profile
        config = yaml.safe_load((root / "config.yaml").read_text())
        assert config["profile"]["id"] == profile
        assert config["terminal"] == {**config["terminal"], "cwd": str(workspace), "home_mode": "profile"}
        assert config["stt"]["provider"] == "openai"
        assert config["stt"]["openai"]["model"] == "gpt-transcribe"
        assert config["tts"]["openai"]["model"] == "gpt-4o-mini-tts"
        assert config["stt"]["providers"]["parakeet"]["model"] == "parakeet-tdt-0.6b-v3"
        binding = json.loads((root / "INSTANCE.json").read_text())
        assert binding["role_profile_map"] == mapping and binding["project_scope"] == "DECLARED_NOT_UNIX_ENFORCED"
        commands = yaml.safe_load((root / "COMMANDS.yaml").read_text())
        if "bot" in commands:
            assert commands["bot"]["nano_director"] == manifest["nano_director"]
        soul = (root / "SOUL.md").read_text()
        assert all(f"`{native}`" in soul for native in mapping.values())
        assert all(f"`{role}`" not in soul for role in mapping)
        if package == "devops":
            team = json.loads((root / "STRIX_TEAM.json").read_text())
            assert team["public_director"] == manifest["nano_director"]


def test_instance_gateway_uses_canonical_home_and_explicit_native_profile(runtime):
    record = runtime.install()
    argv = build_gateway_argv(runtime.zone, "install", runtime_uid=os.getuid(),
        hermes_binary=Path("/fake/hermes"), director_profile=record["nano_director"], instance_id="alpha")
    assert f"HERMES_HOME={record['hermes_home']}" in argv
    assert f"HOME={Path(runtime.zone['state_root']) / 'home'}" in argv
    assert argv[-6:] == ["--profile", record["nano_director"], "gateway", "install",
                         "--no-start-now", "--start-on-login"]


def test_instance_voice_defaults_preserve_explicit_source_overrides():
    from agentik_station.os_runtime import _merge_defaults
    defaults = {"stt": {"provider": "openai", "openai": {"model": "gpt-transcribe"}}, "voice": {"auto_tts": True}}
    config = {"stt": {"provider": "parakeet"}, "profile": {"id": "selected"}}
    merged = _merge_defaults(defaults, config)
    assert merged["stt"] == {"provider": "parakeet", "openai": {"model": "gpt-transcribe"}}
    assert merged["voice"]["auto_tts"] is True and merged["profile"]["id"] == "selected"
    assert defaults["stt"]["provider"] == "openai"


def test_instance_voice_defaults_reject_symlink_parent(tmp_path):
    from agentik_station.os_runtime import _instance_voice_defaults
    repo = tmp_path.resolve()
    (repo / "real/hermes").mkdir(parents=True)
    (repo / "real/hermes/voice.default.yaml").write_text("voice: {}\nstt: {}\ntts: {}\n")
    (repo / "config").symlink_to(repo / "real", target_is_directory=True)
    with pytest.raises(SecurityError):
        _instance_voice_defaults(repo / "os/devops")


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "oversized", "duplicate"])
def test_instance_voice_defaults_reject_unsafe_leaf(tmp_path, kind):
    from agentik_station.os_runtime import _instance_voice_defaults
    repo = tmp_path.resolve()
    path = repo / "config/hermes/voice.default.yaml"
    path.parent.mkdir(parents=True)
    text = "voice: {}\nstt: {}\ntts: {}\n"
    if kind == "symlink":
        other = repo / "other.yaml"
        other.write_text(text)
        path.symlink_to(other)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_text("x" * 65537 if kind == "oversized" else text + ("voice: {}\n" if kind == "duplicate" else ""))
        if kind == "hardlink":
            os.link(path, repo / "other.yaml")
    with pytest.raises((SecurityError, ValidationError, OSError)):
        _instance_voice_defaults(repo / "os/devops")


@pytest.mark.parametrize("instance,profile", [("../escape", "director"), ("alpha", None), ("alpha", "default")])
def test_instance_gateway_rejects_ambiguous_routing(runtime, instance, profile):
    with pytest.raises(ValidationError):
        build_gateway_argv(runtime.zone, "start", runtime_uid=os.getuid(), hermes_binary=Path("/fake/hermes"),
                           instance_id=instance, director_profile=profile)


def test_registered_client_two_real_devops_instances_to_onboarding_and_gateway(runtime, monkeypatch):
    from agentik_station.organizations import register_organization
    from agentik_station.onboarding import build_onboarding_report
    from test_organizations import write_zone

    paths = runtime.paths
    zone, _ = write_zone(paths)
    runtime.zone = zone
    for path in (Path(zone["human_root"]) / "os", Path(zone["state_root"]) / "home", Path(zone["hermes_home"])):
        path.mkdir(parents=True, exist_ok=True, mode=0o750)
    monkeypatch.setattr(lifecycle.pwd, "getpwnam", lambda name: SimpleNamespace(
        pw_dir=str(Path(zone["state_root"]) / "home"), pw_uid=os.getuid(), pw_gid=os.getgid()))
    (paths.config / "station.json").write_text(json.dumps({"schema_version": 1, "host_id": "host-one"}))
    paths.observed.mkdir(parents=True, exist_ok=True, mode=0o750)
    (paths.observed / "host.json").write_text(json.dumps({"schema_version": 1, "host_id": "host-one", "state": "READY_FOR_SETUP"}))
    register_organization(paths, organization_id="acme", zone_ids=[zone["id"]])
    monkeypatch.setattr(instances, "compile_os_to_hermes", compile_os_to_hermes)
    repo = Path(__file__).resolve().parents[2]
    records = []
    for instance_id in ("alpha", "beta"):
        record = instances.install_os_instance(repo / "os/devops", paths=paths, zone=zone,
            instance_id=instance_id, organization_id="acme", os_id="devops-os", os_version="11.12",
            hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
        assert record["state"] == "CONFIGURED" and record["allowed_project_ids"] == []
        record = instances.verify_os_instance(paths, zone=zone, instance_id=instance_id,
            hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
        assert record["state"] == "VERIFIED"
        before = len(runtime.calls)
        report = build_onboarding_report(paths, repo, zone_id=zone["id"], organization_id="acme", instance_id=instance_id)
        assert len(runtime.calls) == before and report["operational"] is False
        gates = {gate["id"]: gate for gate in report["gates"]}
        assert gates["os"]["state"] == "LOCAL_VERIFIED"
        assert gates["os_verification"]["state"] == "LOCAL_VERIFIED"
        assert not gates["accounts"]["satisfied"] and not gates["gateway"]["satisfied"]
        argv = build_gateway_argv(zone, "install", runtime_uid=os.getuid(), hermes_binary=Path("/fake/hermes"),
            director_profile=record["nano_director"], instance_id=instance_id)
        assert f"HERMES_HOME={record['hermes_home']}" in argv
        assert argv[-6:] == ["--profile", record["nano_director"], "gateway", "install",
                             "--no-start-now", "--start-on-login"]
        records.append(record)
    assert not set(records[0]["expected_profiles"]) & set(records[1]["expected_profiles"])
    assert gateway_service_name(records[0]["nano_director"]) != gateway_service_name(records[1]["nano_director"])
    assert records[0]["hermes_home"] != records[1]["hermes_home"]
