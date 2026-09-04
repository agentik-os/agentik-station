"""Synthetic-only Strix tests: no Docker daemon, live target or provider calls."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentik_station import strix
from agentik_station.cli import build_parser
from agentik_station.errors import SecurityError, ValidationError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "repos/app").mkdir(parents=True)
    (root / "repos/app/main.py").write_text("print('synthetic fixture')\n")
    return root


def prepared(project):
    return strix.prepare(project, "app", zone="lab", project_id="fixture", uid=os.geteuid(),
                         model="openai/fixture-model", budget=5, timeout=60)


def test_prepare_has_no_external_side_effect_and_omits_obvious_secrets(project, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("No subprocess during preparation"))
    (project / "repos/app/.env").write_text("PRIVATE=fixture")
    (project / "repos/app/client.key").write_text("PRIVATE")
    plan = prepared(project)
    assert plan["state"] == "PREPARED_NOT_AUTHORIZED"
    snapshot = strix.job_root(project, plan["job"]) / "snapshot"
    assert [name for name, _ in strix.source_files(snapshot, os.geteuid(), filter_source=False)] == ["main.py"]
    assert plan["source_upload_approved"] is False
    assert snapshot.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("repo", ["https://example.com", "../outside", "/etc", "../../root"])
def test_remote_and_escaping_sources_rejected(project, repo):
    with pytest.raises((ValidationError, OSError, SecurityError)):
        strix.prepare(project, repo, zone="lab", project_id="fixture", uid=os.geteuid(),
                      model="openai/fixture", budget=5, timeout=60)


@pytest.mark.parametrize("kind", ["symlink", "directory-symlink", "hardlink", "fifo"])
def test_snapshot_rejects_unsafe_entries(project, tmp_path, kind):
    victim = tmp_path / "victim"
    victim.write_text("DO NOT READ")
    target = project / "repos/app/unsafe"
    if kind == "symlink":
        target.symlink_to(victim)
    elif kind == "directory-symlink":
        target.symlink_to(tmp_path, target_is_directory=True)
    elif kind == "hardlink":
        os.link(victim, target)
    else:
        os.mkfifo(target)
    with pytest.raises((SecurityError, OSError)):
        prepared(project)


@pytest.mark.parametrize("budget", [0, -1, 26, float("nan"), float("inf"), True, "5"])
def test_invalid_budget_rejected(budget):
    with pytest.raises(ValidationError):
        strix.validate_limits("openai/fixture", budget, 60)


def test_model_and_timeout_cannot_smuggle_commands():
    for model, timeout in [("openai/fixture;sh", 60), ("https://endpoint", 60), ("openai/fixture", 999999), ("openai/fixture", True)]:
        with pytest.raises(ValidationError):
            strix.validate_limits(model, 5, timeout)


def test_bound_identity_snapshot_and_clean_execution_environment(project, monkeypatch):
    plan = prepared(project)
    snapshot = strix.job_root(project, plan["job"]) / "snapshot"
    (snapshot / "main.py").write_text("changed")
    assert strix.snapshot_digest(strix.source_files(snapshot, os.geteuid(), filter_source=False)) != plan["snapshot_sha256"]
    with pytest.raises(SecurityError):
        strix.validate_plan(plan, job=plan["job"], zone="another", project_id="fixture", uid=os.geteuid())
    monkeypatch.setenv("GH_TOKEN", "must-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("STRIX_IMAGE", "attacker/image")
    plan["network"] = "station-strix-lab-fixture"
    argv, env = strix.build_execution(snapshot.parent / "execution", plan, image="pinned@sha256:fixture", key="selected-fixture")
    assert env["LLM_API_KEY"] == "selected-fixture"
    assert env["STRIX_IMAGE"] == "pinned@sha256:fixture"
    assert "must-not-leak" not in str(env)
    assert "selected-fixture" not in str(argv)
    assert env["STRIX_TELEMETRY"] == "false"
    assert argv[argv.index("--target") + 1].endswith("/execution/target")
    assert not any(value in argv for value in ["--update", "--resume", "--workspace-file", "--target-list", "cloud"])


def test_read_json_rejects_wrong_owner_and_symlink(tmp_path):
    path = tmp_path / "grant.json"
    path.write_text("{}")
    with pytest.raises(SecurityError):
        strix.read_json(path, uid=os.geteuid() + 1)
    link = tmp_path / "alias.json"
    link.symlink_to(path)
    with pytest.raises(OSError):
        strix.read_json(link, uid=os.geteuid())


def test_no_agent_self_authorization(project):
    with pytest.raises(SecurityError):
        strix.approve(project, job="strix-fixture", zone="lab", project_id="fixture", uid=os.geteuid(),
                      policy_root=project / "policy", host_record=project / "host.json", network="station-strix-lab-fixture",
                      acceptance_sha256="0" * 64, source_upload_approved=True, dedicated_lab=True)


@pytest.mark.parametrize("record,findings,rc,state", [
    ({"status": "completed", "scan_results": {"scan_completed": True}, "llm_usage": {"cost": 1}}, [], 0, "NO_FINDINGS_REPORTED"),
    ({"status": "completed", "scan_results": {"scan_completed": True}, "llm_usage": {"cost": 1}}, [{"id": "fixture"}], 2, "FINDINGS_REPORTED"),
    ({"status": "running", "llm_usage": {"cost": 1}}, [], 0, "INCOMPLETE"),
    ({"status": "completed", "scan_results": {"scan_completed": True}, "llm_usage": {"cost": 6}}, [], 0, "INCOMPLETE"),
    ({"status": "completed", "scan_results": {"scan_completed": True}}, [], 0, "INCOMPLETE"),
    ({"status": "completed", "scan_results": {"scan_completed": True}, "llm_usage": {"cost": 1}}, [], 2, "INCOMPLETE"),
])
def test_exit_code_is_not_acceptance(record, findings, rc, state):
    result = strix.interpret_result(record, findings, rc, 5)
    assert result["state"] == state
    assert result["accepted"] is False and result["untrusted_report"] is True


def test_cleanup_is_label_scoped_and_never_prunes(monkeypatch):
    calls = []
    def docker(args):
        calls.append(args)
        return SimpleNamespace(stdout="0123456789ab\n" if args[0] == "ps" else "")
    monkeypatch.setattr(strix, "_docker", docker)
    strix.cleanup_containers("strix-fixture")
    assert calls == [["ps", "-aq", "--filter", "label=strix-run-id=strix-fixture"], ["rm", "-f", "0123456789ab"]]


def test_cli_has_no_arbitrary_strix_flags():
    parser = build_parser()
    parser.parse_args(["security", "strix", "prepare", "--zone", "lab", "--project", "fixture", "--repo", "app", "--model", "openai/fixture"])
    with pytest.raises(SystemExit):
        parser.parse_args(["security", "strix", "run", "--zone", "lab", "--project", "fixture", "--job", "strix-fixture", "--target", "https://example.com"])


def test_native_plugin_cannot_scan_or_approve(monkeypatch):
    spec = importlib.util.spec_from_file_location("strix_plugin_test", ROOT / "components/agk-tui/hermes/plugins/agentik_os/strix_plugin.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **kw: pytest.fail("Must not start process"))
    for action in ("approve", "run", "cloud", "--update"):
        assert json.loads(plugin.handle_strix({"action": action}))["state"] == "BLOCKED"


def test_pins_team_catalog_and_compiled_profile_contracts_agree(tmp_path):
    from agentik_station.os_runtime import compile_os_to_hermes
    import yaml
    lock = dict(line.split("=", 1) for line in (ROOT / "config/versions.lock").read_text().splitlines() if line and not line.startswith("#"))
    resource = json.loads((ROOT / "resources/strix/RESOURCE.json").read_text())
    assert lock["STRIX_VERSION"] == resource["version"] == strix.VERSION
    assert str(strix.RUNTIME) == resource["code_root"]
    assert lock["STRIX_IMAGE_AMD64"] == strix.IMAGES["x86_64"]
    assert lock["STRIX_IMAGE_ARM64"] == strix.IMAGES["aarch64"]
    compiled = compile_os_to_hermes(ROOT / "os/devops", tmp_path / "dist", project_root=tmp_path / "project")
    team = json.loads((ROOT / "os/devops/team/STRIX.json").read_text())
    assert {stage["owner"] for stage in team["stages"]} - {"human-operator"} == set(compiled["profiles"])
    for profile in compiled["profiles"]:
        root = tmp_path / "dist/profiles" / profile
        config = yaml.safe_load((root / "config.yaml").read_text())
        assert "station-strix" in config["plugins"]["enabled"]
        assert json.loads((root / "STRIX_TEAM.json").read_text()) == team
        assert "STRIX_TEAM.json" in yaml.safe_load((root / "distribution.yaml").read_text())["distribution_owned"]


@pytest.mark.parametrize("outcome", ["clean", "findings", "timeout", "cancel", "missing-report", "cleanup-failed"])
def test_execution_adapter_lifecycle_with_synthetic_process_only(project, tmp_path, monkeypatch, outcome):
    plan = prepared(project)
    job = plan["job"]
    uid = os.geteuid()
    policy = tmp_path / "policy"
    policy.mkdir()
    grant = {**plan, "source_upload_approved": True, "dedicated_lab": True, "host_role": "lab",
             "expires_at": int(strix.time.time()) + 3600, "network": "station-strix-lab-fixture"}
    (policy / f"{job}.json").write_text(json.dumps(grant))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "BUILT").write_text("fixture")
    key = tmp_path / "strix-api-key"
    key.write_text("synthetic-fixture")
    key.chmod(0o600)
    monkeypatch.setattr(strix, "RUNTIME", runtime)
    monkeypatch.setattr(strix.platform, "system", lambda: "Linux")
    monkeypatch.setattr(strix.platform, "machine", lambda: "x86_64")
    # These tests cover process/data flow, NOT real root/Unix/Docker isolation.
    # Independent tests above reject wrong owners and unsafe filesystem objects.
    monkeypatch.setattr(strix, "require_root_owned_directory_chain", lambda path: None)
    original_read = strix._read_at
    monkeypatch.setattr(strix, "_read_at", lambda fd, name, **kw: original_read(fd, name, **{**kw, "uid": uid}))
    calls = []
    def docker(args):
        calls.append(args)
        if args[0] == "network":
            return SimpleNamespace(stdout='[{"Internal":true,"Driver":"bridge"}]')
        if args[0] == "ps" and outcome == "cleanup-failed":
            raise subprocess.CalledProcessError(1, "fixture")
        return SimpleNamespace(stdout="")
    monkeypatch.setattr(strix, "_docker", docker)
    killed = []
    monkeypatch.setattr(strix.os, "killpg", lambda *args: killed.append(args))
    class Process:
        pid = 999999
        waits = 0
        def __init__(self, argv, **kwargs):
            assert "synthetic-fixture" not in str(argv)
            assert kwargs["env"]["LLM_API_KEY"] == "synthetic-fixture"
            target = Path(argv[argv.index("--target") + 1])
            (target / "main.py").write_text("modified ONLY disposable copy")
            if outcome != "missing-report":
                results = kwargs["cwd"] / "strix_runs" / "synthetic"
                results.mkdir(parents=True)
                (results / "run.json").write_text(json.dumps({"status": "completed", "scan_results": {"scan_completed": True}, "llm_usage": {"cost": 1}}))
                if outcome == "findings":
                    (results / "vulnerabilities.json").write_text('[{"id":"fixture"}]')
                else:
                    (results / "findings.sarif").write_text('{"version":"2.1.0","runs":[{"results":[]}]}')
        def wait(self, timeout=None):
            self.waits += 1
            if self.waits == 1:
                if outcome == "timeout":
                    raise subprocess.TimeoutExpired("fixture", 60)
                if outcome == "cancel":
                    raise KeyboardInterrupt()
            return 2 if outcome == "findings" else 0
    monkeypatch.setattr(strix.subprocess, "Popen", Process)
    summary = strix.run(project, job=job, zone="lab", project_id="fixture", uid=uid,
                        policy_root=policy, credential_file=key)
    expected = {"clean": "NO_FINDINGS_REPORTED", "findings": "FINDINGS_REPORTED"}.get(outcome, "INCOMPLETE")
    assert summary["state"] == expected
    assert summary["accepted"] is False
    assert killed and ["ps", "-aq", "--filter", f"label=strix-run-id={job}"] in calls
    assert "synthetic fixture" in (project / "repos/app/main.py").read_text()
    assert "synthetic fixture" in (strix.job_root(project, job) / "snapshot/main.py").read_text()
    assert (project / "evidence/strix" / job / "summary.json").is_file()
    with pytest.raises(ValidationError, match="already attempted"):
        strix.run(project, job=job, zone="lab", project_id="fixture", uid=uid, policy_root=policy, credential_file=key)


def test_root_cannot_run_assessments(project, monkeypatch):
    monkeypatch.setattr(strix.platform, "system", lambda: "Linux")
    monkeypatch.setattr(strix.os, "geteuid", lambda: 0)
    with pytest.raises(SecurityError):
        strix.run(project, job="strix-fixture", zone="lab", project_id="fixture", uid=0,
                  policy_root=project, credential_file=project / "key")


def test_status_does_not_reuse_stale_preparation_state(project):
    plan = prepared(project)
    common = dict(job=plan["job"], zone="lab", project_id="fixture", uid=os.geteuid(), policy_root=project / "policy")
    assert strix.status(project, **common)["state"] == "PREPARED_NOT_AUTHORIZED"
    (strix.job_root(project, plan["job"]) / "execution").mkdir()
    assert strix.status(project, **common)["state"] == "AWAITING_EXECUTION_EVIDENCE"
    evidence = project / "evidence/strix" / plan["job"]
    evidence.mkdir(parents=True)
    (evidence / "summary.json").write_text('{"state":"INCOMPLETE","accepted":false}')
    assert strix.status(project, **common)["state"] == "INCOMPLETE"


@pytest.mark.parametrize("changes", [{"expires_at": 1}, {"source_upload_approved": False}, {"uid": -1}, {"zone": "another"}, {"host_role": "core"}])
def test_invalid_grant_stops_before_any_docker_call(project, monkeypatch, changes):
    plan = prepared(project)
    grant = {**plan, "expires_at": int(strix.time.time()) + 3600, "source_upload_approved": True,
             "dedicated_lab": True, "host_role": "lab", **changes}
    monkeypatch.setattr(strix.platform, "system", lambda: "Linux")
    monkeypatch.setattr(strix, "require_root_owned_directory_chain", lambda path: None)
    monkeypatch.setattr(strix, "read_json", lambda *a, **kw: grant)
    monkeypatch.setattr(strix, "_docker", lambda *a, **kw: pytest.fail("Invalid grant must not reach Docker"))
    with pytest.raises(SecurityError):
        strix.run(project, job=plan["job"], zone="lab", project_id="fixture", uid=os.geteuid(),
                  policy_root=project / "policy", credential_file=project / "key")
