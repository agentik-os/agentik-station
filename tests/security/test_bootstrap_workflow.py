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
    assert "installation: full-stack" in result.stdout
    assert "AI stack:     install-all" in result.stdout
    calls = harness.calls()
    assert [call["kind"] for call in calls] == ["kernel", "preflight", "kernel", "kernel"]
    assert [call["args"][0] for call in calls if call["kind"] == "kernel"] == ["doctor", "spec", "plan"]
    plan = calls[-1]
    assert json.loads(plan["spec_bytes"])["role"] == role
    assert not Path(plan["spec_path"]).exists(), "Temporary plan must be cleaned up"


SOFTWARE_SKIPS = (
    "--skip-hermes", "--skip-toolchain", "--skip-codex", "--skip-agk-tui",
    "--skip-voice", "--skip-scrapegraphai", "--skip-crawl4ai",
)


@pytest.mark.parametrize("flag", SOFTWARE_SKIPS)
def test_software_skips_require_explicit_minimal_before_preflight(shell, harness, flag):
    result = harness.run(shell, "bootstrap.sh", "--plan", flag)
    assert result.returncode == 2
    assert "software skips require --minimal" in result.stderr
    assert not harness.calls()


@pytest.mark.parametrize("before", [False, True])
@pytest.mark.parametrize("flag", SOFTWARE_SKIPS)
def test_minimal_allows_software_skips_independent_of_argument_order(shell, harness, flag, before):
    args = ["--minimal", flag] if before else [flag, "--minimal"]
    result = harness.run(shell, "bootstrap.sh", "--plan", *args)
    assert result.returncode == 0, result.stderr
    assert "installation: minimal-partial" in result.stdout
    assert "AI stack:     omitted (--minimal)" in result.stdout
    assert [call["kind"] for call in harness.calls()] == ["kernel", "preflight", "kernel", "kernel"]


@pytest.mark.parametrize("args", [
    ["--minimal", "--with-ai-stack"], ["--with-ai-stack", "--minimal"],
])
def test_explicit_full_and_minimal_conflict_before_preflight(shell, harness, args):
    result = harness.run(shell, "bootstrap.sh", "--plan", *args)
    assert result.returncode == 2
    assert "mutually exclusive" in result.stderr
    assert not harness.calls()


@pytest.mark.parametrize("args", [[], ["--with-ai-stack"], ["--minimal"]])
def test_scheduled_update_opt_out_preserves_selected_software_profile(shell, harness, args):
    result = harness.run(shell, "bootstrap.sh", "--plan", *args, "--skip-hermes-auto-update")
    assert result.returncode == 0, result.stderr
    profile = "minimal-partial" if "--minimal" in args else "full-stack"
    assert f"installation: {profile}" in result.stdout
    assert "Hermes:       install" in result.stdout
    assert "Hermes update: disabled" in result.stdout
    assert "Toolchain:    install" in result.stdout
    assert "Voice:        OpenAI audio + local Parakeet" in result.stdout
    assert all(call["kind"] != "forbidden" for call in harness.calls())


def test_full_stack_failure_never_records_success_or_reaches_later_stages(shell, tmp_path):
    source = (ROOT / "bootstrap.sh").read_text()
    section = source.split("# Runtime services are installed only after", 1)[1]
    section = section[section.index('if [[ "$INSTALL_AI_STACK" -eq 1 ]]'):]
    section = section.split('if [[ "$INSTALL_HERMES" -eq 1 ]]', 1)[0]
    immutable_installer = "/opt/station/current/scripts/station_deps_install.sh"
    assert f"{immutable_installer} --all" in section
    # Production must use the published release. Substitute only that exact
    # executable in this extracted block so the fixture cannot touch the Host.
    section = section.replace(immutable_installer, '"$REPO_DIR/scripts/station_deps_install.sh"', 1)
    scripts = tmp_path / "repo" / "scripts"
    scripts.mkdir(parents=True)
    executable(scripts / "station_deps_install.sh", f"#!{shell}\nexit 43\n")
    result = subprocess.run(
        [shell, "-c", "set -Eeuo pipefail\n"
         "bootstrap_checkpoint() { printf '%s %s\\n' \"$1\" \"$2\"; };\n"
         + section + "printf 'LATER_STAGES_WOULD_RUN\\n'\n"],
        env=dict(os.environ, INSTALL_AI_STACK="1", INSTALL_VOICE="1", STATION_USER="fixture",
                 STATION_HOME=str(tmp_path / "untouched-home"), REPO_DIR=str(scripts.parent)),
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 43
    assert result.stdout.splitlines() == ["ai-stack running"]
    assert not (tmp_path / "untouched-home").exists()


@pytest.mark.parametrize("ai_stack,audit_rc", [(1, 0), (1, 41), (0, 41)])
def test_final_full_audit_fails_closed_after_setup_before_updater_and_completion(shell, tmp_path, ai_stack, audit_rc):
    source = (ROOT / "bootstrap.sh").read_text()
    section = source.split("# Runtime services are installed only after", 1)[1]
    section = section[section.index('if [[ "$INSTALL_AI_STACK" -eq 1 ]]'):]
    section = section.split("bootstrap_checkpoint tool-inventory running", 1)[0]
    immutable_installer = "/opt/station/current/scripts/station_deps_install.sh"
    immutable_audit = '/opt/station/current/station deps full-check --operator "$STATION_USER"'
    assert f"{immutable_installer} --all" in section
    assert immutable_audit in section
    assert section.index("bootstrap_checkpoint guided-setup success") < section.index(immutable_audit)
    assert section.index(immutable_audit) < section.index("bootstrap_checkpoint hermes-update-timer running")
    # Substitute only exact reviewed executables; this extracted block cannot
    # reach a real Host, service, enrolled account or installation.
    section = section.replace(immutable_installer, '"$REPO_DIR/scripts/station_deps_install.sh"', 1)
    section = section.replace(immutable_audit, '"$REPO_DIR/station" deps full-check --operator "$STATION_USER"', 1)
    scripts = tmp_path / "repo" / "scripts"
    scripts.mkdir(parents=True)
    executable(scripts / "station_deps_install.sh", f"#!{shell}\nprintf 'INSTALL %s\\n' \"$*\"\nexit 0\n")
    executable(scripts / "station_guided_setup_enable.sh", f"#!{shell}\nprintf 'GUIDED_SETUP %s\\n' \"$*\"\nexit 0\n")
    executable(scripts.parent / "station", f'''#!{shell}
[[ "$*" == 'deps full-check --operator fixture' ]] || exit 81
printf 'FULL_AUDIT\\n'
exit "$AUDIT_RC"
''')
    trap_source = "finish_bootstrap(){" + source.split("finish_bootstrap(){", 1)[1].split(
        "bootstrap_checkpoint system-packages running", 1)[0]
    finalizer = "bootstrap_state finish --attempt" + source.split("bootstrap_state finish --attempt", 1)[1].split(
        "cat <<EOF", 1)[0]
    harness = '''set -Eeuo pipefail
bootstrap_finished=0
bootstrap_interrupted=0
bootstrap_attempt=op-fixture
bootstrap_checkpoint() { printf 'CHECKPOINT %s %s\\n' "$1" "$2"; }
bootstrap_state() { printf 'STATE %s\\n' "$*"; }
cleanup_bootstrap_plan() { :; }
'''
    result = subprocess.run(
        [shell, "-c", harness + trap_source + section + finalizer + "printf 'AGK Station bootstrap complete.\\n'\n"],
        env=dict(os.environ, INSTALL_AI_STACK=str(ai_stack), INSTALL_VOICE="1", INSTALL_HERMES="1",
                 INSTALL_HERMES_AUTO_UPDATE="1", STATION_USER="fixture", AUDIT_RC=str(audit_rc),
                 STATION_HOME=str(tmp_path / "untouched-home"), REPO_DIR=str(scripts.parent)),
        text=True, capture_output=True, timeout=10,
    )
    expected_rc = audit_rc if ai_stack else 0
    assert result.returncode == expected_rc, result.stderr
    lines = result.stdout.splitlines()
    assert "GUIDED_SETUP --if-enrolled" in lines
    assert ("FULL_AUDIT" in lines) == bool(ai_stack)
    assert ("CHECKPOINT full-stack-verify running" in lines) == bool(ai_stack)
    assert ("CHECKPOINT full-stack-verify success" in lines) == bool(ai_stack and not audit_rc)
    assert ("INSTALL --enable-hermes-auto-update" in lines) == (expected_rc == 0)
    assert ("STATE finish --attempt op-fixture --exit-code 0" in lines) == (expected_rc == 0)
    assert ("AGK Station bootstrap complete." in lines) == (expected_rc == 0)
    if expected_rc:
        assert f"STATE finish --attempt op-fixture --exit-code {expected_rc}" in lines
        assert "CHECKPOINT ai-stack success" in lines
        assert "CHECKPOINT hermes-update-timer running" not in lines
    assert not (tmp_path / "untouched-home").exists()


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


@pytest.mark.parametrize("relative", [".local", ".local/share", ".local/lib", ".config", ".profile"])
def test_preflight_rejects_symlinked_operator_install_targets(preflight, relative):
    preflight.home.mkdir()
    (preflight.home / relative).parent.mkdir(parents=True, exist_ok=True)
    (preflight.home / relative).symlink_to(preflight.repo, target_is_directory=True)
    with pytest.raises(preflight.module.ValidationError):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


def test_preflight_rejects_nonregular_profile(preflight):
    (preflight.home / ".profile").mkdir(parents=True)
    with pytest.raises(preflight.module.ValidationError, match="regular file"):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


@pytest.mark.parametrize("relative", ["tools", "tools/hermes", "tools/hermes/current", "tools/hermes/python", "tools/hermes/python/bin"])
def test_preflight_rejects_symlinked_shared_hermes_code(preflight, relative):
    target = preflight.releases.parent / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(preflight.repo, target_is_directory=True)
    with pytest.raises(preflight.module.ValidationError, match="real directory"):
        preflight.module.check_existing_targets(preflight.repo, preflight.home, preflight.releases)


def test_operator_scaffolding_explicitly_owns_intermediate_local_directories(shell, tmp_path):
    source = (ROOT / "bootstrap.sh").read_text()
    section = source.split("bootstrap_checkpoint operator-account running\n", 1)[1].split(
        "bootstrap_checkpoint operator-account success", 1)[0]
    command = section[section.index("\ninstall -d ") + 1:]
    home = tmp_path / "operator with spaces"
    result = subprocess.run([shell, "-c", "install() { printf '%s\\0' \"$@\"; };\n" + command],
                            env=dict(os.environ, STATION_USER="fixture", STATION_HOME=str(home)),
                            text=True, capture_output=True, check=True)
    operands = result.stdout.split("\0")
    assert operands[:7] == ["-d", "-m", "0750", "-o", "fixture", "-g", "fixture"]
    assert set(operands[7:-1]) == {str(home / relative) for relative in
                                 ("repos", ".local", ".local/bin", ".local/share", ".local/lib", ".config")}


def test_native_installer_receives_shared_managed_python_without_changing_private_home(shell, tmp_path):
    source = (ROOT / "bootstrap.sh").read_text()
    start = source.index('  sudo -u "$STATION_USER" -H env HERMES_HOME=')
    end = source.index('\n  [[ -x "$STATION_HOME/.local/bin/hermes" ]]', start)
    command = source[start:end]
    installer = tmp_path / "upstream fixture.sh"
    installer.write_text("[[ \" $* \" == *\" --force-commit \"* ]] || exit 81\n"
                         "printf '%s\\n' \"$HERMES_HOME\" \"$UV_PYTHON_INSTALL_DIR\" \"$UV_PYTHON_BIN_DIR\" \"$UV_PYTHON_PREFERENCE\"\n")
    home = tmp_path / "private operator"
    shared = tmp_path / "shared code" / "python"
    result = subprocess.run([shell, "-c", "sudo() { shift 3; \"$@\"; };\n" + command],
                            env=dict(os.environ, STATION_USER="fixture", STATION_HOME=str(home),
                                     hermes_python_dir=str(shared), hermes_install_dir=str(shared.parent / "current"),
                                     HERMES_COMMIT="0" * 40, tmp=str(installer)),
                            text=True, capture_output=True, check=True)
    assert result.stdout.splitlines() == [str(home / ".hermes"), str(shared), str(shared / "bin"), "only-managed"]
    assert not home.exists()


@pytest.fixture
def hermes_retry(tmp_path):
    repo = tmp_path / "shared hermes"
    repo.mkdir()
    home = tmp_path / "private operator"
    (home / ".hermes").mkdir(parents=True)
    for name in (".env", "config.yaml", "SOUL.md"):
        (home / ".hermes" / name).write_text("preserve this user data\n")

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              check=True, env=dict(os.environ, GIT_CONFIG_NOSYSTEM="1")) .stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Fixture")
    (repo / "tracked.txt").write_text("reviewed\n")
    (repo / ".gitignore").write_text("venv/\nnode_modules/\n.env\n")
    git("add", ".")
    git("commit", "-m", "Reviewed fixture")
    pin = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", pin)
    git("checkout", "--detach", pin)
    source = (ROOT / "bootstrap.sh").read_text()
    functions = source.split("# Pinned Hermes retry checks:", 1)[1].split("# End pinned Hermes retry checks.", 1)[0]
    functions = functions[functions.index("hermes_git()") :]

    def run(shell, command="check_hermes_retry"):
        return subprocess.run([shell, "-c", "set -euo pipefail\nsudo() { shift 3; \"$@\"; };\n" + functions + command],
                              capture_output=True, text=True, timeout=10,
                              env=dict(os.environ, STATION_USER="fixture", STATION_HOME=str(home),
                                       hermes_install_dir=str(repo), HERMES_COMMIT=pin))

    return SimpleNamespace(repo=repo, home=home, git=git, pin=pin, run=run)


def test_clean_pinned_hermes_retry_preserves_user_configuration(shell, hermes_retry):
    (hermes_retry.repo / "venv").mkdir()
    (hermes_retry.repo / "venv" / "generated").write_text("managed environment")
    result = hermes_retry.run(shell)
    assert result.returncode == 0, result.stderr
    assert hermes_retry.git("rev-parse", "HEAD") == hermes_retry.pin
    for name in (".env", "config.yaml", "SOUL.md"):
        assert (hermes_retry.home / ".hermes" / name).read_text() == "preserve this user data\n"


def test_missing_hermes_checkout_is_allowed_without_creating_it(shell, hermes_retry):
    preserved = hermes_retry.repo.with_name("preserved fixture")
    hermes_retry.repo.rename(preserved)
    result = hermes_retry.run(shell)
    assert result.returncode == 0, result.stderr
    assert not hermes_retry.repo.exists()
    assert preserved.is_dir()


@pytest.mark.parametrize("state", ["tracked-edit", "untracked", "unpinned", "main-divergence", "stash", "source-env"])
def test_hermes_retry_refuses_unreviewed_state_without_changing_it(shell, hermes_retry, state):
    repo, git = hermes_retry.repo, hermes_retry.git
    if state == "tracked-edit":
        (repo / "tracked.txt").write_text("private change\n")
    elif state == "untracked":
        (repo / "work.txt").write_text("private change\n")
    elif state in {"unpinned", "main-divergence"}:
        if state == "main-divergence":
            git("checkout", "main")
        (repo / "tracked.txt").write_text("private commit\n")
        git("commit", "-am", "Local work")
        if state == "main-divergence":
            git("checkout", "--detach", hermes_retry.pin)
    elif state == "stash":
        (repo / "tracked.txt").write_text("private stash\n")
        git("stash", "push", "-m", "Local work")
    else:
        (repo / ".env").write_text("SECRET_SENTINEL=private\n")
    before = (git("rev-parse", "HEAD"), git("status", "--porcelain", "--untracked-files=all"),
              git("stash", "list", "--format=%H"))
    result = hermes_retry.run(shell, "check_hermes_retry\nprintf 'UPSTREAM_WOULD_RUN\\n'")
    assert result.returncode != 0
    assert "UPSTREAM_WOULD_RUN" not in result.stdout
    assert "SECRET_SENTINEL" not in result.stdout + result.stderr
    after = (git("rev-parse", "HEAD"), git("status", "--porcelain", "--untracked-files=all"),
             git("stash", "list", "--format=%H"))
    assert after == before
    if state == "source-env":
        assert (repo / ".env").read_text() == "SECRET_SENTINEL=private\n"


@pytest.mark.parametrize("state", ["incomplete", "checkout-link", "config-link", "config-directory"])
def test_hermes_retry_preserves_incomplete_or_unsafe_paths(shell, hermes_retry, state):
    if state in {"incomplete", "checkout-link"}:
        saved = hermes_retry.repo.with_name("preserved checkout")
        hermes_retry.repo.rename(saved)
        if state == "incomplete":
            hermes_retry.repo.mkdir()
            (hermes_retry.repo / "partial").write_text("keep")
        else:
            hermes_retry.repo.symlink_to(saved, target_is_directory=True)
    else:
        config = hermes_retry.home / ".hermes/config.yaml"
        saved = config.with_name("preserved.yaml")
        config.rename(saved)
        if state == "config-link":
            config.symlink_to(saved)
        else:
            config.mkdir()
    result = hermes_retry.run(shell)
    assert result.returncode != 0
    assert saved.exists()
    if state == "incomplete":
        assert (hermes_retry.repo / "partial").read_text() == "keep"


def test_installer_success_with_wrong_head_is_rejected_before_stage_success(shell, hermes_retry):
    source = (ROOT / "bootstrap.sh").read_text()
    post = source.split("# Upstream may otherwise ignore --commit after fetching a newer main.", 1)[1]
    post = post.split('  install -m 0755 -o root -g root "$STATION_HOME/.local/bin/hermes"', 1)[0]
    (hermes_retry.repo / "tracked.txt").write_text("unexpected upstream version\n")
    hermes_retry.git("commit", "-am", "Unexpected version")
    result = hermes_retry.run(shell, post + "printf 'STAGE_SUCCESS\\n'")
    assert result.returncode != 0
    assert "STAGE_SUCCESS" not in result.stdout


def test_hermes_venv_sanity_rejects_private_operator_interpreter(shell, hermes_retry):
    source = (ROOT / "bootstrap.sh").read_text()
    probe = source.split("# Upstream may otherwise ignore --commit after fetching a newer main.", 1)[1]
    probe = probe.split('  install -m 0755 -o root -g root "$STATION_HOME/.local/bin/hermes"', 1)[0]
    bindir = hermes_retry.repo / "venv/bin"
    bindir.mkdir(parents=True)
    (bindir / "python").symlink_to(sys.executable)
    shared = hermes_retry.repo.parent / "shared-python"
    shared.mkdir()
    result = hermes_retry.run(shell, f"hermes_python_dir={str(shared)!r}\n" + probe + "printf 'STAGE_SUCCESS\\n'")
    assert result.returncode != 0
    assert "reviewed shared Python" in result.stderr
    assert "STAGE_SUCCESS" not in result.stdout


def test_bootstrap_rechecks_source_after_external_builds_before_kernel_publication():
    source = (ROOT / "bootstrap.sh").read_text()
    build = source.index("bootstrap_checkpoint agk-tui success")
    apply_stage = source.index("bootstrap_checkpoint kernel-apply running", build)
    doctor = source.index('"$REPO_DIR/station" doctor --repo', apply_stage)
    apply = source.index('"$REPO_DIR/station" apply --spec "$bootstrap_spec"', doctor)
    assert build < apply_stage < doctor < apply
