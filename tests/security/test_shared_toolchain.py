"""Shared executable publication uses synthetic sources and no accounts/network."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/station_shared_toolchain.py"
PINS = {
    "NODE_VERSION": "24.20.0",
    "NPM_VERSION": "12.0.2",
    "PYTHON_VERSION": "3.14.7",
    "AI_PYTHON_VERSION": "3.13.15",
    "GITHUB_CLI_VERSION": "2.88.0",
    "UV_VERSION": "0.11.0",
    "VERCEL_CLI_VERSION": "59.11.2",
    "CODEX_CLI_VERSION": "0.110.0",
    "SHADCN_CLI_VERSION": "3.8.0",
    "CHATBOTX_CLI_VERSION": "0.1.3",
    "CHATBOTX_CLI_ENTRY_SHA256": hashlib.sha256(b"console.log('0.1.3');\n").hexdigest(),
}
EXPORTS = {"node", "npm", "npx", "python-latest", "python-ai", "gh", "uv", "uvx",
           "vercel", "codex", "shadcn", "chatbotx"}


def write(path: Path, text: str, *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755 if executable else 0o644)
    return path


def snapshot(root: Path) -> dict:
    """Evidence excludes atime, which ordinary read-only checks may update."""
    result = {}
    if not root.exists():
        return result
    for path in sorted([root, *root.rglob("*")]):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            payload = os.readlink(path)
        elif stat.S_ISREG(info.st_mode):
            payload = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            payload = None
        result[str(path.relative_to(root))] = (
            info.st_mode, info.st_uid, info.st_gid, info.st_ino, payload,
        )
    return result


@pytest.fixture(scope="module")
def publisher():
    spec = importlib.util.spec_from_file_location("station_shared_toolchain_tests", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.publish_toolchain


@pytest.fixture
def layout(tmp_path, publisher):
    # Resolve macOS /var before testing intentionally non-symlinked parents.
    root = tmp_path.resolve()
    home = root / "operator"
    home.mkdir(mode=0o700)
    local = home / ".local"
    bins = local / "bin"
    bins.mkdir(parents=True)
    node = local / f"lib/node-v{PINS['NODE_VERSION']}-linux-x64"
    write(node / "bin/node", "#!/bin/sh\nprintf 'v24.20.0\\n'\n", executable=True)
    write(node / "include/node/node.h", "/* complete synthetic Node tree */\n")
    bundled_npm = node / "lib/node_modules/npm"
    write(bundled_npm / "package.json", '{"name":"npm","version":"11.0.0"}')
    for alias in ("npm", "npx"):
        write(bundled_npm / f"bin/{alias}-cli.js", "// synthetic bundled npm\n", executable=True)
        (node / "bin" / alias).symlink_to(f"../lib/node_modules/npm/bin/{alias}-cli.js")

    packages = {}
    definitions = (
        ("npm", "NPM_VERSION", {"npm": "bin/npm-cli.js", "npx": "bin/npx-cli.js"}),
        ("vercel", "VERCEL_CLI_VERSION", {"vercel": "dist/vc.js"}),
        ("shadcn", "SHADCN_CLI_VERSION", {"shadcn": "dist/index.js"}),
        ("@openai/codex", "CODEX_CLI_VERSION", {"codex": "bin/codex.js"}),
        ("chatbotx", "CHATBOTX_CLI_VERSION", {"chatbotx": "dist/index.cjs"}),
    )
    for name, pin, entrypoints in definitions:
        package = (local / "share/station-clis/chatbotx/node_modules/chatbotx" if name == "chatbotx"
                   else local / "lib/node_modules" / name)
        packages[name] = package
        write(package / "package.json", json.dumps({
            "name": name, "version": PINS[pin], "bin": entrypoints,
        }))
        for entrypoint in entrypoints.values():
            content = "console.log('0.1.3');\n" if name == "chatbotx" else "#!/usr/bin/env node\n// synthetic CLI\n"
            write(package / entrypoint, content, executable=name != "chatbotx")
        if name == "chatbotx":
            for relative in ("README.md", "dist/index.mjs", "dist/index.d.cts", "dist/index.d.mts"):
                write(package / relative, "// synthetic bundled support file\n")
        dependency = package / "node_modules/synthetic-dependency"
        write(dependency / "package.json", '{"name":"synthetic-dependency","version":"1.0.0"}')
        write(dependency / "bin/helper.js", "// internal dependency\n", executable=True)
        (package / "node_modules/.bin").mkdir()
        (package / "node_modules/.bin/helper").symlink_to("../synthetic-dependency/bin/helper.js")

    runtimes = {}
    for alias, pin, minor in (("python-latest", "PYTHON_VERSION", "3.14"),
                              ("python-ai", "AI_PYTHON_VERSION", "3.13")):
        runtime = local / f"share/uv/python/cpython-{PINS[pin]}-linux-x86_64-gnu"
        runtimes[alias] = runtime
        write(runtime / f"bin/python{minor}", f"#!/bin/sh\nprintf 'Python {PINS[pin]}\\n'\n",
              executable=True)
        write(runtime / f"lib/python{minor}/encodings/__init__.py", "# synthetic stdlib\n")
        write(runtime / f"lib/libpython{minor}.so.1.0", "synthetic shared library\n")
        (runtime / "bin/python3").symlink_to(f"python{minor}")
        (runtime / "bin/python").symlink_to("python3")
        (bins / alias).symlink_to(runtime / f"bin/python{minor}")
    for name in ("gh", "uv", "uvx"):
        write(bins / name, "#!/bin/sh\nexit 0\n", executable=True)

    # Normal operator-private state lies OUTSIDE the explicit software roots.
    write(home / ".env", "SYNTHETIC_PRIVATE_VALUE=never-copy-this\n")
    write(home / ".config/gh/hosts.yml", "synthetic private account state\n")
    write(home / ".codex/auth.json", '{"synthetic":"private account state"}')
    write(home / ".chatbotX/config.json", '{"token":"SYNTHETIC_PRIVATE_CHATBOTX_TOKEN"}')
    shared = root / "shared"
    public = root / "public-bin"
    public.mkdir()
    calls = []

    def probe(final_root, exports, pins):
        assert final_root.is_dir()
        assert pins == PINS
        calls.append((final_root, dict(exports)))

    def publish(**overrides):
        arguments = {
            "station_home": home, "station_uid": os.getuid(), "station_gid": os.getgid(),
            "pins": dict(PINS), "node_arch": "x64", "shared_root": shared, "bin_root": public,
            "include_codex": True, "authority_uid": os.getuid(), "authority_gid": os.getgid(),
            "probe": probe,
        }
        arguments.update(overrides)
        return publisher(**arguments)

    yield SimpleNamespace(root=root, home=home, local=local, bins=bins, node=node,
                          packages=packages, runtimes=runtimes, shared=shared, public=public,
                          calls=calls, publish=publish)
    # Only this synthetic fixture is relaxed AFTER assertions. pytest's ordinary
    # temporary-directory cleanup cannot unlink a symlink inside a 0555 parent
    # reliably on every supported local filesystem. Never follow test symlinks.
    for current, directories, _ in os.walk(root, followlinks=False):
        current_path = Path(current)
        if not current_path.is_symlink():
            current_path.chmod(0o700)
        directories[:] = [name for name in directories if not (current_path / name).is_symlink()]


def final_root(layout) -> Path:
    target = layout.public / "node"
    assert target.is_symlink()
    return target.resolve().parent.parent


def assert_no_exports(layout):
    assert not any(os.path.lexists(layout.public / name) for name in EXPORTS)


def forbid_content_read(publisher, monkeypatch, target):
    """Record helper reads; even an empty excluded config must never be opened."""
    original = publisher.__globals__["_read"]
    observed = []

    def checked(path, *args, **kwargs):
        observed.append(Path(path))
        assert Path(path) != target, "excluded/private npm configuration must not be read"
        return original(path, *args, **kwargs)

    monkeypatch.setitem(publisher.__globals__, "_read", checked)
    return observed


def test_publish_complete_private_state_free_toolchain_and_idempotent_retry(layout):
    original = snapshot(layout.home)
    result = layout.publish()
    assert isinstance(result, dict)
    release = final_root(layout)
    assert result["schema_version"] == 1
    assert result["state"] == "SHARED_CODE_VERIFIED"
    assert result["root"] == str(release)
    assert result["release_id"] == release.name
    assert set(result["exports"]) == EXPORTS
    assert result["credentials"] == "NOT_SHARED"
    assert result["operational"] is False
    assert release.parent == layout.shared
    assert set(path.name for path in layout.public.iterdir()) >= EXPORTS
    assert layout.calls and layout.calls[-1][0] == release
    for name in EXPORTS:
        launcher = layout.public / name
        assert launcher.is_symlink()
        assert launcher.resolve() == release / "bin" / name
        assert launcher.resolve().is_file()
        assert os.access(launcher, os.X_OK)
        wrapper = launcher.read_text()
        assert str(layout.home) not in wrapper
        assert "HERMES_HOME=" not in wrapper
        assert "HOME=" not in wrapper
    assert (release / "node/include/node/node.h").is_file()
    for name in ("npm", "vercel", "shadcn", "codex", "chatbotx"):
        package = release / "npm" / name
        link = package / "node_modules/.bin/helper"
        assert link.is_symlink()
        assert link.resolve().is_relative_to(package)
        assert link.read_text() == "// internal dependency\n"
    for category, minor in (("latest", "3.14"), ("ai", "3.13")):
        runtime = release / "python" / category
        assert (runtime / f"lib/python{minor}/encodings/__init__.py").is_file()
        assert (runtime / f"lib/libpython{minor}.so.1.0").is_file()
        assert (runtime / "bin/python").resolve().is_relative_to(runtime)
    for path in release.rglob("*"):
        assert path.name not in {".env", "auth.json", "hosts.yml", ".chatbotX"}
        assert path.lstat().st_uid == os.getuid()
        if not path.is_symlink():
            assert not path.stat().st_mode & 0o022
    published = snapshot(release)
    layout.publish()
    assert final_root(layout) == release
    assert snapshot(release) == published
    assert snapshot(layout.home) == original


def test_without_codex_neither_requires_nor_exports_codex(layout):
    # A deliberately invalid optional package must not enter a non-Codex build.
    write(layout.packages["@openai/codex"] / ".env", "synthetic forbidden content\n")
    layout.publish(include_codex=False)
    assert not os.path.lexists(layout.public / "codex")
    assert not (final_root(layout) / "npm/codex").exists()


@pytest.mark.parametrize("configured_prefix", [None, "/synthetic-zone/custom-prefix"])
def test_actual_wrapper_preserves_caller_accounts_and_literal_arguments(layout, configured_prefix):
    write(layout.node / "bin/node", '#!/bin/sh\nprintf "%s\\n" "$HOME" "$HERMES_HOME" '
          '"${NPM_CONFIG_PREFIX-unset}" "$@"\n', executable=True)
    layout.publish()
    env = {"HOME": "/synthetic-zone/home", "HERMES_HOME": "/synthetic-zone/hermes"}
    if configured_prefix is not None:
        env["NPM_CONFIG_PREFIX"] = configured_prefix
    literal = "literal ; argument $(no-subprocess)"
    result = subprocess.run([str(layout.public / "npm"), literal], env=env, cwd=layout.root,
                            capture_output=True, text=True, check=True, timeout=5)
    assert result.stdout.splitlines() == [
        env["HOME"], env["HERMES_HOME"], configured_prefix or "/synthetic-zone/home/.local",
        str(final_root(layout) / "npm/npm/bin/npm-cli.js"), literal,
    ]


@pytest.mark.parametrize("kind", ["operator", "shared"])
@pytest.mark.parametrize("existing_account", [False, True])
def test_chatbotx_wrappers_execute_shebang_free_code_and_keep_caller_accounts_private(
        layout, publisher, kind, existing_account):
    node = shutil.which("node")
    if node is None:
        pytest.skip("native Node unavailable for shebang-free CLI acceptance")
    write(layout.node / "bin/node", "#!/bin/sh\nexec " + shlex.quote(node) + ' "$@"\n', executable=True)
    entry = layout.packages["chatbotx"] / "dist/index.cjs"
    code = """const fs = require('node:fs');
const path = require('node:path');
const account = path.join(process.env.HOME, '.chatbotX');
fs.mkdirSync(account, {recursive: true});
fs.writeFileSync(path.join(account, 'new-config.json'), '{}');
console.log(JSON.stringify({home: process.env.HOME, hermes: process.env.HERMES_HOME,
  args: process.argv.slice(2), prefix: process.env.NPM_CONFIG_PREFIX || null}));
"""
    write(entry, code)
    pins = {**PINS, "CHATBOTX_CLI_ENTRY_SHA256": hashlib.sha256(code.encode()).hexdigest()}
    original = snapshot(layout.home)
    if kind == "operator":
        publisher.__globals__["_private_chatbotx_launcher"](
            layout.home, layout.node / "bin/node", pins["CHATBOTX_CLI_VERSION"], pins["CHATBOTX_CLI_ENTRY_SHA256"])
        command = layout.bins / "chatbotx"
    else:
        layout.publish(pins=pins, probe=lambda *args: None)
        command = layout.public / "chatbotx"
    caller = layout.root / "calling-zone"
    caller.mkdir(mode=0o700)
    (caller / "home").mkdir(mode=0o700)
    account = caller / "home/.chatbotX"
    if existing_account:
        existing = write(account / "config.json", '{"token":"synthetic; preserve"}')
        account.chmod(0o750)
        existing.chmod(0o640)
    existing_before = snapshot(caller)
    env = {"HOME": str(caller / "home"), "HERMES_HOME": str(caller / "instance-hermes")}
    literal = "literal ; argument $(no-subprocess)"
    completed = subprocess.run([str(command), literal], env=env, cwd=caller,
                               check=True, capture_output=True, text=True, timeout=10)
    assert json.loads(completed.stdout) == {"home": env["HOME"], "hermes": env["HERMES_HOME"],
                                           "args": [literal], "prefix": None}
    assert stat.S_IMODE(account.stat().st_mode) == (0o750 if existing_account else 0o700)
    assert stat.S_IMODE((account / "new-config.json").stat().st_mode) == 0o600
    if existing_account:
        assert snapshot(caller)["home/.chatbotX/config.json"] == existing_before["home/.chatbotX/config.json"]
    assert entry.read_text() == code
    assert snapshot(layout.home)[".chatbotX/config.json"] == original[".chatbotX/config.json"]


@pytest.mark.parametrize("kind", ["unrelated", "symlink", "hardlink", "fifo", "wrong-version", "wrong-bin"])
def test_private_chatbotx_launcher_rejects_unsafe_existing_files_and_metadata(layout, publisher, kind):
    wrapper = layout.bins / "chatbotx"
    sentinel = write(layout.root / "preserved-file", "preserve\n")
    if kind == "unrelated":
        write(wrapper, "#!/bin/sh\nexit 0\n", executable=True)
    elif kind == "symlink":
        wrapper.symlink_to(sentinel)
    elif kind == "hardlink":
        os.link(sentinel, wrapper)
    elif kind == "fifo":
        os.mkfifo(wrapper)
    else:
        manifest = layout.packages["chatbotx"] / "package.json"
        value = json.loads(manifest.read_text())
        value["version" if kind == "wrong-version" else "bin"] = "0.0.0" if kind == "wrong-version" else "unexpected.js"
        manifest.write_text(json.dumps(value))
    original = snapshot(layout.home)
    with pytest.raises((OSError, ValueError, RuntimeError)):
        publisher.__globals__["_private_chatbotx_launcher"](
            layout.home, layout.node / "bin/node", PINS["CHATBOTX_CLI_VERSION"], PINS["CHATBOTX_CLI_ENTRY_SHA256"])
    assert snapshot(layout.home) == original
    assert sentinel.read_text() == "preserve\n"


def test_private_chatbotx_wrapper_supports_reviewed_node_upgrade_and_repeat(layout, publisher):
    helper = publisher.__globals__["_private_chatbotx_launcher"]
    helper(layout.home, layout.node / "bin/node", PINS["CHATBOTX_CLI_VERSION"], PINS["CHATBOTX_CLI_ENTRY_SHA256"])
    wrapper = layout.bins / "chatbotx"
    old = wrapper.read_bytes()
    helper(layout.home, layout.node / "bin/node", PINS["CHATBOTX_CLI_VERSION"], PINS["CHATBOTX_CLI_ENTRY_SHA256"], check=True)
    assert wrapper.read_bytes() == old
    newer = layout.local / "lib/node-v24.20.1-linux-x64/bin/node"
    write(newer, "#!/bin/sh\nexit 0\n", executable=True)
    with pytest.raises(ValueError, match="pinned Node runtime"):
        helper(layout.home, newer, PINS["CHATBOTX_CLI_VERSION"], PINS["CHATBOTX_CLI_ENTRY_SHA256"], verify=True)
    assert wrapper.read_bytes() == old
    helper(layout.home, newer, PINS["CHATBOTX_CLI_VERSION"], PINS["CHATBOTX_CLI_ENTRY_SHA256"])
    assert str(newer) in wrapper.read_text() and wrapper.read_bytes() != old


@pytest.mark.parametrize("relative", ["node_modules", "node_modules/chatbotx", "node_modules/chatbotx/dist"])
def test_private_chatbotx_preflight_rejects_symlinked_install_parents(layout, publisher, relative):
    prefix = layout.local / "share/station-clis/chatbotx"
    path = prefix / relative
    moved = path.with_name(path.name + "-preserved")
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=True)
    original = snapshot(layout.home)
    with pytest.raises((OSError, ValueError, RuntimeError)):
        publisher.__globals__["_private_chatbotx_launcher"](
            layout.home, layout.node / "bin/node", PINS["CHATBOTX_CLI_VERSION"], PINS["CHATBOTX_CLI_ENTRY_SHA256"], check=True)
    assert snapshot(layout.home) == original


@pytest.mark.parametrize("root_name", ["npm", "chatbotx"])
def test_chatbotx_account_namespace_inside_software_is_rejected_before_read(layout, publisher, monkeypatch, root_name):
    private = write(layout.packages[root_name] / ".chatbotX/config.json", '{"token":"synthetic"}')
    observed = forbid_content_read(publisher, monkeypatch, private)
    with pytest.raises(ValueError, match="Private state is forbidden"):
        layout.publish()
    assert private not in observed
    assert_no_exports(layout)


@pytest.mark.parametrize("missing", ["README.md", "dist/index.cjs", "dist/index.mjs", "dist/index.d.cts", "dist/index.d.mts"])
def test_chatbotx_missing_reviewed_support_file_blocks_publication(layout, missing):
    (layout.packages["chatbotx"] / missing).unlink()
    with pytest.raises((OSError, ValueError)):
        layout.publish()
    assert_no_exports(layout)


@pytest.mark.parametrize("stage", ["operator-install", "operator-check", "shared"])
def test_modified_regular_chatbotx_entry_is_rejected_before_execution(layout, publisher, stage):
    helper = publisher.__globals__["_private_chatbotx_launcher"]
    entry = layout.packages["chatbotx"] / "dist/index.cjs"
    wrapper = layout.bins / "chatbotx"
    if stage == "operator-check":
        helper(layout.home, layout.node / "bin/node", PINS["CHATBOTX_CLI_VERSION"], PINS["CHATBOTX_CLI_ENTRY_SHA256"])
    entry.write_text("console.log('0.1.3'); // altered regular file\n")
    original = snapshot(layout.home)
    with pytest.raises(ValueError, match="reviewed SHA-256"):
        if stage == "shared":
            layout.publish(probe=lambda *args: pytest.fail("modified CLI must not be probed"))
        else:
            helper(layout.home, layout.node / "bin/node", PINS["CHATBOTX_CLI_VERSION"], PINS["CHATBOTX_CLI_ENTRY_SHA256"],
                   verify=stage == "operator-check")
    assert snapshot(layout.home) == original
    assert wrapper.exists() == (stage == "operator-check")
    assert_no_exports(layout)


@pytest.mark.parametrize("already_published", [False, True])
def test_chatbotx_change_between_source_validation_and_inventory_cannot_be_published(
        layout, publisher, monkeypatch, already_published):
    if already_published:
        layout.publish()
    before_shared, before_public = snapshot(layout.shared), snapshot(layout.public)
    original_sources = publisher.__globals__["_sources"]

    def changed_after_validation(*args, **kwargs):
        sources = original_sources(*args, **kwargs)
        (sources["npm/chatbotx"] / "dist/index.cjs").write_text("console.log('0.1.3'); // concurrent replacement\n")
        return sources

    monkeypatch.setitem(publisher.__globals__, "_sources", changed_after_validation)
    with pytest.raises(ValueError, match="Inventoried ChatbotX entrypoint differs"):
        layout.publish(probe=lambda *args: pytest.fail("changed inventoried code must not be probed"))
    assert snapshot(layout.shared) == before_shared
    assert snapshot(layout.public) == before_public


@pytest.mark.parametrize("entry_hash", [None, "", "0" * 63, "g" * 64, "0" * 64])
def test_invalid_or_wrong_chatbotx_hash_pin_blocks_shared_publication(layout, entry_hash):
    pins = {**PINS, "CHATBOTX_CLI_ENTRY_SHA256": entry_hash}
    if entry_hash is None:
        del pins["CHATBOTX_CLI_ENTRY_SHA256"]
    with pytest.raises(ValueError):
        layout.publish(pins=pins, probe=lambda *args: pytest.fail("invalid digest must not be probed"))
    assert_no_exports(layout)


def test_installer_chatbotx_check_verifies_package_before_native_execution(tmp_path):
    source = (ROOT / "scripts/station_toolchain_install.sh").read_text()
    function = source[source.index("check_pinned_tool() {"):source.index("\ncheck_toolchain() {")]
    binary = write(tmp_path / "chatbotx", "#!/bin/sh\nexit 0\n", executable=True)
    result = subprocess.run(["bash", "-c", """set -Eeuo pipefail
manage_chatbotx_launcher() { [[ "$1" == verify ]]; return 1; }
run_version_probe() { printf 'UNVERIFIED_CODE_WAS_EXECUTED'; }
""" + function + '\ncheck_pinned_tool chatbotx "$BINARY" 0.1.3 --version'],
                            env={"BINARY": str(binary)}, capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    assert "reviewed package/launcher verification failed" in result.stdout
    assert "UNVERIFIED_CODE_WAS_EXECUTED" not in result.stdout + result.stderr


def test_chatbotx_readonly_verifier_clears_inherited_account_environment(tmp_path):
    source = (ROOT / "scripts/station_toolchain_install.sh").read_text()
    function = source[source.index("manage_chatbotx_launcher() {"):source.index("\ninstall_chatbotx_cli() {")]
    helper_root = tmp_path / "station-source"
    write(helper_root / "scripts/station_shared_toolchain.py", """import os
def _private_chatbotx_launcher(home, node, version, entry_sha256, *, check, verify):
    assert check is False and verify is True
    assert 'CHATBOTX_API_KEY' not in os.environ
    assert 'NODE_OPTIONS' not in os.environ
    assert 'HOME' not in os.environ
    assert os.environ['PATH'] == '/usr/bin:/bin'
    assert version == '0.1.3' and entry_sha256 == 'a' * 64
    print('ISOLATED_PACKAGE_VERIFIED')
""")
    harness = "set -Eeuo pipefail\nas_station() { echo UNSAFE_INSTALL_ENVIRONMENT; return 99; }\n"
    result = subprocess.run(["/bin/bash", "-c", harness + function + "\nmanage_chatbotx_launcher verify"],
                            env={"ROOT": str(helper_root), "STATION_HOME": str(tmp_path / "operator"),
                                 "STATION_USER": pwd.getpwuid(os.geteuid()).pw_name, "NODE_ARCH": "x64",
                                 "NODE_VERSION": "24.20.0", "CHATBOTX_CLI_VERSION": "0.1.3",
                                 "CHATBOTX_CLI_ENTRY_SHA256": "a" * 64, "HOME": str(tmp_path / "private-home"),
                                 "CHATBOTX_API_KEY": "SYNTHETIC_PRIVATE_TOKEN", "NODE_OPTIONS": "--require /absent",
                                 "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ISOLATED_PACKAGE_VERIFIED\n"


@pytest.mark.parametrize("failure", ["none", "wrong-version", "version-error", "help-error", "wrong-help"])
def test_shared_chatbotx_acceptance_requires_exact_version_and_help_with_disposable_home(
        layout, publisher, monkeypatch, failure):
    calls = []
    module = publisher.__globals__
    monkeypatch.setenv("CHATBOTX_API_KEY", "SYNTHETIC_MUST_NOT_REACH_PROBE")
    monkeypatch.setenv("NODE_PATH", "/synthetic/dependencies/must-not-reach-probe")
    monkeypatch.setattr(module["shutil"], "which", lambda name: "/usr/sbin/runuser")
    monkeypatch.setattr(module["os"], "chown", lambda *args: None)

    def run(command, **options):
        calls.append((command, options))
        assert command[:7] == ["/usr/sbin/runuser", "--user", "fixture", "--", "/usr/bin/env", "-i", f"HOME={options['cwd']}"]
        assert options["cwd"] != str(layout.home)
        assert Path(options["cwd"]).is_dir()
        assert not any(value.startswith(("CHATBOTX_", "NODE_PATH=")) for value in command)
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 1 if failure == "version-error" else 0,
                                               "10.1.3\n" if failure == "wrong-version" else "0.1.3\n", "")
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 1 if failure == "help-error" else 0,
                                               "unexpected help" if failure == "wrong-help" else "chatbotx <group> <action> [options]\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module["subprocess"], "run", run)
    if failure == "none":
        module["_probe"](layout.root / "candidate", {"chatbotx": "npm/chatbotx/dist/index.cjs"},
                         PINS, "fixture", os.getuid(), os.getgid())
    else:
        with pytest.raises(ValueError, match="verification failed"):
            module["_probe"](layout.root / "candidate", {"chatbotx": "npm/chatbotx/dist/index.cjs"},
                             PINS, "fixture", os.getuid(), os.getgid())
    assert calls and not Path(calls[0][1]["cwd"]).exists()
    assert any(command[-1] == "--help" for command, _ in calls) == (failure not in {"wrong-version", "version-error"})


def test_same_owner_pin_upgrade_preserves_previous_immutable_release(layout):
    layout.publish()
    previous = final_root(layout)
    original = snapshot(previous)
    pins = {**PINS, "VERCEL_CLI_VERSION": "59.11.3"}
    manifest = layout.packages["vercel"] / "package.json"
    payload = json.loads(manifest.read_text())
    payload["version"] = pins["VERCEL_CLI_VERSION"]
    manifest.write_text(json.dumps(payload))
    probed = []

    def probe(release, exports, observed):
        assert observed == pins and set(exports) == EXPORTS
        assert release != previous and release.is_dir()
        # No launcher switch until the complete new release passes its probe.
        assert final_root(layout) == previous
        probed.append(release)

    result = layout.publish(pins=pins, probe=probe)
    current = final_root(layout)
    assert current != previous and probed == [current]
    assert result["root"] == str(current)
    assert snapshot(previous) == original
    for name in EXPORTS:
        assert (layout.public / name).resolve() == current / "bin" / name


@pytest.mark.parametrize("source", ["node", "npm", "python", "standalone", "chatbotx"])
def test_same_pin_source_content_drift_is_rejected(layout, source):
    layout.publish()
    release = final_root(layout)
    original = snapshot(release)
    path = {"node": layout.node / "include/node/node.h",
            "npm": layout.packages["npm"] / "bin/npm-cli.js",
            "python": layout.runtimes["python-ai"] / "lib/python3.13/encodings/__init__.py",
            "standalone": layout.bins / "gh", "chatbotx": layout.packages["chatbotx"] / "dist/index.cjs"}[source]
    path.write_text("changed source under the same pins\n")
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert snapshot(release) == original


@pytest.mark.parametrize("relative", ["node/bin/node", "npm/npm/bin/npm-cli.js",
                                      "python/ai/lib/python3.13/encodings/__init__.py", "bin/node",
                                      "npm/chatbotx/dist/index.cjs", "bin/chatbotx"])
def test_published_file_drift_is_rejected_without_repairing_in_place(layout, relative):
    layout.publish()
    target = final_root(layout) / relative
    target.chmod(0o755)
    target.write_text("untrusted published replacement\n")
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert target.read_text() == "untrusted published replacement\n"


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "dangling"])
def test_unrelated_public_entrypoint_is_preserved(layout, kind):
    entry = layout.public / "node"
    sentinel = write(layout.root / "unrelated", "preserve unrelated data\n")
    if kind == "file":
        write(entry, "unrelated launcher\n", executable=True)
    elif kind == "directory":
        entry.mkdir()
        write(entry / "keep", "unrelated directory content\n")
    else:
        entry.symlink_to(sentinel if kind == "symlink" else layout.root / "absent")
    original = snapshot(layout.public)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert snapshot(layout.public) == original
    assert sentinel.read_text() == "preserve unrelated data\n"


@pytest.mark.parametrize("location", ["node", "npm", "python", "standalone"])
def test_symlinked_explicit_source_root_is_rejected(layout, location):
    source = {"node": layout.node, "npm": layout.packages["npm"],
              "python": layout.runtimes["python-ai"], "standalone": layout.bins / "gh"}[location]
    moved = source.with_name(source.name + "-unrelated")
    source.rename(moved)
    source.symlink_to(moved, target_is_directory=moved.is_dir())
    original = snapshot(layout.home)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert snapshot(layout.home) == original
    assert_no_exports(layout)


@pytest.mark.parametrize("location", ["source", "shared", "public"])
def test_symlinked_parent_is_rejected(layout, location):
    if location == "source":
        parent = layout.local / "lib"
    elif location == "shared":
        parent = layout.shared
        parent.mkdir()
    else:
        parent = layout.public
    moved = parent.with_name(parent.name + "-real")
    parent.rename(moved)
    parent.symlink_to(moved, target_is_directory=True)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert_no_exports(layout)


@pytest.mark.parametrize("kind", ["relative", "absolute", "dangling", "cycle"])
def test_escaping_or_unresolvable_internal_symlink_is_rejected(layout, kind):
    package = layout.packages["npm"]
    link = package / "node_modules/unsafe-link"
    sentinel = write(layout.root / "private-sentinel", "private synthetic state\n")
    target = {"relative": os.path.relpath(sentinel, link.parent), "absolute": str(sentinel),
              "dangling": "missing-target", "cycle": "unsafe-link"}[kind]
    link.symlink_to(target)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert sentinel.read_text() == "private synthetic state\n"
    assert_no_exports(layout)


@pytest.mark.parametrize("secret", [".env", ".env.production", "auth.json", "credentials.json", ".npmrc"])
@pytest.mark.parametrize("location", ["npm", "python", "chatbotx"])
def test_secret_shaped_files_inside_explicit_software_root_are_rejected(layout, secret, location):
    root = layout.runtimes["python-ai"] if location == "python" else layout.packages[location]
    path = write(root / "nested" / secret, "synthetic private material; never publish\n")
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert path.read_text() == "synthetic private material; never publish\n"
    assert_no_exports(layout)


@pytest.mark.parametrize("mode", [0o600, 0o644])
def test_only_empty_bundled_npm_placeholder_is_omitted_without_reading(layout, publisher,
                                                                    monkeypatch, mode):
    placeholder = write(layout.node / "lib/node_modules/npm/.npmrc", "")
    placeholder.chmod(mode)
    observed = forbid_content_read(publisher, monkeypatch, placeholder)
    layout.publish()
    release = final_root(layout)
    relative = "node/lib/node_modules/npm/.npmrc"
    assert not os.path.lexists(release / relative)
    manifest = json.loads((release / "MANIFEST.json").read_text())
    assert relative not in manifest["files"]
    original = snapshot(release)
    placeholder.write_text("")
    layout.publish()
    assert final_root(layout) == release
    assert snapshot(release) == original
    assert placeholder.lstat().st_size == 0
    assert observed and placeholder not in observed


@pytest.mark.parametrize("content", ["\n", "registry=https://synthetic.invalid\n",
                                      "//registry.npmjs.org/:_authToken=SYNTHETIC_NOT_A_REAL_TOKEN\n"])
def test_nonempty_bundled_npm_config_is_rejected_without_reading_or_disclosing(
        layout, publisher, monkeypatch, capsys, content):
    placeholder = write(layout.node / "lib/node_modules/npm/.npmrc", content)
    observed = forbid_content_read(publisher, monkeypatch, placeholder)
    with pytest.raises(ValueError) as failure:
        layout.publish()
    output = capsys.readouterr()
    assert "SYNTHETIC_NOT_A_REAL_TOKEN" not in str(failure.value) + output.out + output.err
    assert "registry=" not in str(failure.value) + output.out + output.err
    assert observed and placeholder not in observed
    assert_no_exports(layout)


def test_bundled_npm_config_becoming_nonempty_blocks_retry_without_changing_exports(
        layout, publisher, monkeypatch):
    placeholder = write(layout.node / "lib/node_modules/npm/.npmrc", "")
    observed = forbid_content_read(publisher, monkeypatch, placeholder)
    layout.publish()
    release = final_root(layout)
    original_release, original_exports = snapshot(release), snapshot(layout.public)
    placeholder.write_text("//registry.npmjs.org/:_authToken=SYNTHETIC_ROTATED_PRIVATE_CONFIG\n")
    with pytest.raises(ValueError):
        layout.publish()
    assert snapshot(release) == original_release
    assert snapshot(layout.public) == original_exports
    assert observed and placeholder not in observed


@pytest.mark.parametrize("kind", ["symlink", "dangling", "fifo", "directory", "hardlink",
                                  "group-writable", "world-writable", "wrong-owner"])
def test_bundled_npm_placeholder_unsafe_type_or_authority_is_rejected_without_reading(
        layout, publisher, monkeypatch, kind):
    placeholder = layout.node / "lib/node_modules/npm/.npmrc"
    sentinel = write(layout.root / "unrelated-empty-config", "")
    if kind == "symlink":
        placeholder.symlink_to(sentinel)
    elif kind == "dangling":
        placeholder.symlink_to(layout.root / "absent-config")
    elif kind == "fifo":
        os.mkfifo(placeholder)
    elif kind == "directory":
        placeholder.mkdir()
    elif kind == "hardlink":
        os.link(sentinel, placeholder)
    else:
        write(placeholder, "")
        if kind in {"group-writable", "world-writable"}:
            placeholder.chmod(0o664 if kind == "group-writable" else 0o646)
        else:
            original_lstat = Path.lstat

            def wrong_owner(path, *args, **kwargs):
                info = original_lstat(path, *args, **kwargs)
                if path == placeholder:
                    fields = list(info)
                    fields[4] = os.getuid() + 10000
                    return os.stat_result(fields)
                return info

            monkeypatch.setattr(Path, "lstat", wrong_owner)
    observed = forbid_content_read(publisher, monkeypatch, placeholder)
    with pytest.raises(ValueError):
        layout.publish()
    assert observed and placeholder not in observed
    assert_no_exports(layout)


@pytest.mark.parametrize("location", ["node-root", "node-nested", "global-npm"])
def test_empty_npmrc_elsewhere_remains_forbidden_without_reading(layout, publisher,
                                                               monkeypatch, location):
    folder = {"node-root": layout.node, "node-nested": layout.node / "include/node",
              "global-npm": layout.packages["npm"]}[location]
    private = write(folder / ".npmrc", "")
    observed = forbid_content_read(publisher, monkeypatch, private)
    with pytest.raises(ValueError):
        layout.publish()
    assert observed and private not in observed
    assert_no_exports(layout)


def test_generated_python_cache_is_skipped_without_deleting_source_cache(layout):
    runtime = layout.runtimes["python-ai"]
    cache = write(runtime / "lib/python3.13/encodings/__pycache__/__init__.cpython-313.pyc",
                  "synthetic cached bytecode\n")
    layout.publish()
    assert cache.read_text() == "synthetic cached bytecode\n"
    assert not list(final_root(layout).rglob("__pycache__"))
    assert not list(final_root(layout).rglob("*.pyc"))


def test_failed_probe_leaves_no_public_entrypoint_or_operator_change(layout):
    original = snapshot(layout.home)
    called = []

    def reject(final, exports, pins):
        called.append(final)
        assert final.is_dir() and exports and pins == PINS
        assert_no_exports(layout)
        raise RuntimeError("synthetic non-root smoke failure")

    with pytest.raises(RuntimeError, match="synthetic non-root smoke failure"):
        layout.publish(probe=reject)
    assert called
    assert_no_exports(layout)
    assert snapshot(layout.home) == original
    layout.publish()
    assert len(layout.calls) == 1, "an intact retained candidate must still pass a new probe"


def test_published_tree_changed_during_probe_is_rejected_before_export(layout):
    def mutate(final, exports, pins):
        target = final / "npm/npm/bin/npm-cli.js"
        target.chmod(0o755)
        target.write_text("changed after initial immutable verification\n")

    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish(probe=mutate)
    assert_no_exports(layout)


def test_tampered_managed_export_target_is_not_silently_repaired(layout):
    layout.publish()
    entry = layout.public / "node"
    wrong = final_root(layout) / "bin/npm"
    entry.unlink()
    entry.symlink_to(wrong)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert os.readlink(entry) == str(wrong)


@pytest.mark.parametrize("field", ["name", "version", "bin"])
@pytest.mark.parametrize("package", ["npm", "chatbotx"])
def test_package_metadata_must_match_approved_pinned_package_and_entrypoint(layout, field, package):
    manifest = layout.packages[package] / "package.json"
    payload = json.loads(manifest.read_text())
    payload[field] = {"name": "unrelated-package", "version": "0.0.0",
                      "bin": {"npm": "../../private-state", "npx": "bin/npx-cli.js"}}[field]
    manifest.write_text(json.dumps(payload))
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert_no_exports(layout)


@pytest.mark.parametrize("package,entrypoints", [
    ("shadcn", "./dist/index.js"),
    ("vercel", {"vercel": "./dist/vc.js", "vc": "./dist/vc.js"}),
    ("npm", {"npm": "./bin/npm-cli.js", "npx": "./bin/npx-cli.js"}),
    ("chatbotx", {"chatbotx": "./dist/index.cjs"}),
])
def test_standard_package_bin_forms_and_additional_aliases_are_supported(layout, package, entrypoints):
    manifest = layout.packages[package] / "package.json"
    payload = json.loads(manifest.read_text())
    payload["bin"] = entrypoints
    manifest.write_text(json.dumps(payload))
    layout.publish()
    assert final_root(layout).is_dir()


def test_python_alias_cannot_select_another_runtime(layout):
    alias = layout.bins / "python-latest"
    alias.unlink()
    alias.symlink_to(layout.runtimes["python-ai"] / "bin/python3.13")
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert_no_exports(layout)


@pytest.mark.parametrize("location", ["node", "npm", "python", "shared", "public"])
def test_writable_managed_roots_are_rejected(layout, location):
    path = {"node": layout.node, "npm": layout.packages["npm"],
            "python": layout.runtimes["python-ai"], "shared": layout.shared,
            "public": layout.public}[location]
    path.mkdir(exist_ok=True)
    path.chmod(0o777)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert_no_exports(layout)


def test_source_ownership_must_match_expected_operator(layout):
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish(station_uid=os.getuid() + 10000)
    assert_no_exports(layout)


def test_writable_source_intermediate_parent_is_rejected(layout):
    (layout.local / "lib").chmod(0o777)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert_no_exports(layout)


@pytest.mark.parametrize("destination", ["shared_root", "bin_root"])
@pytest.mark.parametrize("defect", ["writable", "wrong-owner"])
def test_unsafe_destination_ancestor_is_rejected_before_publication(layout, monkeypatch,
                                                                  destination, defect):
    ancestor = layout.root / "destination-parent"
    ancestor.mkdir()
    target = ancestor / "not-created-yet"
    if defect == "writable":
        ancestor.chmod(0o777)
    else:
        original_lstat = Path.lstat

        def unrelated_owner(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if path == ancestor:
                fields = list(info)
                fields[4] = os.getuid() + 10000
                return os.stat_result(fields)
            return info

        monkeypatch.setattr(Path, "lstat", unrelated_owner)
    with pytest.raises(ValueError, match="Untrusted shared-software parent"):
        layout.publish(**{destination: target})
    assert not target.exists()
    assert_no_exports(layout)


@pytest.mark.parametrize("stage", ["source", "published"])
def test_incomplete_directory_scan_fails_closed(layout, publisher, monkeypatch, stage):
    original_walk = os.walk
    seen = []

    def incomplete_walk(top, *args, **kwargs):
        path = Path(top)
        selected = path == layout.packages["npm"] if stage == "source" else path.parent == layout.shared
        if selected:
            seen.append(path)
            # A filesystem walk normally suppresses scandir failures unless the
            # caller supplies onerror. Without the callback this synthetic tree
            # would otherwise look complete and incorrectly pass publication.
            callback = kwargs.get("onerror")
            if callback is not None:
                callback(PermissionError("synthetic unreadable subtree"))
        return original_walk(top, *args, **kwargs)

    proxy = SimpleNamespace(**vars(os))
    proxy.walk = incomplete_walk
    monkeypatch.setitem(publisher.__globals__, "os", proxy)
    with pytest.raises(ValueError, match="synthetic unreadable subtree"):
        layout.publish()
    assert seen
    assert_no_exports(layout)


@pytest.mark.parametrize("kind", ["group-writable", "world-writable", "fifo", "hardlink"])
def test_unsafe_source_files_are_rejected(layout, kind):
    path = layout.packages["npm"] / "unsafe-source"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "hardlink":
        os.link(layout.packages["npm"] / "package.json", path)
    else:
        write(path, "untrusted writable content\n")
        path.chmod(0o664 if kind == "group-writable" else 0o666)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert_no_exports(layout)


def test_installer_publishes_only_after_successful_private_toolchain_checks():
    installer = ROOT / "scripts/station_toolchain_install.sh"
    source = installer.read_text()
    _, dispatch = source.rsplit('case "$MODE" in\n', 1)
    _, install = dispatch.split("\nesac\n", 1)
    assert "set -Eeuo pipefail\n" in source
    assert install.rstrip().endswith("check_toolchain\npublish_shared_toolchain")
    assert source.count("\npublish_shared_toolchain\n") == 1
    assert '/usr/bin/python3 -I -B "$ROOT/scripts/station_shared_toolchain.py" "${arguments[@]}"' in source
    subprocess.run(["bash", "-n", str(installer)], check=True, timeout=5)


def test_plan_and_check_exit_before_any_shared_toolchain_publication():
    source = (ROOT / "scripts/station_toolchain_install.sh").read_text()
    _, dispatch = source.rsplit('case "$MODE" in\n', 1)
    branches, _ = dispatch.split("\nesac\n", 1)
    assert "plan) print_plan; exit 0;;" in branches
    assert "check) print_plan; check_toolchain; exit $?;;" in branches
    assert "publish_shared_toolchain" not in branches
    assert "station_shared_toolchain.py" not in branches


@pytest.mark.parametrize("failure", ["none", "preflight", "integrity", "install"])
def test_chatbotx_install_gates_wrapper_publication_on_integrity_and_install_success(tmp_path, failure):
    source = (ROOT / "scripts/station_toolchain_install.sh").read_text()
    function = source[source.index("install_chatbotx_cli() {"):source.index("\ninstall_composio() {")]
    log = tmp_path / "actions"
    harness = """set -Eeuo pipefail
manage_chatbotx_launcher() {
  printf '%s\\n' "launcher:$1" >> "$ACTION_LOG"
  [[ "$FAILURE" != preflight || "$1" != check ]]
}
verify_npm_integrity() {
  printf '%s\\n' "integrity:$1:$2:$3" >> "$ACTION_LOG"
  [[ "$FAILURE" != integrity ]]
}
as_station() {
  printf '%s\\n' "$@" >> "$ACTION_LOG"
  [[ "$FAILURE" != install ]]
}
"""
    integrity = "sha512-THfVVu1dCnOTep1xy1hsVk+wH7CeLyyBK/xtA0EYMls834riJ2QnlmICQCuSoPSXI8cgg16uXu2FBIA4uiQCjA=="
    result = subprocess.run(["bash", "-c", harness + function + "\ninstall_chatbotx_cli"],
                            env={"PATH": os.environ["PATH"], "STATION_HOME": str(tmp_path),
                                 "tool_path": str(tmp_path / ".local/bin"), "ACTION_LOG": str(log),
                                 "CHATBOTX_CLI_VERSION": "0.1.3", "CHATBOTX_CLI_NPM_INTEGRITY": integrity,
                                 "FAILURE": failure}, capture_output=True, text=True, timeout=10)
    actions = log.read_text().splitlines()
    assert (result.returncode == 0) == (failure == "none"), result.stderr
    assert actions[0] == "launcher:check"
    if failure != "preflight":
        assert actions[1] == f"integrity:chatbotx:0.1.3:{integrity}"
    if failure in {"none", "install"}:
        assert actions[2:11] == [str(tmp_path / ".local/bin/npm"), "install", "--global=false",
                                 "--ignore-scripts", "--bin-links=false", "--omit=dev", "--prefix",
                                 str(tmp_path / ".local/share/station-clis/chatbotx"), "chatbotx@0.1.3"]
    assert ("launcher:publish" in actions) == (failure == "none")
    _, dispatch = source.rsplit('case "$MODE" in\n', 1)
    assert "\ninstall_chatbotx_cli\n" in dispatch
    assert 'check_pinned_tool chatbotx "$tool_path/chatbotx" "$CHATBOTX_CLI_VERSION" --version' in source
