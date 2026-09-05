"""Dependency batch tests execute only synthetic children and receipt storage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/station_deps_install.sh"
COMPONENTS = (
    "toolchain", "hermes-clients", "hermes-voice", "hermes-updater", "strix", "scrapegraphai", "ponytail", "langfuse",
    "honcho", "hindsight", "tigervnc", "crawl4ai", "parakeet", "chatbotx",
)


def executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


@pytest.fixture
def harness(tmp_path):
    root = tmp_path.resolve()
    repo = root / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (repo / "config").mkdir()
    (repo / "config/versions.lock").write_text("")
    package = repo / "src/agentik_station"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "bootstrap_state.py").write_text(
        "from pathlib import Path\n"
        "def _secure_chain(path, owner, *, allow_missing=False):\n"
        "    assert path == Path('/var/lib/station/dependency-install')\n"
        "    assert owner == 0 and allow_missing is True\n"
    )
    # The real receipt serializer runs, while its filesystem sink is confined to
    # this fixture. It cannot write its production /var/lib path.
    (package / "filesystem.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "class SafeFS:\n"
        "    def __init__(self, roots):\n"
        "        assert roots == [Path('/var/lib/station/dependency-install')]\n"
        "    def mkdir(self, path, **kwargs):\n"
        "        assert path == Path('/var/lib/station/dependency-install')\n"
        "    def write_text(self, path, content, **kwargs):\n"
        "        assert path.parent == Path('/var/lib/station/dependency-install')\n"
        "        assert kwargs == {'mode': 0o600, 'owner': (0, 0)}\n"
        "        Path(os.environ['FIXTURE_RECEIPT']).write_text(content)\n"
    )
    calls, receipt, mutations = root / "children", root / "receipt.json", root / "mutations"
    executable(scripts / "station_deps_install.sh", """#!/bin/bash
set -Eeuo pipefail
[[ "$1" == --component ]]
printf '%s\n' "$2" >> "$FIXTURE_CALLS"
install_fixture() {
  if [[ "$2" == "$FIXTURE_FAILED_COMPONENT" ]]; then
    if [[ "$FIXTURE_FAILURE" == internal ]]; then
      false
      printf 'FALSE_INSTALL_SUCCESS\n'
    else
      return "$FIXTURE_FAILURE"
    fi
  fi
}
install_fixture "$@"
printf 'CHILD_COMPLETE %s\n' "$2"
""")
    bins = root / "bin"
    bins.mkdir()
    executable(bins / "id", "#!/bin/sh\nprintf '0\\n'\n")
    executable(bins / "uname", "#!/bin/sh\nprintf 'Linux\\n'\n")
    for name in ("install", "apt-get", "systemctl", "sudo", "podman", "curl"):
        executable(bins / name, f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(name)} >> \"$FIXTURE_MUTATIONS\"\nexit 79\n")
    # This entry has the real parser/dispatcher. Self-invoked children above are
    # synthetic; only its fixed receipt interpreter is substituted for macOS.
    entry = scripts / "entry.sh"
    entry.write_text(SCRIPT.read_text().replace("/usr/bin/python3", shlex.quote(sys.executable)))
    env = dict(os.environ, PATH=f"{bins}:/usr/bin:/bin", STATION_HOME=str(root / "absent-home"),
               STATION_USER="fixture", FIXTURE_CALLS=str(calls), FIXTURE_RECEIPT=str(receipt),
               FIXTURE_MUTATIONS=str(mutations), FIXTURE_FAILED_COMPONENT="", FIXTURE_FAILURE="43",
               PYTHONDONTWRITEBYTECODE="1")

    def run(*arguments, **overrides):
        return subprocess.run(["/bin/bash", str(entry), *arguments], env=env | overrides,
                              capture_output=True, text=True, timeout=20)

    return SimpleNamespace(run=run, calls=calls, receipt=receipt, mutations=mutations)


@pytest.mark.parametrize("failure", ["43", "internal"])
def test_full_batch_attempts_later_components_and_records_failure(harness, failure):
    result = harness.run("--all", FIXTURE_FAILED_COMPONENT="ponytail", FIXTURE_FAILURE=failure)
    assert result.returncode == 1
    assert harness.calls.read_text().splitlines() == list(COMPONENTS)
    assert "FALSE_INSTALL_SUCCESS" not in result.stdout
    assert "CHILD_COMPLETE ponytail" not in result.stdout
    assert "CHILD_COMPLETE chatbotx" in result.stdout
    receipt = json.loads(harness.receipt.read_text())
    assert receipt["full_selection"] is True
    assert receipt["installation_steps_passed"] is False
    assert receipt["operational"] is False
    rows = {row["component"]: row["exit_code"] for row in receipt["components"]}
    assert rows["ponytail"] == (1 if failure == "internal" else 43)
    assert rows["chatbotx"] == 0
    assert "INCOMPLETE" in result.stderr
    assert not harness.mutations.exists()


def test_success_receipt_never_claims_operational(harness):
    result = harness.run("--all")
    assert result.returncode == 0, result.stderr
    receipt = json.loads(harness.receipt.read_text())
    assert receipt["installation_steps_passed"] is True
    assert receipt["operational"] is False
    assert [row["component"] for row in receipt["components"]] == list(COMPONENTS)
    assert all(row["exit_code"] == 0 for row in receipt["components"])


def test_explicit_batch_continues_after_failure_and_records_partial_selection(harness):
    result = harness.run("--component", "ponytail", "--component", "langfuse",
                         FIXTURE_FAILED_COMPONENT="ponytail", FIXTURE_FAILURE="internal")
    assert result.returncode == 1
    assert harness.calls.read_text().splitlines() == ["ponytail", "langfuse"]
    receipt = json.loads(harness.receipt.read_text())
    assert receipt["full_selection"] is False
    assert receipt["installation_steps_passed"] is False
    assert receipt["components"] == [
        {"component": "ponytail", "exit_code": 1}, {"component": "langfuse", "exit_code": 0},
    ]


@pytest.mark.parametrize("code", ["130", "143"])
def test_interruption_stops_later_children_and_keeps_incomplete_receipt(harness, code):
    result = harness.run("--all", FIXTURE_FAILED_COMPONENT="ponytail", FIXTURE_FAILURE=code)
    assert result.returncode != 0
    assert harness.calls.read_text().splitlines() == list(COMPONENTS[:COMPONENTS.index("ponytail") + 1])
    receipt = json.loads(harness.receipt.read_text())
    assert receipt["installation_steps_passed"] is False
    assert receipt["operational"] is False
    assert receipt["components"][-1] == {"component": "ponytail", "exit_code": int(code)}


@pytest.mark.parametrize("arguments", [
    ("--component", "invalid"),
    ("--component", "strix", "--component", "invalid"),
    ("--enable-hermes-auto-update", "--component", "invalid"),
    ("--all", "--component", "invalid"),
    ("--component", "invalid", "--all"),
])
def test_all_explicit_components_are_validated_before_mutation(harness, arguments):
    result = harness.run(*arguments)
    assert result.returncode == 2
    assert any(message in result.stderr for message in (
        "unknown component", "Choose --all OR explicit --component", "Choose one action",
    ))
    assert not harness.calls.exists()
    assert not harness.mutations.exists()
    assert not harness.receipt.exists()


@pytest.mark.parametrize("arguments", [
    ("--component",), ("--component", "--all"), ("--component", ""),
])
def test_missing_component_argument_fails_without_running_installers(harness, arguments):
    result = harness.run(*arguments)
    assert result.returncode == 2
    assert not harness.calls.exists()
    assert not harness.mutations.exists()
    assert not harness.receipt.exists()
