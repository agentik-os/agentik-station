import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/station_guided_setup_enable.sh"
READY_STATUS = {
    "BackendState": "Running",
    "Self": {
        "Online": True,
        "TailscaleIPs": ["100.100.100.100"],
        "DNSName": "fixture.example.ts.net.",
    },
}

MOCK_COMMAND = r'''
import json
import os
import sys
import tempfile
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["AGK_TEST_COMMAND_LOG"], "a") as log:
    log.write(json.dumps([name, *args]) + "\n")
if name == "id":
    if args == ["-u"]:
        print("0")
elif name == "install":
    assert Path(args[-1]).resolve().is_relative_to(Path(os.environ["AGK_TEST_ROOT"]).resolve())
    Path(args[-1]).mkdir(parents=True, exist_ok=True)
elif name == "curl":
    if args[-1] == "http://127.0.0.1:8787/health":
        counter = Path(os.environ["AGK_TEST_HEALTH_COUNTER"])
        attempts = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(attempts))
        if attempts <= int(os.environ.get("AGK_TEST_HEALTH_FAILURES", "0")):
            sys.exit(7)
    elif args[-1].startswith("https:"):
        counter = Path(os.environ["AGK_TEST_ROOT"]) / "https-attempts"
        attempts = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(attempts))
        if attempts <= int(os.environ.get("AGK_TEST_HTTPS_FAILURES", "0")):
            sys.exit(int(os.environ.get("AGK_TEST_HTTPS_TRANSIENT_CODE", "28")))
        sys.exit(int(os.environ.get("AGK_TEST_READBACK_RETURN_CODE", "0")))
elif name == "tailscale":
    if args == ["status", "--json"]:
        print(os.environ["AGK_TEST_TAILSCALE_STATUS"])
        sys.exit(int(os.environ.get("AGK_TEST_STATUS_RETURN_CODE", "0")))
    if not args or args[0] != "serve":
        sys.exit(99)
elif name == "mktemp":
    directory = args[0].removeprefix("--tmpdir=")
    assert Path(directory).resolve().is_relative_to(Path(os.environ["AGK_TEST_ROOT"]).resolve())
    descriptor, path = tempfile.mkstemp(prefix=".env.station.", dir=directory)
    os.close(descriptor)
    print(path)
elif name == "stat":
    print("z-system-discord")
elif name not in {"systemctl", "sleep", "chown"}:
    sys.exit(99)
'''


@pytest.fixture
def setup_fixture(tmp_path):
    jq = shutil.which("jq")
    if not jq:
        pytest.skip("jq is required by the guided-setup script")
    zone_root = tmp_path / "zones/discord-bootstrap"
    (zone_root / "hermes").mkdir(parents=True)
    zone_record = tmp_path / "discord-bootstrap.json"
    zone_record.write_text(
        json.dumps({
            "id": "discord-bootstrap",
            "unix_user": "z-system-discord",
            "state_root": str(zone_root),
        }),
        encoding="utf-8",
    )
    # Remap only filesystem roots; every exercised branch is the real script.
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count("zone_root=/var/lib/station/zones/discord-bootstrap\n") == 1
    assert source.count("zone_record=/etc/station/zones.d/discord-bootstrap.json\n") == 1
    source = source.replace(
        "zone_root=/var/lib/station/zones/discord-bootstrap", f"zone_root={zone_root}"
    ).replace(
        "zone_record=/etc/station/zones.d/discord-bootstrap.json",
        f"zone_record={zone_record}",
    )
    script = tmp_path / "guided-setup.sh"
    script.write_text(source, encoding="utf-8")
    fixture_bin = tmp_path / "bin"
    fixture_bin.mkdir()
    mock = fixture_bin / "mock-command"
    mock.write_text(f"#!{sys.executable}\n{MOCK_COMMAND}", encoding="utf-8")
    mock.chmod(0o700)
    for command in ("id", "install", "systemctl", "curl", "sleep", "tailscale", "mktemp", "stat", "chown"):
        (fixture_bin / command).symlink_to(mock)
    (fixture_bin / "jq").symlink_to(jq)
    env = {
        "PATH": f"{fixture_bin}:/usr/bin:/bin",
        "AGK_TEST_ROOT": str(tmp_path),
        "AGK_TEST_COMMAND_LOG": str(tmp_path / "commands.jsonl"),
        "AGK_TEST_HEALTH_COUNTER": str(tmp_path / "health-attempts"),
        "AGK_TEST_TAILSCALE_STATUS": json.dumps(READY_STATUS),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return script, zone_root, env


def run_setup(fixture, *, optional=True):
    script, _, env = fixture
    return subprocess.run(
        ["/bin/bash", str(script), *(["--if-enrolled"] if optional else [])],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def commands(fixture):
    return [
        json.loads(line)
        for line in Path(fixture[2]["AGK_TEST_COMMAND_LOG"]).read_text().splitlines()
    ]


@pytest.mark.parametrize("optional", [False, True])
@pytest.mark.parametrize("unmet_gate", ["needs-login", "offline", "missing-online", "missing-ips", "missing-dns", "invalid-dns", "invalid-json", "status-error"])
def test_unmet_tailnet_gate_does_not_publish_or_write_credentials(setup_fixture, optional, unmet_gate):
    _, zone_root, env = setup_fixture
    status = json.loads(json.dumps(READY_STATUS))
    if unmet_gate == "needs-login":
        status["BackendState"] = "NeedsLogin"
        status["Self"].pop("DNSName")
    elif unmet_gate == "offline":
        status["Self"]["Online"] = False
    elif unmet_gate == "missing-online":
        status["Self"].pop("Online")
    elif unmet_gate == "missing-ips":
        status["Self"]["TailscaleIPs"] = []
    elif unmet_gate == "missing-dns":
        status["Self"].pop("DNSName")
    elif unmet_gate == "invalid-dns":
        status["Self"]["DNSName"] = "fixture.example.com"
    elif unmet_gate == "status-error":
        env["AGK_TEST_STATUS_RETURN_CODE"] = "1"
    env["AGK_TEST_TAILSCALE_STATUS"] = "not-json" if unmet_gate == "invalid-json" else json.dumps(status)

    result = run_setup(setup_fixture, optional=optional)

    assert result.returncode == (0 if optional else 2), result.stderr
    assert "LOCAL_BROKER_READY_TAILNET_NOT_READY" in result.stdout
    assert "NEXT:" in result.stdout
    observed = commands(setup_fixture)
    assert ["systemctl", "enable", "--now", "station-guided-setup.service"] in observed
    assert not any(call[:2] == ["tailscale", "serve"] for call in observed)
    assert not (zone_root / "hermes/.env").exists()
    assert not any("CONFIGURED" in line for line in result.stdout.splitlines())


def test_broker_startup_is_retried_before_one_tailnet_snapshot(setup_fixture):
    _, zone_root, env = setup_fixture
    env["AGK_TEST_HEALTH_FAILURES"] = "2"

    result = run_setup(setup_fixture)

    assert result.returncode == 0, result.stderr
    assert Path(env["AGK_TEST_HEALTH_COUNTER"]).read_text() == "3"
    observed = commands(setup_fixture)
    assert sum(call == ["tailscale", "status", "--json"] for call in observed) == 1
    assert sum(call == ["sleep", "1"] for call in observed) == 2
    assert ["tailscale", "serve", "--bg", "--yes", "--https=443", "--set-path=/station-setup", "http://127.0.0.1:8787"] in observed
    assert any(call[0] == "curl" and call[-1] == "https://fixture.example.ts.net/station-setup/health" for call in observed)
    assert "STATE: TAILNET_GUIDED_SETUP_CONFIGURED" in result.stdout
    environment = zone_root / "hermes/.env"
    assert "STATION_SETUP_BASE_URL=https://fixture.example.ts.net/station-setup\n" in environment.read_text()
    assert environment.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("optional", [False, True])
def test_unhealthy_broker_fails_after_bounded_retries(setup_fixture, optional):
    _, _, env = setup_fixture
    env["AGK_TEST_HEALTH_FAILURES"] = "100"

    result = run_setup(setup_fixture, optional=optional)

    assert result.returncode == 2
    assert "loopback setup broker" in result.stderr
    assert Path(env["AGK_TEST_HEALTH_COUNTER"]).read_text() == "10"
    assert not any(call[0] == "tailscale" for call in commands(setup_fixture))


def test_optional_mode_does_not_hide_enrolled_tailnet_readback_failure(setup_fixture):
    _, zone_root, env = setup_fixture
    env["AGK_TEST_READBACK_RETURN_CODE"] = "7"

    result = run_setup(setup_fixture)

    assert result.returncode != 0
    assert not (zone_root / "hermes/.env").exists()
    assert "TAILNET_GUIDED_SETUP_CONFIGURED" not in result.stdout
    assert (Path(env["AGK_TEST_ROOT"]) / "https-attempts").read_text() == "5"


@pytest.mark.parametrize("code", [6, 7, 28, 35, 52, 56])
def test_first_https_certificate_or_transport_startup_is_bounded_and_retried(setup_fixture, code):
    _, zone_root, env = setup_fixture
    env["AGK_TEST_HTTPS_FAILURES"] = "2"
    env["AGK_TEST_HTTPS_TRANSIENT_CODE"] = str(code)
    result = run_setup(setup_fixture)
    assert result.returncode == 0, result.stderr
    assert (Path(env["AGK_TEST_ROOT"]) / "https-attempts").read_text() == "3"
    observed = commands(setup_fixture)
    assert sum(call == ["sleep", "2"] for call in observed) == 2
    assert sum(call[:2] == ["tailscale", "serve"] and "--bg" in call for call in observed) == 1
    requests = [call for call in observed if call[0] == "curl" and call[-1].startswith("https:")]
    assert all("--fail" in call and "--connect-timeout" in call and "--max-time" in call for call in requests)
    assert all("--insecure" not in call and "-k" not in call for call in requests)
    assert "STATION_SETUP_BASE_URL=https://fixture.example.ts.net/station-setup" in (zone_root / "hermes/.env").read_text()


@pytest.mark.parametrize("code", [22, 60, 77])
def test_https_http_or_certificate_errors_fail_without_retry_or_credential_write(setup_fixture, code):
    _, zone_root, env = setup_fixture
    existing = zone_root / "hermes/.env"
    existing.write_text("EXISTING_PRIVATE_VALUE=fixture-sentinel\n")
    env["AGK_TEST_READBACK_RETURN_CODE"] = str(code)
    result = run_setup(setup_fixture)
    assert result.returncode == code
    assert (Path(env["AGK_TEST_ROOT"]) / "https-attempts").read_text() == "1"
    assert existing.read_text() == "EXISTING_PRIVATE_VALUE=fixture-sentinel\n"
    assert "fixture-sentinel" not in result.stdout + result.stderr
    assert "TAILNET_GUIDED_SETUP_CONFIGURED" not in result.stdout
    assert not list((zone_root / "hermes").glob(".env.station.*"))
