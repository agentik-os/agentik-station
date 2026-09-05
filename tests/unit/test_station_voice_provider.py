"""Offline native-provider contract and hostile local-output regression checks."""

import abc
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "runtime/hermes-station/hermes/plugins/station-voice"
SECRET = "SECRET_PROVIDER_BODY_OR_TOKEN"


@pytest.fixture
def plugin():
    spec = importlib.util.spec_from_file_location("station_voice_fixture", PLUGIN / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def provider(plugin, monkeypatch):
    class NativeABC(abc.ABC):
        @property
        @abc.abstractmethod
        def name(self):
            pass

        @abc.abstractmethod
        def transcribe(self, file_path, *, model=None, language=None, **extra):
            pass

    agent = ModuleType("agent")
    native = ModuleType("agent.transcription_provider")
    native.TranscriptionProvider = NativeABC
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.transcription_provider", native)
    return plugin._make_provider()


@pytest.fixture
def audio(tmp_path):
    path = tmp_path.resolve() / "audio.wav"
    path.write_bytes(b"RIFF-synthetic-audio")
    path.chmod(0o600)
    return str(path)


@pytest.fixture
def primary(plugin, monkeypatch):
    observed = SimpleNamespace(calls=[], result={"success": True, "transcript": "Bonjour!"},
                               exception=None)

    def transcribe(file_path, model_name, *, language=None, prompt=None):
        observed.calls.append((file_path, model_name, language, prompt))
        if observed.exception:
            raise observed.exception
        return observed.result

    tools = ModuleType("tools")
    native = ModuleType("tools.transcription_tools")
    native._transcribe_openai = transcribe
    native.transcribe_audio = lambda *args, **kwargs: pytest.fail("Recursive native dispatch")
    monkeypatch.setitem(sys.modules, "tools", tools)
    monkeypatch.setitem(sys.modules, "tools.transcription_tools", native)
    return observed


@pytest.fixture
def local(plugin, monkeypatch):
    observed = SimpleNamespace(calls=[], directories=[], payload=b" Local transcript. \n",
                               exception=None, output_callback=None)
    monkeypatch.setattr(plugin, "_adapter_available", lambda: True)

    def run(argv, **kwargs):
        observed.calls.append((argv, kwargs))
        output = Path(argv[2])
        observed.directories.append(output.parent)
        info = output.parent.stat()
        assert stat.S_IMODE(info.st_mode) == 0o700
        assert info.st_uid == os.geteuid()
        assert not output.exists()
        if observed.exception:
            raise observed.exception
        if observed.output_callback:
            observed.output_callback(output)
        else:
            output.write_bytes(observed.payload)
            output.chmod(0o600)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(plugin.subprocess, "run", run)
    return observed


def failed_primary(primary):
    primary.result = {"success": False, "transcript": "", "error": SECRET}


def assert_private_error(result, capsys=None):
    assert result["success"] is False
    assert result["transcript"] == ""
    assert result["provider"] == "station-openai-parakeet"
    assert SECRET not in str(result)
    if capsys:
        captured = capsys.readouterr()
        assert captured.out == captured.err == ""


def test_manifest_declares_backend_without_tools_hooks_or_required_cloud_key():
    manifest = yaml.safe_load((PLUGIN / "plugin.yaml").read_text())
    assert manifest["name"] == "station-voice"
    assert manifest["kind"] == "backend"
    assert manifest["provides_tools"] == manifest["provides_hooks"] == manifest["requires_env"] == []


def test_registration_uses_only_native_context_and_does_not_mutate_profiles(
        plugin, provider, monkeypatch, tmp_path):
    scopes = {"one": {}, "two": {}}
    files = [tmp_path / "one.yaml", tmp_path / "two.yaml"]
    for index, path in enumerate(files):
        path.write_text(f"stt:\n  provider: openai\nprofile: {index}\n")
    original = [path.read_bytes() for path in files]
    environment = dict(os.environ)

    class Context:
        def register_transcription_provider(self, instance):
            scopes["one"][instance.name] = instance

    plugin.register(Context())
    registered = scopes["one"][plugin.PROVIDER_NAME]
    assert registered.name == provider.name
    assert registered is not provider
    assert scopes["two"] == {}
    assert [path.read_bytes() for path in files] == original
    assert dict(os.environ) == environment


def test_lazy_import_does_not_need_native_hermes_until_registration(plugin):
    assert callable(plugin.register)
    assert callable(plugin._make_provider)


def test_primary_uses_exact_native_arguments_and_drops_unknown_extras(
        plugin, provider, primary, local, audio):
    before = Path(audio).read_bytes()
    result = provider.transcribe(audio, model="gpt-4o-mini-transcribe", language="fr",
                                 prompt="Station engineering", base_url=SECRET,
                                 api_key=SECRET, command=SECRET)
    assert primary.calls == [(audio, "gpt-4o-mini-transcribe", "fr", "Station engineering")]
    assert result == {"success": True, "transcript": "Bonjour!", "provider": plugin.PROVIDER_NAME,
                      "backend": "openai"}
    assert local.calls == []
    assert Path(audio).read_bytes() == before


def test_default_model_is_explicit_without_reading_other_profiles(provider, primary, local, audio):
    provider.transcribe(audio)
    assert primary.calls == [(audio, "gpt-transcribe", None, None)]
    assert provider.default_model() == "gpt-transcribe"
    assert provider.list_models()[0]["id"] == "gpt-transcribe"
    assert provider.get_setup_schema()["env_vars"] == []
    assert not local.calls


@pytest.mark.parametrize("transcript", ["", " ", "\n\t", "Ordinary speech"])
def test_primary_success_never_falls_back_including_silence(
        provider, primary, local, audio, transcript):
    primary.result = {"success": True, "transcript": transcript, "error": SECRET,
                      "provider": SECRET, "metadata": SECRET}
    result = provider.transcribe(audio)
    assert result["transcript"] == transcript
    assert result["backend"] == "openai"
    assert SECRET not in str(result)
    assert not local.calls


def test_failure_routes_to_fixed_local_adapter_with_private_environment(
        plugin, provider, primary, local, audio, monkeypatch, capsys):
    failed_primary(primary)
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.setenv("HTTPS_PROXY", SECRET)
    monkeypatch.setenv("CURL_HOME", SECRET)
    result = provider.transcribe(audio, language="fr")
    assert result == {"success": True, "transcript": "Local transcript.",
                      "provider": plugin.PROVIDER_NAME, "backend": "parakeet"}
    argv, options = local.calls[0]
    directory = local.directories[0]
    assert argv == ["/usr/local/libexec/station-parakeet-transcribe", audio,
                    str(directory / "transcript.txt"), "fr"]
    assert options == {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                       "stderr": subprocess.DEVNULL, "check": True, "timeout": 310,
                       "env": {"PATH": "/usr/bin:/bin", "HOME": str(directory),
                               "CURL_HOME": str(directory), "XDG_CONFIG_HOME": str(directory),
                               "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}}
    assert not directory.exists()
    assert os.environ["OPENAI_API_KEY"] == SECRET
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("language", [None, "", "auto", "en", "fr", "pt-BR", "eng"])
def test_local_language_hints(provider, primary, local, audio, language):
    failed_primary(primary)
    assert provider.transcribe(audio, language=language)["success"] is True
    assert local.calls[0][0][3] == (language or "auto")


@pytest.mark.parametrize("language", ["../../key", "en;command", "--url", "EN", "a", "en_US"])
def test_invalid_local_language_fails_without_executing(provider, primary, local, audio, language):
    failed_primary(primary)
    assert_private_error(provider.transcribe(audio, language=language))
    assert not local.calls


@pytest.mark.parametrize("exception", [OSError(SECRET), TimeoutError(SECRET), ConnectionError(SECRET)])
def test_expected_primary_io_failure_falls_back(provider, primary, local, audio, exception, capsys):
    primary.exception = exception
    assert provider.transcribe(audio)["backend"] == "parakeet"
    assert len(local.calls) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("exception", [TypeError(SECRET), AttributeError(SECRET), ImportError(SECRET),
                                       ValueError(SECRET), RuntimeError(SECRET)])
def test_compatibility_failure_never_runs_fallback_or_discloses_exception(
        provider, primary, local, audio, exception, capsys):
    primary.exception = exception
    assert_private_error(provider.transcribe(audio), capsys)
    assert not local.calls


@pytest.mark.parametrize("result", [None, [], SECRET, {}, {"success": False},
                                    {"success": "false", "transcript": ""},
                                    {"success": 1, "transcript": ""},
                                    {"success": True, "transcript": None},
                                    {"success": True, "transcript": b"bytes"},
                                    {"success": False, "transcript": "partial", "error": SECRET},
                                    {"success": False, "transcript": "", "error": None}])
def test_malformed_native_results_fail_closed(provider, primary, local, audio, result, capsys):
    primary.result = result
    assert_private_error(provider.transcribe(audio), capsys)
    assert not local.calls


@pytest.mark.parametrize("options", [{"model": ""}, {"model": " "}, {"model": 3},
                                     {"language": []}, {"prompt": {}}])
def test_invalid_options_do_not_contact_either_backend(provider, primary, local, audio, options):
    assert_private_error(provider.transcribe(audio, **options))
    assert primary.calls == local.calls == []


@pytest.mark.parametrize("case", ["relative", "missing", "directory", "symlink", "parent-symlink",
                                  "hardlink", "fifo", "empty", "oversized", "dotdot", "nul", "type"])
def test_unsafe_audio_never_reaches_backends(provider, primary, local, audio, tmp_path, case):
    path = Path(audio)
    target = audio
    if case == "relative":
        target = "audio.wav"
    elif case == "missing":
        target = str(path.parent / "missing.wav")
    elif case == "directory":
        target = str(path.parent)
    elif case == "symlink":
        target = str(path.parent / "link.wav")
        Path(target).symlink_to(path)
    elif case == "parent-symlink":
        link = path.parent / "alias"
        link.symlink_to(path.parent, target_is_directory=True)
        target = str(link / path.name)
    elif case == "hardlink":
        os.link(path, path.parent / "second.wav")
    elif case == "fifo":
        target = str(path.parent / "pipe.wav")
        os.mkfifo(target)
    elif case in {"empty", "oversized"}:
        with path.open("wb") as stream:
            stream.truncate(0 if case == "empty" else 25 * 1024 * 1024 + 1)
    elif case == "dotdot":
        target = str(path.parent) + "/../" + path.parent.name + "/audio.wav"
    elif case == "nul":
        target += "\x00"
    elif case == "type":
        target = path
    assert_private_error(provider.transcribe(target))
    assert primary.calls == local.calls == []


def test_input_is_rechecked_after_primary_failure(provider, primary, local, audio, monkeypatch):
    def primary_changes_input(*args):
        Path(audio).unlink()
        Path(audio).symlink_to("/unavailable")
        return {"success": False, "transcript": "", "error": SECRET}
    monkeypatch.setattr(sys.modules["tools.transcription_tools"], "_transcribe_openai", primary_changes_input)
    assert_private_error(provider.transcribe(audio))
    assert not local.calls


@pytest.mark.parametrize("case", ["foreign-file", "group-writable-file", "other-writable-file",
                                  "foreign-parent", "group-writable-parent", "other-writable-parent",
                                  "sticky-private-parent", "symlink-parent"])
def test_cross_uid_input_substitution_is_rejected_before_any_backend(
        plugin, provider, primary, local, audio, monkeypatch, case):
    path = Path(audio)
    native_lstat = Path.lstat

    def lstat(candidate):
        info = native_lstat(candidate)
        is_target = candidate == path if case.endswith("file") else candidate == path.parent
        if not is_target:
            return info
        fields = {name: getattr(info, name) for name in ("st_mode", "st_uid", "st_nlink", "st_size")}
        if case.startswith("foreign"):
            fields["st_uid"] = os.geteuid() + 12345
        elif case.startswith("group-writable"):
            fields["st_mode"] |= 0o020
        elif case.startswith("other-writable"):
            fields["st_mode"] |= 0o002
        elif case == "sticky-private-parent":
            fields["st_mode"] |= 0o002 | stat.S_ISVTX
        else:
            fields["st_mode"] = stat.S_IFLNK | 0o777
        return SimpleNamespace(**fields)

    monkeypatch.setattr(plugin.Path, "lstat", lstat)
    assert_private_error(provider.transcribe(audio))
    assert primary.calls == local.calls == []


@pytest.mark.parametrize("temporary", ["/tmp", "/private/tmp"])
@pytest.mark.parametrize("case", ["root-sticky", "root-no-sticky", "foreign-sticky",
                                  "caller-sticky", "foreign-protected-child"])
def test_shared_temporary_parent_requires_exact_root_owned_sticky_contract(
        plugin, monkeypatch, temporary, case):
    # Synthetic metadata exercises both Linux and macOS canonical temp roots.
    # A non-root identity avoids treating caller-owned sticky as root-owned in CI.
    caller_uid = 12345
    source = Path(temporary) / "station-audio" / "audio.wav"
    monkeypatch.setattr(plugin.os, "geteuid", lambda: caller_uid)
    monkeypatch.setattr(plugin.Path, "resolve", lambda path, **kwargs: path)

    def lstat(path):
        if path == source:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=caller_uid,
                                   st_nlink=1, st_size=128)
        owner = caller_uid if path == source.parent else 0
        mode = stat.S_IFDIR | 0o700
        if path == Path(temporary):
            mode = stat.S_IFDIR | 0o777 | stat.S_ISVTX
            if case == "root-no-sticky":
                mode &= ~stat.S_ISVTX
            elif case == "foreign-sticky":
                owner = 45678
            elif case == "caller-sticky":
                owner = caller_uid
        if path == source.parent and case == "foreign-protected-child":
            owner = 45678
        return SimpleNamespace(st_mode=mode, st_uid=owner)

    monkeypatch.setattr(plugin.Path, "lstat", lstat)
    assert plugin._safe_input(str(source)) is (case == "root-sticky")


def test_local_path_grammar_is_rejected_before_child(provider, primary, local, audio):
    failed_primary(primary)
    path = Path(audio).with_name("space comma,.wav")
    path.write_bytes(b"synthetic")
    assert_private_error(provider.transcribe(str(path)))
    assert not local.calls


@pytest.mark.parametrize("payload", [b"", b" \n\t", b"bad\xffutf8", b"embedded\x00nul",
                                     b"x" * (1024 * 1024 + 1)])
def test_invalid_transcript_bytes_are_rejected_and_removed(provider, primary, local, audio, payload):
    failed_primary(primary)
    local.payload = payload
    assert_private_error(provider.transcribe(audio))
    assert all(not directory.exists() for directory in local.directories)


@pytest.mark.parametrize("case", ["absent", "symlink", "dangling", "directory", "fifo", "hardlink",
                                  "readable", "executable"])
def test_unsafe_transcript_file_is_rejected(provider, primary, local, audio, case):
    failed_primary(primary)

    def output_callback(output):
        if case == "absent":
            return
        if case in {"symlink", "dangling"}:
            output.symlink_to(audio if case == "symlink" else output.parent / "missing")
        elif case == "directory":
            output.mkdir()
        elif case == "fifo":
            os.mkfifo(output)
        elif case == "hardlink":
            os.link(audio, output)
        else:
            output.write_text("secret")
            output.chmod(0o644 if case == "readable" else 0o700)

    local.output_callback = output_callback
    assert_private_error(provider.transcribe(audio))
    assert all(not directory.exists() for directory in local.directories)


def test_transcript_with_wrong_owner_is_rejected(plugin, provider, primary, local, audio, monkeypatch):
    failed_primary(primary)
    monkeypatch.setattr(plugin.os, "geteuid", lambda: os.getuid() + 123)
    # The child fixture's directory check is independent of this injected readback.
    local.output_callback = lambda output: None
    output = Path(audio).with_name("transcript.txt")
    output.write_text("untrusted")
    output.chmod(0o600)
    with pytest.raises(ValueError):
        plugin._read_transcript(output)


@pytest.mark.parametrize("attribute", ["st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink",
                                       "st_mode", "st_uid"])
def test_transcript_drift_during_read_is_rejected(plugin, audio, monkeypatch, attribute):
    output = Path(audio).with_name("transcript.txt")
    output.write_text("bounded transcript")
    output.chmod(0o600)
    native_fstat = os.fstat
    calls = []

    def changed_fstat(descriptor):
        info = native_fstat(descriptor)
        calls.append(descriptor)
        if len(calls) == 1:
            return info
        fields = {name: getattr(info, name) for name in
                  ("st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink", "st_mode", "st_uid")}
        fields[attribute] += 1
        return SimpleNamespace(**fields)

    monkeypatch.setattr(plugin.os, "fstat", changed_fstat)
    with pytest.raises(ValueError):
        plugin._read_transcript(output)


@pytest.mark.parametrize("exception", [subprocess.TimeoutExpired("adapter", 310, output=SECRET),
                                       subprocess.CalledProcessError(2, "adapter", stderr=SECRET),
                                       OSError(SECRET)])
def test_adapter_failure_is_bounded_redacted_and_cleans_private_output(
        provider, primary, local, audio, exception, capsys):
    failed_primary(primary)
    local.exception = exception
    assert_private_error(provider.transcribe(audio), capsys)
    assert all(not directory.exists() for directory in local.directories)


def test_missing_adapter_returns_error_without_secret(plugin, provider, primary, local, audio, monkeypatch):
    failed_primary(primary)
    monkeypatch.setattr(plugin, "_adapter_available", lambda: False)
    assert_private_error(provider.transcribe(audio))
    assert not local.calls


@pytest.mark.parametrize("adapter,sdk,expected", [(True, False, True), (False, True, True),
                                                 (False, False, False)])
def test_availability_is_dependency_only_without_auth_network_or_audio(
        plugin, provider, primary, local, monkeypatch, adapter, sdk, expected):
    monkeypatch.setattr(plugin, "_adapter_available", lambda: adapter)
    monkeypatch.setattr(plugin.importlib.util, "find_spec", lambda name: object() if sdk else None)
    assert provider.is_available() is expected
    assert primary.calls == local.calls == []


def test_availability_never_raises(plugin, provider, monkeypatch):
    def broken():
        raise RuntimeError(SECRET)
    monkeypatch.setattr(plugin, "_adapter_available", broken)
    assert provider.is_available() is False


def test_adapter_path_must_be_canonical_trusted_and_executable(plugin, monkeypatch, tmp_path):
    executable = tmp_path.resolve() / "adapter"
    executable.write_text("fixture")
    executable.chmod(0o755)
    monkeypatch.setattr(plugin, "PARAKEET_ADAPTER", str(executable))
    # A private fixture beneath /tmp is never a trusted system executable, even
    # under root CI: the writable ancestor is deliberately rejected.
    assert plugin._adapter_available() is False
    executable.chmod(0o777)
    assert plugin._adapter_available() is False
    executable.chmod(0o644)
    assert plugin._adapter_available() is False
    executable.unlink()
    assert plugin._adapter_available() is False


@pytest.mark.parametrize("case", ["root-safe", "wrong-owner", "writable-parent", "symlink-parent",
                                  "writable-executable", "special-executable", "not-executable"])
def test_fixed_adapter_trust_chain(plugin, monkeypatch, case):
    expected_path = Path(plugin.PARAKEET_ADAPTER)

    def lstat(path):
        is_file = path == expected_path
        mode = stat.S_IFREG | 0o755 if is_file else stat.S_IFDIR | 0o755
        owner = 0
        if is_file and case == "wrong-owner":
            owner = 1000
        if not is_file and case == "writable-parent":
            mode |= 0o002
        if not is_file and case == "symlink-parent":
            mode = stat.S_IFLNK | 0o777
        if is_file and case == "writable-executable":
            mode |= 0o020
        if is_file and case == "special-executable":
            mode = stat.S_IFIFO | 0o755
        return SimpleNamespace(st_mode=mode, st_uid=owner)

    monkeypatch.setattr(plugin.Path, "resolve", lambda path, **kwargs: path)
    monkeypatch.setattr(plugin.Path, "lstat", lstat)
    monkeypatch.setattr(plugin.os, "access", lambda path, flags: case != "not-executable")
    assert plugin._adapter_available() is (case == "root-safe")


def test_exact_limit_audio_and_transcript_are_allowed(plugin, provider, primary, local, audio):
    failed_primary(primary)
    with Path(audio).open("wb") as stream:
        stream.truncate(plugin.MAX_AUDIO_BYTES)
    local.payload = b"x" * plugin.MAX_TRANSCRIPT_BYTES
    assert len(provider.transcribe(audio)["transcript"]) == plugin.MAX_TRANSCRIPT_BYTES
