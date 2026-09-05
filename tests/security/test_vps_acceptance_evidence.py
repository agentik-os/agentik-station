"""Temp-only evidence tests; never invoke bootstrap, SSH or installed Host gates."""
import errno
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ci_vps_evidence", REPO / "scripts/ci_vps_evidence.py")
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setattr(evidence, "OUTPUT_ROOT", root)
    monkeypatch.setattr(evidence.platform, "freedesktop_os_release", lambda: {"ID": "ubuntu", "VERSION_ID": "26.04"})
    monkeypatch.setattr(evidence.platform, "system", lambda: "Linux")
    monkeypatch.setattr(evidence.platform, "machine", lambda: "aarch64")
    doctor_dir = root / "station-vps-readback.abcdefghij"
    doctor_dir.mkdir(mode=0o700)
    doctor = doctor_dir / "devops-os-doctor.json"
    doctor.write_bytes(b'{"ok":true,"secret-looking-unused-debug":"not-published"}\n')
    return root, doctor


@pytest.mark.parametrize("distro,version,architecture", [("ubuntu", "26.04", "aarch64"), ("ubuntu", "24.04", "x86_64"), ("debian", "13", "x86_64")])
def test_evidence_records_observed_host_without_fixed_or_disposable_claim(workspace, monkeypatch, distro, version, architecture):
    root, doctor = workspace
    monkeypatch.setattr(evidence.platform, "freedesktop_os_release", lambda: {"ID": distro, "VERSION_ID": version})
    monkeypatch.setattr(evidence.platform, "machine", lambda: architecture)
    output = root / "station-vps-acceptance.20260905-11-15.json"
    payload = evidence.publish(output, "core", doctor)
    assert payload["environment"] == f"{distro}-{version}"
    assert payload["observed_host"] == {"system": "Linux", "distribution_id": distro,
                                        "distribution_version_id": version, "architecture": architecture}
    assert payload["external_accounts_accepted"] is False
    assert payload["claim"] == "VERIFIED_INSTALL_READY_FOR_EXTERNAL_SETUP"
    assert payload["devops_doctor_sha256"] == hashlib.sha256(doctor.read_bytes()).hexdigest()
    assert "not-published" not in output.read_text()
    assert "disposable" not in output.read_text()
    assert output.stat().st_mode & 0o777 == 0o644
    assert output.stat().st_nlink == 1
    assert not list(root.glob("station-vps-publish.*"))


def test_full_keeps_the_additional_parakeet_gate(workspace):
    root, doctor = workspace
    payload = evidence.publish(root / "station-vps-acceptance.json", "full", doctor)
    assert payload["checks"][-1] == "parakeet-loopback-health"
    assert len(payload["checks"]) == 9
    assert "shared-zone-cli-pins-private-home-network-isolated" in payload["checks"]


@pytest.mark.parametrize("path", ["/etc/passwd", "/root/evidence.json", "/tmp/other.json", "/tmp/station-vps-acceptance...json", "/tmp/station-vps-acceptance.SECRET.json"])
def test_arbitrary_root_destinations_are_rejected(workspace, path):
    _, doctor = workspace
    with pytest.raises(ValueError):
        evidence.publish(Path(path), "core", doctor)


@pytest.mark.parametrize("name", ["other.json", "station-vps-acceptance...json",
                                 "station-vps-acceptance.SECRET.json", "station-vps-acceptance.-id.json",
                                 "station-vps-acceptance." + "a" * 65 + ".json"])
def test_invalid_basename_is_rejected_inside_allowed_directory(workspace, name):
    root, doctor = workspace
    with pytest.raises(ValueError):
        evidence.validate_output(root / name)
    with pytest.raises(ValueError):
        evidence.publish(root / name, "core", doctor)
    assert not (root / name).exists()


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling", "directory", "fifo", "hardlink"])
def test_output_refuses_any_existing_leaf_without_overwriting(workspace, kind):
    root, doctor = workspace
    output = root / "station-vps-acceptance.json"
    target = root / "unrelated-user-file"
    target.write_text("preserve")
    if kind == "file":
        output.write_text("earlier acceptance")
    elif kind == "symlink":
        output.symlink_to(target)
    elif kind == "dangling":
        output.symlink_to(root / "missing")
    elif kind == "directory":
        output.mkdir()
    elif kind == "fifo":
        os.mkfifo(output)
    else:
        os.link(target, output)
    with pytest.raises(FileExistsError):
        evidence.validate_output(output)
    with pytest.raises(FileExistsError):
        evidence.publish(output, "core", doctor)
    assert target.read_text() == "preserve"
    if kind == "file":
        assert output.read_text() == "earlier acceptance"
    assert not list(root.glob("station-vps-publish.*"))


def test_destination_symlink_race_fails_without_following_or_overwriting(workspace, monkeypatch):
    root, doctor = workspace
    output = root / "station-vps-acceptance.json"
    target = root / "unrelated-user-file"
    target.write_text("preserve")
    real_link = evidence.os.link

    def race(source, destination, **kwargs):
        assert not output.exists()
        output.symlink_to(target)
        return real_link(source, destination, **kwargs)

    monkeypatch.setattr(evidence.os, "link", race)
    with pytest.raises(FileExistsError):
        evidence.publish(output, "core", doctor)
    assert output.is_symlink() and target.read_text() == "preserve"
    assert not list(root.glob("station-vps-publish.*"))


def test_publication_is_complete_before_it_becomes_visible(workspace, monkeypatch):
    root, doctor = workspace
    output = root / "station-vps-acceptance.json"
    real_link = evidence.os.link

    def inspect(source, destination, **kwargs):
        assert not output.exists()
        data = json.loads(Path(source).read_text())
        assert data["observed_host"]["distribution_version_id"] == "26.04"
        return real_link(source, destination, **kwargs)

    monkeypatch.setattr(evidence.os, "link", inspect)
    evidence.publish(output, "core", doctor)
    assert json.loads(output.read_text())["environment"] == "ubuntu-26.04"


@pytest.mark.parametrize("kind", ["leaf_symlink", "parent_symlink", "fifo", "hardlink", "oversize", "public_workspace"])
def test_doctor_input_is_bounded_private_regular_and_not_followed(workspace, kind):
    root, doctor = workspace
    if kind == "leaf_symlink":
        target = root / "private-key"
        target.write_text("secret")
        doctor.unlink()
        doctor.symlink_to(target)
    elif kind == "parent_symlink":
        doctor.parent.rename(root / "moved")
        doctor.parent.symlink_to(root / "moved", target_is_directory=True)
    elif kind == "fifo":
        doctor.unlink()
        os.mkfifo(doctor)
    elif kind == "hardlink":
        os.link(doctor, root / "other-doctor")
    elif kind == "oversize":
        doctor.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    else:
        doctor.parent.chmod(0o755)
    output = root / "station-vps-acceptance.json"
    with pytest.raises((ValueError, OSError)):
        evidence.publish(output, "core", doctor)
    assert not output.exists()


@pytest.mark.parametrize("release", [{"ID": "ubuntu"}, {"ID": "ubuntu", "VERSION_ID": ""}, {"ID": "$(bad)", "VERSION_ID": "26.04"}])
def test_missing_or_invalid_observation_does_not_publish_success(workspace, monkeypatch, release):
    root, doctor = workspace
    monkeypatch.setattr(evidence.platform, "freedesktop_os_release", lambda: release)
    with pytest.raises(ValueError):
        evidence.publish(root / "station-vps-acceptance.json", "core", doctor)
    assert not list(root.glob("station-vps-acceptance*.json"))


def test_linux_tmp_symlink_is_rejected(workspace, monkeypatch):
    root, _ = workspace
    link = root / "linked-tmp"
    link.symlink_to(root, target_is_directory=True)
    monkeypatch.setattr(evidence, "OUTPUT_ROOT", link)
    monkeypatch.setattr(evidence.sys, "platform", "linux")
    with pytest.raises(OSError):
        evidence.validate_output(link / "station-vps-acceptance.json")


def test_world_writable_nonsticky_output_directory_is_rejected(workspace):
    root, _ = workspace
    root.chmod(0o777)
    with pytest.raises(ValueError):
        evidence.validate_output(root / "station-vps-acceptance.json")


def test_no_unsafe_fallback_when_atomic_publication_is_unavailable(workspace, monkeypatch):
    root, doctor = workspace

    def unsupported(*args, **kwargs):
        raise OSError(errno.EOPNOTSUPP, "unsupported")

    monkeypatch.setattr(evidence.os, "link", unsupported)
    with pytest.raises(OSError):
        evidence.publish(root / "station-vps-acceptance.json", "core", doctor)
    assert not list(root.glob("station-vps-acceptance*.json"))


def test_script_keeps_gates_and_never_uses_predictable_root_redirects():
    source = (REPO / "scripts/ci_vps_acceptance.sh").read_text()
    assert ">/tmp/devops-os-doctor.json" not in source
    assert ">/tmp/agk-help.txt" not in source
    assert "output.write_text" not in source
    assert "disposable-ubuntu-24.04" not in source
    assert source.index("--check-output") < source.index('"$REPO/station" doctor --full')
    assert 'mktemp -d /tmp/station-vps-readback.XXXXXXXXXX' in source
    assert 'os doctor --id devops-os --json >"$READBACK_DIR/devops-os-doctor.json"' in source
    assert 'agk" help >/dev/null' in source
    for gate in ('doctor --full', 'station_toolchain_install.sh" --check',
                 'is-enabled --quiet station-hermes-update.timer', 'is-active --quiet station-hermes-update.timer',
                 'deps web-check', 'real Zone traversal', 'station-parakeet.service', '127.0.0.1:5092/health'):
        assert gate in source
    subprocess.run(["bash", "-n", str(REPO / "scripts/ci_vps_acceptance.sh")], check=True)
