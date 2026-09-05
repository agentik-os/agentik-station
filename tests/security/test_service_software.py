"""Synthetic OCI probes only: no daemon, downloads, containers, or accounts."""
import hashlib
import json
import os
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from agentik_station import service_software as software
from agentik_station.errors import ReconcileError, SecurityError, ValidationError

ROOT = Path(__file__).resolve().parents[2]


class Podman:
    def __init__(self):
        self.calls = []
        self.images = {}
        self.fail_pull = None
        self.transform = lambda value: value

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        command, reference = argv[6], argv[-1]
        if command == "pull":
            if self.fail_pull == reference:
                return subprocess.CompletedProcess(argv, 1, "", "synthetic failure")
            self.images[reference] = {"Id": "sha256:" + hashlib.sha256(reference.encode()).hexdigest(),
                                      "Digest": reference.split("@")[1], "RepoDigests": [reference],
                                      "Os": "linux", "Architecture": "amd64"}
            return subprocess.CompletedProcess(argv, 0, "synthetic pull", "")
        assert argv[6:9] == ["image", "inspect", "--"]
        if reference not in self.images:
            return subprocess.CompletedProcess(argv, 1, "", "missing image")
        value = self.transform(dict(self.images[reference]))
        return subprocess.CompletedProcess(argv, 0, json.dumps([value]), "")


@pytest.fixture
def fixture(tmp_path):
    repo = tmp_path / "repo"
    directory = repo / "resources/services"
    directory.mkdir(parents=True)
    manifest = {"schema_version": 1, "id": "fixture", "source": {
        "repository": "https://github.com/example/service", "commit": "a" * 40},
        "platforms": ["linux/amd64"], "images": [
            {"name": "server", "reference": "ghcr.io/example/server@sha256:" + "1" * 64,
             "version": "1.2.3", "role": "api-and-worker"},
            {"name": "database", "reference": "docker.io/library/postgres@sha256:" + "2" * 64,
             "version": "17", "role": "database"}],
        "configuration_required": True, "limitations": ["No service activation or account enrollment."]}
    path = directory / "fixture.json"
    path.write_text(json.dumps(manifest))
    return repo, tmp_path / "evidence", manifest, path, Podman()


def install(fixture, **kwargs):
    repo, evidence, _, _, podman = fixture
    return software.install_bundle(repo, "fixture", evidence_root=evidence, run=podman, **kwargs)


def check(fixture, **kwargs):
    repo, evidence, _, _, podman = fixture
    return software.check_bundle(repo, "fixture", evidence_root=evidence, run=podman, **kwargs)


def receipt(fixture):
    return fixture[1] / "fixture/receipt.json"


def test_install_and_check_bind_all_images_and_keep_activation_false(fixture, monkeypatch):
    monkeypatch.setenv("HOME", "/real-account")
    monkeypatch.setenv("REGISTRY_AUTH_FILE", "/real-account/auth.json")
    monkeypatch.setenv("CONTAINER_HOST", "ssh://production.example")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    result = install(fixture)
    assert result["software_installed"] is True
    assert result["configuration_required"] is True
    assert result["operational"] is False
    assert result["state"] == "SOFTWARE_INSTALLED"
    assert len(result["images"]) == 2
    assert check(fixture)["software_installed"] is True
    assert receipt(fixture).stat().st_mode & 0o777 == 0o600
    for path in (fixture[1], fixture[1] / "fixture", fixture[1] / "fixture/home"):
        assert path.stat().st_mode & 0o777 == 0o700
    assert "must-not-leak" not in receipt(fixture).read_text()
    for argv, options in fixture[4].calls:
        assert argv[:6] == ["/usr/bin/podman", "--remote=false", "--root", "/var/lib/containers/storage",
                            "--runroot", "/run/containers/storage"]
        assert argv[6] in {"pull", "image"}
        assert not {"run", "create", "start", "exec", "login", "compose", "build", "prune"} & set(argv)
        assert options["env"]["HOME"] == str(fixture[1] / "fixture/home")
        assert "must-not-leak" not in str(options)
        assert "CONTAINER_HOST" not in options["env"]
        assert options["stdin"] == subprocess.DEVNULL
        assert options["cwd"] == "/"
        if argv[6] == "pull":
            assert "--platform=linux/amd64" in argv and "--tls-verify=true" in argv


def test_idempotent_install_preserves_receipt_bytes(fixture):
    install(fixture)
    before = receipt(fixture).read_bytes()
    install(fixture)
    assert receipt(fixture).read_bytes() == before


@pytest.mark.parametrize("operation", [install, check])
def test_plan_never_executes_or_creates_evidence(fixture, operation, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Unexpected native execution"))
    result = operation(fixture, plan=True)
    assert result["software_installed"] is False and result["state"] == "PLANNED"
    assert not fixture[1].exists()
    assert fixture[4].calls == []


def test_check_missing_receipt_and_images_is_nonmutating(fixture):
    result = check(fixture)
    assert result["software_installed"] is False
    assert all(image["verified"] is False for image in result["images"])
    assert not fixture[1].exists()
    assert all(argv[6] == "image" for argv, _ in fixture[4].calls)


def test_existing_receipt_is_not_proof_when_an_image_is_removed(fixture):
    install(fixture)
    fixture[4].images.pop(fixture[2]["images"][1]["reference"])
    assert check(fixture)["software_installed"] is False


@pytest.mark.parametrize("reference", ["ghcr.io/example/server:latest", "ghcr.io/example/server@sha256:1234",
                                      "--help", "example/server@sha256:" + "a" * 64,
                                      "https://ghcr.io/example/server@sha256:" + "a" * 64])
def test_bad_reference_refused_before_execution(fixture, reference):
    fixture[2]["images"][0]["reference"] = reference
    fixture[3].write_text(json.dumps(fixture[2]))
    with pytest.raises(ValidationError):
        install(fixture)
    assert not fixture[4].calls and not fixture[1].exists()


@pytest.mark.parametrize("change", [{"images": []}, {"schema_version": True}, {"operational": True},
                                   {"configuration_required": False}, {"platforms": ["linux/arm64"]}])
def test_manifest_schema_is_fail_closed(fixture, change):
    fixture[2].update(change)
    fixture[3].write_text(json.dumps(fixture[2]))
    with pytest.raises(ValidationError):
        install(fixture)
    assert not fixture[4].calls


def test_duplicate_json_key_refused(fixture):
    fixture[3].write_text(fixture[3].read_text().replace('"id": "fixture"', '"id": "fixture", "id": "fixture"'))
    with pytest.raises(ValidationError):
        install(fixture)
    assert not fixture[4].calls


def test_missing_manifest_has_actionable_failure_without_execution(fixture):
    fixture[3].unlink()
    with pytest.raises(ValidationError, match="manifest is missing"):
        install(fixture)
    assert not fixture[4].calls


@pytest.mark.parametrize("change", [{"Digest": "sha256:" + "0" * 64}, {"RepoDigests": []},
                                   {"RepoDigests": "ghcr.io/example/server@sha256:" + "1" * 64},
                                   {"Os": "windows"}, {"Architecture": "arm64"}, {"Id": "not-a-digest"}])
def test_native_digest_and_platform_failures_never_issue_receipt(fixture, change):
    fixture[4].transform = lambda value: {**value, **change}
    with pytest.raises(ReconcileError):
        install(fixture)
    assert not receipt(fixture).exists()


def test_partial_pull_failure_never_issues_complete_receipt(fixture):
    fixture[4].fail_pull = fixture[2]["images"][1]["reference"]
    with pytest.raises(ReconcileError):
        install(fixture)
    assert len(fixture[4].images) == 1
    assert not receipt(fixture).exists()


def test_timeout_never_issues_receipt(fixture):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("podman", 60)
    with pytest.raises(ReconcileError):
        software.install_bundle(fixture[0], "fixture", evidence_root=fixture[1], run=timeout)
    assert not receipt(fixture).exists()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory", "writable"])
def test_hostile_manifest_file_is_not_read_or_executed(fixture, tmp_path, kind):
    path = fixture[3]
    victim = tmp_path / "original.json"
    path.rename(victim)
    if kind == "symlink":
        path.symlink_to(victim)
    elif kind == "hardlink":
        os.link(victim, path)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    else:
        path.write_bytes(victim.read_bytes())
        path.chmod(0o666)
    with pytest.raises((SecurityError, OSError)):
        install(fixture)
    assert not fixture[4].calls


def test_symlink_manifest_parent_refused(fixture, tmp_path):
    parent = fixture[3].parent
    moved = tmp_path / "moved"
    parent.rename(moved)
    parent.symlink_to(moved, target_is_directory=True)
    with pytest.raises((SecurityError, OSError)):
        install(fixture)
    assert not fixture[4].calls


@pytest.mark.parametrize("kind", ["symlink", "file", "writable-directory"])
def test_evidence_root_not_adopted(fixture, tmp_path, kind):
    if kind == "symlink":
        fixture[1].symlink_to(tmp_path, target_is_directory=True)
    elif kind == "file":
        fixture[1].write_text("preserve")
    else:
        fixture[1].mkdir(mode=0o755)
    with pytest.raises((SecurityError, OSError)):
        install(fixture)
    assert not fixture[4].calls


def test_manifest_drift_refused_before_any_reinstall_pull(fixture):
    install(fixture)
    fixture[3].write_text(fixture[3].read_text() + "\n")
    fixture[4].calls.clear()
    with pytest.raises(SecurityError, match="drift"):
        install(fixture)
    assert not fixture[4].calls


@pytest.mark.parametrize("field,value", [("operational", True), ("manifest_sha256", "0" * 64),
                                       ("images", []), ("software_installed", 1), ("schema_version", True)])
def test_receipt_drift_refused_before_execution(fixture, field, value):
    install(fixture)
    data = json.loads(receipt(fixture).read_text())
    data[field] = value
    receipt(fixture).write_text(json.dumps(data))
    fixture[4].calls.clear()
    with pytest.raises(SecurityError):
        install(fixture)
    assert not fixture[4].calls


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "writable"])
def test_hostile_receipt_is_preserved_without_execution(fixture, tmp_path, kind):
    install(fixture)
    victim = tmp_path / "original-receipt"
    receipt(fixture).rename(victim)
    before = victim.read_bytes()
    if kind == "symlink":
        receipt(fixture).symlink_to(victim)
    elif kind == "hardlink":
        os.link(victim, receipt(fixture))
    elif kind == "fifo":
        os.mkfifo(receipt(fixture))
    else:
        receipt(fixture).write_bytes(before)
        receipt(fixture).chmod(0o666)
    fixture[4].calls.clear()
    with pytest.raises((SecurityError, OSError)):
        install(fixture)
    assert victim.read_bytes() == before and not fixture[4].calls


def test_wrong_manifest_owner_is_rejected(fixture):
    with pytest.raises(SecurityError):
        software._read(fixture[3], uid=os.geteuid() + 1)


def test_privileged_chain_refuses_user_writable_temporary_ancestors(tmp_path):
    with pytest.raises(SecurityError):
        software._chain(tmp_path, privileged=True)


@pytest.mark.parametrize("operation", [install, check])
def test_existing_registry_credentials_never_adopted(fixture, operation):
    install(fixture)
    auth = fixture[1] / "fixture/auth.json"
    private = '{"auths":{"registry.example":{"auth":"synthetic-private"}}}'
    auth.write_text(private)
    fixture[4].calls.clear()
    with pytest.raises(SecurityError):
        operation(fixture)
    assert auth.read_text() == private and not fixture[4].calls


def test_checker_rejects_symlink_home_before_podman(fixture, tmp_path):
    install(fixture)
    home = fixture[1] / "fixture/home"
    home.rename(tmp_path / "original-home")
    home.symlink_to(tmp_path, target_is_directory=True)
    fixture[4].calls.clear()
    with pytest.raises(SecurityError):
        check(fixture)
    assert not fixture[4].calls


@pytest.mark.parametrize("target", ["home/.docker", "home/config/containers", "certs/client.key"])
def test_fallback_accounts_and_client_certificates_are_never_adopted(fixture, target):
    install(fixture)
    path = fixture[1] / "fixture" / target
    path.write_text("synthetic-private-do-not-adopt")
    fixture[4].calls.clear()
    with pytest.raises(SecurityError):
        install(fixture)
    assert path.read_text() == "synthetic-private-do-not-adopt"
    assert not fixture[4].calls


def test_manifest_modified_during_pull_never_gets_receipt(fixture):
    original = fixture[4]
    def modified(argv, **kwargs):
        result = original(argv, **kwargs)
        if argv[6] == "pull":
            fixture[3].write_text(fixture[3].read_text() + "\n")
        return result
    with pytest.raises(SecurityError, match="changed"):
        software.install_bundle(fixture[0], "fixture", evidence_root=fixture[1], run=modified)
    assert not receipt(fixture).exists()


def test_injected_executor_cannot_forge_canonical_receipts(fixture):
    with pytest.raises(SecurityError):
        software.install_bundle(fixture[0], "fixture", run=fixture[4])
    assert not fixture[4].calls


def test_native_mutation_has_root_and_linux_gate(fixture, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 12345)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("No native execution"))
    with pytest.raises(SecurityError, match="root on Linux"):
        software.install_bundle(fixture[0], "fixture", evidence_root=fixture[1])
    assert not fixture[1].exists()


@pytest.mark.parametrize("command,capture", [(["pull", "--", "example"], False),
                                           (["image", "inspect", "--", "example"], True)])
def test_live_runner_uses_clean_env_and_bounded_group_cleanup(tmp_path, monkeypatch, command, capture):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    def bounded(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess("native command", 0, b"[]" if capture else None, b"")
    monkeypatch.setattr(software, "run_bounded_native", bounded)
    monkeypatch.setattr(software, "_trusted_executable", lambda *a, **k: Path("/usr/lib/cargo/bin/coreutils/env"))
    result = software._command(command, base=tmp_path, run=None, timeout=60)
    argv, options = calls[0]
    assert argv[:2] == ["/usr/lib/cargo/bin/coreutils/env", "-i"]
    assert not any("must-not-leak" in item for item in argv)
    assert f"HOME={tmp_path / 'home'}" in argv
    assert options == {"timeout": 60, "capture": capture}
    assert result.stdout == ("[]" if capture else None)


@pytest.fixture
def env_alias(tmp_path, monkeypatch):
    alias = tmp_path / "bin/env"
    target = tmp_path / "lib/coreutils/env"
    alias.parent.mkdir()
    target.parent.mkdir(parents=True)
    target.write_text("synthetic-not-executed")
    target.chmod(0o755)
    alias.symlink_to(target)
    monkeypatch.setattr(software, "ENV", alias)
    original_lstat = Path.lstat
    owners = {alias: 0, target: 0}
    def lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path in owners:
            return SimpleNamespace(st_mode=info.st_mode, st_uid=owners[path])
        return info
    monkeypatch.setattr(Path, "lstat", lstat)
    checked = []
    def chain(path, *, privileged):
        assert privileged is True
        checked.append(path)
        # Ownership is synthesized above; real directory modes/symlinks are not.
        software.SafeFS._assert_existing_absolute_chain(path)
        if path.stat().st_mode & 0o022:
            raise SecurityError("Synthetic directory is writable")
    monkeypatch.setattr(software, "_chain", chain)
    return alias, target, owners, checked


def test_only_trusted_env_alias_resolves_to_actual_executable(env_alias):
    alias, target, _, checked = env_alias
    assert software._trusted_executable(alias, env_alias=True) == target
    assert checked == [alias.parent, target.parent]


@pytest.mark.parametrize("unsafe", ["link-owner", "target-owner", "target-mode", "parent-mode", "podman-link", "nested-link"])
def test_env_alias_rejects_untrusted_or_indirect_targets(env_alias, tmp_path, unsafe):
    alias, target, owners, _ = env_alias
    if unsafe == "link-owner":
        owners[alias] = 12345
    elif unsafe == "target-owner":
        owners[target] = 12345
    elif unsafe == "target-mode":
        target.chmod(0o777)
    elif unsafe == "parent-mode":
        target.parent.chmod(0o777)
    elif unsafe == "nested-link":
        second = tmp_path / "another"
        second.write_text("not-executed")
        target.unlink()
        target.symlink_to(second)
    with pytest.raises(SecurityError):
        software._trusted_executable(alias, env_alias=unsafe != "podman-link")


def test_output_overflow_and_native_errors_are_redacted(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise software.subprocess.SubprocessError("PRIVATE_NATIVE_DIAGNOSTIC")
    monkeypatch.setattr(software, "run_bounded_native", fail)
    with pytest.raises(ReconcileError) as exc:
        software._command(["image", "inspect", "--", "example"], base=tmp_path, run=None, timeout=1)
    assert "PRIVATE_NATIVE_DIAGNOSTIC" not in str(exc.value)
    assert exc.value.__suppress_context__ is True


def test_captured_inspect_output_limit_is_fail_closed(fixture):
    fixture[4].transform = lambda value: {**value, "untrusted_label": "x" * 65536}
    with pytest.raises(ReconcileError):
        install(fixture)
    assert not receipt(fixture).exists()


def test_no_other_podman_operations_are_accepted(tmp_path):
    with pytest.raises(SecurityError):
        software._command(["run", "example"], base=tmp_path, run=Podman(), timeout=60)


@pytest.mark.parametrize("component", ["langfuse", "honcho", "hindsight", "chatbotx"])
def test_actual_manifests_load_in_nonexecuting_plan(component, tmp_path):
    result = software.install_bundle(ROOT, component, evidence_root=tmp_path / component, plan=True)
    assert result["configuration_required"] is True and result["operational"] is False
    assert result["images"] and result["software_installed"] is False
    assert not (tmp_path / component).exists()


def test_default_canonical_plan_is_portable_without_inspecting_host_evidence(monkeypatch):
    original = software._chain
    def chain(path, **kwargs):
        if path == software.EVIDENCE_ROOT:
            pytest.fail("A portable plan must not inspect canonical Host evidence")
        return original(path, **kwargs)
    monkeypatch.setattr(software, "_chain", chain)
    result = software.install_bundle(ROOT, "langfuse", plan=True)
    assert result["state"] == "PLANNED"
    assert result["evidence_path"] == "/var/lib/station/service-software/langfuse/receipt.json"
