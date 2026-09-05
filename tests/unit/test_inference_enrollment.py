"""Model enrollment policy uses trusted local files and fake native execution.

These tests never contact a model, copy source credentials, or start a service.
Native Zone execution itself is covered by the existing runtime/voice tests.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import inference
from agentik_station.errors import SecurityError, ValidationError
from agentik_station.paths import LayoutPaths


DIGEST = hashlib.sha256(b"synthetic-zone-capability").hexdigest()


@pytest.fixture
def enrollment(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve())
    root = paths.software / "inference"
    (root / "bindings").mkdir(parents=True, mode=0o755)
    for path in (paths.bin, paths.systemd):
        path.mkdir(parents=True, exist_ok=True)
    (paths.bin / "station-inference-token").write_text("#!/usr/bin/python3\n# Synthetic helper; never executed.\n")
    (paths.bin / "station-inference-token").chmod(0o755)
    zone = {"id": "moonbase-dev", "unix_user": "z-moonbase-dev",
            "organization": "moonbase", "environment": "development"}
    context = {"uid": 2101, "gid": 2101, "home": tmp_path / "zone-home"}
    records = {name: {"instance_id": name, "organization_id": "moonbase",
                     "role_profile_map": {"director": name + "-director", "worker": name + "-worker"},
                     "nano_director": name + "-director"} for name in ("alpha", "beta")}
    profiles = {profile: {"model": {}, "plugins": {"enabled": ["station-web"]},
                          "memory": {"sentinel": "PRIVATE-UNRELATED-STATE"}}
                for record in records.values() for profile in record["role_profile_map"].values()}
    state = SimpleNamespace(paths=paths, root=root, zone=zone, context=context, records=records,
                            profiles=profiles, calls=[], probes=[], digest=DIGEST,
                            fail_write=None, skip_write=None, effective={}, source_calls=[], runtime_checks=[])
    state.config_path = root / "config.json"
    state.binding_path = root / "bindings/moonbase-dev.json"
    state.base_config = {"schema_version": 1, "port": inference.PORT,
                         "source": copy.deepcopy(inference.SOURCE), "grants": []}

    def write(path, value, mode=0o600):
        path.write_text(json.dumps(value))
        path.chmod(mode)
    state.write = write
    state.read = lambda path: json.loads(path.read_text())
    write(state.config_path, state.base_config, 0o640)
    monkeypatch.setattr(inference.lifecycle, "_context", lambda paths, zone: context)

    def record(paths, *, zone, instance_id, require_configured=False):
        if instance_id not in records:
            raise ValidationError("Unknown installed instance")
        return copy.deepcopy(records[instance_id])
    monkeypatch.setattr(inference.os_instances, "load_os_instance_record", record)

    def scope(paths, zone, instance, role):
        selected = records[instance]
        if role not in selected["role_profile_map"]:
            raise ValidationError("Unknown role")
        profile = selected["role_profile_map"][role]
        return selected, context, profile, tmp_path / "profiles" / profile, copy.deepcopy(profiles[profile])
    monkeypatch.setattr(inference.voice, "_scope", scope)
    monkeypatch.setattr(inference, "build_gateway_argv", lambda zone, action, **kwargs:
                        ["fake-hermes", kwargs["director_profile"], action])
    monkeypatch.setattr(inference.voice, "_effective_profile", lambda prefix, path:
                        state.probes.append(("path", str(path))))

    def effective(prefix, key, default=None):
        state.probes.append((prefix[1], key))
        if key in state.effective:
            return state.effective[key]
        value = profiles[prefix[1]]
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return copy.deepcopy(value)
    monkeypatch.setattr(inference.voice, "_effective_value", effective)

    def native(argv, *, timeout=60):
        if argv[0] == "/usr/sbin/runuser" and str(argv[-1]).endswith("profile_check.py"):
            state.runtime_checks.append(list(argv))
            assert "HOME=" + str(context["home"]) in argv
            assert "-I" in argv and "-B" in argv
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "state": "NATIVE_ROUTE_VERIFIED", "model": inference.MODEL,
                "provider": inference.PROVIDER, "live_inference_tested": False}).encode(), stderr=b"")
        state.calls.append(list(argv))
        if argv[0] == "/usr/sbin/runuser":
            assert argv[:6] == ["/usr/sbin/runuser", "--user", zone["unix_user"], "--", "/usr/bin/env", "-i"]
            assert argv[-1] in ("--create", "--digest")
            return SimpleNamespace(returncode=0, stdout=json.dumps({"token_sha256": state.digest}).encode(), stderr=b"")
        if argv[0] == "/usr/bin/systemctl":
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if argv[0] == "/usr/bin/python3":
            assert argv[1:3] == ["-I", "-B"] and str(argv[3]).endswith("preflight.py")
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        assert argv[:1] == ["fake-hermes"] and argv[2:4] == ["config", "set"]
        key, raw = argv[4:]
        if key == state.fail_write:
            raise ValidationError("Native write failed")
        if key != state.skip_write:
            value = profiles[argv[1]]
            parts = key.split(".")
            for part in parts[:-1]:
                value = value.setdefault(part, {})
            value[parts[-1]] = json.loads(raw) if raw.startswith("{") else raw
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(inference, "_native", native)
    state.grant = lambda **kwargs: inference.grant(paths, zone, kwargs.pop("instances", ["alpha"]), **kwargs)
    state.plan = lambda role=None: inference.inheritance_plan(paths, zone, records["alpha"], role)
    state.enroll = lambda **kwargs: inference.enroll_profile(paths, zone, records["alpha"], **kwargs)
    return state


def test_grant_plan_has_no_token_creation_or_policy_mutation(enrollment):
    before = enrollment.config_path.read_bytes()
    result = enrollment.grant(plan=True)
    assert result["state"] == "PREPARED" and result["operational"] is False
    assert not enrollment.calls and not enrollment.binding_path.exists()
    assert enrollment.config_path.read_bytes() == before


def test_grant_publishes_binding_before_network_authority(enrollment, monkeypatch):
    writes = []
    original = inference._save
    def save(paths, path, value):
        writes.append(path.name)
        return original(paths, path, value)
    monkeypatch.setattr(inference, "_save", save)
    result = enrollment.grant()
    assert result["state"] == "GRANTED_NOT_MODEL_ACCEPTED"
    assert writes == ["moonbase-dev.json", "config.json"]
    assert enrollment.read(enrollment.config_path)["grants"] == [
        {"zone_id": "moonbase-dev", "uid": 2101, "token_sha256": DIGEST}]
    assert enrollment.read(enrollment.binding_path)["instances"] == ["alpha"]
    assert enrollment.calls[0][-1] == "--create"
    assert "PRIVATE" not in json.dumps(result)


def test_exact_grant_retry_reuses_capability_and_does_not_widen_scope(enrollment):
    enrollment.grant()
    before = enrollment.read(enrollment.config_path)
    enrollment.grant()
    assert enrollment.read(enrollment.config_path) == before
    assert [call[-1] for call in enrollment.calls] == ["--create", "--digest"]
    assert enrollment.read(enrollment.binding_path)["instances"] == ["alpha"]


def test_changed_capability_cannot_be_silently_regranted(enrollment):
    enrollment.grant()
    original = enrollment.config_path.read_bytes()
    enrollment.digest = "b" * 64
    with pytest.raises(SecurityError, match="token changed"):
        enrollment.grant()
    assert enrollment.config_path.read_bytes() == original


def test_binding_failure_never_publishes_network_grant(enrollment, monkeypatch):
    original = inference._save
    def save(paths, path, value):
        if path == enrollment.binding_path:
            raise OSError("synthetic publication failure")
        return original(paths, path, value)
    monkeypatch.setattr(inference, "_save", save)
    with pytest.raises(OSError):
        enrollment.grant()
    assert enrollment.read(enrollment.config_path)["grants"] == []


def test_revoke_disables_network_before_marking_binding(enrollment, monkeypatch):
    enrollment.grant()
    writes = []
    original = inference._save
    def save(paths, path, value):
        writes.append(path.name)
        return original(paths, path, value)
    monkeypatch.setattr(inference, "_save", save)
    result = enrollment.grant(instances=[], revoke=True)
    assert result["state"] == "REVOKED" and result["token_retained"] is True
    assert writes == ["config.json", "moonbase-dev.json"]
    assert enrollment.read(enrollment.config_path)["grants"] == []
    assert enrollment.read(enrollment.binding_path)["revoked"] is True
    assert len(enrollment.calls) == 1


@pytest.mark.parametrize("damage", ["missing", "malformed", "wrong-digest", "already-revoked"])
def test_revoke_is_not_blocked_by_broken_enrollment_metadata(enrollment, damage):
    enrollment.grant()
    if damage == "missing":
        enrollment.binding_path.unlink()
    elif damage == "malformed":
        enrollment.write(enrollment.binding_path, {"broken": True})
    else:
        value = enrollment.read(enrollment.binding_path)
        value["token_sha256" if damage == "wrong-digest" else "revoked"] = "c" * 64 if damage == "wrong-digest" else True
        enrollment.write(enrollment.binding_path, value)
    result = enrollment.grant(instances=[], revoke=True)
    assert result["state"] == "REVOKED"
    assert enrollment.read(enrollment.config_path)["grants"] == []


def test_grant_detects_authority_change_while_waiting_for_lock(enrollment, monkeypatch):
    @contextmanager
    def raced_lock(*args):
        enrollment.write(enrollment.config_path, {**enrollment.base_config, "grants": [
            {"zone_id": "another-dev", "uid": 2102, "token_sha256": "d" * 64}]}, 0o640)
        yield
    monkeypatch.setattr(inference, "install_lock", raced_lock)
    with pytest.raises(SecurityError, match="changed"):
        enrollment.grant()
    assert not enrollment.calls and not enrollment.binding_path.exists()


@pytest.mark.parametrize("instances", [[], ["../alpha"], ["unknown"], [None], ["ALPHA"]])
def test_invalid_or_uninstalled_instances_are_not_granted(enrollment, instances):
    with pytest.raises((SecurityError, ValidationError)):
        enrollment.grant(instances=instances)
    assert not enrollment.calls
    assert enrollment.read(enrollment.config_path)["grants"] == []


def test_ungranted_instance_does_not_depend_on_broker_or_source(enrollment):
    enrollment.write(enrollment.config_path, {"broken": True})
    assert enrollment.plan() is None
    assert enrollment.enroll() is None
    assert not enrollment.calls and not enrollment.probes


@pytest.mark.parametrize("change", ["revoked", "other-instance"])
def test_inactive_or_unselected_binding_does_not_enroll(enrollment, change):
    enrollment.grant()
    binding = enrollment.read(enrollment.binding_path)
    binding["revoked" if change == "revoked" else "instances"] = True if change == "revoked" else ["beta"]
    enrollment.write(enrollment.binding_path, binding)
    enrollment.calls.clear()
    assert enrollment.plan() is None and enrollment.enroll() is None
    assert not enrollment.calls


@pytest.mark.parametrize("model", ["explicit-model", {"default": "explicit-model"}, {"provider": "anthropic"},
    {"provider": inference.PROVIDER, "default": "explicit-model"}, *[
        {key: "PRIVATE-EXPLICIT-OVERRIDE"} for key in
        ("base_url", "api_key", "api_key_env", "key_cmd", "transport", "api_mode")]])
def test_explicit_model_and_endpoint_preferences_are_preserved_without_broker_dependency(enrollment, model):
    enrollment.grant()
    enrollment.profiles["alpha-director"]["model"] = copy.deepcopy(model)
    enrollment.write(enrollment.config_path, {"broken": True})
    enrollment.calls.clear()
    before = copy.deepcopy(enrollment.profiles)
    result = enrollment.enroll()
    assert result["state"] == "EXPLICIT_MODEL_PRESERVED" and result["mutates"] is False
    assert enrollment.profiles == before and not enrollment.calls
    assert "PRIVATE" not in json.dumps(result)


def test_enrollment_plan_is_pure_and_selects_only_namespaced_director(enrollment):
    enrollment.grant()
    enrollment.calls.clear()
    before = copy.deepcopy(enrollment.profiles)
    result = enrollment.enroll(plan=True)
    assert result["state"] == "INHERITANCE_PREPARED" and result["profile"] == "alpha-director"
    assert result["provider"] == inference.PROVIDER and result["model"] == inference.MODEL
    assert not enrollment.calls and not enrollment.probes
    assert enrollment.profiles == before
    assert "PRIVATE" not in json.dumps(result)


def test_native_enrollment_is_idempotent_and_preserves_other_state(enrollment):
    enrollment.grant()
    enrollment.calls.clear()
    before = copy.deepcopy(enrollment.profiles)
    result = enrollment.enroll()
    assert result["state"] == "INHERITED" and result["verification_required"] is True
    assert result["operational"] is False
    assert [call[4] for call in enrollment.calls] == ["providers.station-inference", "model.provider", "model.default"]
    current = enrollment.profiles["alpha-director"]
    assert current["model"] == {"provider": inference.PROVIDER, "default": inference.MODEL}
    assert current["memory"] == before["alpha-director"]["memory"]
    assert current["plugins"] == before["alpha-director"]["plugins"]
    assert all(enrollment.profiles[key] == value for key, value in before.items() if key != "alpha-director")
    assert "PRIVATE" not in json.dumps(result)
    count = len(enrollment.calls)
    assert enrollment.enroll()["state"] == "INHERITED"
    assert len(enrollment.calls) == count


def test_worker_enrollment_selects_worker_not_shared_director(enrollment):
    enrollment.grant()
    enrollment.calls.clear()
    result = enrollment.enroll(role="worker")
    assert result["profile"] == "alpha-worker"
    assert all(call[1] == "alpha-worker" for call in enrollment.calls)
    assert enrollment.profiles["alpha-director"]["model"] == {}


def test_conflicting_named_provider_is_not_overwritten(enrollment):
    enrollment.grant()
    enrollment.profiles["alpha-director"]["providers"] = {"station-inference": {"base_url": "https://private.invalid"}}
    enrollment.calls.clear()
    with pytest.raises(ValidationError, match="differs"):
        enrollment.enroll()
    assert not enrollment.calls


@pytest.mark.parametrize("override", [{"default": "managed-model"}, {"provider": "managed-provider"},
                                     {"base_url": "https://managed.invalid"}, {"api_key": "PRIVATE-KEY"}])
def test_effective_model_overlay_is_preserved_before_native_writes(enrollment, override):
    enrollment.grant()
    enrollment.calls.clear()
    enrollment.effective["model"] = override
    with pytest.raises(SecurityError, match="Effective target model"):
        enrollment.enroll()
    assert not enrollment.calls


@pytest.mark.parametrize("key", ["providers.station-inference", "model.provider", "model.default"])
def test_partial_native_failure_stops_without_false_acceptance(enrollment, key):
    enrollment.grant()
    enrollment.calls.clear()
    enrollment.fail_write = key
    with pytest.raises(ValidationError, match="Native write failed"):
        enrollment.enroll()
    assert enrollment.calls[-1][4] == key


def test_zero_exit_without_native_readback_is_not_inherited(enrollment):
    enrollment.grant()
    enrollment.skip_write = "model.default"
    with pytest.raises(ValidationError, match="readback differs"):
        enrollment.enroll()


@pytest.mark.parametrize("damage", ["symlink", "hardlink", "writable", "duplicate-key", "oversize"])
def test_policy_authority_uses_bounded_nofollow_reader(enrollment, damage):
    path = enrollment.config_path
    if damage in ("symlink", "hardlink"):
        original = path.with_name("saved.json")
        path.rename(original)
        path.symlink_to(original) if damage == "symlink" else os.link(original, path)
    elif damage == "writable":
        path.chmod(0o666)
    elif damage == "duplicate-key":
        path.write_text('{"schema_version":1,"schema_version":1}')
    else:
        path.write_bytes(b"x" * 65537)
    with pytest.raises((SecurityError, ValidationError, OSError)):
        enrollment.grant(plan=True)
    assert not enrollment.calls


@pytest.mark.parametrize("parser_prefix", [["os", "instance", "setup"], ["platform", "configure"]])
def test_setup_exposes_explicit_provider_override(parser_prefix):
    from agentik_station.cli import build_parser
    args = build_parser().parse_args([*parser_prefix, "--zone", "moonbase-dev", "--instance", "alpha", "--choose-provider", "--plan"])
    assert args.choose_provider is True and args.plan is True


@pytest.fixture
def service(enrollment, monkeypatch):
    state = enrollment
    def make_release(version):
        release = state.paths.releases / version
        scripts = release / "runtime/inference"
        scripts.mkdir(parents=True)
        (release / "VERSION").write_text(version + "\n")
        for name in ("broker.py", "token.py", "preflight.py", "profile_check.py"):
            (scripts / name).write_text("# Synthetic immutable source " + version + " " + name + "\n")
        return release
    state.make_release = make_release
    state.release = make_release("11.36")
    (state.paths.bin / "station-inference-token").write_bytes((state.release / "runtime/inference/token.py").read_bytes())
    monkeypatch.setattr(inference.pwd, "getpwnam", lambda name:
                        SimpleNamespace(pw_uid=2110, pw_gid=2110, pw_dir="/home/agk-station"))
    state.enable = lambda **kwargs: inference.enable(state.release, state.paths, **kwargs)
    return state


def test_enable_plan_never_starts_service_or_reads_source_auth(service):
    result = service.enable(plan=True)
    assert result["state"] == "PREPARED" and result["provider_authenticated"] is False
    assert not service.calls
    assert not (service.paths.systemd / inference.UNIT).exists()


def test_enable_idempotence_preserves_grants_and_private_metadata(service):
    service.grant()
    before = service.config_path.read_bytes()
    service.calls.clear()
    result = service.enable()
    assert result["state"] == "SERVICE_ACTIVE_NO_MODEL_ACCEPTANCE"
    assert result["operational"] is False and result["zone_grants"] == 1
    assert service.config_path.read_bytes() == before
    assert service.root.stat().st_mode & 0o777 == 0o750
    assert service.binding_path.parent.stat().st_mode & 0o777 == 0o700
    assert service.config_path.stat().st_mode & 0o777 == 0o640
    assert service.binding_path.stat().st_mode & 0o777 == 0o600
    unit = (service.paths.systemd / inference.UNIT).read_text()
    assert "User=agk-station" in unit and "NoNewPrivileges=true" in unit
    assert "-I -B " in unit and "StandardOutput=null" in unit
    service.enable()
    assert service.config_path.read_bytes() == before
    assert not any(call[1] == "restart" for call in service.calls if call[0] == "/usr/bin/systemctl")


def test_enable_rechecks_stale_missing_config_before_creating_any_service(service, monkeypatch):
    service.config_path.unlink()
    @contextmanager
    def race(*args):
        service.write(service.config_path, {**service.base_config, "grants": [
            {"zone_id": "another-dev", "uid": 2102, "token_sha256": "d" * 64}]}, 0o640)
        yield
    monkeypatch.setattr(inference, "install_lock", race)
    with pytest.raises(SecurityError, match="configuration changed"):
        service.enable()
    assert service.read(service.config_path)["grants"][0]["zone_id"] == "another-dev"
    assert not service.calls and not (service.paths.systemd / inference.UNIT).exists()


def test_enable_rechecks_existing_software_after_waiting_for_lock(service, monkeypatch):
    @contextmanager
    def race(*args):
        (service.paths.bin / "station-inference-token").write_text("# Unreviewed competing software\n")
        yield
    monkeypatch.setattr(inference, "install_lock", race)
    with pytest.raises(SecurityError, match="software changed"):
        service.enable()
    assert not service.calls


def test_enable_updates_only_known_previous_immutable_service(service):
    previous = service.make_release("11.35")
    unit = service.paths.systemd / inference.UNIT
    unit.write_text(inference._unit(previous))
    unit.chmod(0o644)
    (service.paths.bin / "station-inference-token").write_bytes((previous / "runtime/inference/token.py").read_bytes())
    assert service.enable()["state"] == "SERVICE_ACTIVE_NO_MODEL_ACCEPTANCE"
    assert unit.read_text() == inference._unit(service.release)
    assert ["/usr/bin/systemctl", "restart", inference.UNIT] in service.calls


@pytest.mark.parametrize("tamper", ["unit", "helper"])
def test_enable_refuses_unreviewed_existing_software(service, tamper):
    if tamper == "unit":
        path = service.paths.systemd / inference.UNIT
        path.write_text(inference._unit(service.release) + "Environment=UNREVIEWED=yes\n")
        path.chmod(0o644)
    else:
        (service.paths.bin / "station-inference-token").write_text("# Unreviewed helper\n")
    with pytest.raises(SecurityError):
        service.enable()
    assert not service.calls


@pytest.mark.parametrize("key,value", [("schema_version", True), ("schema_version", 1.0),
                                      ("port", float(inference.PORT)), ("grants", "invalid")])
def test_authority_schema_agrees_with_broker_strict_types(enrollment, key, value):
    enrollment.write(enrollment.config_path, {**enrollment.base_config, key: value}, 0o640)
    with pytest.raises(ValidationError):
        enrollment.grant(plan=True)


@pytest.mark.parametrize("key,value", [("schema_version", True), ("schema_version", 1.0),
    ("uid", True), ("uid", 2101.0), ("instances", [["alpha"]]), ("instances", ["alpha", "alpha"]),
    ("organization_id", "other-client"), ("environment", "production")])
def test_binding_schema_and_ownership_are_exact(enrollment, key, value):
    enrollment.grant()
    binding = enrollment.read(enrollment.binding_path)
    binding[key] = value
    enrollment.write(enrollment.binding_path, binding)
    with pytest.raises(SecurityError):
        enrollment.plan()


@pytest.mark.parametrize("damage", ["uid-range", "duplicate-digest"])
def test_grant_authority_limits_agree_with_runtime_broker(enrollment, damage):
    grants = [{"zone_id": "one-dev", "uid": 2201, "token_sha256": "a" * 64}]
    if damage == "uid-range":
        grants[0]["uid"] = 2 ** 31
    else:
        grants.append({"zone_id": "two-dev", "uid": 2202, "token_sha256": "a" * 64})
    enrollment.write(enrollment.config_path, {**enrollment.base_config, "grants": grants}, 0o640)
    with pytest.raises(ValidationError):
        enrollment.grant(plan=True)


def test_full_grant_capacity_never_publishes_an_invalid_257th_entry(enrollment):
    grants = [{"zone_id": "zone-" + str(index), "uid": 10000 + index,
               "token_sha256": hashlib.sha256(str(index).encode()).hexdigest()} for index in range(256)]
    enrollment.write(enrollment.config_path, {**enrollment.base_config, "grants": grants}, 0o640)
    before = enrollment.config_path.read_bytes()
    with pytest.raises((SecurityError, ValidationError)):
        enrollment.grant()
    assert enrollment.config_path.read_bytes() == before
    assert not enrollment.binding_path.exists()


@pytest.mark.parametrize("collision", ["uid", "token_sha256"])
def test_new_grant_cannot_disable_other_zones_by_duplicate_identity(enrollment, collision):
    other = {"zone_id": "another-dev", "uid": 2201, "token_sha256": "e" * 64}
    other[collision] = 2101 if collision == "uid" else DIGEST
    enrollment.write(enrollment.config_path, {**enrollment.base_config, "grants": [other]}, 0o640)
    before = enrollment.config_path.read_bytes()
    with pytest.raises((SecurityError, ValidationError)):
        enrollment.grant()
    assert enrollment.config_path.read_bytes() == before
    assert not enrollment.binding_path.exists()
