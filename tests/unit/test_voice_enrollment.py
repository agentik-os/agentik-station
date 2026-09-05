"""Real Station authority fixtures; all native commands are isolated fakes."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from agentik_station import voice
from agentik_station.errors import SecurityError, ValidationError

# Reuse the full no-network canonical Zone/instance fixtures, including trusted
# ledgers and immutable distribution checks. Keep the temporary import path local.
_security_tests = str(Path(__file__).resolve().parents[1] / "security")
sys.path.insert(0, _security_tests)
try:
    from test_os_instances import runtime as instance_runtime
    from test_os_lifecycle import runtime as legacy_runtime
finally:
    sys.path.remove(_security_tests)


REVISION = "a" * 40


@pytest.fixture
def enrollment(instance_runtime, monkeypatch):
    data = instance_runtime
    data.install()
    profile = data.native()
    config_path = profile / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["stt"] = {"provider": "openai", "enabled": True, "openai": {"api_key": "PRIVATE-CONFIG-SENTINEL"}}
    config_path.write_text(yaml.safe_dump(config))
    (profile / ".env").write_text("OTHER_SECRET=PRIVATE-ENV-SENTINEL\n")
    data.original_config = config_path.read_bytes()
    data.original_env = (profile / ".env").read_bytes()
    data.voice_calls = []
    data.policy_calls = []
    data.effective = {}
    data.probe_failure = None
    data.native_path_reply = None
    data.fail_step = None
    data.exception = None
    data.skip_write = None
    data.config_path = config_path
    data.config = lambda: yaml.safe_load(config_path.read_text())
    data.write_config = lambda value: config_path.write_text(yaml.safe_dump(value))
    data.options = dict(paths=data.paths, zone=data.zone, instance_id="alpha", role="director",
                        revision=REVISION, hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
    data.plan = lambda **kwargs: voice.prepare_voice_enrollment(**{**data.options, **kwargs})
    data.enroll = lambda **kwargs: voice.enroll_voice_profile(**{**data.options, **kwargs})

    def run(argv, **kwargs):
        assert argv[:6] == ["/fake/runuser", "--user", data.zone["unix_user"], "--", "/usr/bin/env", "-i"]
        assert f"HOME={Path(data.zone['state_root']) / 'home'}" in argv
        assert f"HERMES_HOME={profile.parent.parent}" in argv
        args = argv[argv.index("/fake/hermes") + 1:]
        assert args[:2] == ["--profile", profile.name]
        command = args[2:]
        assert "--force" not in args and "--all" not in args
        assert "PRIVATE" not in " ".join(argv)
        if command == ["config", "path"]:
            data.policy_calls.append((argv, kwargs))
            assert kwargs == dict(timeout=60, capture=True)
            return data.native_path_reply or SimpleNamespace(
                returncode=0, stdout=str(config_path).encode() + b"\n", stderr=b"",
            )
        if command[:2] == ["config", "get"]:
            data.policy_calls.append((argv, kwargs))
            assert kwargs == dict(timeout=60, capture=True)
            if data.probe_failure is not None:
                return data.probe_failure
            key = command[2]
            assert command[-1] == "--json"
            missing = object()
            if key in data.effective:
                value = data.effective[key]
            elif "\\" in key:
                value = missing
            else:
                value = data.config()
                for part in key.split("."):
                    value = value.get(part, missing) if isinstance(value, dict) else missing
            if value is missing:
                return SimpleNamespace(returncode=1, stdout=b"", stderr=f"Config key not set: {key}\n".encode())
            return SimpleNamespace(returncode=0, stdout=json.dumps(value).encode() + b"\n", stderr=b"")
        data.voice_calls.append((argv, kwargs))
        assert kwargs == dict(timeout=300, capture=False)
        step = len(data.voice_calls)
        if data.exception and step == data.fail_step:
            raise data.exception
        if step == data.fail_step:
            return SimpleNamespace(returncode=17, stdout="PRIVATE-OUTPUT", stderr="PRIVATE-ERROR")
        if step == data.skip_write:
            return SimpleNamespace(returncode=0)
        value = data.config()
        if command[:2] == ["plugins", "install"]:
            assert command == ["plugins", "install", voice.SOURCE, "--ref", REVISION, "--no-enable"]
            (profile / "plugins" / voice.PLUGIN).mkdir()
            (profile / "plugins" / voice.PLUGIN / "plugin.yaml").write_text("name: station-voice\n")
            (profile / "plugins/.install-metadata.json").write_text(json.dumps({voice.PLUGIN: {
                "source": voice.SOURCE, "revision": REVISION, "pinned": True}}))
        elif command[:2] == ["plugins", "doctor"]:
            assert command == ["plugins", "doctor", "--ci", voice.PLUGIN]
        elif command[:2] == ["plugins", "enable"]:
            assert command == ["plugins", "enable", "--no-allow-tool-override", voice.PLUGIN]
            value["plugins"]["enabled"].append(voice.PLUGIN)
            value["plugins"]["entries"][voice.PLUGIN] = {"allow_tool_override": False}
            data.write_config(value)
        elif command[:3] == ["config", "set", f"stt.{voice.PROVIDER}.model"]:
            value["stt"][voice.PROVIDER] = {"model": voice.MODEL}
            data.write_config(value)
        elif command == ["config", "set", "stt.provider", voice.PROVIDER]:
            value["stt"]["provider"] = voice.PROVIDER
            data.write_config(value)
        else:
            raise AssertionError(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(voice, "run_bounded_native", run)
    return data


def test_prepare_is_pure_one_role_plan_and_never_exposes_secrets(enrollment):
    plan = enrollment.plan()
    assert plan["state"] == "PREPARED" and plan["operational"] is False
    assert plan["profile"] == enrollment.native().name
    assert plan["os_version"] == "11.12"
    assert not enrollment.voice_calls
    assert not enrollment.policy_calls
    assert enrollment.config_path.read_bytes() == enrollment.original_config
    assert "PRIVATE" not in json.dumps(plan)
    assert [step["id"] for step in plan["steps"]] == ["install", "doctor", "enable", "model", "select"]
    assert plan["steps"][-1]["argv"][-4:] == ["config", "set", "stt.provider", voice.PROVIDER]
    assert not (enrollment.native() / "plugins" / voice.PLUGIN).exists()


def test_enrollment_only_changes_selected_profile_preserves_credentials_and_distribution(enrollment):
    sibling = enrollment.native("worker")
    before = (sibling / "config.yaml").read_bytes()
    bundle = json.loads(enrollment.ledger.read_text())["compiled_distribution"]
    bundle_before = {str(p): p.read_bytes() for p in Path(bundle).rglob("*") if p.is_file()}
    result = enrollment.enroll()
    assert result["state"] == "CONFIGURED" and result["operational"] is False
    assert len(result["steps"]) == 6 and len(enrollment.voice_calls) == 5
    assert "PRIVATE" not in json.dumps(result)
    assert (sibling / "config.yaml").read_bytes() == before
    assert (enrollment.native() / ".env").read_bytes() == enrollment.original_env
    actual = enrollment.config()
    assert actual["stt"]["openai"]["api_key"] == "PRIVATE-CONFIG-SENTINEL"
    assert actual["stt"]["enabled"] is True
    assert bundle_before == {str(p): p.read_bytes() for p in Path(bundle).rglob("*") if p.is_file()}
    assert enrollment.load(require_configured=True)["state"] == "CONFIGURED"
    with pytest.raises(ValidationError, match="already exists"):
        enrollment.enroll()


@pytest.mark.parametrize("value", [None, "", "../director", "default", "worker-other", "DIRECTOR"])
def test_role_is_explicit_and_exactly_bound(enrollment, value):
    with pytest.raises((SecurityError, ValidationError)):
        enrollment.plan(role=value)
    assert not enrollment.voice_calls


@pytest.mark.parametrize("value", [None, "", "main", "a" * 39, "A" * 40, "a" * 41, "../" + "a" * 40])
def test_revision_is_exact_immutable_commit(enrollment, value):
    with pytest.raises(ValidationError):
        enrollment.plan(revision=value)


@pytest.mark.parametrize("field", ["state_root", "hermes_home", "unix_user", "human_root", "id"])
def test_zone_authority_cannot_be_overridden(enrollment, field):
    zone = {**enrollment.zone, field: "another"}
    with pytest.raises((SecurityError, ValidationError, OSError)):
        enrollment.plan(zone=zone)
    assert not enrollment.voice_calls


@pytest.mark.parametrize("section,key,value", [
    ("plugins", "scan_on_install", False), ("plugins", "scan_on_install", "true"),
    ("stt", "enabled", False), ("stt", "enabled", "false"), ("stt", "enabled", None),
    ("stt", "provider", "local"), ("stt", "provider", None),
    ("stt", "provider", []), ("plugins", "disabled", None),
    ("plugins", "entries", {"station-web": "invalid"}),
    ("stt", "providers", {voice.PROVIDER: {"type": "command", "command": "other"}}),
    ("stt", voice.PROVIDER, {"model": "user-model"}),
])
def test_disabled_scanning_stt_and_conflicting_provider_choices_refused(enrollment, section, key, value):
    config = enrollment.config()
    config[section][key] = value
    enrollment.write_config(config)
    before = enrollment.config_path.read_bytes()
    with pytest.raises((SecurityError, ValidationError)):
        enrollment.enroll()
    assert not enrollment.voice_calls and enrollment.config_path.read_bytes() == before


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "dangling", "fifo", "metadata", "enabled", "disabled", "entries"])
def test_existing_plugin_or_policy_is_never_replaced(enrollment, kind):
    target = enrollment.native() / "plugins" / voice.PLUGIN
    if kind == "directory":
        target.mkdir()
    elif kind == "file":
        target.write_text("preserve")
    elif kind in {"symlink", "dangling"}:
        target.symlink_to(enrollment.config_path if kind == "symlink" else target.with_name("missing"))
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind == "metadata":
        (target.parent / ".install-metadata.json").write_text(json.dumps({voice.PLUGIN: {"source": "keep"}}))
    else:
        config = enrollment.config()
        config["plugins"][kind] = {voice.PLUGIN: {}} if kind == "entries" else [voice.PLUGIN, "station-web"]
        enrollment.write_config(config)
    with pytest.raises((SecurityError, ValidationError)):
        enrollment.plan()
    assert not enrollment.voice_calls


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "large", "duplicate", "writable"])
def test_profile_config_uses_bounded_nofollow_reader(enrollment, kind):
    path = enrollment.config_path
    if kind in {"symlink", "hardlink", "fifo"}:
        path.rename(path.with_name("saved.yaml"))
        if kind == "symlink":
            path.symlink_to(path.with_name("saved.yaml"))
        elif kind == "hardlink":
            os.link(path.with_name("saved.yaml"), path)
        else:
            os.mkfifo(path)
    elif kind == "large":
        path.write_text("x" * (2 * 1024 * 1024 + 1))
    elif kind == "duplicate":
        path.write_text(path.read_text() + "stt: {}\n")
    else:
        path.chmod(0o666)
    with pytest.raises((SecurityError, ValidationError, OSError)):
        enrollment.plan()
    assert not enrollment.voice_calls


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5])
def test_native_failures_stop_without_claiming_rollback_or_leaking_output(enrollment, step):
    enrollment.fail_step = step
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE" and result["operational"] is False
    assert len(enrollment.voice_calls) == step
    assert result["steps"][-1]["returncode"] == 17
    assert enrollment.config()["stt"]["provider"] == "openai"
    assert "PRIVATE" not in json.dumps(result)
    assert (enrollment.native() / ".env").read_bytes() == enrollment.original_env


@pytest.mark.parametrize("exception,expected", [
    (OSError("PRIVATE-ERROR"), 127),
    (subprocess.SubprocessError("PRIVATE-OVERFLOW"), 125),
    (subprocess.TimeoutExpired("PRIVATE-COMMAND", 300, output="PRIVATE-OUTPUT"), 124),
])
def test_native_exception_details_are_never_returned(enrollment, exception, expected):
    enrollment.fail_step, enrollment.exception = 1, exception
    result = enrollment.enroll()
    assert result["steps"][-1]["returncode"] == expected
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("step", [1, 3, 4, 5])
def test_zero_exit_without_required_native_readback_never_counts_as_configured(enrollment, step):
    enrollment.skip_write = step
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE"
    assert result["steps"][-1]["status"] == "BLOCKED"


@pytest.mark.parametrize("binary", ["relative", "../hermes", "/tmp/../hermes", "", "\x00"])
def test_executable_paths_cannot_be_options_or_traversal(enrollment, binary):
    with pytest.raises(ValidationError):
        enrollment.plan(hermes_binary=binary)


@pytest.mark.parametrize("flag", ["--zone", "--instance", "--role", "--revision"])
def test_cli_requires_each_explicit_scope_field(flag):
    from agentik_station.cli import build_parser
    options = ["--zone", "lab", "--instance", "alpha", "--role", "director", "--revision", REVISION]
    index = options.index(flag)
    del options[index:index + 2]
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["voice", "setup", *options])
    assert exc.value.code == 2


@pytest.mark.parametrize("plan,state,expected", [(True, "PREPARED", 0), (False, "INCOMPLETE", 1), (False, "CONFIGURED", 0)])
def test_cli_uses_explicit_scope_and_reports_incomplete(monkeypatch, capsys, plan, state, expected):
    from agentik_station import cli
    calls = []
    def action(paths, **kwargs):
        calls.append((paths, kwargs))
        return {"state": state, "operational": False}
    monkeypatch.setattr(voice, "prepare_voice_enrollment" if plan else "enroll_voice_profile", action)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/fake/" + name)
    monkeypatch.setattr(cli, "_load_zone_record", lambda name: {"id": name})
    argv = ["voice", "setup", "--zone", "lab", "--instance", "alpha", "--role", "director", "--revision", REVISION]
    if plan:
        argv.append("--plan")
    assert cli.main(argv) == expected
    assert calls[0][1] == dict(zone={"id": "lab"}, instance_id="alpha", role="director", revision=REVISION,
                               hermes_binary="/fake/hermes", runuser_binary="/fake/runuser")
    assert json.loads(capsys.readouterr().out)["state"] == state


@pytest.mark.parametrize("exception", [OSError("PRIVATE-PATH-ERROR"), ValueError("PRIVATE-VALUE"),
                                       subprocess.SubprocessError("PRIVATE-NATIVE-ERROR")])
def test_cli_sanitizes_preflight_and_native_exception_details(monkeypatch, capsys, exception):
    from agentik_station import cli
    def blocked(paths, **kwargs):
        raise exception
    monkeypatch.setattr(voice, "prepare_voice_enrollment", blocked)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/fake/" + name)
    monkeypatch.setattr(cli, "_load_zone_record", lambda name: {"id": name})
    code = cli.main(["voice", "setup", "--zone", "lab", "--instance", "alpha", "--role", "director",
                     "--revision", REVISION, "--plan"])
    assert code == 2
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err
    assert "inspect its native state" in output.err


@pytest.mark.parametrize("key,value", [
    ("plugins.scan_on_install", False), ("plugins.scan_on_install", "true"),
    ("stt.enabled", False), ("stt.provider", "managed-vendor"),
    (f"stt.providers.{voice.PROVIDER}", {"type": "command"}),
    (f"stt.{voice.PROVIDER}.model", "managed-model"),
])
def test_effective_managed_overrides_block_before_any_mutation(enrollment, key, value):
    enrollment.effective[key] = value
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE" and result["steps"][-1]["status"] == "BLOCKED"
    assert not enrollment.voice_calls
    assert enrollment.config_path.read_bytes() == enrollment.original_config


@pytest.mark.parametrize("key", [
    "plugins\\.scan_on_install", "stt\\.provider", "stt\\.station-openai-parakeet",
    "stt\\.station-openai-parakeet\\.model", "stt.station-openai-parakeet\\.model",
])
def test_effective_literal_dotted_keys_cannot_spoof_nested_policy(enrollment, key):
    enrollment.effective[key] = "PRIVATE-MANAGED-VALUE"
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE" and not enrollment.voice_calls
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("reply", [
    SimpleNamespace(returncode=1, stdout=b"", stderr=b"PRIVATE-UNRELATED-ERROR"),
    SimpleNamespace(returncode=1, stdout=b"PRIVATE-OUTPUT", stderr=b"Config key not set: plugins\\.scan_on_install\n"),
    SimpleNamespace(returncode=0, stdout=b"PRIVATE-NONJSON", stderr=b""),
    SimpleNamespace(returncode=0, stdout=b"true\n", stderr=b"PRIVATE-ERROR"),
    SimpleNamespace(returncode=0, stdout=b"\xff", stderr=b""),
    SimpleNamespace(returncode=0, stdout=b"x" * 65537, stderr=b""),
])
def test_effective_probe_requires_exact_bounded_native_reply(enrollment, reply):
    enrollment.probe_failure = reply
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE" and not enrollment.voice_calls
    assert "PRIVATE" not in json.dumps(result)


def test_final_effective_readback_does_not_accept_masked_plugin_enablement(enrollment):
    enrollment.effective["plugins.enabled"] = ["station-web"]
    result = enrollment.enroll()
    assert len(enrollment.voice_calls) == 5
    assert result["state"] == "INCOMPLETE" and result["steps"][-1]["id"] == "readback"


def test_managed_scan_policy_changed_between_steps_stops_enablement(enrollment, monkeypatch):
    original = voice.run_bounded_native
    def run(argv, **kwargs):
        result = original(argv, **kwargs)
        if not kwargs["capture"]:
            enrollment.effective["plugins.scan_on_install"] = False
        return result
    monkeypatch.setattr(voice, "run_bounded_native", run)
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE" and len(enrollment.voice_calls) == 1
    assert result["steps"][-1]["id"] == "doctor"
    assert enrollment.config()["stt"]["provider"] == "openai"


@pytest.mark.parametrize("reply", [
    SimpleNamespace(returncode=0, stdout=b"/another/profile/config.yaml\n", stderr=b""),
    SimpleNamespace(returncode=0, stdout=b"relative/config.yaml\n", stderr=b""),
    SimpleNamespace(returncode=0, stdout=b"PRIVATE-INVALID-OUTPUT\n", stderr=b""),
    SimpleNamespace(returncode=0, stdout=b"\xff", stderr=b""),
    SimpleNamespace(returncode=1, stdout=b"", stderr=b"PRIVATE-PATH-ERROR"),
])
def test_native_profile_redirect_or_invalid_path_reply_blocks_all_mutations(enrollment, reply):
    enrollment.native_path_reply = reply
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE" and result["steps"][-1]["status"] == "BLOCKED"
    assert not enrollment.voice_calls
    assert enrollment.config_path.read_bytes() == enrollment.original_config
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("formatting", ["missing-newline", "duplicate-line", "stderr", "nonzero", "traversal"])
def test_native_path_readback_requires_exact_successful_scoped_path(enrollment, formatting):
    expected = str(enrollment.config_path).encode() + b"\n"
    reply = SimpleNamespace(returncode=0, stdout=expected, stderr=b"")
    if formatting == "missing-newline":
        reply.stdout = expected.rstrip(b"\n")
    elif formatting == "duplicate-line":
        reply.stdout += expected
    elif formatting == "stderr":
        reply.stderr = b"PRIVATE-WARNING"
    elif formatting == "nonzero":
        reply.returncode = 1
    else:
        reply.stdout = str(enrollment.config_path.parent / ".." / enrollment.config_path.parent.name / "config.yaml").encode() + b"\n"
    enrollment.native_path_reply = reply
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE" and not enrollment.voice_calls
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("after_step", [1, 2, 3, 4, 5])
def test_native_profile_path_is_rechecked_between_mutations_and_at_final_readback(enrollment, monkeypatch, after_step):
    original = voice.run_bounded_native
    def run(argv, **kwargs):
        result = original(argv, **kwargs)
        if not kwargs["capture"] and len(enrollment.voice_calls) == after_step:
            enrollment.native_path_reply = SimpleNamespace(
                returncode=0, stdout=b"/another/profile/config.yaml\n", stderr=b"",
            )
        return result
    monkeypatch.setattr(voice, "run_bounded_native", run)
    result = enrollment.enroll()
    assert result["state"] == "INCOMPLETE" and len(enrollment.voice_calls) == after_step
    assert result["steps"][-1]["status"] == "BLOCKED"
    if after_step == 5:
        assert result["steps"][-1]["id"] == "readback"
