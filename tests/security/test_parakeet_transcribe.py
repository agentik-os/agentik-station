"""Actual GNU no-clobber publication with a local, non-network curl fixture."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/station_parakeet_transcribe.sh"


@pytest.fixture
def adapter(tmp_path):
    root = tmp_path.resolve()
    binaries = root / "bin"
    binaries.mkdir()
    for name in ("ln", "stat", "mktemp", "realpath"):
        binary = shutil.which("g" + name) or shutil.which(name)
        if not binary:
            pytest.skip("GNU coreutils are required by the Linux Parakeet adapter")
        version = subprocess.run([binary, "--version"], capture_output=True, text=True)
        if version.returncode or "GNU coreutils" not in version.stdout:
            pytest.skip("GNU coreutils are required by the Linux Parakeet adapter")
        (binaries / name).symlink_to(binary)
    source = root / "input.wav"
    source.write_bytes(b"synthetic fixture; no audio is uploaded")
    output = root / "transcript.txt"
    sentinel = root / "unrelated.txt"
    sentinel.write_text("unrelated user data")
    marker = root / "curl-called.json"
    curl = binaries / "curl"
    curl.write_text(f"#!{sys.executable}\n" + """
import json, os, pathlib, stat, sys
root = pathlib.Path(os.environ['PARAKEET_FIXTURE_ROOT'])
output, sentinel = root / 'transcript.txt', root / 'unrelated.txt'
temporaries = list(root.glob('.station-parakeet.*'))
assert len(temporaries) == 1
metadata = temporaries[0].stat()
assert stat.S_ISREG(metadata.st_mode) and metadata.st_mode & 0o777 == 0o600
assert metadata.st_nlink == 1
(root / 'curl-called.json').write_text(json.dumps(sys.argv[1:]))
scenario = os.environ['PARAKEET_FIXTURE_SCENARIO']
if scenario == 'file':
    output.write_text('concurrent user data')
elif scenario == 'directory':
    output.mkdir()
    (output / 'keep.txt').write_text('concurrent directory data')
elif scenario in ('symlink', 'dangling'):
    output.symlink_to(sentinel if scenario == 'symlink' else root / 'absent-target')
elif scenario == 'fifo':
    os.mkfifo(output)
elif scenario == 'hardlink':
    os.link(sentinel, output)
elif scenario == 'http-failure':
    print('partial response; not a transcript')
    sys.exit(22)
elif scenario == 'empty':
    sys.exit(0)
sys.stdout.write('Private synthetic transcript.\\n')
""")
    curl.chmod(0o755)
    env = {**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
           "PARAKEET_FIXTURE_ROOT": str(root)}

    def run(scenario="success"):
        return subprocess.run(["bash", str(SCRIPT), str(source), str(output), "en"],
                              env={**env, "PARAKEET_FIXTURE_SCENARIO": scenario},
                              cwd=root, capture_output=True, text=True, timeout=15)

    return SimpleNamespace(root=root, source=source, output=output, sentinel=sentinel,
                           marker=marker, run=run)


def test_success_publishes_complete_private_transcript_and_cleans_temp(adapter):
    result = adapter.run()
    assert result.returncode == 0, result.stderr
    assert adapter.output.read_text() == "Private synthetic transcript.\n"
    info = adapter.output.stat()
    assert info.st_mode & 0o777 == 0o600 and info.st_nlink == 1
    assert not list(adapter.root.glob(".station-parakeet.*"))
    argv = json.loads(adapter.marker.read_text())
    assert argv[-1] == "http://127.0.0.1:5092/v1/audio/transcriptions"
    assert f"file=@{adapter.source}" in argv and "response_format=text" in argv
    assert "language=en" in argv
    assert "Private synthetic transcript" not in result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "dangling", "fifo", "hardlink"])
def test_concurrent_output_is_never_overwritten_or_used_as_directory(adapter, kind):
    result = adapter.run(kind)
    assert adapter.marker.is_file(), "competition must happen after the initial output guard"
    assert result.returncode != 0
    assert adapter.sentinel.read_text() == "unrelated user data"
    assert not list(adapter.root.glob(".station-parakeet.*"))
    info = adapter.output.lstat()
    if kind == "file":
        assert adapter.output.read_text() == "concurrent user data"
    elif kind == "directory":
        assert sorted(path.name for path in adapter.output.iterdir()) == ["keep.txt"]
        assert (adapter.output / "keep.txt").read_text() == "concurrent directory data"
    elif kind in {"symlink", "dangling"}:
        target = adapter.sentinel if kind == "symlink" else adapter.root / "absent-target"
        assert stat.S_ISLNK(info.st_mode) and os.readlink(adapter.output) == str(target)
        if kind == "dangling":
            assert not target.exists()
    elif kind == "fifo":
        assert stat.S_ISFIFO(info.st_mode)
    else:
        assert (info.st_dev, info.st_ino) == (adapter.sentinel.stat().st_dev, adapter.sentinel.stat().st_ino)


@pytest.mark.parametrize("failure", ["http-failure", "empty"])
def test_incomplete_response_publishes_nothing_and_cleans_temp(adapter, failure):
    result = adapter.run(failure)
    assert result.returncode != 0
    assert not os.path.lexists(adapter.output)
    assert not list(adapter.root.glob(".station-parakeet.*"))


def test_existing_output_still_fails_before_any_http_request(adapter):
    adapter.output.write_text("keep existing transcript")
    result = adapter.run()
    assert result.returncode != 0
    assert adapter.output.read_text() == "keep existing transcript"
    assert not adapter.marker.exists()
    assert not list(adapter.root.glob(".station-parakeet.*"))


def test_adapter_shell_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
