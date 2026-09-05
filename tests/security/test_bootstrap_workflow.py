"""Bootstrap rejection and planning tests; all executable side effects are stubbed."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
BASHES = [path for path in ("/bin/bash", "/opt/homebrew/bin/bash") if Path(path).is_file()]


def executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


@pytest.fixture(params=BASHES, ids=lambda path: "system" if path == "/bin/bash" else "homebrew")
def shell(request):
    return request.param


@pytest.fixture
def harness(tmp_path):
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    repo.mkdir()
    bin_dir.mkdir()
    for name in ("bootstrap.sh", "station.sh"):
        shutil.copy2(ROOT / name, repo / name)
    log = tmp_path / "calls.jsonl"
    preamble = f"#!{sys.executable}\nimport json, os, pathlib, sys\nlog=pathlib.Path({str(log)!r})\n"
    record = "def record(value):\n    with log.open('a') as stream: stream.write(json.dumps(value)+'\\n')\n"
    executable(repo / "station", preamble + record + f"""
args=sys.argv[1:]
entry={{'kind':'kernel','args':args}}
if args[0] in ('plan','apply') and '--spec' in args:
    path=pathlib.Path(args[args.index('--spec')+1])
    entry.update(spec_path=str(path), spec_bytes=path.read_text())
record(entry)
if args[0]=='spec':
    os.execv({str(ROOT / 'station')!r}, [{str(ROOT / 'station')!r}, *args])
if args[0]=='doctor': sys.exit(int(os.environ.get('FIXTURE_DOCTOR_RC','0')))
if args[0] in ('doctor','plan','apply','status','setup'): sys.exit(0)
sys.exit(78)
""")
    executable(bin_dir / "python3", preamble + record + f"""
if len(sys.argv)>1 and sys.argv[1].endswith('/scripts/station_bootstrap_preflight.py'):
    record({{'kind':'preflight'}})
    sys.exit(int(os.environ.get('FIXTURE_PREFLIGHT_RC','0')))
os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
""")
    executable(bin_dir / "awk", preamble + record + """
if sys.argv[-1]=='/etc/os-release':
    print('ubuntu' if '$1 == "ID"' in sys.argv[2] else 'noble')
    sys.exit(0)
sys.exit(79)
""")
    for name in ("apt-get", "curl", "install", "useradd", "usermod", "chown", "systemctl", "rsync", "sudo"):
        executable(bin_dir / name, preamble + record + f"record({{'kind':'forbidden','name':{name!r}}})\nsys.exit(77)\n")
    env = dict(os.environ, PATH=f"{bin_dir}:/usr/bin:/bin", PYTHONDONTWRITEBYTECODE="1")
    def run(shell, script, *args, **extra):
        return subprocess.run([shell, str(repo / script), *args], env=env | extra, cwd=repo,
                              text=True, capture_output=True, timeout=30)
    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return SimpleNamespace(repo=repo, bin=bin_dir, log=log, env=env, run=run, calls=calls,
                           preamble=preamble, record=record)


@pytest.mark.parametrize("args", [
    ["--mode", "invalid"], ["--mode", "team"], ["--host-id"], ["--mode"],
    ["--organization"], ["--project"], ["--env"], ["--host-id", "--mode", "full"],
    ["--mode", "full", "--project", "example"],
    ["--mode", "full", "--organization", "example"],
    ["--mode", "full", "--env", "production"],
])
@pytest.mark.parametrize("command", ["spec", "plan", "bootstrap"])
def test_wrapper_rejects_invalid_input_without_kernel_calls(shell, harness, command, args):
    result = harness.run(shell, "station.sh", command, *args)
    assert result.returncode != 0, result.stdout
    assert not harness.calls(), harness.calls()


@pytest.mark.parametrize("args", [
    ["--mode", "invalid"], ["--mode", "team"], ["--host-id"], ["--mode"],
    ["--organization"], ["--project"], ["--env"], ["--sudo-mode"],
])
def test_bootstrap_rejects_invalid_input_before_preflight(shell, harness, args):
    result = harness.run(shell, "bootstrap.sh", "--plan", *args)
    assert result.returncode != 0
    assert not harness.calls(), harness.calls()


@pytest.mark.parametrize("args,role,host,seed", [
    ([], "core", "station-core-01", None),
    (["--mode", "full", "--host-id", "core-02"], "core", "core-02", None),
    (["--mode", "team", "--organization", "example", "--project", "platform", "--env", "production"],
     "team", "example-station-01", {"category":"ORGANIZATIONS", "name":"example",
      "organization":"example", "project":"platform", "environment":"production"}),
])
def test_wrapper_emits_real_typed_spec(shell, harness, args, role, host, seed):
    result = harness.run(shell, "station.sh", "spec", *args)
    assert result.returncode == 0, result.stderr
    spec = json.loads(result.stdout)
    assert (spec["role"], spec["host_id"], spec["seed"]) == (role, host, seed)


@pytest.mark.parametrize("args,role", [([], "core"), (["--mode", "team", "--organization", "example"], "team")])
def test_unprivileged_bootstrap_plan_never_mutates(shell, harness, args, role):
    result = harness.run(shell, "bootstrap.sh", "--plan", *args)
    assert result.returncode == 0, result.stderr
    assert "PLAN_ONLY" in result.stdout
    calls = harness.calls()
    assert [call["kind"] for call in calls] == ["kernel", "preflight", "kernel", "kernel"]
    assert [call["args"][0] for call in calls if call["kind"] == "kernel"] == ["doctor", "spec", "plan"]
    plan = calls[-1]
    assert json.loads(plan["spec_bytes"])["role"] == role
    assert not Path(plan["spec_path"]).exists(), "Temporary plan must be cleaned up"


def test_bootstrap_stops_when_preflight_rejects(shell, harness):
    result = harness.run(shell, "bootstrap.sh", "--plan", FIXTURE_PREFLIGHT_RC="2")
    assert result.returncode == 2
    assert [call["kind"] for call in harness.calls()] == ["kernel", "preflight"]


def test_bootstrap_stops_when_repository_doctor_rejects(shell, harness):
    result = harness.run(shell, "bootstrap.sh", "--plan", FIXTURE_DOCTOR_RC="2")
    assert result.returncode == 2
    assert [call["kind"] for call in harness.calls()] == ["kernel"]


def test_bootstrap_rejects_invalid_typed_identifier_without_mutation(shell, harness):
    result = harness.run(shell, "bootstrap.sh", "--plan", "--host-id", "bad/host")
    assert result.returncode != 0
    calls = harness.calls()
    assert all(call["kind"] != "forbidden" for call in calls)
    assert not any(call["kind"] == "kernel" and call["args"][0] in ("plan", "apply") for call in calls)


@pytest.mark.parametrize("args", [[], ["--mode", "team", "--organization", "example"]])
def test_wrapper_applies_identical_spec(shell, harness, args):
    executable(harness.bin / "sudo", harness.preamble + harness.record + f"""
args=sys.argv[1:]
assert args[0]=={str(harness.repo / 'station')!r}
record({{'kind':'sudo-stub','args':args}})
os.execv(args[0], args)
""")
    result = harness.run(shell, "station.sh", "bootstrap", *args, "--yes")
    assert result.returncode == 0, result.stderr
    invocations = [call for call in harness.calls() if call["kind"] == "kernel"]
    planned = next(call for call in invocations if call["args"][0] == "plan")
    applied = next(call for call in invocations if call["args"][0] == "apply")
    assert (planned["spec_path"], planned["spec_bytes"]) == (applied["spec_path"], applied["spec_bytes"])
    assert not Path(planned["spec_path"]).exists()


@pytest.fixture
def preflight(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bootstrap_preflight_under_test", ROOT / "scripts/station_bootstrap_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def missing(_name):
        raise KeyError(_name)
    monkeypatch.setattr(module.pwd, "getpwnam", missing)
    monkeypatch.setattr(module.grp, "getgrnam", missing)
    base = tmp_path.resolve()
    repo, home, releases = base / "source", base / "operator", base / "releases"
    repo.mkdir()
    (repo / "VERSION").write_text("11.12\n")
    (repo / "RELEASE_PROVENANCE.json").write_text('{"fixture":true}\n')
    return SimpleNamespace(module=module, repo=repo, home=home, releases=releases)


def test_preflight_does_not_create_missing_targets(preflight):
    preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)
    assert not preflight.home.exists()
    assert not preflight.releases.exists()


@pytest.mark.parametrize("target", ["home", "releases"])
def test_preflight_rejects_symlink_ancestors(preflight, target):
    path = getattr(preflight, target)
    path.symlink_to(preflight.repo, target_is_directory=True)
    with pytest.raises(preflight.module.ValidationError, match="real directory"):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


@pytest.mark.parametrize("field,value", [("pw_uid",0), ("pw_gid",43), ("pw_dir","/different/home")])
def test_preflight_rejects_conflicting_operator(preflight, monkeypatch, field, value):
    values = dict(pw_uid=42, pw_gid=42, pw_dir=str(preflight.home))
    values[field] = value
    monkeypatch.setattr(preflight.module.pwd, "getpwnam", lambda name: SimpleNamespace(**values))
    monkeypatch.setattr(preflight.module.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=42))
    with pytest.raises(preflight.module.ValidationError, match="identity/home/group"):
        preflight.module.check_operator(preflight.home)


def test_preflight_preserves_foreign_checkout(preflight):
    destination = preflight.home / "repos" / "agentik-station"
    destination.mkdir(parents=True)
    work = destination / "operator-work.txt"
    work.write_text("preserve me")
    with pytest.raises(preflight.module.ValidationError, match="checkout already exists"):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)
    assert work.read_text() == "preserve me"


def test_preflight_rejects_same_version_provenance_conflict(preflight):
    published = preflight.releases / "11.12"
    published.mkdir(parents=True)
    (published / "RELEASE_PROVENANCE.json").write_text("different")
    with pytest.raises(preflight.module.ValidationError, match="Same-version"):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


def test_preflight_rejects_missing_published_provenance(preflight):
    published = preflight.releases / "11.12"
    published.mkdir(parents=True)
    with pytest.raises(preflight.module.ValidationError, match="no provenance"):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


def test_preflight_rejects_installed_file_drift_even_with_matching_provenance(preflight):
    published = preflight.releases / "11.12"
    shutil.copytree(preflight.repo, published)
    (published / "VERSION").write_text("11.11\n")
    with pytest.raises(preflight.module.ValidationError):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


def test_preflight_accepts_matching_release_while_ignoring_unpublished_source_metadata(preflight):
    published = preflight.releases / "11.12"
    shutil.copytree(preflight.repo, published)
    (preflight.repo / ".git").mkdir()
    (preflight.repo / ".git" / "config").write_text("local checkout metadata")
    preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


@pytest.mark.parametrize("relative", [".local", ".config", ".profile"])
def test_preflight_rejects_symlinked_operator_install_targets(preflight, relative):
    preflight.home.mkdir()
    (preflight.home / relative).symlink_to(preflight.repo, target_is_directory=True)
    with pytest.raises(preflight.module.ValidationError):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


def test_preflight_rejects_nonregular_profile(preflight):
    (preflight.home / ".profile").mkdir(parents=True)
    with pytest.raises(preflight.module.ValidationError, match="regular file"):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)
