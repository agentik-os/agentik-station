"""Zone Composio routing tests use synthetic metadata, never account/native calls."""
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from agentik_station import cli, os_lifecycle, os_runtime
from agentik_station.errors import SecurityError, StationError, ValidationError


PUBLIC = Path("/usr/local/bin/composio")
TARGET = Path("/opt/station/tools/composio/0.4.0/composio")
RELEASE = Path("/opt/station/releases/synthetic-test")


def info(mode, *, uid=0, links=1):
    return SimpleNamespace(st_mode=mode, st_uid=uid, st_nlink=links)


@pytest.fixture
def metadata(monkeypatch):
    state = SimpleNamespace(
        lock=b"OTHER_PIN=1\nCOMPOSIO_CLI_VERSION=0.4.0\n",
        link=str(TARGET), checked=[], reads=[],
        files={PUBLIC: info(stat.S_IFLNK | 0o777), TARGET: info(stat.S_IFREG | 0o755)},
        parents={path: info(stat.S_IFDIR | 0o755)
                 for parent in (PUBLIC.parent, TARGET.parent)
                 for path in (parent, *parent.parents)},
    )
    monkeypatch.setattr(cli, "repository_root", lambda: RELEASE)

    def read(path, **kwargs):
        assert path == RELEASE / "config/versions.lock"
        assert kwargs == {"uid": 0, "immutable": True, "limit": 65536}
        state.reads.append(path)
        if isinstance(state.lock, Exception):
            raise state.lock
        return state.lock

    def checked(path):
        assert path in {PUBLIC.parent, TARGET.parent}
        state.checked.append(path)
        if hasattr(state, "ancestry_error"):
            raise state.ancestry_error

    original_lstat, original_stat, original_readlink = Path.lstat, Path.stat, cli.os.readlink

    def lstat(path):
        if path in {PUBLIC, TARGET}:
            result = state.files[path]
            if isinstance(result, Exception):
                raise result
            return result
        return original_lstat(path)

    def directory_stat(path, *, follow_symlinks=True):
        if path in state.parents:
            assert follow_symlinks is False
            return state.parents[path]
        return original_stat(path, follow_symlinks=follow_symlinks)

    def readlink(path, *args, **kwargs):
        if path == PUBLIC:
            return state.link
        return original_readlink(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Resolver must not use ambient PATH, execute software, or probe private homes")

    monkeypatch.setattr(os_lifecycle, "_read_bytes", read)
    monkeypatch.setattr(os_runtime, "require_root_owned_directory_chain", checked)
    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(Path, "stat", directory_stat)
    monkeypatch.setattr(cli.os, "readlink", readlink)
    monkeypatch.setattr(cli.shutil, "which", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.os, "access", forbidden)
    return state


def refused():
    with pytest.raises(StationError, match="Pinned public Composio CLI is missing or untrusted") as error:
        cli._composio_binary()
    assert "toolchain-install" in str(error.value)
    assert "synthetic-sensitive-detail" not in str(error.value)


def test_selects_only_root_managed_public_export_without_path_or_private_fallback(metadata, monkeypatch):
    monkeypatch.setenv("PATH", "/home/agk-station/.local/bin:/attacker/bin:/usr/local/bin")
    assert cli._composio_binary() == PUBLIC
    assert metadata.checked == [PUBLIC.parent, TARGET.parent]
    assert metadata.reads == [RELEASE / "config/versions.lock"]


@pytest.mark.parametrize("lock", [
    b"", b"COMPOSIO_CLI_VERSION", b"COMPOSIO_CLI_VERSION=", b"COMPOSIO_CLI_VERSION=0.4",
    b"COMPOSIO_CLI_VERSION=0.4.0.1", b"COMPOSIO_CLI_VERSION=0.4.0-beta.1",
    b"COMPOSIO_CLI_VERSION=../../private", b"COMPOSIO_CLI_VERSION=0.4.0 ",
    b"COMPOSIO_CLI_VERSION=0.4.0\nCOMPOSIO_CLI_VERSION=0.4.0",
    b"COMPOSIO_CLI_VERSION=\xff.4.0",
])
def test_rejects_missing_ambiguous_or_invalid_lock_pin(metadata, lock):
    metadata.lock = lock
    refused()
    assert not metadata.checked


@pytest.mark.parametrize("failure", [
    FileNotFoundError("synthetic-sensitive-detail"),
    SecurityError("synthetic-sensitive-detail"),
])
def test_rejects_untrusted_or_missing_release_lock_with_redacted_error(metadata, failure):
    metadata.lock = failure
    refused()


@pytest.mark.parametrize("target", [
    "/home/agk-station/.local/bin/composio", "/home/agk-station/.composio/composio",
    "/opt/station/tools/composio/0.3.9/composio", "/opt/unreviewed/composio",
    "../../../opt/station/tools/composio/0.4.0/composio",
])
def test_rejects_private_foreign_old_pin_or_noncanonical_link(metadata, target):
    metadata.link = target
    refused()


@pytest.mark.parametrize("metadata_entry", [
    info(stat.S_IFREG | 0o755), info(stat.S_IFLNK | 0o777, uid=1001),
    info(stat.S_IFLNK | 0o777, links=2), FileNotFoundError("synthetic-sensitive-detail"),
])
def test_rejects_unmanaged_or_missing_public_entrypoint(metadata, metadata_entry):
    metadata.files[PUBLIC] = metadata_entry
    refused()


@pytest.mark.parametrize("metadata_entry", [
    info(stat.S_IFLNK | 0o777), info(stat.S_IFIFO | 0o755),
    info(stat.S_IFREG | 0o755, uid=1001), info(stat.S_IFREG | 0o755, links=2),
    info(stat.S_IFREG | 0o775), info(stat.S_IFREG | 0o757),
    info(stat.S_IFREG | 0o4755), info(stat.S_IFREG | 0o2755),
    info(stat.S_IFREG | 0o750), info(stat.S_IFREG | 0o754), info(stat.S_IFREG | 0o751),
    FileNotFoundError("synthetic-sensitive-detail"),
])
def test_rejects_unsafe_or_zone_inaccessible_export(metadata, metadata_entry):
    metadata.files[TARGET] = metadata_entry
    refused()


def test_rejects_untrusted_ancestry_without_fallback(metadata):
    metadata.ancestry_error = SecurityError("synthetic-sensitive-detail")
    refused()


@pytest.mark.parametrize("parent", [PUBLIC.parent, TARGET.parent, Path("/opt/station")])
def test_rejects_parent_that_zone_cannot_traverse(metadata, parent):
    metadata.parents[parent] = info(stat.S_IFDIR | 0o750)
    refused()


@pytest.fixture
def blocked_adapter(monkeypatch):
    state = SimpleNamespace(
        zone={"id": "os", "organization": None, "unix_user": "z-factory",
              "ignored_private_metadata": "synthetic-sensitive-detail"},
        loaded=[],
    )

    def load(zone_id):
        state.loaded.append(zone_id)
        if zone_id != state.zone["id"]:
            raise ValidationError("Local Zone desired state not found")
        return state.zone

    def forbidden(*args, **kwargs):
        pytest.fail("Unbound Composio facade must not resolve binaries, execute, enroll or write")

    monkeypatch.setattr(cli, "_load_zone_record", load)
    monkeypatch.setattr(cli, "_composio_binary", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.shutil, "which", forbidden)
    monkeypatch.setattr(cli.pwd, "getpwnam", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    return state


def adapter_args(action, zone="os"):
    return SimpleNamespace(composio_discord_command=action, zone=zone)


@pytest.mark.parametrize("zone_id,organization,principal", [
    ("os", None, "station:personal:os:atlas"),
    ("acme-development", "acme", "station:acme:acme-development:atlas"),
])
def test_composio_plan_has_only_scoped_non_executable_pinned_grammar_templates(
        blocked_adapter, capsys, zone_id, organization, principal):
    blocked_adapter.zone.update(id=zone_id, organization=organization)
    assert cli.cmd_composio_discord(adapter_args("plan", zone_id)) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert blocked_adapter.loaded == [zone_id]
    assert payload["zone_id"] == zone_id and payload["principal"] == principal
    assert payload["state"] == "CONFIGURATION_REQUIRED"
    assert payload["claim"] == "NON_EXECUTABLE_TEMPLATES"
    assert all(payload[key] is False for key in ("execution_authorized", "accounts_checked", "operational"))
    assert payload["gateway"] == "hermes-native"
    assert payload["policy"] == "config/composio/discord-tool-policy.json"
    assert "commands" not in payload and "stdout" not in payload and "stderr" not in payload
    templates = {row["action"]: row for row in payload["command_templates"]}
    assert templates["link"]["argv"] == [
        "composio", "dev", "connected-accounts", "link", "discord",
        "--project-name", "<VERIFIED_DEVELOPER_PROJECT_NAME>",
        "--user-id", principal, "--no-browser",
    ]
    assert templates["account-readback"]["argv"] == [
        "composio", "dev", "connected-accounts", "list", "--toolkits", "discord",
        "--user-id", principal,
    ]
    assert templates["tool-catalog"]["argv"] == ["composio", "tools", "list", "discord"]
    assert all(row["cwd"].startswith("<") for row in templates.values())
    assert "COMPOSIO_USER_ID" not in captured.out
    assert "synthetic-sensitive-detail" not in captured.out + captured.err
    assert "developer-project" in payload["next_repair_action"]
    assert "COMPOSIO_DEVELOPER_BINDING.md" in payload["next_repair_action"]


@pytest.mark.parametrize("action", ["link", "verify"])
@pytest.mark.parametrize("uid", [0, 990, 1001])
def test_composio_account_actions_refuse_before_any_native_or_account_call(
        blocked_adapter, capsys, monkeypatch, action, uid):
    monkeypatch.setattr(cli.os, "geteuid", lambda: uid)
    with pytest.raises(StationError, match="explicit trusted developer-project") as error:
        cli.cmd_composio_discord(adapter_args(action))
    assert "working-directory binding" in str(error.value)
    assert "COMPOSIO_DEVELOPER_BINDING.md" in str(error.value)
    assert "synthetic-sensitive-detail" not in str(error.value)
    assert blocked_adapter.loaded == ["os"]
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


@pytest.mark.parametrize("action", ["plan", "link", "verify"])
def test_composio_facade_rejects_unresolved_zone_without_fallback(blocked_adapter, capsys, action):
    with pytest.raises(ValidationError, match="Local Zone desired state not found"):
        cli.cmd_composio_discord(adapter_args(action, "other-zone"))
    assert blocked_adapter.loaded == ["other-zone"]
    assert capsys.readouterr().out == ""


def test_composio_facade_rejects_unknown_action_without_native_call(blocked_adapter, capsys):
    with pytest.raises(ValidationError, match="Unknown Composio Discord action"):
        cli.cmd_composio_discord(adapter_args("login"))
    assert capsys.readouterr().out == ""


def test_composio_blocker_guide_records_exact_source_and_no_execution_claim():
    guide = (Path(__file__).resolve().parents[2]
             / "docs/dependencies/COMPOSIO_DEVELOPER_BINDING.md").read_text()
    for fact in ("1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28", "CONFIGURATION_REQUIRED",
                 "composio tools list discord", "consumer", "working-directory",
                 ".env.local", "zero CLI exit"):
        assert fact in guide
