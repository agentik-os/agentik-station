"""Project-only fixtures: no Host installers, accounts, services, or live paths."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import os_lifecycle, projects
from agentik_station.doctor import _expected_zone_human_path
from agentik_station.errors import ReconcileError, SecurityError, ValidationError
from agentik_station.identity import zone_unix_user
from agentik_station.installer import StationInstaller, project_creation_layout
from agentik_station.models import InstallSpec, ZoneSpec
from agentik_station.paths import LayoutPaths

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve())
    spec = ZoneSpec("SYSTEM", "station-maintainer", "system", "station-core-01")
    human = _expected_zone_human_path(paths, spec)
    state = paths.zones_state / spec.zone_id
    user = zone_unix_user(spec.category, spec.name, spec.environment)
    zone = {"schema_version": 2, "id": spec.zone_id, "name": spec.name, "category": spec.category,
            "organization": spec.organization, "environment": spec.environment, "host_id": spec.host_id,
            "unix_user": user, "human_root": str(human), "state_root": str(state),
            "hermes_home": str(state / "hermes"), "log_root": str(paths.log / "zones" / spec.zone_id),
            "runtime_root": str(paths.run / "zones" / spec.zone_id),
            "backup_staging_root": str(paths.backups / "zones" / spec.zone_id), "placement": "local",
            "isolation": {"filesystem": "unix-identity", "hermes_home": "dedicated", "credentials": "zone-scoped", "cross_zone_mounts": "deny"}}
    for path in (paths.config / "zones.d", paths.varlib, human / "projects", state / "projects", state / "home", state / "hermes"):
        path.mkdir(parents=True, exist_ok=True, mode=0o750)
    zone_file = paths.config / "zones.d" / f"{spec.zone_id}.json"
    zone_file.write_text(json.dumps(zone))
    zone_file.chmod(0o600)
    identity = SimpleNamespace(pw_dir=str(state / "home"), pw_uid=os.getuid(), pw_gid=os.getgid())
    monkeypatch.setattr(projects.pwd, "getpwnam", lambda _: identity)
    monkeypatch.setattr(os_lifecycle.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(os_lifecycle.subprocess, "run", lambda *a, **k: pytest.fail("Project creation must not execute external commands"))
    monkeypatch.setattr(StationInstaller, "apply", lambda *a: pytest.fail("Project creation must not reconcile Host/Zone"))
    return SimpleNamespace(paths=paths, zone=zone, human=human, state=state, identity=identity, spec=spec,
                           create=lambda **kw: projects.create_project(paths, REPO, zone=zone, project_id="control", **kw))


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_plan_creates_no_roots_lock_receipts_or_files(runtime, monkeypatch):
    before = snapshot(runtime.paths.config.parent.parent)
    monkeypatch.setattr(projects, "install_lock", lambda *a: pytest.fail("plan may not lock/write"))
    report = runtime.create(plan=True)
    assert report["claim"] == "PREPARED_NOT_RUN"
    assert report["human_root"] == str(runtime.human / "projects/control")
    assert report["runtime_state_root"] == str(runtime.state / "projects/control")
    layout = project_creation_layout(runtime.paths, runtime.human, runtime.spec.zone_id, "control")
    assert report["directories"] == [{"path": str(path), "mode": f"{mode:04o}"} for path, mode in layout["directories"]]
    assert before == snapshot(runtime.paths.config.parent.parent)
    assert not runtime.paths.run.exists()
    assert not (runtime.paths.varlib / "project-operations").exists()


def test_core_system_zone_can_create_project_with_kernel_rules_and_private_receipt(runtime):
    assert list((runtime.human / "projects").iterdir()) == []
    result = runtime.create()
    human, state = runtime.human / "projects/control", runtime.state / "projects/control"
    descriptor = json.loads((human / "PROJECT.json").read_text())
    assert descriptor["human_root"] == str(human)
    assert descriptor["runtime_state_root"] == str(state)
    assert descriptor["zone_id"] == runtime.spec.zone_id
    assert (human / ".station/STATION_AGENT_RULES.md").read_bytes() == (REPO / "rules/STATION_AGENT_RULES.md").read_bytes()
    for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        assert ".station/STATION_AGENT_RULES.md" in (human / name).read_text()
    for item in result["directories"]:
        assert Path(item["path"]).is_dir()
        assert Path(item["path"]).stat().st_mode & 0o777 == int(item["mode"], 8)
    receipt = Path(result["receipt"])
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert receipt.parent.stat().st_mode & 0o777 == 0o700
    assert json.loads(receipt.read_text())["status"] == "COMPLETED"
    assert result["claim"] == "PROJECT_LAYOUT_CREATED_NOT_OS_INSTALLED"
    assert not result["operational"]
    assert not (human / "installed.yaml").exists()


@pytest.mark.parametrize("root_kind", ["human", "runtime", "human_symlink", "runtime_symlink"])
def test_existing_or_foreign_partial_project_is_never_overwritten(runtime, tmp_path, root_kind):
    root = (runtime.human if root_kind.startswith("human") else runtime.state) / "projects/control"
    if "symlink" in root_kind:
        outside = tmp_path / "foreign"
        outside.mkdir()
        (outside / "user.txt").write_text("untouched")
        root.symlink_to(outside, target_is_directory=True)
    else:
        root.mkdir()
        (root / "user.txt").write_text("untouched")
    before = snapshot(tmp_path)
    with pytest.raises(ValidationError, match="already exists"):
        runtime.create()
    assert snapshot(tmp_path) == before
    assert not runtime.paths.run.exists()


def test_second_invocation_refuses_even_identical_project(runtime):
    runtime.create()
    before = snapshot(runtime.paths.config.parent.parent)
    with pytest.raises(ValidationError, match="already exists"):
        runtime.create()
    assert snapshot(runtime.paths.config.parent.parent) == before


@pytest.mark.parametrize("field,value", [("pw_dir", "/tmp/foreign"), ("pw_gid", 999999)])
def test_wrong_unix_identity_fails_before_mutation(runtime, field, value):
    setattr(runtime.identity, field, value)
    with pytest.raises(SecurityError):
        runtime.create()
    assert not (runtime.human / "projects/control").exists()
    assert not runtime.paths.run.exists()


def test_forged_zone_paths_are_not_used(runtime):
    runtime.zone["state_root"] = "/tmp/foreign"
    with pytest.raises(SecurityError):
        runtime.create()
    assert not runtime.paths.run.exists()


def test_group_writable_project_parent_is_rejected(runtime):
    (runtime.human / "projects").chmod(0o770)
    with pytest.raises(SecurityError):
        runtime.create()
    assert not runtime.paths.run.exists()


def test_template_failure_rolls_back_only_new_files_and_records_failure(runtime, monkeypatch):
    original = StationInstaller._create_project

    def fail(installer, *args):
        original(installer, *args)
        raise RuntimeError("secret-looking detail must not enter receipt")

    monkeypatch.setattr(StationInstaller, "_create_project", fail)
    with pytest.raises(ReconcileError):
        runtime.create()
    assert not (runtime.human / "projects/control").exists()
    assert not (runtime.state / "projects/control").exists()
    receipt = next((runtime.paths.varlib / "project-operations").glob("*.json"))
    payload = json.loads(receipt.read_text())
    assert payload["status"] == "FAILED" and payload["new_tree_rollback_completed"]
    assert "secret-looking" not in receipt.read_text()


@pytest.mark.parametrize("replacement", ["directory", "symlink"])
def test_renamed_root_cannot_redirect_kernel_writes_and_is_retained_for_inspection(runtime, monkeypatch, replacement):
    victim = runtime.human / "projects/existing"
    victim.mkdir()
    (victim / "README.md").write_text("existing user data")
    original = projects._NewProjectFS.publish
    moved = runtime.human / "projects/moved-private-reservation"

    def rename(fs):
        original(fs)
        root = runtime.human / "projects/control"
        root.rename(moved)
        if replacement == "symlink":
            root.symlink_to(victim, target_is_directory=True)
        else:
            root.mkdir()
            (root / "unrelated.txt").write_text("do not alter")

    monkeypatch.setattr(projects._NewProjectFS, "publish", rename)
    with pytest.raises(ReconcileError):
        runtime.create()
    assert (victim / "README.md").read_text() == "existing user data"
    assert sorted(p.name for p in victim.iterdir()) == ["README.md"]
    assert (moved / "PROJECT.json").exists()  # Write stayed on the new descriptor, not the replaced path.
    if replacement == "directory":
        assert list((runtime.human / "projects/control").iterdir()) == [runtime.human / "projects/control/unrelated.txt"]
    receipt = json.loads(next((runtime.paths.varlib / "project-operations").glob("*.json")).read_text())
    assert receipt["status"] == "FAILED" and not receipt["new_tree_rollback_completed"]


def test_second_root_reservation_race_preserves_existing_state(runtime, monkeypatch):
    original = projects._NewProjectFS.reserve
    target = runtime.state / "projects/control"

    def race(fs):
        target.mkdir()
        (target / "foreign.txt").write_text("untouched")
        original(fs)

    monkeypatch.setattr(projects._NewProjectFS, "reserve", race)
    with pytest.raises(ReconcileError):
        runtime.create()
    # First publication may have completed before the second path raced in.
    # It is retained rather than removed through a mutable Zone pathname.
    assert (runtime.human / "projects/control").is_dir()
    assert (target / "foreign.txt").read_text() == "untouched"


def test_invalid_project_id_is_rejected_before_paths(runtime):
    with pytest.raises(ValidationError):
        projects.create_project(runtime.paths, REPO, zone=runtime.zone, project_id="../other")
    assert not runtime.paths.run.exists()


def test_atomic_publication_never_adopts_an_old_private_target(runtime, monkeypatch):
    old = runtime.human / "projects/old-partial"
    old.mkdir(mode=0o700)
    (old / "prior.txt").write_text("old root-owned private tree")
    target = runtime.human / "projects/control"
    original = projects._rename_noreplace
    swapped = False

    def replace(source_fd, source, target_fd, name):
        nonlocal swapped
        if not swapped:
            old.rename(target)
            swapped = True
        return original(source_fd, source, target_fd, name)

    monkeypatch.setattr(projects, "_rename_noreplace", replace)
    with pytest.raises(ReconcileError):
        runtime.create()
    assert sorted(path.name for path in target.iterdir()) == ["prior.txt"]
    assert (target / "prior.txt").read_text() == "old root-owned private tree"
    receipt = json.loads(next((runtime.paths.varlib / "project-operations").glob("*.json")).read_text())
    assert receipt["new_tree_rollback_completed"]  # Only unpublished trusted staging was removed.


def test_post_check_root_substitution_cannot_delete_an_unrelated_empty_directory(runtime, monkeypatch):
    victim = runtime.human / "projects/empty-existing"
    victim.mkdir(mode=0o700)
    original = projects._NewProjectFS.still_named
    target = runtime.human / "projects/control"
    moved = runtime.human / "projects/new-hidden"
    attacked = False

    def rename_after_check(fs):
        nonlocal attacked
        result = original(fs)
        if result and not attacked:
            target.rename(moved)
            victim.rename(target)
            attacked = True
        return result

    monkeypatch.setattr(projects._NewProjectFS, "still_named", rename_after_check)
    with pytest.raises(ReconcileError):
        runtime.create()
    assert target.is_dir() and list(target.iterdir()) == []
    assert (moved / "PROJECT.json").is_file()
    receipt = json.loads(next((runtime.paths.varlib / "project-operations").glob("*.json")).read_text())
    assert not receipt["new_tree_rollback_completed"]


def test_native_atomic_wrapper_moves_only_when_destination_is_absent(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "new").write_text("new")
    (destination / "old").write_text("old")
    with projects._directory(tmp_path.resolve()) as parent:
        with pytest.raises(FileExistsError):
            projects._rename_noreplace(parent, "source", parent, "destination")
        assert (destination / "old").read_text() == "old" and (source / "new").exists()
        projects._rename_noreplace(parent, "source", parent, "fresh")
    assert not source.exists() and (tmp_path / "fresh/new").read_text() == "new"


def test_missing_atomic_rename_never_falls_back_to_replacing_rename(monkeypatch):
    monkeypatch.setattr(projects.ctypes, "CDLL", lambda *a, **k: object())
    monkeypatch.setattr(projects.os, "rename", lambda *a, **k: pytest.fail("unsafe rename fallback"))
    with pytest.raises(SecurityError, match="unavailable"):
        projects._rename_noreplace(1, "source", 2, "destination")


def test_project_creation_after_full_core_fixture_does_not_reconcile_or_change_release(tmp_path, monkeypatch):
    paths = LayoutPaths.under(tmp_path.resolve())
    spec = InstallSpec(host_id="station-core-01", role="core", install_system_packages=False,
                       configure_fail2ban=False, enable_doctor_timer=False)
    assert StationInstaller(REPO, spec, paths).apply() == "READY_FOR_SETUP"
    zone = json.loads((paths.config / "zones.d/station-maintainer.json").read_text())
    assert list((Path(zone["human_root"]) / "projects").iterdir()) == []
    host_before = (paths.observed / "host.json").read_bytes()
    desired_before = snapshot(paths.config)
    release_before = snapshot(paths.releases)
    monkeypatch.setattr(projects.pwd, "getpwnam", lambda _: SimpleNamespace(
        pw_dir=str(Path(zone["state_root"]) / "home"), pw_uid=os.getuid(), pw_gid=os.getgid()))
    monkeypatch.setattr(os_lifecycle.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(StationInstaller, "apply", lambda *a: pytest.fail("narrow create reconciled Host"))
    monkeypatch.setattr(os_lifecycle.subprocess, "run", lambda *a, **k: pytest.fail("narrow create launched command"))
    result = projects.create_project(paths, REPO, zone=zone, project_id="control")
    assert result["human_root"] == str(Path(zone["human_root"]) / "projects/control")
    assert result["runtime_state_root"] == str(Path(zone["state_root"]) / "projects/control")
    assert (paths.observed / "host.json").read_bytes() == host_before
    assert snapshot(paths.config) == desired_before
    assert snapshot(paths.releases) == release_before
