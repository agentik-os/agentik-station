"""Shared executable publication uses synthetic sources and no accounts/network."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
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
}
EXPORTS = {"node", "npm", "npx", "python-latest", "python-ai", "gh", "uv", "uvx",
           "vercel", "codex", "shadcn"}


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
    )
    for name, pin, entrypoints in definitions:
        package = local / "lib/node_modules" / name
        packages[name] = package
        write(package / "package.json", json.dumps({
            "name": name, "version": PINS[pin], "bin": entrypoints,
        }))
        for entrypoint in entrypoints.values():
            write(package / entrypoint, "#!/usr/bin/env node\n// synthetic CLI\n", executable=True)
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
    for name in ("npm", "vercel", "shadcn", "codex"):
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
        assert path.name not in {".env", "auth.json", "hosts.yml"}
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


@pytest.mark.parametrize("source", ["node", "npm", "python", "standalone"])
def test_same_pin_source_content_drift_is_rejected(layout, source):
    layout.publish()
    release = final_root(layout)
    original = snapshot(release)
    path = {"node": layout.node / "include/node/node.h",
            "npm": layout.packages["npm"] / "bin/npm-cli.js",
            "python": layout.runtimes["python-ai"] / "lib/python3.13/encodings/__init__.py",
            "standalone": layout.bins / "gh"}[source]
    path.write_text("changed source under the same pins\n")
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert snapshot(release) == original


@pytest.mark.parametrize("relative", ["node/bin/node", "npm/npm/bin/npm-cli.js",
                                      "python/ai/lib/python3.13/encodings/__init__.py", "bin/node"])
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
@pytest.mark.parametrize("location", ["npm", "python"])
def test_secret_shaped_files_inside_explicit_software_root_are_rejected(layout, secret, location):
    root = layout.packages["npm"] if location == "npm" else layout.runtimes["python-ai"]
    path = write(root / "nested" / secret, "synthetic private material; never publish\n")
    with pytest.raises((ValueError, OSError, RuntimeError)):
        layout.publish()
    assert path.read_text() == "synthetic private material; never publish\n"
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
def test_package_metadata_must_match_approved_pinned_package_and_entrypoint(layout, field):
    manifest = layout.packages["npm"] / "package.json"
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
