"""Governed native cache links do not relax privileged writes or release policy."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest

from agentik_station.filesystem import SafeFS, ensure_no_symlinks
from agentik_station.errors import SecurityError
from agentik_station.installer import StationInstaller
from agentik_station.models import InstallSpec, SeedSpec
from agentik_station.paths import LayoutPaths


ROOT = Path(__file__).resolve().parents[2]
CODEX_BINARY = "npm/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"
CODEX_COMMANDS = ("applypatch", "apply_patch", "codex-execve-wrapper", "codex-linux-sandbox")


def write(path, content="synthetic\n", mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)
    return path


def snapshot(root):
    result = {}
    for path in (root, *root.rglob("*")):
        info = path.lstat()
        payload = os.readlink(path) if stat.S_ISLNK(info.st_mode) else None
        if stat.S_ISREG(info.st_mode):
            payload = hashlib.sha256(path.read_bytes()).hexdigest()
        result[str(path.relative_to(root))] = (info.st_ino, info.st_mode, info.st_uid, info.st_gid, payload)
    return result


def make_layout(root, paths=None, human=None, state_root=None):
    # /private/tmp inherits wheel on macOS, not the test process's primary group.
    # Set the owning fixture directory before child creation to model the real
    # Zone/authority UID:GID contract instead of bypassing group verification.
    os.chown(root, os.getuid(), os.getgid())
    paths = paths or LayoutPaths.under(root / "root")
    human = human or paths.runtime / "2_ZONES/3_AGENTIK/dev"
    state_root = state_root or paths.zones_state / "dev"
    home = state_root / "home"
    for directory in (human, state_root, home):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    uv = home / ".cache/uv"
    wheel = uv / "wheels-v6/pypi/synthetic-package/1.0.0-py3-none-any"
    archive = uv / "archive-v0/NativeArchive123"
    archive.mkdir(parents=True)
    write(archive / "synthetic.py", "# cache data must not be opened by the link audit\n")
    wheel.parent.mkdir(parents=True)
    codex = home / ".codex/tmp/arg0/codex-arg0AbC123xyz"
    codex.mkdir(parents=True)
    identity = {"schema_version": 1, "pins": {"CODEX_CLI_VERSION": "0.114.0"},
                "node_arch": "x64", "codex": True}
    release_id = "v1-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    release = paths.software / "tools/toolchain" / release_id
    binary = write(release / CODEX_BINARY, "#!/bin/sh\nexit 0\n", 0o555)
    files = {CODEX_BINARY: {"type": "file", "mode": 0o555, "size": binary.stat().st_size,
                           "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}}
    for parent in Path(CODEX_BINARY).parents:
        if str(parent) != ".":
            files[str(parent)] = {"type": "directory", "mode": 0o555}
            (release / parent).chmod(0o555)
    manifest = {**identity, "release_id": release_id, "credentials": "NOT_SHARED",
                "exports": {"codex": "npm/codex/bin/codex.js"}, "files": files}
    manifest_path = write(release / "MANIFEST.json", json.dumps(manifest), 0o444)
    release.chmod(0o555)
    return SimpleNamespace(root=root, paths=paths, human=human, state_root=state_root, home=home,
                           uv=uv, wheel=wheel, archive=archive, codex=codex, release=release,
                           binary=binary, manifest=manifest, manifest_path=manifest_path,
                           owner=(os.getuid(), os.getgid()))


@pytest.fixture
def policy():
    return importlib.import_module("agentik_station.runtime_links")


@pytest.fixture
def runtime(tmp_path, policy):
    layout = make_layout(tmp_path.resolve())
    layout.audit = lambda **kwargs: policy.audit_zone_links(
        layout.paths, human=layout.human, state_root=layout.state_root,
        owner=kwargs.pop("owner", layout.owner), **kwargs)
    yield layout
    # Only synthetic immutable fixtures, after assertions; never follow links.
    for current, directories, _ in os.walk(layout.root, followlinks=False):
        parent = Path(current)
        parent.chmod(0o700)
        directories[:] = [name for name in directories if not (parent / name).is_symlink()]


def uv_link(runtime, target=None, source=None):
    link = source or runtime.wheel
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target or "../../../archive-v0/NativeArchive123", target_is_directory=True)
    return link


def codex_link(runtime, name="apply_patch", target=None, source=None):
    link = source or runtime.codex / name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target or runtime.binary)
    return link


def assert_denied(report, link):
    assert link not in report["allowed"]
    assert link in report["unsafe"] or report["errors"]


def test_empty_zone_has_no_link_policy_failures(runtime):
    report = runtime.audit()
    assert report == {"unsafe": [], "allowed": [], "errors": []}


@pytest.mark.parametrize("command", CODEX_COMMANDS)
def test_exact_codex_native_link_to_intact_immutable_binary_is_allowed(runtime, command):
    link = codex_link(runtime, command)
    report = runtime.audit()
    assert report["unsafe"] == [] and report["errors"] == []
    assert report["allowed"] == [link]


def test_native_uv_wheel_link_to_own_zone_archive_is_allowed(runtime):
    link = uv_link(runtime)
    report = runtime.audit()
    assert report["unsafe"] == [] and report["errors"] == []
    assert report["allowed"] == [link]


def test_audit_does_not_open_cache_data_execute_tools_or_mutate_anything(runtime, monkeypatch):
    links = [uv_link(runtime), codex_link(runtime)]
    before = snapshot(runtime.root)
    read_bytes = Path.read_bytes
    read_text = Path.read_text
    original_open = os.open

    def safe_read_bytes(path, *args, **kwargs):
        assert not path.is_relative_to(runtime.archive), "cache payload was opened"
        return read_bytes(path, *args, **kwargs)

    def safe_read_text(path, *args, **kwargs):
        assert not path.is_relative_to(runtime.archive), "cache payload was opened"
        return read_text(path, *args, **kwargs)

    def safe_open(path, *args, **kwargs):
        assert Path(path).name != "synthetic.py", "cache payload was opened through a raw descriptor"
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "read_bytes", safe_read_bytes)
        scoped.setattr(Path, "read_text", safe_read_text)
        scoped.setattr(os, "open", safe_open)
        scoped.setattr(subprocess, "run", lambda *a, **k: pytest.fail("audit ran a native tool"))
        report = runtime.audit()
    assert set(report["allowed"]) == set(links)
    assert not report["unsafe"] and not report["errors"]
    assert snapshot(runtime.root) == before


@pytest.mark.parametrize("kind", ["human", "project", "credentials", "home", "other-cache", "lookalike"])
def test_same_targets_do_not_authorize_links_outside_exact_native_cache_shapes(runtime, kind):
    source = {"human": runtime.human / "alias", "project": runtime.human / "projects/demo/repos/alias",
              "credentials": runtime.human / "credentials/alias", "home": runtime.home / "alias",
              "other-cache": runtime.home / ".cache/another-tool/alias",
              "lookalike": runtime.home / ".codex/tmp/arg0/codex-arg0AbC123xyz/other-command"}[kind]
    link = codex_link(runtime, source=source)
    assert_denied(runtime.audit(), link)


@pytest.mark.parametrize("kind", ["cross-zone", "root", "operator", "config", "registry", "undeclared-software"])
def test_native_source_shape_never_authorizes_foreign_or_authority_targets(runtime, kind):
    target = {"cross-zone": runtime.paths.zones_state / "other/home/.cache/uv/archive-v0/private",
              "root": runtime.root / "root-home/private", "operator": runtime.root / "operator-home/private",
              "config": runtime.paths.config / "desired.json",
              "registry": runtime.paths.varlib / "registry/authority.json",
              "undeclared-software": runtime.paths.software / "tools/unmanaged/bin/codex"}[kind]
    write(target, "unrelated synthetic data\n", 0o555)
    before = target.read_bytes()
    link = codex_link(runtime, target=target)
    assert_denied(runtime.audit(), link)
    assert target.read_bytes() == before


@pytest.mark.parametrize("kind", ["cross-zone", "credentials", "other-cache", "file", "dangling", "cycle"])
def test_uv_target_must_be_real_archive_directory_in_same_zone(runtime, kind):
    if kind == "cross-zone":
        target = runtime.paths.zones_state / "other/home/.cache/uv/archive-v0/NativeArchive123"
        target.mkdir(parents=True)
    elif kind == "credentials":
        target = runtime.human / "credentials"
        target.mkdir()
    elif kind == "other-cache":
        target = runtime.home / ".cache/another/archive"
        target.mkdir(parents=True)
    elif kind == "file":
        target = write(runtime.uv / "archive-v0/not-a-directory")
    elif kind == "dangling":
        target = runtime.uv / "archive-v0/missing"
    else:
        target = runtime.wheel
    link = uv_link(runtime, target=target)
    assert_denied(runtime.audit(), link)


@pytest.mark.parametrize("defect", ["changed-bytes", "wrong-size", "wrong-digest", "wrong-release-id",
                                    "wrong-export", "wrong-mode", "missing-parent-entry", "credentials"])
def test_codex_requires_complete_matching_immutable_manifest_evidence(runtime, defect):
    link = codex_link(runtime)
    if defect == "changed-bytes":
        runtime.binary.chmod(0o755)
        runtime.binary.write_text("tampered immutable code\n")
        runtime.binary.chmod(0o555)
    elif defect == "wrong-mode":
        runtime.binary.chmod(0o755)
    else:
        manifest = json.loads(runtime.manifest_path.read_text())
        if defect == "wrong-size":
            manifest["files"][CODEX_BINARY]["size"] += 1
        elif defect == "wrong-digest":
            manifest["files"][CODEX_BINARY]["sha256"] = "0" * 64
        elif defect == "wrong-release-id":
            manifest["release_id"] = "v1-" + "0" * 24
        elif defect == "wrong-export":
            manifest["exports"]["codex"] = "npm/other/bin/codex.js"
        elif defect == "missing-parent-entry":
            manifest["files"].pop(str(Path(CODEX_BINARY).parent))
        else:
            manifest["credentials"] = "SHARED"
        runtime.manifest_path.chmod(0o644)
        runtime.manifest_path.write_text(json.dumps(manifest))
        runtime.manifest_path.chmod(0o444)
    assert_denied(runtime.audit(), link)


@pytest.mark.parametrize("location", ["uv-parent", "codex-parent", "archive", "release", "manifest"])
def test_writable_governed_parents_or_evidence_fail_closed(runtime, location):
    link = uv_link(runtime) if location in {"uv-parent", "archive"} else codex_link(runtime)
    target = {"uv-parent": runtime.wheel.parent, "codex-parent": runtime.codex,
              "archive": runtime.archive, "release": runtime.release,
              "manifest": runtime.manifest_path}[location]
    target.chmod(0o777 if target.is_dir() else 0o666)
    assert_denied(runtime.audit(), link)


@pytest.mark.parametrize("location", ["source-parent", "archive", "shared-binary", "manifest"])
def test_symlinked_governed_parent_or_target_is_not_followed(runtime, location):
    link = uv_link(runtime) if location in {"source-parent", "archive"} else codex_link(runtime)
    target = {"source-parent": runtime.wheel.parent, "archive": runtime.archive,
              "shared-binary": runtime.binary, "manifest": runtime.manifest_path}[location]
    target.parent.chmod(0o755)
    moved = target.with_name(target.name + "-preserved")
    target.rename(moved)
    target.symlink_to(moved, target_is_directory=moved.is_dir())
    if location == "source-parent":
        # The parent link itself is outside any allowlisted native source shape.
        assert_denied(runtime.audit(), target)
    else:
        assert_denied(runtime.audit(), link)


def test_missing_expected_zone_owner_cannot_grant_runtime_link_exceptions(runtime):
    link = uv_link(runtime)
    assert_denied(runtime.audit(owner=None), link)


@pytest.mark.parametrize("location", ["link-uid", "link-gid", "uv-parent", "codex-parent",
                                     "shared-binary", "manifest"])
def test_wrong_zone_or_authority_identity_cannot_grant_a_native_exception(runtime, monkeypatch, location):
    link = uv_link(runtime) if location == "uv-parent" else codex_link(runtime)
    if location in {"link-uid", "link-gid"}:
        original_stat = os.stat

        def foreign_link(path, *args, **kwargs):
            info = original_stat(path, *args, **kwargs)
            if str(path) == link.name and kwargs.get("dir_fd") is not None:
                fields = list(info)
                fields[4 if location == "link-uid" else 5] += 10000
                return os.stat_result(fields)
            return info

        monkeypatch.setattr(os, "stat", foreign_link)
    else:
        target = {"uv-parent": runtime.wheel.parent, "codex-parent": runtime.codex,
                  "shared-binary": runtime.binary, "manifest": runtime.manifest_path}[location]
        actual = target.stat()
        original_fstat = os.fstat

        def foreign_opened_object(fd):
            info = original_fstat(fd)
            if (info.st_dev, info.st_ino) == (actual.st_dev, actual.st_ino):
                fields = list(info)
                fields[4] += 10000
                return os.stat_result(fields)
            return info

        monkeypatch.setattr(os, "fstat", foreign_opened_object)
    assert_denied(runtime.audit(), link)


def test_unreadable_subtree_fails_closed_without_exposing_native_exception_detail(runtime, policy,
                                                                                 monkeypatch):
    original_walk = os.walk

    def inaccessible(top, *args, **kwargs):
        if Path(top) == runtime.state_root:
            callback = kwargs.get("onerror")
            if callback:
                callback(PermissionError("SYNTHETIC_PRIVATE_EXCEPTION_DETAIL"))
        return original_walk(top, *args, **kwargs)

    proxy = SimpleNamespace(**vars(os))
    proxy.walk = inaccessible
    monkeypatch.setattr(policy, "os", proxy)
    report = runtime.audit()
    assert report["errors"]
    assert "SYNTHETIC_PRIVATE_EXCEPTION_DETAIL" not in str(report)


def test_governed_cache_allowance_does_not_relax_safefs_or_release_symlink_policy(runtime):
    link = uv_link(runtime)
    assert link in runtime.audit()["allowed"]
    assert link in ensure_no_symlinks(runtime.state_root)
    fs = SafeFS([runtime.state_root])
    with pytest.raises(SecurityError):
        fs.write_text(link / "privileged-write", "must never be written")
    assert not (runtime.archive / "privileged-write").exists()


def install_fixture(tmp_path, operation_id):
    paths = LayoutPaths.under(tmp_path.resolve() / "root")
    spec = InstallSpec(operation_id=operation_id, host_id="organization-alpha-prod-01", role="team",
                       install_system_packages=False, configure_fail2ban=False, enable_doctor_timer=False,
                       seed=SeedSpec("ORGANIZATIONS", "organization-alpha", "production", "organization-alpha", "platform"))
    assert StationInstaller(ROOT, spec, paths=paths).apply() == "READY_FOR_SETUP"
    return make_layout(tmp_path.resolve(), paths,
                       paths.runtime / "2_ZONES/4_ORGANIZATIONS/organization-alpha/prod",
                       paths.zones_state / "organization-alpha-prod")


def test_full_doctor_accepts_governed_native_cache_links_without_weakening_project_checks(tmp_path):
    from agentik_station.doctor import station_doctor

    runtime = install_fixture(tmp_path, "op-doctor-native-caches")
    uv_link(runtime)
    codex_link(runtime)
    result = station_doctor(runtime.paths, repo_root=ROOT, full=True)
    assert result.ok, result.to_dict()
    assert any(check["name"] == "zone:organization-alpha-prod:symlinks" for check in result.checks)
    assert any(check["name"] == "project:organization-alpha-prod:platform:symlinks" for check in result.checks)


def test_full_doctor_still_rejects_unapproved_zone_link_after_native_allowance(tmp_path):
    from agentik_station.doctor import station_doctor

    runtime = install_fixture(tmp_path, "op-doctor-native-cache-escape")
    uv_link(runtime)
    codex_link(runtime)
    bad = runtime.human / "projects/platform/repos/unapproved-code-link"
    codex_link(runtime, source=bad)
    result = station_doctor(runtime.paths, repo_root=ROOT, full=True)
    assert not result.ok
    assert any(issue["name"] == "zone:organization-alpha-prod:symlinks" for issue in result.issues)
    assert any(issue["name"] == "project:organization-alpha-prod:platform:symlinks" for issue in result.issues)
