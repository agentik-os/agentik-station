from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("station_controls_refresh", ROOT / "scripts/refresh-controls.py")
assert SPEC and SPEC.loader
refresh = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = refresh
SPEC.loader.exec_module(refresh)
REVIEWED_PREVIOUS = refresh.PREVIOUS


@pytest.fixture
def controls(tmp_path, monkeypatch):
    home = tmp_path / "home"
    prefix = home / ".local"
    source = tmp_path / "source"
    account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(), pw_name="agk-station", pw_dir=str(home))
    monkeypatch.setattr(refresh, "_operator", lambda: account)
    previous = {}
    pairs = []
    for destination, (relative, mode) in refresh.TARGETS.items():
        src = source / relative
        dst = home / destination
        src.parent.mkdir(parents=True, exist_ok=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        old = ("#!/bin/sh\n# old " + relative + "\n").encode()
        new = ("#!/bin/sh\n# new " + relative + "\n").encode()
        src.write_bytes(new)
        dst.write_bytes(old)
        src.chmod(mode)
        dst.chmod(mode)
        previous[relative] = frozenset({hashlib.sha256(old).hexdigest()})
        pairs.append((src, dst, old, new))
    monkeypatch.setattr(refresh, "PREVIOUS", previous)
    return source, prefix, pairs


def changed_paths(prefix, pairs):
    return [str(dst.relative_to(prefix.parent)) for _, dst, _, _ in pairs]


def test_refresh_only_reviewed_software_and_idempotent(controls):
    source, prefix, pairs = controls
    untouched = [prefix / "lib/agk-terminal/bin/agk-tui", prefix / "lib/agk-terminal/config/providers.yaml",
                 prefix.parent / ".hermes/.env", prefix.parent / ".agentik/runtime.db",
                 prefix.parent / ".hermes/config.yaml",
                 prefix.parent / ".hermes/profiles/other/plugins/platforms/discord/agk_session_panel.py"]
    for path in untouched:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic-do-not-touch")
        path.chmod(0o600)
    result = refresh.refresh_controls(source, prefix)
    assert result == {"state": "CONTROLS_REFRESHED", "changed": changed_paths(prefix, pairs), "runtime_verified": False}
    for _, dst, _, new in pairs:
        assert dst.read_bytes() == new
        assert stat.S_IMODE(dst.stat().st_mode) == refresh.TARGETS[str(dst.relative_to(prefix.parent))][1]
    assert all(path.read_bytes() == b"synthetic-do-not-touch" for path in untouched)
    assert refresh.refresh_controls(source, prefix)["changed"] == []


def test_frozen_sources_use_actual_shipped_modes_not_destination_execute_bits(controls):
    source, prefix, pairs = controls
    for src, _, _, _ in pairs:
        relative = src.relative_to(source)
        shipped_mode = stat.S_IMODE((ROOT / relative).stat().st_mode)
        src.chmod(shipped_mode & ~0o222)
    # This Git-0644 helper is installed 0755 by the component installer. A
    # frozen release has source mode0444: reading it is not an execution probe.
    watchdog = source / "scripts/gateway_watchdog.py"
    assert not watchdog.stat().st_mode & 0o111
    assert refresh.refresh_controls(source, prefix)["changed"] == changed_paths(prefix, pairs)
    assert stat.S_IMODE((prefix / "lib/agk-terminal/scripts/gateway_watchdog.py").stat().st_mode) == 0o755


@pytest.mark.parametrize("version", ["11.22", "11.23", "11.24", "11.25"])
def test_refresh_accepts_each_exact_reviewed_predecessor(controls, monkeypatch, version):
    source, prefix, pairs = controls
    previous = {}
    for (relative, _), (_, dst, _, _) in zip(refresh.TARGETS.values(), pairs):
        versions = {name: f"#!/bin/sh\n# {name} {relative}\n".encode()
                    for name in ("11.22", "11.23", "11.24", "11.25")}
        previous[relative] = frozenset(hashlib.sha256(value).hexdigest()
                                       for value in versions.values())
        dst.write_bytes(versions[version])
    monkeypatch.setattr(refresh, "PREVIOUS", previous)
    assert refresh.refresh_controls(source, prefix)["changed"] == changed_paths(prefix, pairs)
    assert all(dst.read_bytes() == new for _, dst, _, new in pairs)


def test_predecessor_allowlist_is_only_exact_reviewed_software():
    assert refresh.PREVIOUS == {
        "bin/agk": frozenset({
            "f86d05b8e2c014056eb49e362bffcac2c9c73755536ebd5699b4b59364b68df8",
            "4e84b0bf28eb936a062b476c52dc3d546281c1739dec2c117e7d97e96e829be6",
            "94a54f416f35db6b0a2f5f5c3cda4fd176f716bc5e5aa0a8d1678add40af4013",
        }),
        "scripts/agk_control.py": frozenset({
            "5ae627aa79d2eca21194b0b735dbee5030039c3a498526ec3f3b262f5773133d",
            "0e527d95999f1bf052abe6b27adc1e01054c6f505328fb853d68da328ffcba5b",
            "21a84b2cc3566fe2d1ed59c9d95f7aa15d7026d28e0a3ce5ef5aa898d3753c9a",
            "e12560e812fb40f52c5e535d9f5699f4b0ddd3761a2f8837c99835e33b13e561",
        }),
        "scripts/provider.sh": frozenset({
            "e9d8c11fe54612b7598cf4aa2690a5b8526300f5aa1ecca8a96a76fca0037c13",
            "9e1bb99c5ae16c2ae89f66c4e507de05e2dbf6e7fd70be6955c38fe9a318ea7d",
        }),
        "scripts/gateway_watchdog.py": frozenset({
            "a20c69424a87d6121ac62e54756836d4e63d7c090a7e80fff9a431c122f24419",
        }),
        "scripts/doctor.sh": frozenset({
            "ace715215cecb66869c20aed1a7402fcdfc8c6fd6e36233421a4cb3c8b9b1c82",
        }),
        "hermes/plugins/platforms/discord/agk_session_panel.py": frozenset({
            "28695b10ddc08b55f5563bb9a6fb712db7b2f8b8e6836cd1e77e724290b59b98",
        }),
        "scripts/sync-hermes.sh": frozenset({
            "246dc7015ad4c4fb5722218a89127d7b244b9d5a4ab0b92e193a061733c27c80",
        }),
        "hermes/plugins/agentik_os/agent_registry.py": frozenset({
            "e48d609d88727a6f2c27d0adf69b6ff5917ded14776aa94caf5e13ebfcc9a3c8",
        }),
        "hermes/plugins/agentik_os/canonical_routing.py": frozenset(),
    }
    assert {source for source, _ in refresh.TARGETS.values()} == set(refresh.PREVIOUS)
    assert set(refresh.TARGETS) == {
        ".local/bin/agk", ".local/lib/agk-terminal/scripts/agk_control.py",
        ".local/lib/agk-terminal/scripts/provider.sh",
        ".local/lib/agk-terminal/scripts/gateway_watchdog.py",
        ".local/lib/agk-terminal/scripts/doctor.sh",
        ".local/lib/agk-terminal/hermes/plugins/platforms/discord/agk_session_panel.py",
        ".hermes/plugins/platforms/discord/agk_session_panel.py",
        ".local/lib/agk-terminal/scripts/sync-hermes.sh",
        ".local/lib/agk-terminal/hermes/plugins/agentik_os/canonical_routing.py",
        ".hermes/plugins/agentik_os/canonical_routing.py",
        ".local/lib/agk-terminal/hermes/plugins/agentik_os/agent_registry.py",
        ".hermes/plugins/agentik_os/agent_registry.py",
    }


@pytest.fixture
def reviewed_host_controls(controls, monkeypatch):
    """Reconstruct exact 11.24/11.25 bytes from the reviewed 023c036 delta.

    No Git history or network is required in packaged-source test runs. These
    hashes were independently matched against Git and immutable live 11.25.
    """
    source, prefix, pairs = controls
    removed = {
        "bin/agk": '''    if [ -n "${STATION_WORKSTATION_ROOT:-}" ]; then
      /usr/bin/python3 -I -S "$install_root/hermes/plugins/agentik_os/workstation.py" --validate >/dev/null || exit 2
      echo 'Client Organizations and isolated OS instances belong to a Linux Station Host with independent-UID Zones. The legacy agk client controller is not supported in personal Workstation mode; use the Host station organization/project/os instance workflow.' >&2
      exit 2
    fi
''',
        "scripts/provider.sh": '''if [ -n "${STATION_WORKSTATION_ROOT:-}" ]; then
  workstation_component=${AGK_TERMINAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}
  /usr/bin/python3 -I -S "$workstation_component/hermes/plugins/agentik_os/workstation.py" --validate >/dev/null || exit 2
  if [ "$action" = install ]; then
    echo 'Station Workstation owns pinned dependencies: use agentik-station repair --root PATH; model enrollment uses agentik-station model --root PATH. Installed CLIs retain their scoped login commands.' >&2
    exit 2
  fi
fi

''',
        "scripts/agk_control.py": '''        permitted = cwd == allowed or allowed in cwd.parents
        if os.environ.get("STATION_WORKSTATION_ROOT"):
            # Shared canonical resolver used by the plugin and controller. Load
            # just this stdlib helper, not the Hermes plugin __init__ package.
            import importlib.util
            helper = Path(__file__).resolve().parents[1] / "hermes/plugins/agentik_os/workstation.py"
            spec = importlib.util.spec_from_file_location("agk_workstation_scope", helper)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            permitted = module.permitted_cwd(cwd, self.env.home)
        if not permitted:
''',
    }
    expected = {
        "bin/agk": "94a54f416f35db6b0a2f5f5c3cda4fd176f716bc5e5aa0a8d1678add40af4013",
        "scripts/agk_control.py": "21a84b2cc3566fe2d1ed59c9d95f7aa15d7026d28e0a3ce5ef5aa898d3753c9a",
        "scripts/provider.sh": "9e1bb99c5ae16c2ae89f66c4e507de05e2dbf6e7fd70be6955c38fe9a318ea7d",
    }
    actual_pairs = []
    for src, dst, _, _ in pairs:
        relative = str(src.relative_to(source))
        new = (ROOT / relative).read_bytes()
        old = new
        if relative == "scripts/agk_control.py":
            # Remove the later identity-aware specialist policy as well; keep
            # the fixture bound to actual 11.24/11.25 bytes, not today's source.
            helper_start = old.index(b"def specialist_environment(")
            helper_end = old.index(b"def specialist_definition(", helper_start)
            old = old[:helper_start] + old[helper_end:]
            old = old.replace(
                b"    environment, policy_scope = specialist_environment(env)\n"
                b"    if not {environment, policy_scope}.intersection(scope):\n",
                b'    if env.name != "operator" and env.name not in scope:\n',
            )
            # Strip the later canonical Station handoff too. The fixed
            # predecessor hash below must keep proving historical bytes.
            routing_start = old.index(b"    # This operator-local catalog is not the trusted Station instance ledger.")
            routing_end = old.index(b"    root = agent_catalog_path(env.home).resolve()", routing_start)
            old = old[:routing_start] + old[routing_end:]
            old = old.replace(
                b'''    canonical = f"{env.name}-{definition['id']}"\n''',
                b'    canonical = f"{env.name}-{agent_id}"\n',
            )
        if relative in removed:
            delta = removed[relative].encode()
            assert old.count(delta) == 1
            replacement = (b"        if cwd != allowed and allowed not in cwd.parents:\n"
                           if relative == "scripts/agk_control.py" else b"")
            old = old.replace(delta, replacement)
            assert hashlib.sha256(old).hexdigest() == expected[relative]
        src.write_bytes(new)
        dst.write_bytes(old)
        actual_pairs.append((src, dst, old, new))
    monkeypatch.setattr(refresh, "PREVIOUS", REVIEWED_PREVIOUS)
    return source, prefix, actual_pairs


def test_reviewed_1124_1125_refresh_changes_only_three_software_files(reviewed_host_controls):
    source, prefix, pairs = reviewed_host_controls
    untouched = {dst: dst.stat().st_ino for _, dst, old, new in pairs if old == new}
    # The new helper is Workstation-only, not an extra Host refresh destination.
    assert not (prefix / "lib/agk-terminal/hermes/plugins/agentik_os/workstation.py").exists()
    result = refresh.refresh_controls(source, prefix)
    assert result == {"state": "CONTROLS_REFRESHED", "changed": changed_paths(prefix, pairs[:3]),
                      "runtime_verified": False}
    assert len(untouched) == len(refresh.TARGETS) - 3
    assert all(dst.stat().st_ino == inode for dst, inode in untouched.items())
    assert all(dst.read_bytes() == new for _, dst, _, new in pairs)
    assert refresh.refresh_controls(source, prefix)["changed"] == []


@pytest.mark.parametrize("which", range(3))
def test_modified_reviewed_host_predecessor_is_preserved(reviewed_host_controls, which):
    source, prefix, pairs = reviewed_host_controls
    dst = pairs[which][1]
    dst.write_bytes(dst.read_bytes() + b"\n# local customization\n")
    before = [path.read_bytes() for _, path, _, _ in pairs]
    with pytest.raises(ValueError, match="customized"):
        refresh.refresh_controls(source, prefix)
    assert [path.read_bytes() for _, path, _, _ in pairs] == before


@pytest.mark.parametrize("which", range(len(refresh.TARGETS)))
def test_customized_controls_preserved_before_any_write(controls, which):
    source, prefix, pairs = controls
    pairs[which][1].write_bytes(b"operator customized script")
    before = [dst.read_bytes() for _, dst, _, _ in pairs]
    with pytest.raises(ValueError, match="customized"):
        refresh.refresh_controls(source, prefix)
    assert [dst.read_bytes() for _, dst, _, _ in pairs] == before


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "writable", "missing"])
def test_unsafe_controls_are_not_followed_or_replaced(controls, kind):
    source, prefix, pairs = controls
    src, dst, _, _ = pairs[1]
    if kind in {"symlink", "hardlink", "fifo", "missing"}:
        dst.unlink()
        if kind == "symlink":
            dst.symlink_to(src)
        elif kind == "hardlink":
            os.link(src, dst)
        elif kind == "fifo":
            os.mkfifo(dst)
    else:
        dst.chmod(0o777)
    with pytest.raises((ValueError, OSError)):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]


@pytest.mark.parametrize("which", [5, 6])
def test_writable_or_missing_panel_copy_blocks_the_complete_refresh(controls, which):
    source, prefix, pairs = controls
    target = pairs[which][1]
    target.chmod(0o664)
    with pytest.raises(ValueError, match="Unsafe controls file"):
        refresh.refresh_controls(source, prefix)
    assert all(dst.read_bytes() == old for _, dst, old, _ in pairs)
    target.unlink()
    with pytest.raises(OSError):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]


def test_symlinked_destination_parent_is_refused(controls):
    source, prefix, pairs = controls
    parent = pairs[1][1].parent
    moved = parent.with_name("moved")
    parent.rename(moved)
    parent.symlink_to(moved, target_is_directory=True)
    with pytest.raises(OSError):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]


def test_unexpected_prefix_is_refused(controls):
    source, prefix, _ = controls
    with pytest.raises(ValueError, match="canonical"):
        refresh.refresh_controls(source, prefix.parent / "elsewhere")


def test_changed_target_between_preflight_and_write_is_preserved(controls, monkeypatch):
    source, prefix, pairs = controls
    read = refresh._read
    count = 0
    def racing_read(*args):
        nonlocal count
        count += 1
        if count == 2 * len(pairs) + 1:
            pairs[0][1].write_bytes(b"concurrent operator edit")
        return read(*args)
    monkeypatch.setattr(refresh, "_read", racing_read)
    with pytest.raises(ValueError, match="changed during"):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == b"concurrent operator edit"
    assert pairs[1][1].read_bytes() == pairs[1][2]


def test_parent_rename_cannot_claim_readback_of_obsolete_directory(controls, monkeypatch):
    source, prefix, pairs = controls
    read = refresh._read
    count = 0
    def renamed_read(*args):
        nonlocal count
        count += 1
        data = read(*args)
        if count == 2 * len(pairs) + 2:
            parent = pairs[0][1].parent
            parent.rename(parent.with_name("obsolete-bin"))
            parent.mkdir()
            pairs[0][1].write_bytes(pairs[0][2])
            pairs[0][1].chmod(0o755)
        return data
    monkeypatch.setattr(refresh, "_read", renamed_read)
    with pytest.raises(ValueError, match="directory changed"):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]
    assert pairs[1][1].read_bytes() == pairs[1][2]


def test_read_rejects_replaced_file_identity(controls, monkeypatch):
    source, prefix, pairs = controls
    original_stat = refresh.os.stat
    swapped = False
    def changed_stat(path, *args, **kwargs):
        nonlocal swapped
        if path == "agk" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            target = pairs[0][0]
            target.rename(target.with_name("old-agk"))
            target.write_bytes(pairs[0][3])
            target.chmod(0o755)
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(refresh.os, "stat", changed_stat)
    with pytest.raises(ValueError, match="file changed while"):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]


def test_partial_write_failure_can_retry_without_claiming_rollback(controls, monkeypatch):
    source, prefix, pairs = controls
    replace = refresh.os.replace
    count = 0
    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("fixture unavailable")
        return replace(*args, **kwargs)
    monkeypatch.setattr(refresh.os, "replace", fail_second)
    with pytest.raises(OSError):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][3]
    assert pairs[1][1].read_bytes() == pairs[1][2]
    assert not list(prefix.rglob(".station-control-*"))
    assert refresh.refresh_controls(source, prefix)["changed"] == changed_paths(prefix, pairs[1:])


@pytest.mark.parametrize("uid,user,home", [(0, "agk-station", "/home/agk-station"), (1000, "moonbase", "/home/moonbase"), (2000, "agk-station", "/other/home")])
def test_refresh_requires_nonroot_canonical_identity(monkeypatch, uid, user, home):
    monkeypatch.setattr(refresh.os, "geteuid", lambda: uid)
    monkeypatch.setattr(refresh.os, "getuid", lambda: uid)
    monkeypatch.setattr(refresh.pwd, "getpwuid", lambda _: SimpleNamespace(pw_uid=uid, pw_name=user, pw_dir=home))
    with pytest.raises(ValueError, match="non-root"):
        refresh._operator()


def test_component_controls_path_exits_before_build_network_or_hermes():
    source = (ROOT / "install.sh").read_text()
    invoke = source.index('exec /usr/bin/python3 -I "$repo_root/scripts/refresh-controls.py"')
    assert invoke < source.index("install_rmux\n")
    assert invoke < source.index("build --locked --release")
    assert invoke < source.index('pip install')


def test_missing_canonical_helpers_are_published_before_dependent_controller(controls, monkeypatch):
    source, prefix, pairs = controls
    new_pairs = [pair for pair in pairs if str(pair[1].relative_to(prefix.parent)) in refresh.NEW_TARGETS]
    for _, path, _, _ in new_pairs:
        path.unlink()
    replace = refresh.os.replace
    calls = []

    def checked_replace(*args, **kwargs):
        calls.append(args)
        assert all(path.read_bytes() == new for _, path, _, new in new_pairs)
        return replace(*args, **kwargs)

    monkeypatch.setattr(refresh.os, "replace", checked_replace)
    result = refresh.refresh_controls(source, prefix)
    assert calls and set(result["changed"][:2]) == refresh.NEW_TARGETS
    assert all(path.stat().st_nlink == 1 for _, path, _, _ in new_pairs)
    assert refresh.refresh_controls(source, prefix)["changed"] == []


def test_racing_new_helper_is_never_overwritten(controls, monkeypatch):
    source, prefix, pairs = controls
    targets = [pair for pair in pairs if str(pair[1].relative_to(prefix.parent)) in refresh.NEW_TARGETS]
    for _, path, _, _ in targets:
        path.unlink()
    link = refresh.os.link
    victim = targets[0][1]

    def raced_link(*args, **kwargs):
        victim.write_bytes(b"concurrent owner file")
        return link(*args, **kwargs)

    monkeypatch.setattr(refresh.os, "link", raced_link)
    with pytest.raises(FileExistsError):
        refresh.refresh_controls(source, prefix)
    assert victim.read_bytes() == b"concurrent owner file"
    assert pairs[1][1].read_bytes() == pairs[1][2]


@pytest.mark.parametrize("kind", ["symlink", "customized"])
def test_new_helper_is_not_an_arbitrary_adoption_path(controls, monkeypatch, kind):
    source, prefix, pairs = controls
    src, target, _, _ = next(pair for pair in pairs
                            if str(pair[1].relative_to(prefix.parent)) in refresh.NEW_TARGETS)
    previous = dict(refresh.PREVIOUS)
    previous[str(src.relative_to(source))] = frozenset()
    monkeypatch.setattr(refresh, "PREVIOUS", previous)
    if kind == "symlink":
        target.unlink()
        target.symlink_to(src)
    with pytest.raises((ValueError, OSError)):
        refresh.refresh_controls(source, prefix)
    assert pairs[0][1].read_bytes() == pairs[0][2]
