"""Headless voice dependencies fail closed without opening local audio devices."""

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def probe():
    spec = importlib.util.spec_from_file_location("station_voice_check", ROOT / "scripts/station_voice_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dependencies(probe, monkeypatch):
    observed = SimpleNamespace(imports=[], commands=[], libraries=[], missing_import=None,
                               opus_loaded=False, find_opus=True, find_portaudio=True)

    class Aead:
        KEY_SIZE = 32
        NONCE_SIZE = 24

        def __init__(self, key):
            assert key == bytes(self.KEY_SIZE)

        def encrypt(self, message, *, nonce):
            assert nonce == bytes(self.NONCE_SIZE)
            return nonce + message

        def decrypt(self, message):
            return message[self.NONCE_SIZE:]

    class PortAudio:
        def Pa_GetVersion(self):
            return 1246720

        def Pa_Initialize(self):
            raise AssertionError("No PulseAudio session or local device may be opened")

    def dlopen(library):
        assert library == "fixture-portaudio"
        observed.libraries.append(library)
        return PortAudio()

    def load_opus(library):
        assert library == "fixture-opus"
        observed.libraries.append(library)
        observed.opus_loaded = True

    def encode(frame, samples):
        assert frame == probe.PCM_FRAME and samples == 960
        return b"synthetic-opus"

    opus = SimpleNamespace(is_loaded=lambda: observed.opus_loaded, load_opus=load_opus,
                           Encoder=lambda: SimpleNamespace(encode=encode),
                           Decoder=lambda: SimpleNamespace(decode=lambda _: probe.PCM_FRAME))
    observed.modules = {"discord": SimpleNamespace(opus=opus), "numpy": object(),
                        "faster_whisper": object(), "nacl.secret": SimpleNamespace(Aead=Aead),
                        "_sounddevice": SimpleNamespace(ffi=SimpleNamespace(dlopen=dlopen))}

    def import_module(name):
        observed.imports.append(name)
        assert name != "sounddevice", "Import initializes PortAudio on headless Hosts"
        if name == observed.missing_import:
            raise ImportError("SECRET_DEPENDENCY_DIAGNOSTIC")
        return observed.modules[name]

    def find_library(name):
        assert name in {"portaudio", "opus"}
        return "fixture-" + name if getattr(observed, "find_" + name) else None

    def run(argv, **kwargs):
        observed.commands.append(argv)
        assert argv[0] == "/fixture/ffmpeg" and argv[-1] == "pipe:1"
        assert "-nostdin" in argv and "pipe:0" in argv
        assert kwargs == {"input": probe.PCM_FRAME if len(observed.commands) == 1 else b"OggS-synthetic",
                          "stdout": probe.PIPE, "stderr": probe.PIPE, "check": True, "timeout": 20}
        return SimpleNamespace(stdout=b"OggS-synthetic" if len(observed.commands) == 1 else probe.PCM_FRAME)

    monkeypatch.setattr(probe, "import_module", import_module)
    monkeypatch.setattr(probe, "find_library", find_library)
    monkeypatch.setattr(probe, "version", lambda name: "0.5.5" if name == "sounddevice" else None)
    monkeypatch.setattr(probe, "find_spec", lambda name: object() if name == "sounddevice" else None)
    monkeypatch.setattr(probe, "which", lambda name: "/fixture/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(probe, "run", run)
    return observed


def test_headless_success_uses_real_checks_but_never_initializes_local_audio(probe, dependencies, capsys):
    assert probe.main() == 0
    output = capsys.readouterr()
    assert "LOCAL_AUDIO=NOT_TESTED" in output.out
    assert "live acceptance pending" in output.out
    assert not output.err
    assert "sounddevice" not in dependencies.imports
    assert {"discord", "numpy", "faster_whisper", "nacl.secret", "_sounddevice"} <= set(dependencies.imports)
    assert dependencies.libraries == ["fixture-portaudio", "fixture-opus"]
    assert len(dependencies.commands) == 2
    assert "libopus" in dependencies.commands[0]


@pytest.mark.parametrize("name", ["discord", "numpy", "faster_whisper", "nacl.secret", "_sounddevice"])
def test_missing_or_broken_python_dependencies_still_fail(probe, dependencies, capsys, name):
    dependencies.missing_import = name
    assert probe.main() == 1
    output = capsys.readouterr()
    assert "dependency check failed" in output.err
    assert "SECRET_DEPENDENCY_DIAGNOSTIC" not in output.out + output.err
    assert "dependencies OK" not in output.out


@pytest.mark.parametrize("failure", ["aead", "sounddevice-metadata", "sounddevice-module", "portaudio",
                                     "portaudio-load", "opus", "opus-load", "opus-roundtrip", "ffmpeg"])
def test_missing_or_broken_required_audio_components_fail_closed(probe, dependencies, monkeypatch, failure, capsys):
    if failure == "aead":
        dependencies.modules["nacl.secret"] = SimpleNamespace()
    elif failure == "sounddevice-metadata":
        monkeypatch.setattr(probe, "version", lambda _: "")
    elif failure == "sounddevice-module":
        monkeypatch.setattr(probe, "find_spec", lambda _: None)
    elif failure == "portaudio":
        dependencies.find_portaudio = False
    elif failure == "portaudio-load":
        def bad_load(_):
            raise OSError("broken library")
        dependencies.modules["_sounddevice"].ffi.dlopen = bad_load
    elif failure == "opus":
        dependencies.find_opus = False
    elif failure == "opus-load":
        dependencies.modules["discord"].opus.load_opus = lambda _: None
    elif failure == "opus-roundtrip":
        dependencies.modules["discord"].opus.Decoder = lambda: SimpleNamespace(decode=lambda _: b"")
    else:
        monkeypatch.setattr(probe, "which", lambda _: None)
    assert probe.main() == 1
    output = capsys.readouterr()
    assert "dependency check failed" in output.err
    assert "dependencies OK" not in output.out


@pytest.mark.parametrize("failure", ["encode", "decode", "timeout", "wrong-container", "wrong-pcm"])
def test_ffmpeg_execution_and_audio_readback_failures_are_not_suppressed(probe, dependencies, monkeypatch, failure):
    calls = []

    def fail(argv, **kwargs):
        calls.append(argv)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 20)
        if failure == "encode" or failure == "decode" and len(calls) == 2:
            raise subprocess.CalledProcessError(2, argv)
        if failure == "wrong-container":
            return SimpleNamespace(stdout=b"not-audio")
        return SimpleNamespace(stdout=b"OggS-synthetic" if len(calls) == 1 else b"")

    monkeypatch.setattr(probe, "run", fail)
    assert probe.main() == 1


def test_native_ffmpeg_roundtrip_uses_no_device_or_network(probe):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg unavailable locally; real VPS readback remains required")
    probe.check_file_audio()


def test_bootstrap_runs_isolated_probe_before_voice_success():
    source = (ROOT / "bootstrap.sh").read_text()
    # Select the voice checkpoint, not another voice-enabled stage such as
    # Parakeet. Full profiles defer this work to the aggregate dependency batch.
    prefix, block = source.split("  bootstrap_checkpoint voice running\n", 1)
    assert prefix.rstrip().endswith('if [[ "$INSTALL_VOICE" -eq 1 && "$INSTALL_AI_STACK" -eq 0 ]]; then')
    block = block.split("\nfi", 1)[0]
    assert '--editable "${hermes_install_dir}[voice,messaging]"' in block
    assert '"$hermes_install_dir/venv/bin/python" -I -B' in block
    assert 'PATH=/usr/local/bin:/usr/bin:/bin' in block
    assert '"$REPO_DIR/scripts/station_voice_check.py"' in block
    assert '"$source_root/scripts/station_voice_check.py"' not in block
    assert block.index('station_voice_check.py') < block.index('bootstrap_checkpoint voice success')
    assert "import discord, numpy, sounddevice" not in block


@pytest.mark.parametrize("probe_rc", [0, 9])
def test_voice_probe_uses_operator_copy_and_failure_cannot_publish_success(tmp_path, probe_rc):
    source = (ROOT / "bootstrap.sh").read_text()
    block = source.split("  # Discord/file audio needs codecs, not a local microphone or PulseAudio server.", 1)[1]
    block = block.split("\nfi", 1)[0]
    repo = tmp_path / "operator checkout"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts/station_voice_check.py").write_text("# operator-readable fixture\n")
    hermes = tmp_path / "shared hermes"
    (hermes / "venv/bin").mkdir(parents=True)
    python = hermes / "venv/bin/python"
    python.write_text('''#!/bin/sh
[ "$#" -eq 3 ] && [ "$1" = -I ] && [ "$2" = -B ] || exit 81
[ "$3" = "$REPO_DIR/scripts/station_voice_check.py" ] && [ -r "$3" ] || exit 82
[ "$HOME" = "$STATION_HOME" ] && [ "$HERMES_HOME" = "$STATION_HOME/.hermes" ] || exit 83
[ "$PATH" = /usr/local/bin:/usr/bin:/bin ] || exit 84
exit "$PROBE_RC"
''')
    python.chmod(0o700)
    harness = '''set -euo pipefail
sudo() { shift 3; "$@"; }
bootstrap_checkpoint() { printf 'CHECKPOINT %s\\n' "$*"; }
'''
    result = subprocess.run(["bash", "-c", harness + block], capture_output=True, text=True, timeout=10,
                            env={**os.environ, "STATION_USER": "fixture", "STATION_HOME": str(tmp_path / "operator"),
                                 "hermes_install_dir": str(hermes), "REPO_DIR": str(repo),
                                 "source_root": str(tmp_path / "unreadable-launch-checkout"), "PROBE_RC": str(probe_rc)})
    assert result.returncode == probe_rc, result.stderr
    assert ("CHECKPOINT voice success" in result.stdout) == (probe_rc == 0)
