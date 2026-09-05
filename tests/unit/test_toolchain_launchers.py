"""Isolated launcher handoffs; no network or user-global npm installations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/station_toolchain_install.sh"
VERSION = "24.20.0"
NPM_VERSION = "12.0.2"


@pytest.fixture
def layout(tmp_path):
    # macOS /var is a symlink; fixtures use the actual parent path deliberately.
    home = tmp_path.resolve() / "operator"
    bins = home / ".local/bin"
    bundle = home / f".local/lib/node-v{VERSION}-linux-x64"
    for path in (bins, bundle / "bin", bundle / "lib/node_modules/npm/bin"):
        path.mkdir(parents=True)
    node = bundle / "bin/node"
    node.write_text("#!/bin/sh\nexit 0\n")
    node.chmod(0o755)
    (bundle / "lib/node_modules/npm/bin/npm-cli.js").write_text("// fixture\n")
    return home, bins, bundle


def run_shell(layout, body, *, extra_env=None):
    home, bins, bundle = layout
    source = SCRIPT.read_text()
    functions = source[source.index("manage_node_launchers() {"):source.index("\ninstall_github_cli() {")]
    functions += source[source.index("install_node_clis() {"):source.index("\ninstall_discord_sdk() {")]
    env = dict(os.environ, STATION_HOME=str(home), tool_path=str(bins),
               NODE_VERSION=VERSION, NODE_ARCH="x64", NPM_VERSION=NPM_VERSION,
               STATION_USER="fixture", INSTALL_CODEX="0", VERCEL_CLI_VERSION="fixture",
               VERCEL_CLI_INTEGRITY="fixture", SHADCN_CLI_VERSION="fixture",
               SHADCN_CLI_INTEGRITY="fixture", BUNDLE=str(bundle))
    env.update(extra_env or {})
    # install -d is the only privileged operation reached by the cached bundle
    # fixture. Real handoff code always executes, under our current fixture UID.
    harness = """set -Eeuo pipefail
as_station() { "$@"; }
install() { :; }
verify_npm_integrity() { :; }
"""
    return subprocess.run(["bash", "-c", harness + functions + "\n" + body],
                          env=env, cwd=home, capture_output=True, text=True, timeout=30)


def make_global_npm(layout, *, version=NPM_VERSION):
    root = layout[0] / ".local/lib/node_modules/npm"
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(json.dumps({"name": "npm", "version": version}))
    for name in ("npm", "npx"):
        target = root / "bin" / f"{name}-cli.js"
        target.write_text("#!/bin/sh\nexit 0\n")
        target.chmod(0o755)
    return root


def seed_links(layout, kind):
    home, bins, bundle = layout
    if kind == "hermes":
        source = home / ".hermes/node/bin"
        source.mkdir(parents=True)
    elif kind == "bundled":
        source = bundle / "bin"
    else:
        make_global_npm(layout)
        source = None
    for binary in ("npm", "npx"):
        target = str(source / binary) if source else f"../lib/node_modules/npm/bin/{binary}-cli.js"
        (bins / binary).symlink_to(target)


def native_npm():
    npm, node = shutil.which("npm"), shutil.which("node")
    override = os.environ.get("STATION_TEST_NPM_ROOT")
    if not node or (not npm and not override):
        pytest.skip("native npm/node unavailable; launcher tests remain mandatory")
    root = Path(override) if override else Path(npm).resolve().parents[1]
    return root, node


@pytest.mark.parametrize("kind", ["bundled", "hermes"])
def test_native_npm_reproduces_old_global_bin_conflict(layout, kind):
    """Exercise installed npm's own ownership checker, not a simulated error."""
    npm_root, node = native_npm()
    checker = npm_root / "node_modules/bin-links/lib/check-bin.js"
    if not checker.is_file():
        pytest.skip("installed npm does not expose its native bin-links checker")
    seed_links(layout, kind)
    command = [node, "-e", """
const check = require(process.argv[1]);
check({bin:'npm',path:process.argv[2],top:true,global:true,force:false})
  .then(() => process.stdout.write('ACCEPTED'))
  .catch(error => process.stdout.write(error.code));
""", str(checker), str(layout[0] / ".local/lib/node_modules/npm")]
    rejected = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
    assert rejected.stdout == "EEXIST"
    (layout[1] / "npm").unlink()
    (layout[1] / "npm").symlink_to("../lib/node_modules/npm/bin/npm-cli.js")
    accepted = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
    assert accepted.stdout == "ACCEPTED"


@pytest.mark.parametrize("kind", ["bundled", "hermes"])
def test_native_arborist_requires_both_flags_to_skip_global_bin_conflict(layout, kind):
    """Real rebuild queue reproduces the live failure that check-bin missed."""
    npm_root, node = native_npm()
    arborist = npm_root / "node_modules/@npmcli/arborist"
    if not arborist.is_dir():
        pytest.skip("installed npm does not expose its native Arborist")
    seed_links(layout, kind)
    root = make_global_npm(layout)
    marker = layout[0] / "install-script-must-not-run"
    package = json.loads((root / "package.json").read_text())
    package.update(bin={name: f"bin/{name}-cli.js" for name in ("npm", "npx")},
                   scripts={"install": f"touch {marker}"})
    (root / "package.json").write_text(json.dumps(package))
    before = {name: (os.readlink(layout[1] / name), (layout[1] / name).lstat().st_ino)
              for name in ("npm", "npx")}
    program = """
const Arborist = require(process.argv[1]);
const arb = new Arborist({path:process.argv[2],global:true,binLinks:false,
  ignoreScripts:process.argv[3]==='true',force:false});
(async () => {
  const tree = await arb.loadActual();
  const npm = tree.children.get('npm');
  if (!npm || !npm.globalTop) throw Error('fixture must be an actual globalTop npm');
  try {
    await arb.rebuild({nodes:[npm]});
    process.stdout.write('ACCEPTED');
  } catch (error) { process.stdout.write(error.code || error.message); }
})().catch(error => { process.stderr.write(String(error)); process.exitCode=1; });
"""
    base = [node, "-e", program, str(arborist), str(layout[0] / ".local/lib")]
    rejected = subprocess.run([*base, "false"], capture_output=True, text=True, timeout=20, check=True)
    assert rejected.stdout == "EEXIST", rejected.stderr
    accepted = subprocess.run([*base, "true"], capture_output=True, text=True, timeout=20, check=True)
    assert accepted.stdout == "ACCEPTED", accepted.stderr
    assert not marker.exists()
    assert before == {name: (os.readlink(layout[1] / name), (layout[1] / name).lstat().st_ino)
                      for name in before}
    handoff = run_shell(layout, 'manage_node_launchers "$BUNDLE" npm')
    assert handoff.returncode == 0, handoff.stderr
    for name in before:
        assert os.readlink(layout[1] / name) == f"../lib/node_modules/npm/bin/{name}-cli.js"


def test_fresh_node_does_not_seed_conflicting_or_missing_launchers(layout):
    result = run_shell(layout, "install_node")
    assert result.returncode == 0, result.stderr
    assert (layout[1] / "node").resolve() == layout[2] / "bin/node"
    for name in ("npm", "npx", "corepack"):
        assert not os.path.lexists(layout[1] / name)


@pytest.mark.parametrize("kind", ["global", "bundled", "hermes"])
def test_node_retry_preserves_npm_until_verified_handoff(layout, kind):
    seed_links(layout, kind)
    before = {name: (os.readlink(layout[1] / name), (layout[1] / name).lstat().st_ino)
              for name in ("npm", "npx")}
    result = run_shell(layout, "install_node\ninstall_node")
    assert result.returncode == 0, result.stderr
    assert before == {name: (os.readlink(layout[1] / name), (layout[1] / name).lstat().st_ino)
                      for name in before}
    make_global_npm(layout)
    result = run_shell(layout, 'manage_node_launchers "$BUNDLE" npm')
    assert result.returncode == 0, result.stderr
    for name in before:
        assert os.readlink(layout[1] / name) == f"../lib/node_modules/npm/bin/{name}-cli.js"


def test_hermes_node_predecessor_is_replaced_but_not_executed(layout):
    source = layout[0] / ".hermes/node/bin"
    source.mkdir(parents=True)
    (layout[1] / "node").symlink_to(source / "node")
    result = run_shell(layout, "install_node")
    assert result.returncode == 0, result.stderr
    assert os.readlink(layout[1] / "node") == str(layout[2] / "bin/node")


@pytest.mark.parametrize("kind", ["file", "directory", "fifo", "symlink", "dangling"])
def test_refuses_unrelated_npm_before_changing_any_launcher(layout, kind):
    target = layout[1] / "npm"
    outside = layout[0] / "keep"
    outside.write_text("untouched")
    if kind == "file":
        target.write_text("my npm wrapper")
    elif kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        os.mkfifo(target)
    else:
        target.symlink_to(outside if kind == "symlink" else layout[0] / "absent")
    inode = target.lstat().st_ino
    result = run_shell(layout, "install_node")
    assert result.returncode != 0 and "refusing unrelated" in result.stderr
    assert target.lstat().st_ino == inode
    assert outside.read_text() == "untouched"
    assert not os.path.lexists(layout[1] / "node")


@pytest.mark.parametrize("relative", [".local/bin", ".local/lib/node_modules", ".hermes/node"])
def test_refuses_symlinked_parent_without_writing_through_it(layout, relative):
    home, bins, bundle = layout
    seed_links(layout, "hermes")
    target = home / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    outside = home / "outside"
    if target.exists():
        target.rename(outside)
    else:
        outside.mkdir()
    target.symlink_to(outside, target_is_directory=True)
    before = sorted(str(path.relative_to(outside)) for path in outside.rglob("*"))
    result = run_shell(layout, "install_node")
    assert result.returncode != 0 and "handoff failed" in result.stderr
    assert before == sorted(str(path.relative_to(outside)) for path in outside.rglob("*"))


@pytest.mark.parametrize("fault", ["version", "missing-npx", "symlink-npm"])
def test_handoff_refuses_incomplete_or_unsafe_package_and_preserves_old_links(layout, fault):
    seed_links(layout, "bundled")
    root = make_global_npm(layout, version="0.0.0" if fault == "version" else NPM_VERSION)
    if fault == "missing-npx":
        (root / "bin/npx-cli.js").unlink()
    elif fault == "symlink-npm":
        (root / "bin/npm-cli.js").unlink()
        (root / "bin/npm-cli.js").symlink_to(layout[2] / "bin/node")
    before = {name: os.readlink(layout[1] / name) for name in ("npm", "npx")}
    result = run_shell(layout, 'manage_node_launchers "$BUNDLE" npm')
    assert result.returncode != 0
    assert before == {name: os.readlink(layout[1] / name) for name in before}


def test_corepack_is_optional_and_cannot_escape_bundle(layout):
    (layout[2] / "bin/corepack").symlink_to(layout[0] / "external-corepack")
    (layout[0] / "external-corepack").write_text("do not execute")
    result = run_shell(layout, "install_node")
    assert result.returncode != 0 and "Corepack target escapes" in result.stderr
    assert not os.path.lexists(layout[1] / "corepack")


@pytest.mark.parametrize("failure", [False, True])
def test_npm_bootstrap_uses_bundle_with_bin_publication_disabled(layout, failure):
    seed_links(layout, "hermes")
    home, bins, bundle = layout
    bootstrap = bundle / "bin/node"
    bootstrap.write_text("""#!/usr/bin/python3
import json, os, pathlib, sys
home = pathlib.Path(os.environ['STATION_HOME'])
(home / 'bootstrap-argv.json').write_text(json.dumps(sys.argv[1:]))
if os.environ.get('FAIL_NPM') == '1':
    sys.exit(23)
root = home / '.local/lib/node_modules/npm'
(root / 'bin').mkdir(parents=True, exist_ok=True)
(root / 'package.json').write_text(json.dumps({'name':'npm','version':os.environ['NPM_VERSION']}))
for name in ('npm', 'npx'):
    path = root / 'bin' / (name + '-cli.js')
    path.write_text('#!/bin/sh\\nexit 0\\n')
    path.chmod(0o755)
""")
    before = os.readlink(bins / "npm")
    result = run_shell(layout, "install_node_clis", extra_env={"FAIL_NPM": "1" if failure else "0"})
    assert json.loads((home / "bootstrap-argv.json").read_text()) == [
        str(bundle / "lib/node_modules/npm/bin/npm-cli.js"),
        "install", "--global", "--ignore-scripts", "--bin-links=false", f"npm@{NPM_VERSION}",
    ]
    assert result.returncode == (23 if failure else 0), result.stderr
    assert os.readlink(bins / "npm") == (before if failure else "../lib/node_modules/npm/bin/npm-cli.js")


def test_script_has_valid_shell_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
